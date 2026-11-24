import os
import sys
import re
import json
import subprocess
import shutil
import yaml
import hashlib
import signal
import socket
import time
import threading
import asyncio
import concurrent.futures
import zipfile
from pathlib import Path
from flask import Flask, request, send_from_directory, jsonify, Response, stream_with_context
import requests
from api_proxy import run_proxy_thread
import generate_tiles_api
from github_sync import sync_github_files
from aioesphomeapi import APIClient

import logging

app = Flask(__name__, static_folder='dist')

# Activity / Single-emulator state
emulator_lock = threading.RLock()  # RLock allows re-entrant locking
emulator_state = None  # dict when running, None when stopped


def get_session_id():
    sid = request.headers.get('X-Session-Id', 'default')
    return sid


@app.before_request
def before_request():
    pass

@app.errorhandler(401)
def custom_401(error):
    # Prevent 401 from reaching Ingress, which might block the page
    return jsonify({"error": "Unauthorized (Intercepted)"}), 500

# Configuration from environment
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HA_URL = "http://supervisor/core"
IS_ADDON = bool(SUPERVISOR_TOKEN)

# Determine environment paths
# BASE_DIR: Where the user's configuration lives (e.g. /config/esphome)
# We require that lib/ exists and contains at least one *_base.yaml device file,
# otherwise the directory is present but not properly initialised.
def _has_base_yamls(path):
    lib = os.path.join(path, 'lib')
    return os.path.isdir(lib) and any(f.endswith('_base.yaml') for f in os.listdir(lib))

if _has_base_yamls('/config/esphome'):
    BASE_DIR = '/config/esphome'
else:
    # Local fallback: use the esphome folder in the parent directory
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../esphome'))

# APP_DIR: Where the application code lives (e.g. /app)
if os.path.exists('/app'):
    APP_DIR = '/app'
else:
    # Local fallback: use the parent directory (repo root)
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

print(f"Server starting with:")
print(f"  BASE_DIR: {BASE_DIR}")
print(f"  APP_DIR:  {APP_DIR}")

