import os
import json
import requests
from flask import Flask, request, send_from_directory, jsonify

from backend.state import (
    APP_DIR,
    BASE_DIR,
    HA_URL,
    IS_ADDON,
    MOCK_ENTITIES,
    SUPERVISOR_TOKEN,
    _CACHED_SHELLY_KNOWN_NAMES,
    _DEFAULT_DEVICE,
    _DEVICE_CONFIG,
    _GENERATE_SCRIPT,
    _has_base_yamls,
    _load_device_configs,
    _parse_base_yaml,
    _resolve_safe_path,
    _run_generate_subprocess,
    get_session_id,
    is_headless_hub_yaml,
)
from backend import emulator as _emulator_mod
from backend import files_and_config as _files_mod
from backend import esphome_builds as _esphome_mod
from backend import toolchain as _toolchain_mod
from backend import ble_hubs as _ble_hubs_mod
from backend import shelly_backup as _shelly_mod

# Re-export helpers for tests and external callers
from backend.emulator import *  # noqa: F401,F403
from backend.files_and_config import *  # noqa: F401,F403
from backend.esphome_builds import *  # noqa: F401,F403
from backend.toolchain import *  # noqa: F401,F403
from backend.ble_hubs import *  # noqa: F401,F403
from backend.shelly_backup import *  # noqa: F401,F403
from backend.esphome_builds import (  # private helpers used by tests
    _batch_summary,
    _build_esphome_env,
    _check_device_online,
    _classify_batch_device,
    _discover_esphome_devices,
    _find_build_dir,
    _get_ha_timezone,
    _inject_esphome_idf_tools_path,
    _parse_device_yaml,
    _run_batch_update_worker,
    _serialize_batch_state,
)
from backend.ble_hubs import (  # private helpers used by tests
    _ble_fan_vault_path,
    _extract_device_api_info,
    _extract_gree_ac_from_yaml,
    _extract_shelly_bridge_from_yaml,
    _find_ble_fan_hosts_extended,
    _find_fan_ownership_conflicts,
    _list_cyd_devices_with_api,
    _load_ble_vault_raw,
    _load_esphome_secrets,
    _normalize_detached_switches_config,
    _normalize_gree_ac_config,
    _normalize_shelly_mac,
    _normalize_shellys_config,
    _remove_fans_from_host_yaml,
    _render_headless_hub_yaml,
    _replace_top_level_yaml_block,
    _slugify_hub_name,
    _upsert_substitution,
    _write_ble_vault_raw,
)
from backend.shelly_backup import (  # private helpers used by tests
    _SHELLY_HA_DISCOVERY_TEMPLATE,
    _collect_all_detached_switches,
    _collect_entity_to_cyds_map,
    _encode_detached_switches_blob,
    _extract_entity_ids,
    _infer_input_channel_from_trigger,
    _is_shelly_script_switch,
    _load_shelly_script_template,
    _parse_discovered_shelly_devices,
    _probe_shelly_detached_channels,
    _probe_shelly_input_info,
    _shelly_rpc_call,
    _walk_nested_dicts,
)

app = Flask(__name__, static_folder='dist')

app.register_blueprint(_emulator_mod.emulator_bp)
app.register_blueprint(_files_mod.files_bp)
app.register_blueprint(_esphome_mod.esphome_bp)
app.register_blueprint(_toolchain_mod.toolchain_bp)
app.register_blueprint(_ble_hubs_mod.ble_hubs_bp)
app.register_blueprint(_shelly_mod.shelly_bp)


@app.before_request
def before_request():
    pass


@app.errorhandler(401)
def custom_401(error):
    # Prevent 401 from reaching Ingress, which might block the page
    return jsonify({"error": "Unauthorized (Intercepted)"}), 500


def serve_index_with_env():
    """Serve index.html with injected environment variables."""
    try:
        with open(os.path.join(app.static_folder, 'index.html'), 'r') as f:
            content = f.read()
            
        # Determine IS_ADDON state
        # 1. Check explicit env var
        is_addon_env = os.environ.get('IS_ADDON', '').lower()
        if is_addon_env in ('true', '1', 'yes'):
            is_addon = 'true'
        elif is_addon_env in ('false', '0', 'no'):
            is_addon = 'false'
        else:
            # Default to true (Addon mode) if not specified
            is_addon = 'true'

        # Inject script
        injection = f'<script>window.__ENV__ = {{ IS_ADDON: {is_addon} }};</script>'
        content = content.replace('</head>', f'{injection}</head>')
        
        return content
    except Exception as e:
        print(f"Error serving index: {e}")
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/')
def serve_index():
    return serve_index_with_env()

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return serve_index_with_env()

@app.route('/api/ha/<path:path>', methods=['GET', 'POST'])
def proxy_ha(path):
    # Check for mock mode
    if request.headers.get('x-ha-mock') == 'true':
        if path == 'states':
            return jsonify(MOCK_ENTITIES)
        return jsonify({"success": True})

    # Determine target URL and Token
    target_url = request.headers.get('x-ha-url')
    target_token = request.headers.get('x-ha-token')
    
    if target_url and target_url.strip():
        # Remote HA mode
        url = f"{target_url.rstrip('/')}/api/{path}"
        headers = {
            "Content-Type": "application/json",
        }
        if target_token:
            headers["Authorization"] = f"Bearer {target_token}"
    else:
        # Local HA mode (Supervisor)
        if not SUPERVISOR_TOKEN:
             print("Error: SUPERVISOR_TOKEN not set", flush=True)
             return jsonify({"error": "Supervisor token not set and no remote credentials provided"}), 500
             
        url = f"{HA_URL}/api/{path}"
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        }
    
    try:
        if request.method == 'GET':
            response = requests.get(url, headers=headers, params=request.args, timeout=10)
        else:
            response = requests.post(url, headers=headers, json=request.json, timeout=10)
            
        if response.status_code == 401:
             print("Error: HA returned 401 Unauthorized", flush=True)
             return jsonify({"error": "Home Assistant rejected the supervisor token"}), 502

        return (response.content, response.status_code, response.headers.items())
    except requests.exceptions.RequestException as e:
        print(f"HA Proxy Connection Error: {str(e)}")
        return jsonify({"error": f"Could not connect to Home Assistant: {str(e)}"}), 502
    except Exception as e:
        print(f"HA Proxy Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
