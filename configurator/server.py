import os
import sys
import json
import subprocess
import shutil
import yaml
import hashlib
import signal
import socket
import time
import threading
from flask import Flask, request, send_from_directory, jsonify
import requests
import generate_tiles_api

app = Flask(__name__, static_folder='dist')

# Activity Monitoring
EMULATOR_TIMEOUT = 300  # 5 minutes
last_activity_time = time.time()

def update_activity():
    global last_activity_time
    last_activity_time = time.time()

@app.errorhandler(401)
def custom_401(error):
    # Prevent 401 from reaching Ingress, which might block the page
    return jsonify({"error": "Unauthorized (Intercepted)"}), 500

# Configuration from environment
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HA_URL = "http://supervisor/core"

# Determine environment paths
# BASE_DIR: Where the user's configuration lives (e.g. /config/esphome)
if os.path.exists('/config/esphome'):
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

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

@app.route('/api/emulator/start', methods=['POST'])
def start_emulator():
    update_activity()
    # Check existing PID
    if os.path.exists(EMULATOR_PID_FILE):
        try:
            with open(EMULATOR_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                 return jsonify({"status": "running", "message": "Emulator is already running"})
        except (ValueError, OSError):
            pass # Invalid PID file or process dead

    # Validate and Save Configuration
    try:
        config_data = request.get_json()
        if not config_data:
             return jsonify({"status": "error", "message": "No configuration provided"}), 400

        # Check if we received pre-generated YAML or raw pages
        if 'yaml' in config_data:
            yaml_str = config_data['yaml']
        elif 'pages' in config_data:
            # Fallback for older clients (though we should avoid this path if possible as it lacks the complex transformation logic)
            yaml_data = {'screens': config_data['pages']}
            yaml_str = yaml.dump(yaml_data)
        else:
            return jsonify({"status": "error", "message": "Invalid configuration format"}), 400
        
        # Validate using generate_tiles_api
        result = generate_tiles_api.generate_cpp_from_yaml(yaml_str)
        
        if "error" in result:
             return jsonify({"status": "error", "message": f"Configuration invalid: {result['error']}"}), 400
             
        # Write to user_config.yaml
        user_config_path = os.path.join(BASE_DIR, 'lib', 'user_config.yaml')
        with open(user_config_path, 'w') as f:
            f.write(yaml_str)
            
    except Exception as e:
        print(f"Config processing error: {e}")
        return jsonify({"status": "error", "message": f"Failed to process configuration: {str(e)}"}), 500

    script_path = os.path.join(os.path.dirname(__file__), 'run_emulator.sh')
    log_path = '/tmp/emulator.log'
    
    try:
        if os.path.exists(script_path):
            os.chmod(script_path, 0o755)
        
        with open(log_path, 'w', buffering=1) as log_file:
            # Use start_new_session=True to create a new process group
            # This allows us to kill the shell script and all its children (esphome, program)
            proc = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=log_file, 
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(__file__),
                start_new_session=True
            )
        
        with open(EMULATOR_PID_FILE, 'w') as f:
            f.write(str(proc.pid))
            
        return jsonify({"status": "started", "pid": proc.pid})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def _stop_emulator_process():
    if os.path.exists(EMULATOR_PID_FILE):
        try:
            with open(EMULATOR_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            
            # Kill the process group to ensure we get the children too
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
                
            os.remove(EMULATOR_PID_FILE)
        except Exception as e:
            print(f"Error stopping emulator: {e}")
            if os.path.exists(EMULATOR_PID_FILE):
                os.remove(EMULATOR_PID_FILE)
            
    # Fallback cleanup
    subprocess.run(['pkill', '-f', 'program'])
    subprocess.run(['pkill', '-f', 'esphome run'])

@app.route('/api/emulator/stop', methods=['POST'])
def stop_emulator():
    _stop_emulator_process()
    return jsonify({"status": "stopped"})

@app.route('/api/emulator/status', methods=['GET'])
def emulator_status():
    if os.path.exists(EMULATOR_PID_FILE):
        try:
            with open(EMULATOR_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                return jsonify({"status": "running"})
        except:
            pass
    return jsonify({"status": "stopped"})

@app.route('/api/emulator/logs', methods=['GET'])
def emulator_logs():
    update_activity()
    log_path = '/tmp/emulator.log'
    if os.path.exists(log_path):
        try:
            # Read the last 2000 lines to avoid sending too much data
            # Using tail command for efficiency
            result = subprocess.run(['tail', '-n', '2000', log_path], capture_output=True, text=True)
            return result.stdout
        except Exception as e:
            return f"Error reading logs: {e}"
    return "No logs available"

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        input_data = request.get_data(as_text=True)
        result = generate_tiles_api.generate_cpp_from_yaml(input_data)
        
        if "error" in result:
            print(f"Generation Error: {result['error']}", flush=True)
            return jsonify(result), 500
            
        return jsonify(result)
    except Exception as e:
        print(f"Server Error: {str(e)}", flush=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        path = request.args.get('path', '')
        # Security: prevent directory traversal
        if '..' in path:
            return jsonify({"error": "Invalid path"}), 400
        
        if not os.path.exists(BASE_DIR):
            # Ensure base dir exists
            os.makedirs(BASE_DIR, exist_ok=True)
            
        full_path = os.path.join(BASE_DIR, path.lstrip('/'))
        
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
        data = request.get_json()
        path = data.get('path', '')
        if not path or '..' in path:
            return jsonify({"error": "Invalid path"}), 400
            
        full_path = os.path.join(BASE_DIR, path.lstrip('/'))
        
        os.makedirs(full_path, exist_ok=True)
        return jsonify({"success": True, "path": path})
    except Exception as e:
        print(f"Mkdir Error: {str(e)}")
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
        
        # Security: prevent directory traversal
        if '..' in rel_path:
            return jsonify({"error": "Invalid path"}), 400

        target_path = os.path.join(BASE_DIR, rel_path.lstrip('/'))
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        if isinstance(config_data, str):
            with open(target_path, 'w') as f:
                f.write(config_data)
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
        
        # Security: prevent directory traversal
        if '..' in rel_path:
            return jsonify({"error": "Invalid path"}), 400

        target_path = os.path.join(BASE_DIR, rel_path.lstrip('/'))
        
        if os.path.exists(target_path):
            # Custom YAML loader to handle all tags safely
            class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
                pass
            
            def ignore_any_tag(loader, tag_suffix, node):
                return None

            def construct_include(loader, node):
                return loader.construct_scalar(node)
                
            SafeLoaderIgnoreUnknown.add_constructor('!include', construct_include)
            SafeLoaderIgnoreUnknown.add_multi_constructor('!', ignore_any_tag)

            with open(target_path, 'r') as f:
                return jsonify(yaml.load(f, Loader=SafeLoaderIgnoreUnknown))
        
        return jsonify({"error": f"Config file {rel_path} not found"}), 404
    except Exception as e:
        print(f"Load Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/schema')
def get_schema():
    schema_path = os.path.join(APP_DIR, 'esphome/custom_components/tile_ui/schema.json')
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Schema not found"}), 404

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
            shutil.copytree(source_lib, target_lib)
            
        # Update tile_ui without backup
        source_ui = os.path.join(APP_DIR, 'esphome/custom_components/tile_ui')
        target_ui = os.path.join(BASE_DIR, 'custom_components/tile_ui')
        
        if os.path.exists(source_ui):
            if os.path.exists(target_ui):
                shutil.rmtree(target_ui)
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(target_ui), exist_ok=True)
            shutil.copytree(source_ui, target_ui)
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Update Lib Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_directory_hashes(directory):
    if not os.path.exists(directory):
        return {}
    
    file_hashes = {}
    for root, dirs, files in os.walk(directory):
        dirs.sort() # Ensure deterministic traversal
        for file in sorted(files):
            if '_custom.' in file or '__pycache__' in root or file.endswith('.pyc'):
                continue
            path = os.path.join(root, file)
            try:
                with open(path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                    # Include relative path
                    rel_path = os.path.relpath(path, directory).replace('\\', '/')
                    file_hashes[rel_path] = file_hash
            except:
                pass
    return file_hashes

def get_directory_checksum(directory):
    hashes = get_directory_hashes(directory)
    if not hashes:
        return None
    # Create a deterministic string from sorted keys and values
    hash_list = [f"{k}:{v}" for k, v in sorted(hashes.items())]
    return hashlib.md5("".join(hash_list).encode()).hexdigest()

def get_diff(source_hashes, target_hashes):
    diff = []
    all_files = set(source_hashes.keys()) | set(target_hashes.keys())
    
    for f in sorted(all_files):
        if f not in source_hashes:
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
        
        source_ui = os.path.join(APP_DIR, 'esphome/custom_components/tile_ui')
        target_ui = os.path.join(BASE_DIR, 'custom_components/tile_ui')
        
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
        
        lib_synced = len(lib_diff) == 0
        ui_synced = len(ui_diff) == 0
        
        details = []
        if not lib_synced:
            details.append("Library files:")
            details.extend([f"  - {d}" for d in lib_diff])
        if not ui_synced:
            details.append("UI Component files:")
            details.extend([f"  - {d}" for d in ui_diff])

        return jsonify({
            "lib_synced": lib_synced,
            "ui_synced": ui_synced,
            "synced": lib_synced and ui_synced,
            "details": details
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/scripts')
def get_scripts():
    try:
        # Determine source directory once
        # Check BASE_DIR first (User config)
        source_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(source_dir):
            # Fallback to APP_DIR (Default lib)
            source_dir = os.path.join(APP_DIR, 'esphome/lib')
            
        lib_path = os.path.join(source_dir, 'lib.yaml')
        if not os.path.exists(lib_path):
            return jsonify({"error": f"lib.yaml not found in {source_dir}"}), 404

        # Custom YAML loader to handle !secret, !lambda, !include
        class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
            pass
        def ignore_unknown(loader, node):
            return None
        def ignore_any_tag(loader, tag_suffix, node):
            return None
            
        SafeLoaderIgnoreUnknown.add_constructor('!secret', ignore_unknown)
        SafeLoaderIgnoreUnknown.add_constructor('!lambda', ignore_unknown)
        SafeLoaderIgnoreUnknown.add_constructor('!include', ignore_unknown)
        SafeLoaderIgnoreUnknown.add_multi_constructor('!', ignore_any_tag)

        with open(lib_path, 'r') as f:
            doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}

        # Load lib_common.yaml from SAME directory if it exists
        common_lib_path = os.path.join(source_dir, 'lib_common.yaml')
        if os.path.exists(common_lib_path):
            try:
                with open(common_lib_path, 'r') as f:
                    common_doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}
                    
                    # Merge lists from common lib into main doc
                    for key in ['script', 'color', 'globals']:
                        if key in common_doc and isinstance(common_doc[key], list):
                            if key not in doc:
                                doc[key] = []
                            doc[key].extend(common_doc[key])
            except Exception as e:
                print(f"Error loading common lib: {e}")

        # Load custom lib from SAME directory if it exists
        custom_lib_path = os.path.join(source_dir, 'lib_custom.yaml')
        if os.path.exists(custom_lib_path):
            try:
                with open(custom_lib_path, 'r') as f:
                    custom_doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}
                    
                    # Merge lists from custom lib into main doc
                    for key in ['script', 'color', 'globals']:
                        if key in custom_doc and isinstance(custom_doc[key], list):
                            if key not in doc:
                                doc[key] = []
                            doc[key].extend(custom_doc[key])
            except Exception as e:
                print(f"Error loading custom lib: {e}")

        scripts = doc.get('script', [])
        
        # Standard colors
        colors = [
            {'id': 'Color(0, 0, 0)', 'value': '#000000'},
            {'id': 'Color(255, 255, 255)', 'value': '#FFFFFF'},
            {'id': 'Color(0, 0, 255)', 'value': '#FF0000'},
            {'id': 'Color(0, 255, 0)', 'value': '#00FF00'},
            {'id': 'Color(255, 0, 0)', 'value': '#0000FF'},
            {'id': 'Color(0, 255, 255)', 'value': '#FFFF00'},
            {'id': 'Color(0, 165, 255)', 'value': '#FFA500'},
            {'id': 'Color(128, 0, 128)', 'value': '#800080'},
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
        for base_file in ['3248s035_base.yaml', '2432s028_base.yaml']:
            base_path = os.path.join(source_dir, base_file)
            if os.path.exists(base_path):
                try:
                    with open(base_path, 'r') as f:
                        base_doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}
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

def monitor_activity():
    while True:
        time.sleep(60)
        if os.path.exists(EMULATOR_PID_FILE):
            if time.time() - last_activity_time > EMULATOR_TIMEOUT:
                print("Emulator timeout reached. Stopping...", flush=True)
                _stop_emulator_process()

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_activity, daemon=True)
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