MOCK_ENTITIES = [
    {"entity_id": "mock.light_living_room", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
    {"entity_id": "mock.switch_coffee_maker", "state": "off", "attributes": {"friendly_name": "Coffee Maker"}},
    {"entity_id": "mock.sensor_temperature", "state": "22.5", "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "°C"}},
    {"entity_id": "mock.binary_sensor_front_door", "state": "off", "attributes": {"friendly_name": "Front Door"}},
    {"entity_id": "mock.media_player_tv", "state": "playing", "attributes": {"friendly_name": "TV"}},
    {"entity_id": "mock.climate_living_room", "state": "heat", "attributes": {"friendly_name": "Climate"}},
    {"entity_id": "mock.cover_garage_door", "state": "closed", "attributes": {}},
]

_GENERATE_SCRIPT = os.path.join(os.path.dirname(__file__), 'generate_tiles_api.py')

def _run_generate_subprocess(yaml_str, lib_dir=None, images_dir=None, screen_w=320, screen_h=240):
    """Run generate_cpp_from_yaml in a child process so the Flask GIL stays free.

    Gunicorn uses a single worker process with a thread GIL.  Calling
    generate_cpp_from_yaml() directly holds the GIL for the entire duration
    of its CPU-heavy Python work (validation + C++ codegen), starving all
    other request threads and making the whole backend appear frozen.

    Running it in a subprocess means the calling thread waits on OS-level
    pipe I/O (GIL released), so other Flask threads continue to handle
    polling, log and status requests normally.
    """
    env = {
        **os.environ,
        'CYD_LIB_DIR':    lib_dir    or '',
        'CYD_COMPONENTS_DIR': os.path.join(BASE_DIR, 'external_components'),
        'CYD_IMAGES_DIR': images_dir or '',
        'CYD_SCREEN_W':   str(screen_w),
        'CYD_SCREEN_H':   str(screen_h),
    }
    try:
        proc = subprocess.run(
            [sys.executable, _GENERATE_SCRIPT],
            input=yaml_str,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            err = proc.stderr.strip() or 'generator process exited with no output'
            return {'error': err, 'type': 'subprocess_error'}
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {'error': 'Code generation timed out (>120 s)', 'type': 'timeout'}
    except json.JSONDecodeError as e:
        return {'error': f'Bad JSON from generator: {e}', 'type': 'parse_error'}
    except Exception as e:
        return {'error': str(e), 'type': 'unexpected_error'}


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

EMULATOR_PID_FILE = '/tmp/emulator.pid'
EMULATOR_LOG_FILE = '/tmp/emulator.log'
EMULATOR_API_PORT = 6053

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError, ProcessLookupError):
        return False

def _stop_emulator():
    """Stops the running emulator process and cleans up its state."""
    global emulator_state
    with emulator_lock:
        if emulator_state is None:
            return
        pid = emulator_state.get('pid')
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        if os.path.exists(EMULATOR_PID_FILE):
            try:
                os.remove(EMULATOR_PID_FILE)
            except OSError:
                pass
        emulator_state = None

@app.route('/api/emulator/start', methods=['POST'])
def start_emulator():
    global emulator_state

    # Validate and Save Configuration
    try:
        config_data = request.get_json()
        if not config_data:
             return jsonify({"status": "error", "message": "No configuration provided"}), 400

        # If we are just checking and it's already running, return status
        if config_data.get('check_only'):
            with emulator_lock:
                if emulator_state and is_process_running(emulator_state.get('pid')):
                    return jsonify({"status": "running", "pid": emulator_state.get('pid')})
            return jsonify({"status": "stopped", "message": "Emulator not running"}), 404

        # Determine screen type / dimensions
        screen_type = config_data.get('screen_type', _DEFAULT_DEVICE)
        _dev_cfg = _DEVICE_CONFIG.get(screen_type, _DEVICE_CONFIG[_DEFAULT_DEVICE])

        # Check if we received pre-generated YAML or raw pages
        if 'yaml' in config_data:
            yaml_str = config_data['yaml']
        elif 'pages' in config_data:
            yaml_data = {'screens': config_data['pages']}
            yaml_str = yaml.dump(yaml_data)
        else:
            return jsonify({"status": "error", "message": "Invalid configuration format"}), 400
        
        # Write to user_config.yaml
        user_config_filename = 'user_config.yaml'
        user_config_path = os.path.join(BASE_DIR, 'lib', user_config_filename)
        with open(user_config_path, 'w') as f:
            f.write(yaml_str)

        # Validate using generate_tiles_api
        # Resolve lib dir the same way as /api/scripts so lib_custom.yaml is found
        _lib_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(_lib_dir):
            _lib_dir = os.path.join(APP_DIR, 'esphome/lib')
        _images_dir = os.path.join(_lib_dir, 'images')
        result = _run_generate_subprocess(yaml_str, lib_dir=_lib_dir, images_dir=_images_dir, screen_w=_dev_cfg['screen_w'], screen_h=_dev_cfg['screen_h'])
        if "error" in result:
             return jsonify({"status": "error", "message": f"Configuration invalid: {result['error']}"}), 400

    except Exception as e:
        print(f"Config processing error: {e}")
        return jsonify({"status": "error", "message": f"Failed to process configuration: {str(e)}"}), 500

    script_path = os.path.join(os.path.dirname(__file__), 'run_emulator.sh')
    if not os.path.exists(script_path):
        print(f"ERROR: Emulator script not found at {script_path}", flush=True)
        return jsonify({"status": "error", "message": f"Emulator script not found: {script_path}"}), 500

    # Stop any existing emulator instance before starting a new one
    _stop_emulator()

    # Get HA credentials for the proxy
    ha_url = request.headers.get('x-ha-url')
    ha_token = request.headers.get('x-ha-token')
    is_mock = request.headers.get('x-ha-mock') == 'true'
    
    try:
        os.chmod(script_path, 0o755)
        print(f"Starting emulator (screen_type={screen_type}, api={EMULATOR_API_PORT})", flush=True)
        
        with open(EMULATOR_LOG_FILE, 'w', buffering=1) as log_file:
            log_file.write("--- Starting Emulator ---\n")
            log_file.flush()
            # Device config (screen dims, font sizes) is passed via environment variables.
            proc = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(__file__),
                start_new_session=True,
                env={**os.environ, **{k.upper(): str(v) for k, v in _dev_cfg.items()}},
            )
        
        with open(EMULATOR_PID_FILE, 'w') as f:
            f.write(str(proc.pid))
            
        with emulator_lock:
            emulator_state = {
                'pid': proc.pid,
                'log_path': EMULATOR_LOG_FILE,
                'user_config_path': user_config_path,
                'screen_type': screen_type,
                'screen_w': _dev_cfg['screen_w'],
                'screen_h': _dev_cfg['screen_h'],
            }
        
        # Start API proxy thread to forward service calls from emulator to HA
        # Only start if not in mock mode and we have some way to reach HA
        if not is_mock and (SUPERVISOR_TOKEN or (ha_url and ha_url.strip())):
            started_pid = proc.pid
            def check_emulator_alive():
                with emulator_lock:
                    return emulator_state is not None and emulator_state.get('pid') == started_pid

            threading.Thread(
                target=run_proxy_thread, 
                args=('emulator', EMULATOR_API_PORT, ha_url, ha_token, SUPERVISOR_TOKEN, check_emulator_alive),
                daemon=True
            ).start()
        else:
            print("API PROXY [emulator]: Skipping start (Mock mode or no HA credentials)", flush=True)
            
        return jsonify({"status": "started", "pid": proc.pid})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/emulator/stop', methods=['POST'])
def stop_emulator():
    _stop_emulator()
    return jsonify({"status": "stopped"})


@app.route('/api/debug/emulator', methods=['GET'])
def debug_emulator():
    """Diagnostic endpoint: returns emulator + seed-dir state for debugging."""
    import platform as _platform
    seed_dir = os.path.join(
        '/app/esphome' if os.path.isdir('/app/esphome') else
        os.path.abspath(os.path.join(os.path.dirname(__file__), '../esphome')),
        'lib', '.esphome', 'build', 'emulator'
    )
    pio_dir = '/root/.platformio'
    emulator_marker = os.path.join(pio_dir, '.emulator_prebuilt')
    ccache_dir = os.path.join(pio_dir, '.ccache')
    setup_marker = os.path.join(pio_dir, '.cyd_setup_done')

    def _dir_size_mb(path):
        try:
            result = subprocess.run(['du', '-sm', path], capture_output=True, text=True, timeout=5)
            return result.stdout.split()[0] + ' MB' if result.stdout else 'unknown'
        except Exception:
            return 'unknown'

    def _read_file(path):
        try:
            return open(path).read().strip()
        except Exception:
            return None

    with emulator_lock:
        emulator_snapshot = None
        if emulator_state:
            emulator_snapshot = {
                'pid': emulator_state.get('pid'),
                'running': is_process_running(emulator_state.get('pid')),
                'screen_type': emulator_state.get('screen_type'),
            }

    recent_log = None
    if os.path.exists(EMULATOR_LOG_FILE):
        try:
            result = subprocess.run(['tail', '-n', '20', EMULATOR_LOG_FILE], capture_output=True, text=True)
            recent_log = result.stdout
        except Exception:
            pass

    return jsonify({
        'arch': _platform.machine(),
        'emulator': emulator_snapshot,
        'seed_dir': {'path': seed_dir, 'exists': os.path.isdir(seed_dir), 'size': _dir_size_mb(seed_dir) if os.path.isdir(seed_dir) else None},
        'emulator_marker': {'exists': os.path.exists(emulator_marker), 'content': _read_file(emulator_marker)},
        'ccache_dir': {'exists': os.path.isdir(ccache_dir), 'size': _dir_size_mb(ccache_dir) if os.path.isdir(ccache_dir) else None},
        'setup_marker': os.path.exists(setup_marker),
        'generate_script': os.path.exists(_GENERATE_SCRIPT),
        'base_dir': BASE_DIR,
        'recent_emulator_log': recent_log,
        'memory_mb': _read_file('/proc/meminfo').split('\n')[0] if os.path.exists('/proc/meminfo') else None,
    })

@app.route('/api/emulator/status', methods=['GET'])
def emulator_status():
    with emulator_lock:
        if emulator_state and is_process_running(emulator_state.get('pid')):
            return jsonify({"status": "running"})
    return jsonify({"status": "stopped"})

@app.route('/api/emulator/logs', methods=['GET'])
def emulator_logs():
    if os.path.exists(EMULATOR_LOG_FILE):
        try:
            # Read the last 2000 lines to avoid sending too much data
            # Using tail command for efficiency
            result = subprocess.run(['tail', '-n', '2000', EMULATOR_LOG_FILE], capture_output=True, text=True)
            return result.stdout
        except Exception as e:
            return f"Error reading logs: {e}"
    return "No logs available"

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        input_data = request.get_data(as_text=True)
        _lib_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(_lib_dir):
            _lib_dir = os.path.join(APP_DIR, 'esphome/lib')
        # PNG files live inside lib/images/ so ESPHome resolves
        # "file: images/foo.png" relative to lib_common.yaml (which is in lib/).
        _images_dir = os.path.join(_lib_dir, 'images')
        result = _run_generate_subprocess(input_data, lib_dir=_lib_dir, images_dir=_images_dir)
        
        if "error" in result:
            print(f"Generation Error: {result['error']}", flush=True)
            return jsonify(result), 500
            
        return jsonify(result)
    except Exception as e:
        print(f"Server Error: {str(e)}", flush=True)
        return jsonify({"error": str(e)}), 500

def _resolve_safe_path(rel_path, allow_empty=False, base_dir=None):
    """Resolve *rel_path* inside *base_dir* (default BASE_DIR), rejecting traversal or symlink escapes.
    Returns the resolved absolute path string, or None if invalid.
    """
    if not isinstance(rel_path, str):
        return None
    cleaned = rel_path.strip().lstrip('/\\')
    if not cleaned and not allow_empty:
        return None
    if '..' in Path(cleaned).parts or '\\' in cleaned:
        return None
    base = Path(base_dir or BASE_DIR).resolve()
    target = (base / cleaned).resolve()
    if target != base and not target.is_relative_to(base):
        return None
    if not allow_empty and target == base:
        return None
    return str(target)


@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        path = request.args.get('path', '')
        if not os.path.exists(BASE_DIR):
            # Ensure base dir exists
            os.makedirs(BASE_DIR, exist_ok=True)

        full_path = _resolve_safe_path(path, allow_empty=True)
        if not full_path:
            return jsonify({"error": "Invalid path"}), 400
        
        if not os.path.exists(full_path):
            return jsonify({"error": "Path not found"}), 404
            
        items = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_dir = os.path.isdir(item_path)
            # Only show .yaml files or directories
            if is_dir or item.endswith('.yaml') or item.endswith('.yml'):
                items.append({
                    "name": item,
                    "is_dir": is_dir,
                    "path": os.path.relpath(item_path, BASE_DIR).replace('\\', '/')
                })
        
        # Sort: directories first, then files
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            "current_path": path,
            "items": items
        })
    except Exception as e:
        print(f"List Files Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/mkdir', methods=['POST'])
def make_directory():
    try:
        data = request.get_json() or {}
        path = data.get('path', '')
        full_path = _resolve_safe_path(path, allow_empty=False)
        if not full_path:
            return jsonify({"error": "Invalid path"}), 400
        
        os.makedirs(full_path, exist_ok=True)
        return jsonify({"success": True, "path": path})
    except Exception as e:
        print(f"Mkdir Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# Hardware Overrides Validation
# ============================================================

def _collect_lib_ids(screen_type=None):
    """Scan YAML files in the lib directory and return a set of declared IDs.

    If screen_type is provided (e.g. '2432s028' or '3248s035'), base files for
    the OTHER screen type are skipped so validation reflects the actual device.
    """
    lib_dir = os.path.join(BASE_DIR, 'lib')
    ids = set()
    if not os.path.isdir(lib_dir):
        return ids
    import re
    id_re = re.compile(r'^\s+id:\s+([A-Za-z_][A-Za-z0-9_]*)\s*$')
    for fname in os.listdir(lib_dir):
        if not fname.endswith('.yaml') and not fname.endswith('.yml'):
            continue
        # When a specific screen type is given, skip the other screen's base file
        if screen_type and fname.endswith('_base.yaml') and not fname.startswith(screen_type):
            continue
        fpath = os.path.join(lib_dir, fname)
        try:
            with open(fpath, 'r', errors='replace') as f:
                for line in f:
                    m = id_re.match(line)
                    if m:
                        ids.add(m.group(1))
        except Exception:
            pass
    return ids


def _flatten_dict(d, prefix=''):
    """Recursively flatten a dict into a list of {key, value} pairs using dot notation."""
    result = []
    if not isinstance(d, dict):
        return result
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            result.extend(_flatten_dict(v, full_key))
        else:
            result.append({"key": full_key, "value": v})
    return result


def _parse_hw_overrides(yaml_text, screen_type=None):
    """Parse hw_overrides YAML text and return a list of override entries.

    Each entry: {component_type, id, id_found, changes: [{key, value}]}
    Returns (overrides_list, parse_error_string_or_None).
    """
    class _ExtendTag:
        def __init__(self, value):
            self.value = value

    class _ExtendLoader(yaml.SafeLoader):
        pass

    def _construct_extend(loader, node):
        return _ExtendTag(loader.construct_scalar(node))

    def _ignore_tag(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        else:
            return loader.construct_mapping(node)

    _ExtendLoader.add_constructor('!extend', _construct_extend)
    _ExtendLoader.add_multi_constructor('!', _ignore_tag)

    try:
        doc = yaml.load(yaml_text, Loader=_ExtendLoader)
    except yaml.YAMLError as e:
        return [], str(e)

    if not isinstance(doc, dict):
        return [], None

    known_ids = _collect_lib_ids(screen_type)
    overrides = []

    for component_type, entries in doc.items():
        # A dict means the user forgot the list dash "-" — always an error
        if isinstance(entries, dict):
            id_val = entries.get('id')
            extend_id = id_val.value if isinstance(id_val, _ExtendTag) else '<some_id>'
            return [], (
                f"'{component_type}' override is missing the list dash '-'.\n"
                f"Change:\n  {component_type}:\n    id: !extend {extend_id}\n    ...\n"
                f"To:\n  {component_type}:\n    - id: !extend {extend_id}\n    ..."
            )
        if not isinstance(entries, list):
            # Bare scalar or other unexpected value
            return [], (
                f"Unexpected value for '{component_type}': {repr(entries)}\n"
                f"Each top-level key must be a list of component entries, e.g.:\n"
                f"  {component_type}:\n    - id: !extend <some_id>\n    ..."
            )
        for entry in entries:
            if not isinstance(entry, dict):
                return [], (
                    f"Unexpected item in '{component_type}' list: {repr(entry)}\n"
                    f"Each list item must be a mapping with 'id: !extend <id>', e.g.:\n"
                    f"  {component_type}:\n    - id: !extend <some_id>\n    ..."
                )
            id_val = entry.get('id')
            if id_val is None:
                return [], (
                    f"An entry under '{component_type}' is missing the 'id: !extend <id>' key.\n"
                    f"Each list item must start with 'id: !extend <some_id>'."
                )
            if not isinstance(id_val, _ExtendTag):
                return [], (
                    f"'{component_type}' entry has 'id: {id_val}' but is missing the '!extend' tag.\n"
                    f"Change:\n  - id: {id_val}\n"
                    f"To:\n  - id: !extend {id_val}"
                )
            extend_id = id_val.value
            # Build changes from the rest of the entry (everything except 'id')
            rest = {k: v for k, v in entry.items() if k != 'id'}
            changes = _flatten_dict(rest)
            overrides.append({
                "component_type": component_type,
                "id": extend_id,
                "id_found": extend_id in known_ids,
                "changes": changes,
            })

    return overrides, None


@app.route('/api/hw_overrides/validate', methods=['GET', 'POST'])
def validate_hw_overrides():
    """Validate hw_overrides.yaml.

    GET  — reads lib/hw_overrides.yaml from disk.
    POST — accepts {"yaml_text": "..."} to validate unsaved editor content.
    """
    try:
        hw_overrides_path = os.path.join(BASE_DIR, 'lib', 'hw_overrides.yaml')

        if request.method == 'POST':
            body = request.get_json(silent=True) or {}
            yaml_text = body.get('yaml_text', '')
            screen_type = body.get('screen_type') or None
        else:
            screen_type = request.args.get('screen_type') or None
            if not os.path.exists(hw_overrides_path):
                return jsonify({"overrides": [], "parse_error": None})
            with open(hw_overrides_path, 'r', errors='replace') as f:
                yaml_text = f.read()

        overrides, parse_error = _parse_hw_overrides(yaml_text, screen_type)
        return jsonify({"overrides": overrides, "parse_error": parse_error})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/save', methods=['POST'])
def save_config():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        config_data = data.get('config')
        # path is relative to BASE_DIR
        rel_path = data.get('path', 'monitor_config/tiles.yaml')
        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        if isinstance(config_data, str):
            with open(target_path, 'w') as f:
                f.write(config_data)
            if re.search(r'^tuya_ble_fan:', config_data, flags=re.MULTILINE):
                try:
                    loader_cls = generate_tiles_api.create_safe_yaml_loader()
                    parsed_saved = yaml.load(config_data, Loader=loader_cls)
                    if isinstance(parsed_saved, dict):
                        saved_fans = (parsed_saved.get('tuya_ble_fan') or {}).get('fans')
                        if isinstance(saved_fans, list):
                            save_ble_fans_to_vault(saved_fans, os.path.dirname(target_path))
                except Exception:
                    pass
        else:
            with open(target_path, 'w') as f:
                yaml.dump(config_data, f, sort_keys=False)
            
        return jsonify({"success": True, "path": rel_path})
    except Exception as e:
        print(f"Save Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/load', methods=['GET'])
def load_config():
    try:
        # path is relative to BASE_DIR
        rel_path = request.args.get('path', 'monitor_config/tiles.yaml')
        raw_mode = request.args.get('raw', '').lower() in ('1', 'true', 'yes')

        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400

        # Raw mode: return plain text (preserves comments, used by hw_overrides editor)
        if raw_mode:
            if not os.path.exists(target_path):
                return '', 404
            with open(target_path, 'r', errors='replace') as f:
                return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}

        if os.path.exists(target_path):
            loader_cls = generate_tiles_api.create_safe_yaml_loader()
            with open(target_path, 'r') as f:
                return jsonify(yaml.load(f, Loader=loader_cls))
        
        return jsonify({"error": f"Config file {rel_path} not found"}), 404
    except Exception as e:
        print(f"Load Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/load_raw', methods=['GET'])
def load_config_raw():
    """Return the raw text content of a file (not YAML-parsed). Used by the HW overrides editor."""
    try:
        rel_path = request.args.get('path', '')
        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400
        if not os.path.exists(target_path):
            return '', 404
        with open(target_path, 'r', errors='replace') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# ESPHome Device Management - List & Install
# ============================================================

# Track active install processes so we can cancel them
install_processes = {}  # session_id -> {process, lines, status, message}
install_processes_lock = threading.Lock()

# Track active compile processes (for USB flash workflow)
compile_processes = {}  # session_id -> {process, lines, status, message, device_name}
compile_processes_lock = threading.Lock()

def _get_ha_timezone():
    """Try to fetch the timezone from Home Assistant, with fallbacks."""
    # 1. Try HA Supervisor API
    try:
        if SUPERVISOR_TOKEN:
            resp = requests.get(
                f"{HA_URL}/api/config",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
                timeout=5
            )
            if resp.ok:
                tz = resp.json().get('time_zone')
                if tz:
                    print(f"Detected HA timezone: {tz}", flush=True)
                    return tz
    except Exception as e:
        print(f"Could not fetch HA timezone: {e}", flush=True)

    # 2. Try TZ environment variable
    tz_env = os.environ.get('TZ')
    if tz_env:
        print(f"Using TZ env timezone: {tz_env}", flush=True)
        return tz_env

    # 3. Try reading /etc/timezone
    try:
        with open('/etc/timezone', 'r') as f:
            tz = f.read().strip()
            if tz:
                print(f"Using /etc/timezone: {tz}", flush=True)
                return tz
    except Exception:
        pass

    # 4. Try reading /etc/localtime symlink
    try:
        link = os.readlink('/etc/localtime')
        # e.g. /usr/share/zoneinfo/America/New_York -> America/New_York
        if 'zoneinfo/' in link:
            tz = link.split('zoneinfo/')[-1]
            if tz:
                print(f"Using /etc/localtime timezone: {tz}", flush=True)
                return tz
    except Exception:
        pass

    # 5. Fallback to UTC
    print("No timezone detected, falling back to UTC", flush=True)
    return 'UTC'

# ---------------------------------------------------------------------------
# Device configuration — auto-discovered from esphome/lib/*_base.yaml files.
# ---------------------------------------------------------------------------

def _parse_base_yaml(filepath):
    """Return a config dict (screen_w, screen_h, font_tiny, …) from a *_base.yaml.

    Font keys are derived from the YAML font list ids (e.g. id: tiny → font_tiny).
    Screen dimensions come from the globals block (id: width / id: height).
    Returns None if the file can't be parsed or is missing required fields.
    """
    try:
        with open(filepath, 'r') as _f:
            data = yaml.load(_f, Loader=generate_tiles_api.create_safe_yaml_loader())
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    cfg = {}

    # Screen dimensions from globals block
    for g in (data.get('globals') or []):
        if not isinstance(g, dict):
            continue
        gid = g.get('id')
        val = g.get('initial_value')
        if gid == 'width' and val is not None:
            try:
                cfg['screen_w'] = int(str(val).strip('"'))
            except ValueError:
                pass
        elif gid == 'height' and val is not None:
            try:
                cfg['screen_h'] = int(str(val).strip('"'))
            except ValueError:
                pass
        elif gid == 'tile_border_width' and val is not None:
            try:
                cfg['tile_border_width'] = int(str(val).strip('"'))
            except ValueError:
                pass

    # Font sizes from font list  (id → font_<id>)
    for font in (data.get('font') or []):
        if not isinstance(font, dict):
            continue
        fid = font.get('id')
        size = font.get('size')
        if fid and size is not None:
            try:
                cfg[f'font_{fid}'] = int(size)
            except (ValueError, TypeError):
                pass

    if 'screen_w' not in cfg or 'screen_h' not in cfg:
        return None

    return cfg


def _load_device_configs(lib_dir):
    """Scan *lib_dir* for *_base.yaml files and build the device config map."""
    configs = {}
    if not os.path.isdir(lib_dir):
        return configs
    for fname in sorted(os.listdir(lib_dir)):
        if not fname.endswith('_base.yaml'):
            continue
        device_type = fname[: -len('_base.yaml')]
        cfg = _parse_base_yaml(os.path.join(lib_dir, fname))
        if cfg:
            configs[device_type] = cfg
        else:
            print(f"Warning: could not extract device config from {fname}", flush=True)
    return configs


_DEVICE_CONFIG = _load_device_configs(os.path.join(BASE_DIR, 'lib'))
_DEFAULT_DEVICE = '3248s035'
if not _DEVICE_CONFIG:
    raise RuntimeError(
        f"No *_base.yaml files found in {os.path.join(BASE_DIR, 'lib')} — "
        "cannot determine device configuration."
    )
print(f"  Devices: {list(_DEVICE_CONFIG)}", flush=True)



def _parse_device_yaml(filepath):
    """Parse a YAML device config file and extract device metadata.

    Reads only the top-level metadata sections (substitutions, esphome, packages,
    wifi) — stops before the tile_ui block which can be very large.  Uses a quick
    string search to detect whether tile_ui is present.
    """
    try:
        lines = []
        has_tile_ui = False
        has_ota_line = False
        with open(filepath, 'r', errors='replace') as f:
            for line in f:
                if line.startswith('ota:') or line.startswith('ota '):
                    has_ota_line = True
                # Stop accumulating lines once we hit the tile_ui block to avoid
                # parsing the potentially huge tile configuration YAML.
                if not has_tile_ui and (line.startswith('tile_ui:') or line.startswith('tile_ui ')):
                    has_tile_ui = True
                    continue
                if not has_tile_ui:
                    lines.append(line)
        # If we never hit a tile_ui: line, do one fast string check so we still
        # detect files where tile_ui appears indented (e.g. inside a package).
        if not has_tile_ui:
            truncated = ''.join(lines)
            if 'tile_ui:' in truncated:
                has_tile_ui = True

        content = ''.join(lines)
    except Exception:
        return None

    try:
        data = yaml.load(content, Loader=generate_tiles_api.create_safe_yaml_loader())
    except Exception:
        return None

    if not data or not isinstance(data, dict):
        return None

    device_name = None
    friendly_name = None
    screen_type = None
    ip_address = None
    is_device_config = False
    is_cyd = False

    # Check substitutions
    subs = data.get('substitutions', {}) or {}
    if subs:
        device_name = subs.get('device_name')
        friendly_name = subs.get('friendly_name')

    # Check esphome section
    esphome_section = data.get('esphome', {}) or {}
    if esphome_section:
        is_device_config = True
        if not device_name:
            device_name = esphome_section.get('name')
        if not friendly_name:
            friendly_name = esphome_section.get('friendly_name')

    # Check packages for device_base / CYD lib includes
    packages = data.get('packages', {}) or {}
    if isinstance(packages, dict) and packages:
        device_base = packages.get('device_base', '')
        if isinstance(device_base, str):
            if '2432s028' in device_base:
                screen_type = '2432s028'
                is_device_config = True
                is_cyd = True
            elif '3248s035' in device_base:
                screen_type = '3248s035'
                is_device_config = True
                is_cyd = True
        for pkg_val in packages.values():
            if isinstance(pkg_val, str) and ('lib/lib.yaml' in pkg_val or 'lib/lib_common.yaml' in pkg_val):
                is_cyd = True

    # Check for tile_ui section (CYD-specific marker) — detected during line scan above
    if has_tile_ui:
        is_device_config = True
        is_cyd = True

    # Check for OTA section (required for wireless OTA updates)
    ota_section = data.get('ota')
    has_ota = has_ota_line or (ota_section is not None and ota_section is not False)

    # Get IP address from wifi section
    wifi = data.get('wifi', {})
    if isinstance(wifi, dict):
        ip_address = wifi.get('use_address')

    if not is_device_config or not device_name:
        return None

    return {
        'device_name': device_name,
        'friendly_name': friendly_name or device_name,
        'screen_type': screen_type,
        'ip_address': ip_address,
        'address': ip_address or f"{device_name}.local",
        'is_cyd': is_cyd,
        'has_ota': has_ota,
    }


def _classify_batch_device(meta, online):
    """Classify a discovered ESPHome device for batch OTA update."""
    if not meta.get('is_cyd'):
        return ('skipped', 'Not a CYD configuration — no update needed')
    if not meta.get('has_ota'):
        return ('skipped', 'OTA update not configured')
    if not online:
        return ('skipped', 'Device is offline')
    return ('pending', 'Queued for OTA update')


def _check_device_online(device):
    """Ping a device to check if it's reachable on the network."""
    address = device['address']
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '1', address],
            capture_output=True, timeout=3
        )
        device['online'] = (result.returncode == 0)
    except Exception:
        device['online'] = False
    return device


@app.route('/api/esphome/devices', methods=['GET'])
def list_esphome_devices():
    """List all ESPHome device config files with metadata and online status."""
    try:
        devices = []
        skip_dirs = {'lib', 'external_components', '.esphome', '__pycache__'}
        skip_files = {'secrets.yaml'}

        for item in os.listdir(BASE_DIR):
            # Skip hidden files, directories we know aren't device configs
            if item.startswith('.') or item in skip_dirs or item in skip_files:
                continue
            filepath = os.path.join(BASE_DIR, item)
            if not os.path.isfile(filepath):
                continue
            if not (item.endswith('.yaml') or item.endswith('.yml')):
                continue

            try:
                meta = _parse_device_yaml(filepath)
                if meta:
                    meta['filename'] = item
                    devices.append(meta)
            except Exception as e:
                print(f"Error parsing {item}: {e}", flush=True)
                continue

        # Don't ping here — return immediately. The frontend calls
        # /api/esphome/devices/ping to check online status asynchronously.
        for d in devices:
            d['online'] = None  # unknown until pinged

        # Sort by name (no online status yet)
        devices.sort(key=lambda d: d.get('friendly_name', '').lower())

        return jsonify({'devices': devices})
    except Exception as e:
        print(f"List devices error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/esphome/devices/ping', methods=['POST'])
def ping_esphome_devices():
    """Check online status for a list of device addresses in parallel. 
    Body: {"devices": [{"address": "...", "filename": "..."}, ...]}
    Returns: {"results": {"<filename>": true/false, ...}}"""
    try:
        data = request.get_json() or {}
        devices_to_ping = data.get('devices', [])
        if not devices_to_ping:
            return jsonify({'results': {}})

        def _ping(item):
            address = item.get('address', '')
            filename = item.get('filename', address)
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', address],
                    capture_output=True, timeout=3
                )
                return filename, result.returncode == 0
            except Exception:
                return filename, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = dict(executor.map(_ping, devices_to_ping))

        return jsonify({'results': results})
    except Exception as e:
        print(f"Ping devices error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/ha/timezone')
def get_ha_timezone_endpoint():
    """Return the HA timezone so the frontend can bake it into device configs."""
    tz = _get_ha_timezone()
    return jsonify({'timezone': tz})


def _get_esphome_upgrade_notice_lines():
    """Return warning lines to prepend to build/install logs if ESPHome auto-upgrade failed."""
    for warn_file in ('/tmp/cyd_upgrade_warning.json', '/root/.platformio/.cyd_upgrade_warning.json'):
        if os.path.exists(warn_file):
            try:
                with open(warn_file) as f:
                    data = json.load(f)
                reason = data.get('reason')
                installed = data.get('installed_version')
                target = data.get('target_version')
                if reason:
                    return [
                        "=" * 70,
                        f"WARNING: ESPHome is running version {installed} (newer {target} available).",
                        f"         {reason}",
                        "=" * 70,
                        ""
                    ]
            except Exception:
                pass
    return []


@app.route('/api/esphome/install', methods=['POST'])
def install_esphome_device():
    """Start compiling and installing a device config via OTA. Returns immediately; poll /api/esphome/install/status for progress."""
    try:
        print(f"[install] Request received", flush=True)
        data = request.get_json() or {}
        filename = data.get('filename')
        filepath = _resolve_safe_path(filename)

        if not filepath:
            return jsonify({'error': 'Invalid filename'}), 400

        if not os.path.exists(filepath):
            return jsonify({'error': f'File not found: {filename}'}), 404

        session_id = get_session_id()
        print(f"[install] Session: {session_id}, File: {filename}", flush=True)

        # Kill ALL existing install processes across all sessions — only one at a time allowed
        with install_processes_lock:
            for sid, existing in list(install_processes.items()):
                proc = existing['process']
                if proc.poll() is None:
                    print(f"[install] Killing existing install process PID {proc.pid} (session {sid})", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            install_processes.clear()

        # Determine OTA target address so we can pass --device and avoid the
        # interactive "choose upload method" prompt that appears when a USB serial
        # device is also present in the container (e.g. a Zigbee dongle).
        _ota_address = None
        try:
            class _IL(yaml.SafeLoader):
                pass
            _IL.add_constructor('!include', lambda l, n: l.construct_scalar(n))
            _IL.add_multi_constructor('!', lambda l, s, n: None)
            with open(filepath, 'r') as _yf:
                _ydata = yaml.load(_yf, Loader=_IL)
            if isinstance(_ydata, dict):
                # Prefer explicit wifi.use_address; fall back to <device_name>.local
                _wifi = _ydata.get('wifi') or {}
                _ota_address = _wifi.get('use_address') if isinstance(_wifi, dict) else None
                if not _ota_address:
                    _name = ((_ydata.get('substitutions') or {}).get('device_name') or
                             (_ydata.get('esphome') or {}).get('name'))
                    if _name:
                        _ota_address = f'{_name}.local'
        except Exception as _e:
            print(f"[install] Could not determine OTA address: {_e}", flush=True)

        # Build the esphome command.  Always pass --device <address> so ESPHome
        # never falls through to the interactive chooser (EOFError on stdin).
        _esphome_cmd = ['esphome', 'run', filename]
        if _ota_address:
            _esphome_cmd += ['--device', _ota_address]
            print(f"[install] OTA target: {_ota_address}", flush=True)
        else:
            print("[install] WARNING: could not determine OTA address — ESPHome may prompt interactively", flush=True)

        # Start the process immediately — timezone is fetched in the background thread
        _install_env = os.environ.copy()
        _install_env['PYTHONUNBUFFERED'] = '1'
        # Point ESPHome / PlatformIO at the pre-warmed ccache so the compile
        # reuses cached object files instead of rebuilding from scratch.
        _pio_dir = '/root/.platformio'
        _ccache_dir = os.path.join(_pio_dir, '.ccache')
        _ccache_bin = '/usr/local/lib/ccache'
        if os.path.isdir(_ccache_dir):
            _install_env['CCACHE_DIR']           = _ccache_dir
            _install_env['CCACHE_MAXSIZE']        = '2G'
            _install_env['CCACHE_COMPILERCHECK']  = 'content'
            _install_env['CCACHE_SLOPPINESS']     = 'include_file_mtime,time_macros'
            _install_env['CCACHE_NOHASHDIR']      = 'true'
        if os.path.isdir(_ccache_bin):
            _install_env['PATH'] = f"{_ccache_bin}:{_install_env.get('PATH', '')}"
        process = subprocess.Popen(
            _esphome_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,   # prevent interactive prompts from blocking
            cwd=BASE_DIR,
            text=True,
            bufsize=1,
            env=_install_env,
        )

        install_state = {
            'process': process,
            'lines': _get_esphome_upgrade_notice_lines(),
            'status': 'running',      # running | success | error
            'message': f'Starting install of {filename}...',
            'line_offset': 0,          # not used server-side, just tracks total
        }

        with install_processes_lock:
            install_processes[session_id] = install_state

        # Regex to strip ANSI escape codes from ESPHome output
        ansi_re = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        # Split on \r\n, \n, or bare \r so CMake progress lines (\r-terminated) are captured
        line_split_re = re.compile(r'\r\n|\n|\r')

        def _reader_thread(state):
            """Background thread that reads process stdout into the shared line buffer."""
            proc = state['process']
            try:
                print(f"[install] Reader thread started for PID {proc.pid}", flush=True)
                for line in iter(proc.stdout.readline, ''):
                    # readline() returns on \n; split on \r to catch CMake progress lines
                    for raw_part in line_split_re.split(line):
                        clean = ansi_re.sub('', raw_part.rstrip())
                        if not clean.strip():
                            continue
                        state['lines'].append(clean)
                        # Detect OTA upload success patterns
                        lower = clean.lower()
                        if ('successfully uploaded' in lower or
                            'ota successful' in lower or
                            'success' in lower and 'upload' in lower):
                            print(f"[install] OTA upload success detected, terminating process", flush=True)
                            state['status'] = 'success'
                            state['message'] = 'Installation completed successfully!'
                            import time as _time
                            _time.sleep(1)
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            return

                proc.wait()
                if proc.returncode == 0:
                    state['status'] = 'success'
                    state['message'] = 'Installation completed successfully!'
                    print(f"[install] Process completed successfully", flush=True)
                else:
                    # If we already set success from OTA detection, don't override
                    if state['status'] != 'success':
                        state['status'] = 'error'
                        state['message'] = f'Installation failed (exit code {proc.returncode})'
                        print(f"[install] Process failed with exit code {proc.returncode}", flush=True)
            except Exception as e:
                if state['status'] != 'success':  # Don't override OTA success
                    state['status'] = 'error'
                    state['message'] = str(e)
                print(f"[install] Reader thread error: {e}", flush=True)
            finally:
                pass

        t = threading.Thread(target=_reader_thread, args=(install_state,), daemon=True)
        t.start()

        print(f"[install] Returning response, process PID: {process.pid}", flush=True)
        return jsonify({'status': 'started', 'message': install_state['message']})

    except Exception as e:
        print(f"[install] Exception: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/esphome/install/status')
def install_status():
    """Poll for install progress. Pass ?offset=N to get only new lines since line N."""
    session_id = get_session_id()
    with install_processes_lock:
        state = install_processes.get(session_id)
        # Fall back to any running process (e.g. browser reloaded and got new session)
        if not state:
            for s in install_processes.values():
                state = s
                break

    if not state:
        return jsonify({'status': 'not_running'}), 404

    offset = request.args.get('offset', 0, type=int)
    lines = state['lines']
    new_lines = lines[offset:]

    result = {
        'status': state['status'],
        'message': state['message'],
        'lines': new_lines,
        'offset': len(lines),
    }

    # Clean up finished installs after client has seen the final status
    if state['status'] in ('success', 'error'):
        # Keep the state around for one more poll so the client sees the result,
        # but if offset already covers all lines, clean up
        if offset >= len(lines):
            with install_processes_lock:
                install_processes.pop(session_id, None)

    return jsonify(result)


@app.route('/api/esphome/install/cancel', methods=['POST'])
def cancel_install():
    """Cancel a running installation."""
    with install_processes_lock:
        if not install_processes:
            return jsonify({'status': 'not_running'}), 404
        for sid, state in list(install_processes.items()):
            process = state['process']
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            state['status'] = 'error'
            state['message'] = 'Installation cancelled by user'
        install_processes.clear()
        return jsonify({'status': 'cancelled'})


# ============================================================
# Batch OTA Update (Update All Online CYD Devices)
# ============================================================

batch_update_lock = threading.Lock()
batch_update_state = None  # Dict holding current/last batch OTA job


def _build_esphome_env():
    """Return an environment dict configured with ccache for fast ESPHome compiles."""
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    pio_dir = '/root/.platformio'
    ccache_dir = os.path.join(pio_dir, '.ccache')
    ccache_bin = '/usr/local/lib/ccache'
    if os.path.isdir(ccache_dir):
        env['CCACHE_DIR'] = ccache_dir
        env['CCACHE_MAXSIZE'] = '2G'
        env['CCACHE_COMPILERCHECK'] = 'content'
        env['CCACHE_SLOPPINESS'] = 'include_file_mtime,time_macros'
        env['CCACHE_NOHASHDIR'] = 'true'
    if os.path.isdir(ccache_bin):
        env['PATH'] = f"{ccache_bin}:{env.get('PATH', '')}"
    return env


def _discover_esphome_devices():
    """Scan BASE_DIR and return parsed metadata for all ESPHome device YAML files."""
    devices = []
    skip_dirs = {'lib', 'external_components', '.esphome', '__pycache__'}
    skip_files = {'secrets.yaml'}
    if not os.path.isdir(BASE_DIR):
        return devices
    for item in os.listdir(BASE_DIR):
        if item.startswith('.') or item in skip_dirs or item in skip_files:
            continue
        filepath = os.path.join(BASE_DIR, item)
        if not os.path.isfile(filepath):
            continue
        if not (item.endswith('.yaml') or item.endswith('.yml')):
            continue
        try:
            meta = _parse_device_yaml(filepath)
            if meta:
                meta['filename'] = item
                devices.append(meta)
        except Exception as e:
            print(f"[batch_update] Error parsing {item}: {e}", flush=True)
    devices.sort(key=lambda d: d.get('friendly_name', '').lower())
    return devices


def _batch_summary(devices):
    counts = {'total': len(devices), 'updated': 0, 'failed': 0, 'skipped': 0, 'cancelled': 0, 'pending': 0, 'updating': 0}
    for d in devices:
        st = d.get('status')
        if st in counts:
            counts[st] += 1
    return counts


def _serialize_batch_state(state, include_logs=None):
    devices_out = []
    for d in state['devices']:
        entry = {
            'filename': d['filename'],
            'device_name': d['device_name'],
            'friendly_name': d['friendly_name'],
            'screen_type': d.get('screen_type'),
            'address': d['address'],
            'is_cyd': d['is_cyd'],
            'has_ota': d['has_ota'],
            'online': d.get('online'),
            'status': d['status'],
            'reason': d['reason'],
            'duration_s': d.get('duration_s'),
            'log_count': len(d['logs']),
            'last_log': d['logs'][-1] if d['logs'] else '',
        }
        if include_logs and (include_logs == d['filename'] or include_logs == '*'):
            entry['logs'] = list(d['logs'])
        devices_out.append(entry)
    return {
        'phase': state['phase'],  # scanning | pinging | updating | completed | cancelled
        'message': state['message'],
        'current_filename': state.get('current_filename'),
        'started_at': state['started_at'],
        'finished_at': state.get('finished_at'),
        'devices': devices_out,
        'summary': _batch_summary(state['devices']),
    }


def _run_batch_update_worker(state):
    """Background worker that scans, pings, and OTA-updates all eligible CYD devices sequentially."""
    import time as _time
    ansi_re = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
    line_split_re = re.compile(r'\r\n|\n|\r')
    cancel_event = state['cancel_event']

    try:
        # 1. Scan BASE_DIR for all ESPHome device configs
        discovered = _discover_esphome_devices()
        with batch_update_lock:
            state['devices'] = [
                {
                    **meta,
                    'online': None,
                    'status': 'checking',
                    'reason': 'Checking device...',
                    'duration_s': None,
                    'logs': [],
                }
                for meta in discovered
            ]
            if not discovered:
                state['phase'] = 'completed'
                state['message'] = 'No ESPHome device files found on drive.'
                state['finished_at'] = _time.time()
                return
            state['phase'] = 'pinging'
            state['message'] = f'Checking online status for {len(discovered)} device(s)...'

        # 2. Classify non-CYD / non-OTA immediately, ping CYD+OTA devices in parallel
        to_ping = []
        for idx, d in enumerate(state['devices']):
            if not d['is_cyd'] or not d['has_ota']:
                st, reason = _classify_batch_device(d, online=False)
                with batch_update_lock:
                    d['status'] = st
                    d['reason'] = reason
            else:
                to_ping.append((idx, d))

        if to_ping and not cancel_event.is_set():
            def _ping_one(pair):
                idx, dev = pair
                probe = {'address': dev['address']}
                _check_device_online(probe)
                return idx, bool(probe.get('online', False))

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for idx, is_online in executor.map(_ping_one, to_ping):
                    with batch_update_lock:
                        dev = state['devices'][idx]
                        dev['online'] = is_online
                        st, reason = _classify_batch_device(dev, online=is_online)
                        dev['status'] = st
                        dev['reason'] = reason

        if cancel_event.is_set():
            with batch_update_lock:
                for d in state['devices']:
                    if d['status'] in ('checking', 'pending'):
                        d['status'] = 'cancelled'
                        d['reason'] = 'Cancelled by user'
                state['phase'] = 'cancelled'
                state['message'] = 'Batch update cancelled.'
                state['finished_at'] = _time.time()
            return

        eligible = [d for d in state['devices'] if d['status'] == 'pending']
        if not eligible:
            with batch_update_lock:
                state['phase'] = 'completed'
                state['message'] = 'No online CYD devices with OTA needed updating.'
                state['finished_at'] = _time.time()
            return

        # 3. Sequentially compile & OTA-upload each eligible device
        env = _build_esphome_env()
        upgrade_notice = _get_esphome_upgrade_notice_lines()

        with batch_update_lock:
            state['phase'] = 'updating'

        for pos, dev in enumerate(eligible, start=1):
            if cancel_event.is_set():
                with batch_update_lock:
                    dev['status'] = 'cancelled'
                    dev['reason'] = 'Cancelled by user'
                continue

            filename = dev['filename']
            address = dev['address']
            start_ts = _time.time()

            with batch_update_lock:
                state['current_filename'] = filename
                state['message'] = f'Updating {dev["friendly_name"]} ({pos}/{len(eligible)})...'
                dev['status'] = 'updating'
                dev['reason'] = f'Compiling & uploading via OTA ({address})...'
                if upgrade_notice:
                    dev['logs'].extend(upgrade_notice)
                dev['logs'].append(f'Starting OTA update for {filename} -> {address}')

            cmd = ['esphome', 'run', filename, '--device', address, '--no-logs']
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=BASE_DIR,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                with batch_update_lock:
                    state['current_process'] = proc

                ota_success = False
                for line in iter(proc.stdout.readline, ''):
                    if cancel_event.is_set():
                        proc.terminate()
                        break
                    for raw_part in line_split_re.split(line):
                        clean = ansi_re.sub('', raw_part.rstrip())
                        if not clean.strip():
                            continue
                        with batch_update_lock:
                            dev['logs'].append(clean)
                        lower = clean.lower()
                        if ('successfully uploaded' in lower or
                            'ota successful' in lower or
                            ('success' in lower and 'upload' in lower)):
                            ota_success = True

                if cancel_event.is_set():
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    elapsed = int(round(_time.time() - start_ts))
                    with batch_update_lock:
                        dev['status'] = 'cancelled'
                        dev['reason'] = 'Cancelled by user'
                        dev['duration_s'] = elapsed
                        state['current_process'] = None
                    continue

                proc.wait()
                elapsed = int(round(_time.time() - start_ts))
                with batch_update_lock:
                    state['current_process'] = None
                    dev['duration_s'] = elapsed
                    if ota_success or proc.returncode == 0:
                        dev['status'] = 'updated'
                        dev['reason'] = f'Updated successfully ({elapsed}s)'
                    else:
                        dev['status'] = 'failed'
                        dev['reason'] = f'Update failed (exit code {proc.returncode})'
            except Exception as e:
                elapsed = int(round(_time.time() - start_ts))
                with batch_update_lock:
                    state['current_process'] = None
                    dev['duration_s'] = elapsed
                    dev['status'] = 'failed'
                    dev['reason'] = f'Error: {e}'
                    dev['logs'].append(f'Exception: {e}')

        with batch_update_lock:
            state['current_filename'] = None
            state['current_process'] = None
            state['finished_at'] = _time.time()
            summary = _batch_summary(state['devices'])
            if cancel_event.is_set():
                for d in state['devices']:
                    if d['status'] == 'pending':
                        d['status'] = 'cancelled'
                        d['reason'] = 'Cancelled by user'
                summary = _batch_summary(state['devices'])
                state['phase'] = 'cancelled'
                state['message'] = (
                    f"Cancelled: {summary['updated']} updated, "
                    f"{summary['failed']} failed, {summary['skipped']} skipped, {summary['cancelled']} cancelled."
                )
            else:
                state['phase'] = 'completed'
                state['message'] = (
                    f"Done: {summary['updated']} updated, "
                    f"{summary['skipped']} skipped, {summary['failed']} failed."
                )
    except Exception as e:
        with batch_update_lock:
            state['phase'] = 'completed'
            state['message'] = f'Batch update error: {e}'
            state['finished_at'] = _time.time()
            state['current_filename'] = None
            state['current_process'] = None


@app.route('/api/esphome/batch_update/start', methods=['POST'])
def start_batch_update():
    """Start a background OTA update across all online CYD devices."""
    global batch_update_state
    import time as _time

    # Refuse if a single-device OTA install is already running
    with install_processes_lock:
        for existing in install_processes.values():
            proc = existing.get('process')
            if proc and proc.poll() is None:
                return jsonify({'error': 'A single-device OTA install is currently running. Please wait for it to finish.'}), 409

    with batch_update_lock:
        if batch_update_state and batch_update_state['phase'] in ('scanning', 'pinging', 'updating'):
            return jsonify({'status': 'already_running', **_serialize_batch_state(batch_update_state)})

        batch_update_state = {
            'phase': 'scanning',
            'message': 'Scanning device configurations...',
            'current_filename': None,
            'current_process': None,
            'cancel_event': threading.Event(),
            'started_at': _time.time(),
            'finished_at': None,
            'devices': [],
        }
        state = batch_update_state

    t = threading.Thread(target=_run_batch_update_worker, args=(state,), daemon=True)
    t.start()

    with batch_update_lock:
        return jsonify({'status': 'started', **_serialize_batch_state(state)})


@app.route('/api/esphome/batch_update/status', methods=['GET'])
def get_batch_update_status():
    """Return the current or most recent batch OTA update state."""
    include_logs = request.args.get('include_logs')
    with batch_update_lock:
        if not batch_update_state:
            return jsonify({'phase': 'idle', 'devices': [], 'summary': _batch_summary([])})
        return jsonify(_serialize_batch_state(batch_update_state, include_logs=include_logs))


@app.route('/api/esphome/batch_update/cancel', methods=['POST'])
def cancel_batch_update():
    """Cancel a running batch OTA update."""
    with batch_update_lock:
        if not batch_update_state or batch_update_state['phase'] not in ('scanning', 'pinging', 'updating'):
            return jsonify({'status': 'not_running'}), 404
        batch_update_state['cancel_event'].set()
        proc = batch_update_state.get('current_process')
        if proc and proc.poll() is None:
            proc.terminate()
        return jsonify({'status': 'cancelling'})


# ============================================================
# WiFi Credentials (secrets.yaml management)
# ============================================================

WIFI_PLACEHOLDERS = {'WIFI_SSID', 'WIFI_PASSWORD', 'your_ssid', 'your_password', '', 'changeme'}

@app.route('/api/esphome/wifi', methods=['GET'])
def get_wifi_status():
    """Check if WiFi credentials are configured (not placeholders)."""
    secrets_path = os.path.join(BASE_DIR, 'secrets.yaml')
    if not os.path.exists(secrets_path):
        return jsonify({'configured': False, 'ssid': '', 'has_password': False})

    try:
        with open(secrets_path, 'r') as f:
            secrets = yaml.safe_load(f) or {}
        ssid = str(secrets.get('wifi_ssid', '')).strip()
        password = str(secrets.get('wifi_password', '')).strip()
        configured = ssid not in WIFI_PLACEHOLDERS and password not in WIFI_PLACEHOLDERS
        return jsonify({
            'configured': configured,
            'ssid': ssid if configured else '',
            'has_password': bool(password) if configured else False,
        })
    except Exception as e:
        print(f"[wifi] Error reading secrets: {e}", flush=True)
        return jsonify({'configured': False, 'ssid': '', 'has_password': False})


@app.route('/api/esphome/wifi', methods=['POST'])
def save_wifi_credentials():
    """Save WiFi SSID and password to secrets.yaml."""
    data = request.get_json()
    ssid = data.get('ssid', '').strip()
    password = data.get('password', '').strip()

    if not ssid:
        return jsonify({'error': 'SSID is required'}), 400
    if not password:
        return jsonify({'error': 'Password is required'}), 400

    secrets_path = os.path.join(BASE_DIR, 'secrets.yaml')

    # Read existing secrets to preserve other entries
    existing = {}
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, 'r') as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    existing['wifi_ssid'] = ssid
    existing['wifi_password'] = password

    try:
        with open(secrets_path, 'w') as f:
            f.write('# Your Wi-Fi SSID and password\n')
            yaml.safe_dump(existing, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"[wifi] Saved WiFi credentials (SSID: {ssid})", flush=True)
        return jsonify({'success': True})
    except Exception as e:
        print(f"[wifi] Error saving secrets: {e}", flush=True)
        return jsonify({'error': f'Failed to save: {str(e)}'}), 500


# ============================================================
# ESPHome Compile & Firmware Download (for USB/Web Serial flash)
# ============================================================

@app.route('/api/esphome/compile', methods=['POST'])
def compile_esphome_device():
    """Compile firmware for a device config. Returns immediately; poll /api/esphome/compile/status for progress."""
    try:
        print(f"[compile] Request received", flush=True)
        data = request.get_json() or {}
        filename = data.get('filename')
        filepath = _resolve_safe_path(filename)

        if not filepath:
            return jsonify({'error': 'Invalid filename'}), 400

        if not os.path.exists(filepath):
            return jsonify({'error': f'File not found: {filename}'}), 404

        session_id = get_session_id()
        print(f"[compile] Session: {session_id}, File: {filename}", flush=True)

        # Clean up any existing compile for this session
        with compile_processes_lock:
            existing = compile_processes.get(session_id)
            if existing:
                proc = existing['process']
                if proc.poll() is None:
                    print(f"[compile] Killing stale compile process PID {proc.pid}", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                compile_processes.pop(session_id, None)

        # Parse device name from the YAML for locating build output
        device_name = None
        try:
            class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
                pass
            def ignore_any_tag(loader, tag_suffix, node):
                return None
            def construct_include(loader, node):
                return loader.construct_scalar(node)
            SafeLoaderIgnoreUnknown.add_constructor('!include', construct_include)
            SafeLoaderIgnoreUnknown.add_multi_constructor('!', ignore_any_tag)
            with open(filepath, 'r') as f:
                parsed = yaml.load(f, Loader=SafeLoaderIgnoreUnknown)
                device_name = parsed.get('substitutions', {}).get('device_name') or \
                              parsed.get('esphome', {}).get('name') or \
                              os.path.splitext(os.path.basename(filename))[0]
        except Exception:
            device_name = os.path.splitext(os.path.basename(filename))[0]

        # Get timezone
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        tz = _get_ha_timezone()
        if tz:
            env['TZ'] = tz
        # Point ESPHome / PlatformIO at the pre-warmed ccache.
        _pio_dir = '/root/.platformio'
        _ccache_dir = os.path.join(_pio_dir, '.ccache')
        _ccache_bin = '/usr/local/lib/ccache'
        if os.path.isdir(_ccache_dir):
            env['CCACHE_DIR']           = _ccache_dir
            env['CCACHE_MAXSIZE']       = '2G'
            env['CCACHE_COMPILERCHECK'] = 'content'
            env['CCACHE_SLOPPINESS']    = 'include_file_mtime,time_macros'
            env['CCACHE_NOHASHDIR']     = 'true'
        if os.path.isdir(_ccache_bin):
            env['PATH'] = f"{_ccache_bin}:{env.get('PATH', '')}"

        process = subprocess.Popen(
            ['esphome', 'compile', filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=BASE_DIR,
            text=True,
            bufsize=1,
            env=env
        )

        compile_state = {
            'process': process,
            'lines': _get_esphome_upgrade_notice_lines(),
            'status': 'running',
            'message': f'Compiling {filename}...',
            'device_name': device_name,
            'filename': filename,
            # In non-addon (cloud) mode, auto-delete the YAML file after compile so
            # temporary files from this session are not visible to other users.
            'auto_cleanup': not IS_ADDON,
        }

        with compile_processes_lock:
            compile_processes[session_id] = compile_state

        ansi_re = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        line_split_re = re.compile(r'\r\n|\n|\r')

        def _reader_thread(state):
            proc = state['process']
            try:
                print(f"[compile] Reader thread started for PID {proc.pid}", flush=True)
                for line in iter(proc.stdout.readline, ''):
                    for raw_part in line_split_re.split(line):
                        clean = ansi_re.sub('', raw_part.rstrip())
                        if clean.strip():
                            state['lines'].append(clean)
                proc.wait()
                if proc.returncode == 0:
                    state['status'] = 'success'
                    state['message'] = 'Compilation completed successfully!'
                    print(f"[compile] Compilation succeeded", flush=True)
                else:
                    state['status'] = 'error'
                    state['message'] = f'Compilation failed (exit code {proc.returncode})'
                    print(f"[compile] Compilation failed with exit code {proc.returncode}", flush=True)
            except Exception as e:
                state['status'] = 'error'
                state['message'] = str(e)
                print(f"[compile] Reader thread error: {e}", flush=True)
            finally:
                # Auto-delete the device YAML so cloud users don't see each other's files.
                if state.get('auto_cleanup'):
                    _fname = state.get('filename', '')
                    _yaml_path = _resolve_safe_path(_fname)
                    if _yaml_path:
                        try:
                            if os.path.exists(_yaml_path):
                                os.remove(_yaml_path)
                                print(f"[compile] Auto-removed {_yaml_path}", flush=True)
                        except Exception as _e:
                            print(f"[compile] Failed to auto-remove {_yaml_path}: {_e}", flush=True)

        t = threading.Thread(target=_reader_thread, args=(compile_state,), daemon=True)
        t.start()

        print(f"[compile] Returning response, process PID: {process.pid}", flush=True)
        return jsonify({'status': 'started', 'message': compile_state['message'], 'device_name': device_name})

    except Exception as e:
        print(f"[compile] Exception: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/esphome/compile/status')
def compile_status():
    """Poll for compile progress. Pass ?offset=N to get only new lines since line N."""
    session_id = get_session_id()
    with compile_processes_lock:
        state = compile_processes.get(session_id)

    if not state:
        return jsonify({'status': 'not_running'}), 404

    offset = request.args.get('offset', 0, type=int)
    lines = state['lines']
    new_lines = lines[offset:]

    result = {
        'status': state['status'],
        'message': state['message'],
        'lines': new_lines,
        'offset': len(lines),
        'device_name': state.get('device_name'),
    }

    if state['status'] in ('success', 'error'):
        if offset >= len(lines):
            with compile_processes_lock:
                compile_processes.pop(session_id, None)

    return jsonify(result)


@app.route('/api/esphome/compile/cancel', methods=['POST'])
def cancel_compile():
    """Cancel a running compilation."""
    session_id = get_session_id()
    with compile_processes_lock:
        state = compile_processes.get(session_id)
        if state:
            process = state['process']
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                state['status'] = 'error'
                state['message'] = 'Compilation cancelled by user'
            compile_processes.pop(session_id, None)
            return jsonify({'status': 'cancelled'})
    return jsonify({'status': 'not_running'}), 404


@app.route('/api/esphome/compile/cleanup', methods=['POST'])
def cleanup_compile():
    """Delete the temporary device YAML and build artifacts for the current session.
    Called by the client after firmware has been downloaded to the browser, so that
    no files from this session remain visible to other users.
    """
    session_id = get_session_id()
    with compile_processes_lock:
        state = compile_processes.pop(session_id, None)

    if not state:
        return jsonify({'status': 'ok', 'message': 'Nothing to clean up'})

    cleaned = []
    errors = []

    # Remove the device YAML file
    filename = state.get('filename', '')
    yaml_path = _resolve_safe_path(filename)
    if yaml_path:
        try:
            if os.path.exists(yaml_path):
                os.remove(yaml_path)
                cleaned.append(filename)
        except Exception as e:
            errors.append(f"Failed to remove {filename}: {e}")

    # Remove the build directory
    device_name = state.get('device_name', '')
    build_root = os.path.join(BASE_DIR, '.esphome', 'build')
    build_dir = _resolve_safe_path(device_name, base_dir=build_root) if os.path.isdir(build_root) else None
    if build_dir:
        try:
            if os.path.isdir(build_dir):
                shutil.rmtree(build_dir)
                cleaned.append(f'.esphome/build/{device_name}')
        except Exception as e:
            errors.append(f"Failed to remove build dir: {e}")

    print(f"[cleanup] Session {session_id}: removed {cleaned}, errors: {errors}", flush=True)
    return jsonify({'status': 'ok', 'cleaned': cleaned, 'errors': errors})


def _find_build_dir(device_name):
    """Find the directory containing compiled firmware binaries for a device.

    ESP-IDF puts binaries in .esphome/build/<device>/build/
    PlatformIO/Arduino puts binaries in .esphome/build/<device>/.pioenvs/<device>/
    """
    build_root = os.path.join(BASE_DIR, '.esphome', 'build')
    if not os.path.isdir(build_root):
        return None
    dev_dir = _resolve_safe_path(device_name, base_dir=build_root)
    if not dev_dir:
        return None
    candidates = [
        os.path.join(dev_dir, 'build'),
        os.path.join(dev_dir, '.pioenvs', os.path.basename(dev_dir)),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


@app.route('/api/esphome/firmware/<device_name>/manifest.json')
def get_firmware_manifest(device_name):
    """Return a manifest for flashing via esptool-js (ESP Web Tools compatible)."""
    if not _resolve_safe_path(device_name):
        return jsonify({'error': 'Invalid device name'}), 400

    build_dir = _find_build_dir(device_name)
    if not build_dir:
        return jsonify({'error': f'Build output not found for {device_name}. Compile first.'}), 404

    # Check for factory image (esp-idf, single image that includes bootloader+partitions+app)
    factory_bin = os.path.join(build_dir, 'firmware.factory.bin')
    if os.path.exists(factory_bin):
        return jsonify({
            'name': device_name,
            'parts': [
                {'path': f'/api/esphome/firmware/{device_name}/firmware.factory.bin', 'offset': 0}
            ]
        })

    # Arduino framework: separate files
    parts = []
    firmware_bin = os.path.join(build_dir, 'firmware.bin')
    if os.path.exists(firmware_bin):
        # Typical ESP32 Arduino offsets
        bootloader = os.path.join(build_dir, 'bootloader.bin')
        partitions = os.path.join(build_dir, 'partitions.bin')
        boot_app = os.path.join(build_dir, 'boot_app0.bin')

        if os.path.exists(bootloader):
            parts.append({'path': f'/api/esphome/firmware/{device_name}/bootloader.bin', 'offset': 4096})
        if os.path.exists(partitions):
            parts.append({'path': f'/api/esphome/firmware/{device_name}/partitions.bin', 'offset': 32768})
        if os.path.exists(boot_app):
            parts.append({'path': f'/api/esphome/firmware/{device_name}/boot_app0.bin', 'offset': 57344})
        parts.append({'path': f'/api/esphome/firmware/{device_name}/firmware.bin', 'offset': 65536})

        return jsonify({'name': device_name, 'parts': parts})

    return jsonify({'error': f'No firmware binaries found for {device_name}'}), 404


@app.route('/api/esphome/firmware/<device_name>/<filename>')
def get_firmware_file(device_name, filename):
    """Serve a compiled firmware binary file."""
    if not _resolve_safe_path(device_name) or not _resolve_safe_path(filename):
        return jsonify({'error': 'Invalid path'}), 400

    # Only allow known binary extensions
    if not filename.endswith('.bin'):
        return jsonify({'error': 'Invalid file type'}), 400

    build_dir = _find_build_dir(device_name)
    if not build_dir:
        return jsonify({'error': f'Build output not found for {device_name}. Compile first.'}), 404

    filepath = _resolve_safe_path(filename, base_dir=build_dir)
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': f'File not found: {filename}'}), 404

    return send_from_directory(build_dir, os.path.basename(filepath), mimetype='application/octet-stream')


# Cache for the pgrep result in toolchain_status() fallback — avoids spawning a
# new subprocess on every poll when neither the progress file nor the setup-done
# marker exists (e.g. very early in container startup).
_pgrep_cache: dict = {'ts': 0.0, 'running': False}

@app.route('/api/toolchain/status')
def toolchain_status():
    """
    Return the current toolchain setup progress so the UI can show a progress bar.
    Reads from /tmp/toolchain_setup_progress.json (written by toolchain_setup.py).
    Falls back to ready if the legacy .cyd_setup_done marker is present.
    """
    progress_file = '/tmp/toolchain_setup_progress.json'
    upgrade_warning = None
    for warn_file in ('/tmp/cyd_upgrade_warning.json', '/root/.platformio/.cyd_upgrade_warning.json'):
        if os.path.exists(warn_file):
            try:
                with open(warn_file) as f:
                    upgrade_warning = json.load(f)
                break
            except Exception:
                pass

    if os.path.exists(progress_file):
        try:
            with open(progress_file) as f:
                data = json.load(f)
                if upgrade_warning and 'upgrade_warning' not in data:
                    data['upgrade_warning'] = upgrade_warning
                return jsonify(data)
        except (json.JSONDecodeError, OSError):
            pass

    # Legacy: baked-in toolchain (BAKE_TOOLCHAIN=1) or already-set-up volume
    if os.path.exists('/root/.platformio/.cyd_setup_done'):
        res = {'phase': 'ready', 'progress': 100,
               'message': 'Toolchain ready.', 'fallback': False}
        if upgrade_warning:
            res['upgrade_warning'] = upgrade_warning
        return jsonify(res)

    # No progress file and no marker — check if the script is still running.
    # Cache the pgrep result for 5 s so rapid polls don't spawn a new process.
    global _pgrep_cache
    now = time.time()
    if now - _pgrep_cache['ts'] > 5:
        _pgrep_cache['running'] = subprocess.run(
            ['pgrep', '-f', 'toolchain_setup.py'],
            capture_output=True
        ).returncode == 0
        _pgrep_cache['ts'] = now

    if _pgrep_cache['running']:
        return jsonify({'phase': 'starting', 'progress': 0,
                        'message': 'Toolchain setup starting...', 'fallback': False})

    return jsonify({'phase': 'no_toolchain', 'progress': 0,
                    'message': 'Toolchain not initialised. '
                               'Open the Install dialog to build locally.',
                    'fallback': False})


@app.route('/api/toolchain/log', methods=['GET'])
def toolchain_log():
    """
    Return the last N lines of the toolchain setup log.
    Query param ?lines=N (default 200).
    """
    log_path = '/tmp/toolchain_setup.log'
    try:
        n = int(request.args.get('lines', 200))
    except (ValueError, TypeError):
        n = 200
    if not os.path.exists(log_path):
        return '', 200
    try:
        result = subprocess.run(['tail', '-n', str(n), log_path], capture_output=True, text=True)
        return result.stdout, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f'Error reading log: {e}', 500

@app.route('/api/toolchain/start_local_build', methods=['POST'])
def toolchain_start_local_build():
    """
    Trigger a local toolchain build (user confirmed via the UI).
    Launches toolchain_setup.py --force-local in the background.
    """
    progress_file = '/tmp/toolchain_setup_progress.json'
    # Prevent double-start
    if os.path.exists(progress_file):
        try:
            data = json.load(open(progress_file))
            running_phases = ('downloading', 'extracting', 'fixing', 'building')
            if data.get('phase') in running_phases:
                return jsonify({'status': 'already_running', 'phase': data['phase']}), 200
        except (json.JSONDecodeError, OSError):
            pass

    setup_script = '/app/toolchain_setup.py'
    if not os.path.exists(setup_script):
        return jsonify({'error': 'toolchain_setup.py not found'}), 500

    log_file = open('/tmp/toolchain_setup.log', 'w')
    proc = subprocess.Popen(
        ['python3', setup_script, '--force-local'],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
    )
    # Persist PID so the cancel endpoint can kill it
    with open('/tmp/toolchain_setup.pid', 'w') as f:
        f.write(str(proc.pid))
    return jsonify({'status': 'started'})

@app.route('/api/toolchain/cancel', methods=['POST'])
def toolchain_cancel():
    """
    Kill any running toolchain_setup.py process and reset state to no_toolchain.
    """
    import signal as _signal
    killed = False
    pid_file = '/tmp/toolchain_setup.pid'
    # Try pid file first
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, _signal.SIGTERM)
            killed = True
        except (ValueError, ProcessLookupError, OSError):
            pass
        finally:
            try:
                os.remove(pid_file)
            except OSError:
                pass
    # Fallback: pkill by script name
    if not killed:
        try:
            subprocess.run(['pkill', '-f', 'toolchain_setup.py'], check=False)
            killed = True
        except Exception:
            pass
    # Reset progress file to no_toolchain
    progress_file = '/tmp/toolchain_setup_progress.json'
    try:
        import tempfile, json as _json
        payload = _json.dumps({'phase': 'no_toolchain', 'progress': 0,
                               'message': 'Build cancelled.', 'fallback': False})
        tmp = progress_file + '.tmp'
        with open(tmp, 'w') as f:
            f.write(payload)
        os.replace(tmp, progress_file)
    except Exception:
        pass
    return jsonify({'status': 'cancelled', 'killed': killed})

def _has_toolchain_assets() -> bool:
    packages_dir = '/root/.platformio/packages'
    idf_dir = '/root/.cache/esphome/idf'
    return (
        (os.path.isdir(packages_dir) and bool(os.listdir(packages_dir))) or
        (os.path.isdir(idf_dir) and bool(os.listdir(idf_dir)))
    )


@app.route('/api/toolchain/check_update', methods=['GET'])
def toolchain_check_update():
    """
    Non-destructive check: returns whether a newer toolchain build is available.
    Does NOT launch toolchain_setup.py — use POST /api/toolchain/download_latest for that.

    Returns:
      { update_available: bool, remote_build_id, local_build_id, version }
    """
    import urllib.request as _urllib_req
    import urllib.error   as _urllib_err

    build_id_file = '/root/.platformio/.cyd_toolchain_build_id'
    ver_file      = '/app/esphome_version.txt'
    repo_file     = '/app/github_repo.txt'

    expected_version = None
    if os.path.exists(ver_file):
        try:
            expected_version = open(ver_file).read().strip() or None
        except OSError:
            pass

    version_file = '/root/.platformio/.cyd_esphome_version'
    stored_version = None
    if os.path.exists(version_file):
        try:
            stored_version = open(version_file).read().strip() or None
        except OSError:
            pass

    local_build_id = None
    if os.path.exists(build_id_file):
        try:
            local_build_id = open(build_id_file).read().strip() or None
        except OSError:
            pass

    has_pkgs = _has_toolchain_assets()

    repo = 'yatush/cyd-tiled-display'
    if os.path.exists(repo_file):
        try:
            r = open(repo_file).read().strip()
            if r:
                repo = r
        except OSError:
            pass

    # When the stored toolchain is already ahead of the baked-in ESPHome version
    # (e.g. stored=2026.4.3, baked-in=2026.4.0), look up build_id.txt for the
    # stored version — not the baked-in one.  Using the baked-in version would
    # always produce a mismatch against the stored build_id, making the update
    # check incorrectly report that a new download is needed on every restart.
    def _ver_key(v):
        try:
            return tuple(int(x) for x in (v or '').split('.'))
        except Exception:
            return (0,)

    lookup_version = expected_version
    if _ver_key(stored_version) > _ver_key(lookup_version):
        lookup_version = stored_version

    remote_build_id = None
    if lookup_version:
        url = (f'https://github.com/{repo}/releases/download/'
               f'toolchain-esphome-{lookup_version}/build_id.txt')
        try:
            req = _urllib_req.Request(url, headers={'User-Agent': 'cyd-tiled-display/server'})
            with _urllib_req.urlopen(req, timeout=10) as resp:
                remote_build_id = resp.read().decode().strip() or None
        except _urllib_err.HTTPError as e:
            if e.code == 404:
                remote_build_id = None
        except Exception:
            pass

    update_available = bool(remote_build_id and has_pkgs and remote_build_id != local_build_id)

    return jsonify({
        'update_available': update_available,
        'remote_build_id': remote_build_id,
        'local_build_id': local_build_id,
        'version': lookup_version,
    })

@app.route('/api/toolchain/download_latest', methods=['POST'])
def toolchain_download_latest():
    """
    Check whether the installed toolchain is already the latest build on GitHub.

    The comparison uses the per-build build_id.txt published with each release
    (format: {esphome_version}-{YYYYMMDD}-run{N}).  This catches re-builds for
    the same ESPHome version.  Falls back to a version-only comparison for older
    releases that predate build_id.txt.

    Returns:
      { status: 'up_to_date', version, build_id }  — nothing to do
      { status: 'started' }                          — toolchain_setup.py launched
      { status: 'already_running', phase }           — already in progress
    """
    import urllib.request as _urllib_req
    import urllib.error   as _urllib_err

    version_file   = '/root/.platformio/.cyd_esphome_version'
    build_id_file  = '/root/.platformio/.cyd_toolchain_build_id'
    ver_file       = '/app/esphome_version.txt'
    repo_file      = '/app/github_repo.txt'
    progress_file  = '/tmp/toolchain_setup_progress.json'

    # Prevent double-start
    if os.path.exists(progress_file):
        try:
            with open(progress_file) as _f:
                _data = json.load(_f)
            running_phases = ('downloading', 'extracting', 'fixing', 'building', 'warming')
            if _data.get('phase') in running_phases:
                return jsonify({'status': 'already_running', 'phase': _data['phase']}), 200
        except (json.JSONDecodeError, OSError):
            pass

    # Read local state
    expected_version = None
    if os.path.exists(ver_file):
        try:
            expected_version = open(ver_file).read().strip() or None
        except OSError:
            pass

    local_build_id = None
    if os.path.exists(build_id_file):
        try:
            local_build_id = open(build_id_file).read().strip() or None
        except OSError:
            pass

    stored_version = None
    if os.path.exists(version_file):
        try:
            stored_version = open(version_file).read().strip() or None
        except OSError:
            pass

    has_pkgs = _has_toolchain_assets()

    # Determine GitHub repo
    repo = 'yatush/cyd-tiled-display'
    if os.path.exists(repo_file):
        try:
            r = open(repo_file).read().strip()
            if r:
                repo = r
        except OSError:
            pass

    # When the stored toolchain is already ahead of the baked-in ESPHome version
    # (e.g. stored=2026.4.3, baked-in=2026.4.0), look up build_id.txt for the
    # stored version — not the baked-in one.  Using the baked-in version would
    # always produce a mismatch against the stored build_id, triggering a
    # spurious re-download on every container restart.
    def _ver_key(v):
        try:
            return tuple(int(x) for x in (v or '').split('.'))
        except Exception:
            return (0,)

    lookup_version = expected_version
    if _ver_key(stored_version) > _ver_key(lookup_version):
        lookup_version = stored_version

    # Fetch remote build_id.txt (tiny file, fast)
    remote_build_id = None
    if lookup_version:
        url = (f'https://github.com/{repo}/releases/download/'
               f'toolchain-esphome-{lookup_version}/build_id.txt')
        try:
            req = _urllib_req.Request(
                url, headers={'User-Agent': 'cyd-tiled-display/server'})
            with _urllib_req.urlopen(req, timeout=10) as resp:
                remote_build_id = resp.read().decode().strip() or None
        except _urllib_err.HTTPError as e:
            if e.code == 404:
                # Old release without build_id.txt — fall back to version comparison
                remote_build_id = None
            # Other HTTP errors: treat as 'unknown', fall through
        except Exception:
            # Network error: treat as 'unknown', fall through
            pass

    # ── Decision ─────────────────────────────────────────────────────────────
    # Case A: remote build_id fetched successfully — compare directly
    if remote_build_id is not None:
        if remote_build_id == local_build_id:
            return jsonify({'status': 'up_to_date',
                            'version': lookup_version,
                            'build_id': remote_build_id})
        # IDs differ (or no local ID) → fall through to launch

    # Case B: no remote build_id (old release / network error) — version fallback
    else:
        if lookup_version and stored_version and has_pkgs and stored_version == lookup_version:
            return jsonify({'status': 'up_to_date', 'version': stored_version})

    # Launch toolchain_setup.py to download the new build.
    # Pass --force-download so it skips the "version already matches" check
    # (Case 1) and re-downloads even when the ESPHome version is unchanged
    # but a newer build tarball has been published (different build_id).
    setup_script = '/app/toolchain_setup.py'
    if not os.path.exists(setup_script):
        return jsonify({'error': 'toolchain_setup.py not found'}), 500

    log_file = open('/tmp/toolchain_setup.log', 'w')
    proc = subprocess.Popen(
        ['python3', setup_script, '--force-download'],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
    )
    with open('/tmp/toolchain_setup.pid', 'w') as f:
        f.write(str(proc.pid))
    return jsonify({'status': 'started'})

@app.route('/api/schema', methods=['GET'])
def get_schema():
    schema_path = os.path.join(BASE_DIR, 'external_components/tile_ui/schema.json')
    if not os.path.exists(schema_path):
        schema_path = os.path.join(APP_DIR, 'esphome/external_components/tile_ui/schema.json')
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Schema not found"}), 404

@app.route('/api/sync_github_lib', methods=['POST'])
def sync_github_lib():
    if not IS_ADDON:
        return jsonify({"error": "GitHub sync is only available in add-on mode"}), 403
    try:
        def validate_lib(lib_dir):
            configs = _load_device_configs(lib_dir)
            if _DEFAULT_DEVICE not in configs:
                raise ValueError("GitHub archive has an invalid default device configuration")

        count = sync_github_files(BASE_DIR, validate_lib)
        global _DEVICE_CONFIG
        _DEVICE_CONFIG = _load_device_configs(os.path.join(BASE_DIR, 'lib'))
        return jsonify({"success": True, "count": count})
    except (OSError, ValueError, RuntimeError, requests.RequestException, zipfile.BadZipFile) as error:
        app.logger.exception("GitHub sync failed")
        return jsonify({"error": str(error)}), 500

@app.route('/api/update_lib', methods=['POST'])
def update_lib():
    try:
        # Update lib with backup
        source_lib = os.path.join(APP_DIR, 'esphome/lib')
        target_lib = os.path.join(BASE_DIR, 'lib')
        backup_lib = os.path.join(BASE_DIR, 'lib_old')
        
        # If source and target are the same (local dev), skip
        if os.path.abspath(source_lib) == os.path.abspath(target_lib):
             return jsonify({"success": True, "message": "Source and target are the same (local dev)"})

        if os.path.exists(source_lib):
            if os.path.exists(target_lib):
                if os.path.exists(backup_lib):
                    shutil.rmtree(backup_lib)
                shutil.move(target_lib, backup_lib)
            shutil.copytree(source_lib, target_lib, ignore=shutil.ignore_patterns('.*', 'user_config.yaml', 'user_config_*.yaml', 'hw_overrides.yaml', 'test_device_tiles.yaml', 'images.yaml'))

            # Restore hw_overrides.yaml: keep user's existing file, otherwise seed from template
            hw_target = os.path.join(target_lib, 'hw_overrides.yaml')
            hw_backup = os.path.join(backup_lib, 'hw_overrides.yaml')
            hw_source = os.path.join(source_lib, 'hw_overrides.yaml')
            if os.path.exists(hw_backup):
                shutil.copy2(hw_backup, hw_target)
            elif os.path.exists(hw_source):
                shutil.copy2(hw_source, hw_target)
            
        # Update external components (tile_ui and tuya_ble_fan) without backup
        for comp_name in ('tile_ui', 'tuya_ble_fan'):
            source_comp = os.path.join(APP_DIR, 'esphome/external_components', comp_name)
            target_comp = os.path.join(BASE_DIR, 'external_components', comp_name)
            if os.path.exists(source_comp):
                if os.path.exists(target_comp):
                    shutil.rmtree(target_comp)
                os.makedirs(os.path.dirname(target_comp), exist_ok=True)
                shutil.copytree(
                    source_comp,
                    target_comp,
                    ignore=shutil.ignore_patterns('.*', 'tests', '__pycache__'),
                )

        # Update default device YAML files (overwrite if changed, seed if missing).
        for fname in _DEFAULT_DEVICE_YAMLS:
            src = os.path.join(APP_DIR, 'esphome', fname)
            dst = os.path.join(BASE_DIR, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Update Lib Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_directory_hashes(directory):
    if not os.path.exists(directory):
        return {}
    
    file_hashes = {}
    for root, dirs, files in os.walk(directory):
        # Filter out hidden directories and the images/ dir to prevent recursion
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'images']
        dirs.sort() # Ensure deterministic traversal
        for file in sorted(files):
            if '_custom.' in file or '__pycache__' in root or file.endswith('.pyc') or file == 'user_config.yaml' or file.startswith('user_config_') or file == 'hw_overrides.yaml' or file.startswith('.'):                continue
            path = os.path.join(root, file)
            rel_path = os.path.relpath(path, directory).replace('\\', '/')
            if rel_path == 'images.yaml':
                continue
            try:
                with open(path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                    file_hashes[rel_path] = file_hash
            except:
                pass
    return file_hashes

# Device YAML files (shipped with the addon) that should be tracked in diffs and synced on update.
_DEFAULT_DEVICE_YAMLS = ['test_device.yaml']

def get_diff(source_hashes, target_hashes):
    diff = []
    all_files = set(source_hashes.keys()) | set(target_hashes.keys())
    
    # Generated/temp files that should never appear in the diff
    _IGNORED_FILES = {'test_device_tiles.yaml'}

    for f in sorted(all_files):
        # Ignore test files — they are dev-only and not deployed to HA
        if f.startswith('tests/') or f.startswith('tests\\'):
            continue
        # Ignore generated artifacts
        if os.path.basename(f) in _IGNORED_FILES:
            continue
        if f not in source_hashes:
            # Ignore PNG files that exist only in the target (they are generated artifacts)
            if f.endswith('.png'):
                continue
            diff.append(f"{f} (Extra in target)")
        elif f not in target_hashes:
            diff.append(f"{f} (Missing in target)")
        elif source_hashes[f] != target_hashes[f]:
            diff.append(f"{f} (Modified)")
            
    return diff

@app.route('/api/check_lib_status')
def check_lib_status():
    try:
        source_lib = os.path.join(APP_DIR, 'esphome/lib')
        target_lib = os.path.join(BASE_DIR, 'lib')
        
        source_ui = os.path.join(APP_DIR, 'esphome/external_components/tile_ui')
        target_ui = os.path.join(BASE_DIR, 'external_components/tile_ui')
        
        # If source and target are the same (local dev), they are synced
        if os.path.abspath(source_lib) == os.path.abspath(target_lib):
            return jsonify({
                "lib_synced": True,
                "ui_synced": True,
                "synced": True,
                "details": []
            })

        source_lib_hashes = get_directory_hashes(source_lib)
        target_lib_hashes = get_directory_hashes(target_lib)
        lib_diff = get_diff(source_lib_hashes, target_lib_hashes)
        
        source_ui_hashes = get_directory_hashes(source_ui)
        target_ui_hashes = get_directory_hashes(target_ui)
        ui_diff = get_diff(source_ui_hashes, target_ui_hashes)

        source_ble_fan = os.path.join(APP_DIR, 'esphome/external_components/tuya_ble_fan')
        target_ble_fan = os.path.join(BASE_DIR, 'external_components/tuya_ble_fan')
        if os.path.exists(source_ble_fan):
            ble_fan_diff = get_diff(
                get_directory_hashes(source_ble_fan),
                get_directory_hashes(target_ble_fan),
            )
            ui_diff.extend([f"tuya_ble_fan/{d}" for d in ble_fan_diff])

        # For device yamls: flag if missing or modified vs the shipped version,
        # but never complain about extra yamls the user added themselves.
        def _md5_file(path):
            try:
                with open(path, 'rb') as _f:
                    return hashlib.md5(_f.read()).hexdigest()
            except Exception:
                return None

        device_diff = []
        for fname in _DEFAULT_DEVICE_YAMLS:
            src_hash = _md5_file(os.path.join(APP_DIR, 'esphome', fname))
            if src_hash is None:
                continue  # source doesn't exist, nothing to check
            dst_hash = _md5_file(os.path.join(BASE_DIR, fname))
            if dst_hash is None:
                device_diff.append(f"{fname} (Missing in target)")
            elif src_hash != dst_hash:
                device_diff.append(f"{fname} (Modified)")

        lib_synced = len(lib_diff) == 0
        ui_synced = len(ui_diff) == 0
        device_synced = len(device_diff) == 0
        
        details = []
        if not lib_synced:
            details.append("Library files:")
            details.extend([f"  - {d}" for d in lib_diff])
        if not ui_synced:
            details.append("UI Component files:")
            details.extend([f"  - {d}" for d in ui_diff])
        if not device_synced:
            details.append("Device files:")
            details.extend([f"  - {d}" for d in device_diff])

        return jsonify({
            "lib_synced": lib_synced,
            "ui_synced": ui_synced,
            "synced": lib_synced and ui_synced and device_synced,
            "details": details
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


_KNOWN_TUYA_FAN_PRODUCT_IDS = {
    "vfqiwthdnlkynebk",  # Varin VA-E002
    "hceemlamlwxpufpa",  # Sofucor KBS
}


def discover_tuya_ble_fans(ha_config_dir=None):
    """Inspect Home Assistant .storage files to discover Tuya local fans and their companion lights."""
    cfg_dir = ha_config_dir or os.environ.get('HA_CONFIG_DIR', '/config')
    entries_path = os.path.join(cfg_dir, '.storage', 'core.config_entries')
    registry_path = os.path.join(cfg_dir, '.storage', 'core.entity_registry')
    device_registry_path = os.path.join(cfg_dir, '.storage', 'core.device_registry')

    if not os.path.exists(entries_path):
        return []

    try:
        with open(entries_path, 'r', encoding='utf-8') as f:
            entries_doc = json.load(f)
    except Exception as e:
        print(f"[tuya_ble_fans] Failed to read {entries_path}: {e}")
        return []

    # Map config_entry_id -> list of (entity_id, unique_id)
    entities_by_entry = {}
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                reg_doc = json.load(f)
            for ent in reg_doc.get('data', {}).get('entities', []):
                if not isinstance(ent, dict) or ent.get('disabled_by'):
                    continue
                entry_id = ent.get('config_entry_id')
                entity_id = ent.get('entity_id', '')
                unique_id = str(ent.get('unique_id') or '')
                if not entry_id or not entity_id:
                    continue
                entities_by_entry.setdefault(entry_id, []).append((entity_id, unique_id))
        except Exception as e:
            print(f"[tuya_ble_fans] Failed to read {registry_path}: {e}")

    # Map config_entry_id / tuya device_id -> MAC address from core.device_registry
    mac_by_entry = {}
    mac_by_identifier = {}
    if os.path.exists(device_registry_path):
        try:
            with open(device_registry_path, 'r', encoding='utf-8') as f:
                dev_doc = json.load(f)
            for dev in dev_doc.get('data', {}).get('devices', []):
                if not isinstance(dev, dict):
                    continue
                mac_val = ''
                for conn in dev.get('connections') or []:
                    if isinstance(conn, (list, tuple)) and len(conn) >= 2 and str(conn[0]).lower() == 'mac':
                        mac_val = str(conn[1]).strip().upper()
                        break
                if not mac_val:
                    continue
                for ce_id in dev.get('config_entries') or []:
                    mac_by_entry.setdefault(ce_id, mac_val)
                for ident in dev.get('identifiers') or []:
                    if isinstance(ident, (list, tuple)) and len(ident) >= 2:
                        mac_by_identifier.setdefault(str(ident[1]).strip(), mac_val)
        except Exception as e:
            print(f"[tuya_ble_fans] Failed to read {device_registry_path}: {e}")

    fans = []
    seen_device_ids = set()
    for entry in entries_doc.get('data', {}).get('entries', []):
        if not isinstance(entry, dict) or entry.get('disabled_by'):
            continue
        domain = entry.get('domain', '')
        if domain not in ('tuya_local', 'localtuya'):
            continue

        entry_id = entry.get('entry_id', '')
        title = entry.get('title') or ''
        data = entry.get('data') or {}
        options = entry.get('options') or {}

        # Normalize both tuya_local (single device per entry) and localtuya (devices dict)
        is_multi_hub = False
        raw_devices = []
        if 'device_id' in data and 'local_key' in data:
            raw_devices.append((title, data))
        elif isinstance(data.get('devices'), dict):
            is_multi_hub = True
            for dev_id, dev_cfg in data['devices'].items():
                if isinstance(dev_cfg, dict) and dev_cfg.get('local_key'):
                    merged = dict(dev_cfg)
                    merged.setdefault('device_id', dev_id)
                    raw_devices.append((dev_cfg.get('friendly_name') or title, merged))

        entry_entities = entities_by_entry.get(entry_id, [])

        for dev_name, dev_data in raw_devices:
            device_id = str(dev_data.get('device_id') or '').strip()
            local_key = str(dev_data.get('local_key') or '').strip()
            if not device_id or not local_key or device_id in seen_device_ids:
                continue

            product_id = str(
                dev_data.get('product_id')
                or options.get('product_id')
                or dev_data.get('model')
                or ''
            ).strip()

            if is_multi_hub:
                dev_entities = [eid for eid, uid in entry_entities if device_id in uid]
            else:
                dev_entities = [eid for eid, _uid in entry_entities]

            fan_entities = sorted(e for e in dev_entities if e.startswith('fan.'))
            light_entities = sorted(e for e in dev_entities if e.startswith('light.'))

            fan_entity_id = fan_entities[0] if fan_entities else ''
            light_entity_id = light_entities[0] if light_entities else ''

            is_known_product = product_id in _KNOWN_TUYA_FAN_PRODUCT_IDS
            if not fan_entity_id and not is_known_product:
                # Skip non-fan tuya_local/localtuya devices (plugs, heaters, etc.)
                continue

            mac_address = str(
                dev_data.get('mac_address')
                or dev_data.get('mac')
                or mac_by_identifier.get(device_id)
                or (mac_by_entry.get(entry_id) if not is_multi_hub else '')
                or ''
            ).strip().upper()
            uuid_val = str(dev_data.get('uuid') or '').strip()

            seen_device_ids.add(device_id)
            fans.append({
                'name': dev_name or fan_entity_id or device_id,
                'device_id': device_id,
                'local_key': local_key,
                'product_id': product_id,
                'mac_address': mac_address,
                'uuid': uuid_val,
                'fan_entity_id': fan_entity_id,
                'light_entity_id': light_entity_id,
                'supported': is_known_product or bool(fan_entity_id),
            })

    return fans


BLE_FAN_VAULT_FILENAME = '.cyd_ble_fans.json'


def _ble_fan_vault_path(esphome_dir=None):
    root_dir = esphome_dir or BASE_DIR
    return os.path.join(root_dir, BLE_FAN_VAULT_FILENAME)


def load_ble_fan_vault(esphome_dir=None):
    """Load persisted BLE fan credentials from /config/esphome/.cyd_ble_fans.json."""
    path = _ble_fan_vault_path(esphome_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('fans'), dict):
            return dict(data['fans'])
    except Exception:
        pass
    return {}


def save_ble_fans_to_vault(fans, esphome_dir=None):
    """Upsert BLE fan credentials (device_id + local_key) into .cyd_ble_fans.json without deleting existing entries."""
    if not fans:
        return load_ble_fan_vault(esphome_dir)
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return {}

    vault = load_ble_fan_vault(root_dir)
    changed = False
    for fan in fans:
        if not isinstance(fan, dict):
            continue
        dev_id = str(fan.get('device_id') or '').strip()
        local_key = str(fan.get('local_key') or '').strip()
        if not dev_id or not local_key:
            continue
        prev = dict(vault.get(dev_id) or {})
        merged = {
            'name': str(fan.get('name') or prev.get('name') or dev_id).strip(),
            'device_id': dev_id,
            'local_key': local_key,
            'product_id': str(fan.get('product_id') or prev.get('product_id') or '').strip(),
            'mac_address': str(fan.get('mac_address') or prev.get('mac_address') or '').strip().upper(),
            'uuid': str(fan.get('uuid') or prev.get('uuid') or '').strip(),
            'fan_entity_id': str(fan.get('fan_entity_id') or prev.get('fan_entity_id') or '').strip(),
            'light_entity_id': str(fan.get('light_entity_id') or prev.get('light_entity_id') or '').strip(),
            'supported': True,
        }
        if merged != prev:
            vault[dev_id] = merged
            changed = True

    if changed:
        path = _ble_fan_vault_path(root_dir)
        tmp_path = f'{path}.tmp'
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump({'version': 1, 'fans': vault}, f, indent=2, sort_keys=True)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
    return vault


def collect_yaml_ble_fans(esphome_dir=None):
    """Extract all tuya_ble_fan.fans entries currently configured in CYD device YAMLs."""
    root_dir = esphome_dir or BASE_DIR
    collected = []
    if not root_dir or not os.path.isdir(root_dir):
        return collected
    loader_cls = generate_tiles_api.create_safe_yaml_loader()
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in ('secrets.yaml', 'images.yaml'):
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            if not re.search(r'^tuya_ble_fan:', raw_text, flags=re.MULTILINE):
                continue
            parsed = yaml.load(raw_text, Loader=loader_cls)
            if not isinstance(parsed, dict):
                continue
            fans = (parsed.get('tuya_ble_fan') or {}).get('fans')
            if isinstance(fans, list):
                for item in fans:
                    if isinstance(item, dict) and item.get('device_id') and item.get('local_key'):
                        collected.append(dict(item))
        except Exception:
            continue
    return collected


def get_all_known_tuya_ble_fans(ha_config_dir=None, esphome_dir=None):
    """Return deduplicated BLE fans from HA storage, CYD YAMLs, and the persistent .cyd_ble_fans.json vault."""
    ha_fans = discover_tuya_ble_fans(ha_config_dir)
    yaml_fans = collect_yaml_ble_fans(esphome_dir)
    vault = save_ble_fans_to_vault(ha_fans + yaml_fans, esphome_dir)

    by_id = {}
    for fan in ha_fans:
        dev_id = str(fan.get('device_id') or '').strip()
        if dev_id:
            by_id[dev_id] = dict(fan)
    for dev_id, vfan in vault.items():
        if dev_id in by_id:
            # Enrich HA entry with cached MAC/UUID if missing
            for k in ('mac_address', 'uuid', 'product_id'):
                if not by_id[dev_id].get(k) and vfan.get(k):
                    by_id[dev_id][k] = vfan[k]
        else:
            by_id[dev_id] = dict(vfan)

    return sorted(by_id.values(), key=lambda x: (str(x.get('name') or '').lower(), str(x.get('device_id') or '')))


def find_ble_fan_hosts(esphome_dir=None):
    """Scan ESPHome device YAMLs to find which device files already host each Tuya BLE fan device_id."""
    by_id, _by_mac, _by_uuid = _find_ble_fan_hosts_extended(esphome_dir)
    return by_id


@app.route('/api/tuya_ble_fans', methods=['GET'])
def get_tuya_ble_fans():
    try:
        fans = get_all_known_tuya_ble_fans()
        hosted_by = find_ble_fan_hosts()
        for fan in fans:
            fan['hosted_by'] = hosted_by.get(fan['device_id'], [])
        return jsonify({'fans': fans, 'hosted_by': hosted_by})
    except Exception as e:
        return jsonify({'fans': [], 'hosted_by': {}, 'error': str(e)}), 500


def generate_tuya_ble_credentials():
    """Generate a random Tuya-compatible 22-char device_id and 16-char local_key."""
    import secrets as py_secrets
    import string

    id_alphabet = string.ascii_lowercase + string.digits
    key_alphabet = string.ascii_letters + string.digits
    device_id = 'bf' + ''.join(py_secrets.choice(id_alphabet) for _ in range(20))
    local_key = ''.join(py_secrets.choice(key_alphabet) for _ in range(16))
    return device_id, local_key


def _load_esphome_secrets(esphome_dir=None):
    root_dir = esphome_dir or BASE_DIR
    secrets_path = os.path.join(root_dir, 'secrets.yaml')
    if not os.path.isfile(secrets_path):
        return {}
    try:
        with open(secrets_path, 'r', encoding='utf-8', errors='replace') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_device_api_info(filepath, secrets_map=None):
    """Extract api.encryption.key, api.password, and api.port from an ESPHome device YAML, resolving !secret and packages."""
    secrets_map = secrets_map or {}
    base_loader = generate_tiles_api.create_safe_yaml_loader(
        include_base_dir=os.path.dirname(filepath)
    )

    class SecretResolvingLoader(base_loader):
        pass

    def _secret_ctor(loader, node):
        key_name = loader.construct_scalar(node)
        return secrets_map.get(key_name)

    SecretResolvingLoader.add_constructor('!secret', _secret_ctor)

    try:
        # Skip only the indented tile_ui: block so top-level api: after tile_ui: is still parsed
        lines = []
        skipping_tile_ui = False
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('tile_ui:') or line.startswith('tile_ui '):
                    skipping_tile_ui = True
                    continue
                if skipping_tile_ui:
                    if line.strip() and not line[0].isspace() and not line.lstrip().startswith('#'):
                        skipping_tile_ui = False
                    else:
                        continue
                lines.append(line)
        data = yaml.load(''.join(lines), Loader=SecretResolvingLoader)
    except Exception:
        return {'api_key': None, 'api_password': '', 'api_port': 6053}

    if not isinstance(data, dict):
        return {'api_key': None, 'api_password': '', 'api_port': 6053}

    api_key = None
    api_password = ''
    api_port = 6053

    # Check substitutions.api_port first
    subs = data.get('substitutions')
    if isinstance(subs, dict) and subs.get('api_port'):
        try:
            api_port = int(subs['api_port'])
        except (TypeError, ValueError):
            pass

    def _apply_api_cfg(cfg):
        nonlocal api_key, api_password, api_port
        if not isinstance(cfg, dict):
            return
        enc = cfg.get('encryption')
        if isinstance(enc, dict) and enc.get('key'):
            api_key = str(enc['key']).strip()
        if cfg.get('password'):
            api_password = str(cfg['password'])
        if cfg.get('port'):
            try:
                api_port = int(cfg['port'])
            except (TypeError, ValueError):
                pass

    # Check included packages first, then top-level api: (top-level wins)
    packages = data.get('packages')
    if isinstance(packages, dict):
        for pkg_val in packages.values():
            if isinstance(pkg_val, dict) and isinstance(pkg_val.get('api'), dict):
                _apply_api_cfg(pkg_val['api'])
    _apply_api_cfg(data.get('api'))

    return {'api_key': api_key, 'api_password': api_password, 'api_port': api_port}


def _list_cyd_devices_with_api(esphome_dir=None):
    """Return metadata + API credentials for all CYD YAML files in esphome_dir."""
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return []
    secrets_map = _load_esphome_secrets(root_dir)
    skip_files = {'secrets.yaml', 'images.yaml'}
    devices = []
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in skip_files:
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        meta = _parse_device_yaml(fpath)
        if not meta or not meta.get('is_cyd'):
            continue
        api_info = _extract_device_api_info(fpath, secrets_map)
        meta['filename'] = fname
        meta['path'] = fname
        meta['filepath'] = fpath
        meta['api_key'] = api_info['api_key']
        meta['api_password'] = api_info['api_password']
        meta['api_port'] = api_info['api_port']
        devices.append(meta)
    return devices


def _find_ble_fan_hosts_extended(esphome_dir=None):
    """Return maps of device_id -> [files], mac -> [files], and uuid -> [files] across CYD YAMLs."""
    root_dir = esphome_dir or BASE_DIR
    by_id, by_mac, by_uuid = {}, {}, {}
    if not root_dir or not os.path.isdir(root_dir):
        return by_id, by_mac, by_uuid

    loader_cls = generate_tiles_api.create_safe_yaml_loader()
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in ('secrets.yaml', 'images.yaml'):
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            if not re.search(r'^tuya_ble_fan:', raw_text, flags=re.MULTILINE):
                continue
            parsed = yaml.load(raw_text, Loader=loader_cls)
            if not isinstance(parsed, dict):
                continue
            fans = (parsed.get('tuya_ble_fan') or {}).get('fans')
            if not isinstance(fans, list):
                continue
            for fan in fans:
                if not isinstance(fan, dict):
                    continue
                dev_id = str(fan.get('device_id') or '').strip()
                mac = str(fan.get('mac_address') or '').strip().upper()
                uuid_val = str(fan.get('uuid') or '').strip()
                if dev_id:
                    by_id.setdefault(dev_id, [])
                    if fname not in by_id[dev_id]:
                        by_id[dev_id].append(fname)
                if mac:
                    by_mac.setdefault(mac, [])
                    if fname not in by_mac[mac]:
                        by_mac[mac].append(fname)
                if uuid_val:
                    by_uuid.setdefault(uuid_val, [])
                    if fname not in by_uuid[uuid_val]:
                        by_uuid[uuid_val].append(fname)
        except Exception:
            continue
    return by_id, by_mac, by_uuid


def aggregate_ble_scan_sightings(sightings, tuya_local_fans=None,
                                 hosted_by_id=None, hosted_by_mac=None, hosted_by_uuid=None):
    """Deduplicate raw BLE sightings across CYDs by MAC, rank by strongest RSSI, and enrich with HA/CYD info."""
    tuya_local_fans = tuya_local_fans or []
    hosted_by_id = hosted_by_id or {}
    hosted_by_mac = hosted_by_mac or {}
    hosted_by_uuid = hosted_by_uuid or {}

    by_mac = {}
    for s in sightings:
        mac = str(s.get('mac') or '').strip().upper()
        if not mac:
            continue
        cyd_file = str(s.get('cyd_filename') or s.get('cyd_device') or '').strip()
        try:
            rssi = int(s.get('rssi', -127))
        except (TypeError, ValueError):
            rssi = -127
        try:
            addr_type = int(s.get('addr_type', 0))
        except (TypeError, ValueError):
            addr_type = 0
        bound_raw = s.get('bound', False)
        bound = bound_raw if isinstance(bound_raw, bool) else str(bound_raw).strip().lower() in ('true', '1', 'yes')
        uuid_val = str(s.get('uuid') or '').strip()
        product_id = str(s.get('product_id') or '').strip()

        entry = by_mac.get(mac)
        if entry is None:
            entry = {
                'mac': mac,
                'addr_type': addr_type,
                'bound': bound,
                'uuid': uuid_val,
                'product_id': product_id,
                '_cyd_map': {},
            }
            by_mac[mac] = entry
        else:
            if not entry['uuid'] and uuid_val:
                entry['uuid'] = uuid_val
            if not entry['product_id'] and product_id:
                entry['product_id'] = product_id
            # If any sighting says bound=True, mark bound
            if bound:
                entry['bound'] = True

        existing_cyd = entry['_cyd_map'].get(cyd_file)
        if existing_cyd is None or rssi > existing_cyd['rssi']:
            entry['_cyd_map'][cyd_file] = {
                'cyd_filename': cyd_file,
                'cyd_name': s.get('cyd_name') or cyd_file,
                'friendly_name': s.get('friendly_name') or s.get('cyd_name') or cyd_file,
                'rssi': rssi,
            }

    # Build lookup indexes for tuya_local fans
    ha_by_mac = {str(f.get('mac_address') or '').strip().upper(): f for f in tuya_local_fans if f.get('mac_address')}
    ha_by_uuid = {str(f.get('uuid') or '').strip(): f for f in tuya_local_fans if f.get('uuid')}

    results = []
    for mac, entry in by_mac.items():
        ranked = sorted(entry['_cyd_map'].values(), key=lambda x: x['rssi'], reverse=True)
        best = ranked[0] if ranked else None
        matched_ha = ha_by_mac.get(mac) or (ha_by_uuid.get(entry['uuid']) if entry['uuid'] else None)

        hosted = []
        for h in hosted_by_mac.get(mac, []):
            if h not in hosted:
                hosted.append(h)
        if entry['uuid']:
            for h in hosted_by_uuid.get(entry['uuid'], []):
                if h not in hosted:
                    hosted.append(h)
        if matched_ha and matched_ha.get('device_id'):
            for h in hosted_by_id.get(matched_ha['device_id'], []):
                if h not in hosted:
                    hosted.append(h)

        results.append({
            'mac': mac,
            'addr_type': entry['addr_type'],
            'bound': entry['bound'],
            'uuid': entry['uuid'],
            'product_id': entry['product_id'] or (matched_ha.get('product_id', '') if matched_ha else ''),
            'best_cyd': best,
            'best_rssi': best['rssi'] if best else -127,
            'sightings': ranked,
            'hosted_by': hosted,
            'matched_ha_fan': {
                'name': matched_ha.get('name', ''),
                'device_id': matched_ha.get('device_id', ''),
                'local_key': matched_ha.get('local_key', ''),
                'product_id': matched_ha.get('product_id', ''),
                'fan_entity_id': matched_ha.get('fan_entity_id', ''),
                'light_entity_id': matched_ha.get('light_entity_id', ''),
            } if matched_ha else None,
        })

    results.sort(key=lambda r: r['best_rssi'], reverse=True)
    return results


class _YamlSecret(str):
    """Marker scalar that round-trips as `!secret <name>` during YAML dump."""


class _SecretPreservingDumper(yaml.SafeDumper):
    pass


def _represent_yaml_secret(dumper, data):
    return dumper.represent_scalar('!secret', str(data))


_SecretPreservingDumper.add_representer(_YamlSecret, _represent_yaml_secret)


def _replace_top_level_yaml_block(raw_text, block_key, rendered_block):
    """Replace a top-level YAML block cleanly by line boundaries (preserving column-0 comments and backslashes)."""
    lines = raw_text.splitlines(keepends=True)
    start_idx = None
    for i, line in enumerate(lines):
        if re.match(rf'^{re.escape(block_key)}:\s*(?:#.*)?$', line):
            start_idx = i
            break

    if start_idx is None:
        prefix = raw_text
        if prefix and not prefix.endswith('\n'):
            prefix += '\n'
        return prefix + ('\n' if prefix and not prefix.endswith('\n\n') else '') + rendered_block

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not line[0].isspace():
            end_idx = j
            break

    replacement = rendered_block + ('\n' if end_idx < len(lines) else '')
    return ''.join(lines[:start_idx]) + replacement + ''.join(lines[end_idx:])


def compute_ble_resource_plan(fan_count, has_ble_proxy=False):
    """Compute simultaneous BLE connection slots and display buffer sizing for a CYD."""
    count = max(0, int(fan_count or 0))
    max_fan_slots = 2 if has_ble_proxy else 3
    fan_slots = min(count, max_fan_slots) if count > 0 else 1
    proxy_slots = 1 if has_ble_proxy else 0
    total_connections = min(3, fan_slots + proxy_slots)
    persistent = count > 0 and count <= fan_slots
    idle_disconnect_s = 0 if persistent else 30
    display_buffer_size = '15%' if total_connections >= 3 else '20%'
    return {
        'fan_count': count,
        'fan_slots': fan_slots,
        'proxy_slots': proxy_slots,
        'total_connections': total_connections,
        'persistent': persistent,
        'idle_disconnect_s': idle_disconnect_s,
        'display_buffer_size': display_buffer_size,
    }


def _upsert_substitution(raw_text, key, value):
    """Set or update a key inside the top-level substitutions: block, preserving formatting."""
    quoted = f'"{value}"'
    lines = raw_text.splitlines(keepends=True)
    subs_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^substitutions:\s*(?:#.*)?$', line):
            subs_idx = i
            break

    if subs_idx is None:
        return f'substitutions:\n  {key}: {quoted}\n\n' + raw_text

    end_idx = len(lines)
    key_idx = None
    key_re = re.compile(rf'^(\s+){re.escape(key)}\s*:')
    for j in range(subs_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not line[0].isspace():
            end_idx = j
            break
        if key_re.match(line):
            key_idx = j
            break

    if key_idx is not None:
        indent = key_re.match(lines[key_idx]).group(1)
        lines[key_idx] = f'{indent}{key}: {quoted}\n'
    else:
        insert_line = f'  {key}: {quoted}\n'
        if not lines[subs_idx].endswith('\n'):
            lines[subs_idx] += '\n'
        lines.insert(subs_idx + 1, insert_line)
    return ''.join(lines)


def add_ble_fan_to_device_yaml(filepath, fan_entry):
    """Upsert a Tuya BLE fan entry into a target CYD YAML file, preserving comments, !secret tags, and existing fields."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    base_loader = generate_tiles_api.create_safe_yaml_loader()

    class SecretPreservingLoader(base_loader):
        pass

    SecretPreservingLoader.add_constructor(
        '!secret', lambda loader, node: _YamlSecret(loader.construct_scalar(node))
    )

    parsed = yaml.load(raw_text, Loader=SecretPreservingLoader) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    existing_ble_cfg = parsed.get('tuya_ble_fan')
    existing_ble_cfg = dict(existing_ble_cfg) if isinstance(existing_ble_cfg, dict) else {}

    existing_fans = []
    if isinstance(existing_ble_cfg.get('fans'), list):
        for item in existing_ble_cfg['fans']:
            if isinstance(item, dict):
                existing_fans.append(dict(item))

    new_fan = {
        'name': str(fan_entry.get('name') or fan_entry.get('device_id') or 'BLE Fan').strip(),
        'device_id': str(fan_entry.get('device_id') or '').strip(),
        'local_key': str(fan_entry.get('local_key') or '').strip(),
    }
    if not new_fan['device_id'] or not new_fan['local_key']:
        raise ValueError('device_id and local_key are required')

    for opt_key in ('product_id', 'mac_address', 'uuid', 'fan_entity_id', 'light_entity_id'):
        val = str(fan_entry.get(opt_key) or '').strip()
        if val:
            new_fan[opt_key] = val
    new_fan['expose_to_ha'] = fan_entry.get('expose_to_ha', True) is not False

    # Upsert by device_id or mac_address, merging into existing entry to preserve extra fields
    prev_count = len(existing_fans)
    replaced = False
    new_mac = new_fan.get('mac_address', '').upper()
    for idx, ef in enumerate(existing_fans):
        ef_id = str(ef.get('device_id') or '').strip()
        ef_mac = str(ef.get('mac_address') or '').strip().upper()
        if ef_id == new_fan['device_id'] or (new_mac and ef_mac == new_mac):
            merged = dict(ef)
            merged.update(new_fan)
            existing_fans[idx] = merged
            replaced = True
            break
    if not replaced:
        existing_fans.append(new_fan)

    updated_text = raw_text

    # 1. Ensure tuya_ble_fan package include is present under packages: (using parsed dict)
    packages = parsed.get('packages') if isinstance(parsed.get('packages'), dict) else {}
    has_tuya_pkg = any(
        isinstance(v, str) and 'lib/tuya_ble_fan.yaml' in v
        for v in packages.values()
    ) or ('tuya_ble_fan' in packages)
    if not has_tuya_pkg:
        pkg_match = re.search(r'^packages:\s*(?:#.*)?$', updated_text, flags=re.MULTILINE)
        if pkg_match:
            insert_pos = pkg_match.end()
            prefix = updated_text[:insert_pos]
            suffix = updated_text[insert_pos:]
            if not suffix.startswith('\n'):
                suffix = '\n' + suffix
            updated_text = prefix + '\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml' + suffix
        else:
            updated_text = 'packages:\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml\n\n' + updated_text

    # 2. Dynamically size ble_max_connections and display_buffer_size based on fan count & ble_proxy
    has_ble_proxy = any(
        k == 'ble_proxy' or (isinstance(v, str) and 'ble_proxy' in v)
        for k, v in packages.items()
    )
    plan = compute_ble_resource_plan(len(existing_fans), has_ble_proxy)
    updated_text = _upsert_substitution(updated_text, 'ble_max_connections', str(plan['total_connections']))
    updated_text = _upsert_substitution(updated_text, 'display_buffer_size', plan['display_buffer_size'])

    # 3. Render new top-level tuya_ble_fan: block (preserving extra keys)
    new_ble_cfg = {
        k: v for k, v in existing_ble_cfg.items()
        if k not in ('fans', 'idle_disconnect_s', 'max_connections')
    }
    new_ble_cfg['max_connections'] = plan['fan_slots']
    if 'idle_disconnect_s' in existing_ble_cfg and prev_count == len(existing_fans):
        new_ble_cfg['idle_disconnect_s'] = existing_ble_cfg['idle_disconnect_s']
    else:
        new_ble_cfg['idle_disconnect_s'] = plan['idle_disconnect_s']
    new_ble_cfg['fans'] = existing_fans

    rendered_block = yaml.dump(
        {'tuya_ble_fan': new_ble_cfg},
        Dumper=_SecretPreservingDumper,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip() + '\n'

    updated_text = _replace_top_level_yaml_block(updated_text, 'tuya_ble_fan', rendered_block)

    tmp_path = f"{filepath}.tmp.{os.getpid()}"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(updated_text)
    os.replace(tmp_path, filepath)

    # Return plain JSON-serializable fan dicts and back up to persistent vault
    plain_fans = [
        {k: (str(v) if isinstance(v, _YamlSecret) else v) for k, v in fan.items()}
        for fan in existing_fans
    ]
    save_ble_fans_to_vault(plain_fans, os.path.dirname(filepath))
    return plain_fans


async def _exec_esphome_service(client, service, data):
    import inspect
    res = client.execute_service(service, data)
    if inspect.isawaitable(res):
        await res


async def _disconnect_esphome_client(client):
    import inspect
    try:
        res = client.disconnect()
        if inspect.isawaitable(res):
            await asyncio.wait_for(res, timeout=3.0)
    except Exception:
        pass


async def _scan_single_cyd(cyd_info, duration_s=10):
    """Connect to one CYD over ESPHome Native API, invoke scan_tuya_ble_fans, and collect sightings."""
    cyd_file = cyd_info['filename']
    cyd_name = cyd_info['device_name']
    friendly = cyd_info['friendly_name']
    address = cyd_info['address']
    client = APIClient(
        address=address,
        port=int(cyd_info.get('api_port') or 6053),
        password=cyd_info.get('api_password') or '',
        noise_psk=cyd_info.get('api_key') or None,
    )
    sightings = []
    done_event = asyncio.Event()
    disconnect_error = []

    def on_stop(expected_disconnect=False):
        if not expected_disconnect and not done_event.is_set():
            disconnect_error.append('CYD disconnected during scan')
            done_event.set()

    def on_service_call(call):
        svc_name = getattr(call, 'service', '') or ''
        data = dict(getattr(call, 'data', {}) or {})
        if svc_name == 'esphome.tuya_ble_fan_found':
            sightings.append({
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'mac': data.get('mac', ''),
                'addr_type': data.get('addr_type', 0),
                'rssi': data.get('rssi', -127),
                'bound': data.get('bound', 'false'),
                'uuid': data.get('uuid', ''),
                'product_id': data.get('product_id', ''),
            })
        elif svc_name == 'esphome.tuya_ble_scan_done':
            done_event.set()

    try:
        try:
            await asyncio.wait_for(client.connect(login=True, on_stop=on_stop), timeout=8.0)
        except TypeError:
            await asyncio.wait_for(client.connect(login=True), timeout=8.0)
        _, services = await asyncio.wait_for(client.list_entities_services(), timeout=8.0)
        scan_svc = next((s for s in services if getattr(s, 'name', '') == 'scan_tuya_ble_fans'), None)
        if scan_svc is None:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'unsupported',
                'error': 'Firmware does not expose scan_tuya_ble_fans (flash updated firmware)',
                'sightings': [],
            }

        client.subscribe_service_calls(on_service_call)
        await _exec_esphome_service(client, scan_svc, {'duration_s': int(duration_s)})
        try:
            await asyncio.wait_for(done_event.wait(), timeout=float(duration_s) + 5.0)
        except asyncio.TimeoutError:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'error',
                'error': 'Timed out waiting for scan completion event from CYD',
                'sightings': sightings,
            }
        if disconnect_error:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'error',
                'error': disconnect_error[0],
                'sightings': sightings,
            }
        return {
            'cyd_filename': cyd_file,
            'cyd_name': cyd_name,
            'friendly_name': friendly,
            'status': 'ok',
            'error': '',
            'sightings': sightings,
        }
    except Exception as e:
        return {
            'cyd_filename': cyd_file,
            'cyd_name': cyd_name,
            'friendly_name': friendly,
            'status': 'error',
            'error': str(e),
            'sightings': sightings,
        }
    finally:
        await _disconnect_esphome_client(client)


async def _pair_unbound_on_cyd(cyd_info, mac, addr_type, uuid_val, device_id, local_key, blink_confirm=True):
    """Connect to target CYD and invoke pair_unbound_tuya_fan, awaiting esphome.tuya_ble_fan_paired."""
    client = APIClient(
        address=cyd_info['address'],
        port=int(cyd_info.get('api_port') or 6053),
        password=cyd_info.get('api_password') or '',
        noise_psk=cyd_info.get('api_key') or None,
    )
    target_mac = mac.strip().upper()
    result_box = {}
    done_event = asyncio.Event()

    def on_stop(expected_disconnect=False):
        if not expected_disconnect and not done_event.is_set():
            result_box['ok'] = False
            result_box['error'] = 'CYD disconnected during pairing'
            done_event.set()

    def on_service_call(call):
        svc_name = getattr(call, 'service', '') or ''
        data = dict(getattr(call, 'data', {}) or {})
        if svc_name == 'esphome.tuya_ble_fan_paired':
            ev_mac = str(data.get('mac') or '').strip().upper()
            if ev_mac and ev_mac != target_mac:
                return
            result_box['ok'] = str(data.get('ok', 'false')).lower() == 'true'
            result_box['mac'] = ev_mac or target_mac
            result_box['uuid'] = data.get('uuid', uuid_val)
            result_box['error'] = data.get('error', '')
            done_event.set()

    try:
        try:
            await asyncio.wait_for(client.connect(login=True, on_stop=on_stop), timeout=8.0)
        except TypeError:
            await asyncio.wait_for(client.connect(login=True), timeout=8.0)
        _, services = await asyncio.wait_for(client.list_entities_services(), timeout=8.0)
        pair_svc = next((s for s in services if getattr(s, 'name', '') == 'pair_unbound_tuya_fan'), None)
        if pair_svc is None:
            return {'ok': False, 'error': 'Target CYD firmware does not expose pair_unbound_tuya_fan'}

        client.subscribe_service_calls(on_service_call)
        await _exec_esphome_service(client, pair_svc, {
            'mac': target_mac,
            'addr_type': int(addr_type),
            'uuid': uuid_val,
            'device_id': device_id,
            'local_key': local_key,
            'blink_confirm': bool(blink_confirm),
        })
        await asyncio.wait_for(done_event.wait(), timeout=25.0)
        return result_box
    except asyncio.TimeoutError:
        return {'ok': False, 'error': 'Timed out waiting for BLE pairing response from CYD'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    finally:
        await _disconnect_esphome_client(client)


@app.route('/api/tuya_ble/scan', methods=['POST'])
def scan_tuya_ble_whole_house():
    """Trigger an on-demand BLE scan across all online CYDs in parallel and return ranked sightings."""
    try:
        body = request.get_json(silent=True) or {}
        try:
            duration_s = max(3, min(30, int(body.get('duration_s', 10))))
        except (TypeError, ValueError):
            return jsonify({'fans': [], 'cyds': [], 'error': 'Invalid duration_s'}), 400
        requested_devices = body.get('devices')

        all_cyds = _list_cyd_devices_with_api()
        if requested_devices and isinstance(requested_devices, list):
            req_set = set(requested_devices)
            all_cyds = [d for d in all_cyds if d['filename'] in req_set or d['device_name'] in req_set]

        if all_cyds:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(all_cyds))) as ex:
                all_cyds = list(ex.map(_check_device_online, all_cyds))

        online_cyds = [d for d in all_cyds if d.get('online')]
        offline_cyds = [
            {
                'cyd_filename': d['filename'],
                'cyd_name': d['device_name'],
                'friendly_name': d['friendly_name'],
                'status': 'offline',
                'error': 'Device is offline',
                'sightings_count': 0,
            }
            for d in all_cyds if not d.get('online')
        ]

        async def _run_all():
            if not online_cyds:
                return []
            return await asyncio.gather(*[_scan_single_cyd(c, duration_s) for c in online_cyds])

        scan_outputs = asyncio.run(_run_all())

        all_sightings = []
        cyd_statuses = []
        for out in scan_outputs:
            all_sightings.extend(out.get('sightings', []))
            cyd_statuses.append({
                'cyd_filename': out['cyd_filename'],
                'cyd_name': out['cyd_name'],
                'friendly_name': out['friendly_name'],
                'status': out['status'],
                'error': out.get('error', ''),
                'sightings_count': len(out.get('sightings', [])),
            })
        cyd_statuses.extend(offline_cyds)

        tuya_local_fans = get_all_known_tuya_ble_fans()
        hosted_by_id, hosted_by_mac, hosted_by_uuid = _find_ble_fan_hosts_extended()
        aggregated = aggregate_ble_scan_sightings(
            all_sightings,
            tuya_local_fans=tuya_local_fans,
            hosted_by_id=hosted_by_id,
            hosted_by_mac=hosted_by_mac,
            hosted_by_uuid=hosted_by_uuid,
        )

        return jsonify({
            'fans': aggregated,
            'cyds': cyd_statuses,
            'duration_s': duration_s,
            'tuya_local_fans': tuya_local_fans,
        })
    except Exception as e:
        return jsonify({'fans': [], 'cyds': [], 'error': str(e)}), 500


@app.route('/api/tuya_ble/pair', methods=['POST'])
def pair_unbound_tuya_ble_fan():
    """Pair an unbound (bound=0) Tuya BLE fan via the selected target CYD."""
    try:
        body = request.get_json(silent=True) or {}
        target_cyd = str(body.get('target_cyd') or '').strip()
        mac = str(body.get('mac') or '').strip().upper()
        try:
            addr_type = int(body.get('addr_type', 0))
            if addr_type < 0 or addr_type > 3:
                raise ValueError('addr_type out of range')
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid addr_type (expected 0..3)'}), 400
        uuid_val = str(body.get('uuid') or '').strip()
        blink_confirm = body.get('blink_confirm', True) is not False

        if not target_cyd or not mac or not uuid_val:
            return jsonify({'ok': False, 'error': 'target_cyd, mac, and uuid are required'}), 400

        cyds = _list_cyd_devices_with_api()
        cyd_info = next((c for c in cyds if c['filename'] == target_cyd or c['device_name'] == target_cyd), None)
        if cyd_info is None:
            return jsonify({'ok': False, 'error': f'Target CYD {target_cyd} not found'}), 404

        gen_id, gen_key = generate_tuya_ble_credentials()
        device_id = str(body.get('device_id') or gen_id).strip()
        local_key = str(body.get('local_key') or gen_key).strip()

        res = asyncio.run(_pair_unbound_on_cyd(
            cyd_info, mac, addr_type, uuid_val, device_id, local_key, blink_confirm=blink_confirm
        ))
        return jsonify({
            'ok': bool(res.get('ok')),
            'mac': res.get('mac', mac),
            'uuid': res.get('uuid', uuid_val),
            'device_id': device_id if res.get('ok') else '',
            'local_key': local_key if res.get('ok') else '',
            'error': res.get('error', ''),
        }), (200 if res.get('ok') else 502)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/tuya_ble/add_to_device', methods=['POST'])
def add_tuya_ble_fan_to_device():
    """Save a discovered/paired BLE fan directly into the target CYD's YAML config."""
    try:
        body = request.get_json(silent=True) or {}
        target_cyd = str(body.get('target_cyd') or '').strip()
        fan = body.get('fan')
        if not target_cyd or not isinstance(fan, dict):
            return jsonify({'ok': False, 'error': 'target_cyd and fan object are required'}), 400

        safe_name = os.path.basename(target_cyd)
        if not (safe_name.endswith('.yaml') or safe_name.endswith('.yml')) or safe_name != target_cyd:
            return jsonify({'ok': False, 'error': 'Invalid target_cyd filename'}), 400
        if safe_name in ('secrets.yaml', 'images.yaml'):
            return jsonify({'ok': False, 'error': f'{safe_name} is not a CYD device config'}), 400

        filepath = _resolve_safe_path(safe_name)
        if not filepath or not os.path.isfile(filepath):
            return jsonify({'ok': False, 'error': f'Device file {safe_name} not found'}), 404

        meta = _parse_device_yaml(filepath)
        if not meta or not meta.get('is_cyd'):
            return jsonify({'ok': False, 'error': f'{safe_name} is not a CYD device config'}), 400

        fans = add_ble_fan_to_device_yaml(filepath, fan)
        hosted_by = find_ble_fan_hosts()
        return jsonify({
            'ok': True,
            'target_cyd': safe_name,
            'fans': fans,
            'hosted_by': hosted_by,
        })
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/scripts')
def get_scripts():
    try:
        # Determine source directory once
        # Check BASE_DIR first (User config)
        source_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(source_dir):
            # Fallback to APP_DIR (Default lib)
            source_dir = os.path.join(APP_DIR, 'esphome/lib')

        doc = generate_tiles_api.load_merged_lib_doc(
            user_lib_dir=source_dir,
            fallback_lib_dir=os.path.join(APP_DIR, 'esphome/lib'),
            merge_keys=('script', 'color', 'globals'),
        )
        if doc is None:
            return jsonify({"error": f"lib.yaml not found in {source_dir}"}), 404

        scripts = doc.get('script', [])
        
        # Standard colors — Color(r, g, b) in RGB order, value is the matching CSS hex
        colors = [
            {'id': 'Color(0, 0, 0)',       'value': '#000000'},
            {'id': 'Color(255, 255, 255)', 'value': '#FFFFFF'},
            {'id': 'Color(255, 0, 0)',     'value': '#FF0000'},
            {'id': 'Color(0, 255, 0)',     'value': '#00FF00'},
            {'id': 'Color(0, 0, 255)',     'value': '#0000FF'},
            {'id': 'Color(255, 255, 0)',   'value': '#FFFF00'},
            {'id': 'Color(255, 165, 0)',   'value': '#FFA500'},
            {'id': 'Color(128, 0, 128)',   'value': '#800080'},
        ]

        # Add custom colors from lib.yaml
        for c in doc.get('color', []):
            value = '#000000'
            if 'hex' in c:
                hex_val = c['hex'].replace('#', '')
                if len(hex_val) == 6:
                    value = f"#{hex_val}"
                else:
                    value = f"#{hex_val}"
            elif all(k in c for k in ('red', 'green', 'blue')):
                # Simplified RGB handling
                value = f"rgb({c['red']}, {c['green']}, {c['blue']})"
            colors.append({'id': c['id'], 'value': value})

        # Fonts from base files in SAME directory
        fonts = []
        base_loader = generate_tiles_api.create_safe_yaml_loader()
        for base_file in ['3248s035_base.yaml', '2432s028_base.yaml']:
            base_path = os.path.join(source_dir, base_file)
            if os.path.exists(base_path):
                try:
                    with open(base_path, 'r') as f:
                        base_doc = yaml.load(f, Loader=base_loader) or {}
                        for font in base_doc.get('font', []):
                            if 'id' in font and font['id'] not in fonts:
                                fonts.append(font['id'])
                except Exception as e:
                    print(f"Error loading fonts from {base_file}: {e}")

        # Icons from mdi_glyphs.yaml in SAME directory
        icons = []
        glyphs_path = os.path.join(source_dir, 'mdi_glyphs.yaml')
        if os.path.exists(glyphs_path):
            with open(glyphs_path, 'r') as f:
                for line in f:
                    import re
                    match = re.search(r'"\\U([0-9a-fA-F]+)",\s*#\s*(.*)', line)
                    if match:
                        hex_code = match.group(1)
                        label = match.group(2).strip()
                        icons.append({
                            'value': f"\\U{hex_code}",
                            'label': label
                        })

        scripts_list = []

        for s in scripts:
            if 'id' in s:
                params = s.get('parameters', {})
                param_list = [
                    {'name': k, 'type': v}
                    for k, v in params.items()
                    if k not in ('x', 'y', 'entities', 'x_start', 'y_start', 'x_end', 'y_end')
                ]
                scripts_list.append({'id': s['id'], 'params': param_list})

        globals_list = [
            g['id'] for g in doc.get('globals', [])
            if g.get('type') == 'bool'
        ]

        return jsonify({
            "scripts": scripts_list,
            "colors": colors,
            "fonts": fonts,
            "icons": icons,
            "globals": globals_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Serve NoVNC static files
@app.route('/novnc/<path:path>')
def serve_novnc(path):
    novnc_dir = os.path.join(APP_DIR, 'novnc')
    return send_from_directory(novnc_dir, path)

# Proxy websocket requests to internal websockify (port 6081)
# This is needed for Cloud Run where we can only expose one port
@app.route('/websockify')
def websockify_proxy():
    # This won't work for actual websocket upgrade - we need a different approach
    # Return info for debugging
    return jsonify({"error": "Websocket proxy - this endpoint requires websocket upgrade"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
