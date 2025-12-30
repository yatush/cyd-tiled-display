import os
import json
import subprocess
import yaml
from flask import Flask, request, send_from_directory, jsonify
import requests

app = Flask(__name__, static_folder='dist')

# Configuration from environment (provided by HA Supervisor)
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
if not SUPERVISOR_TOKEN:
    print("WARNING: SUPERVISOR_TOKEN is not set. API calls will fail.")

HA_URL = "http://supervisor/core"

MOCK_ENTITIES = [
    {"entity_id": "mock.light_living_room", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
    {"entity_id": "mock.switch_coffee_maker", "state": "off", "attributes": {"friendly_name": "Coffee Maker"}},
    {"entity_id": "mock.sensor_temperature", "state": "22.5", "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "°C"}},
    {"entity_id": "mock.binary_sensor_front_door", "state": "off", "attributes": {"friendly_name": "Front Door"}},
    {"entity_id": "mock.media_player_tv", "state": "playing", "attributes": {"friendly_name": "TV"}},
    {"entity_id": "mock.climate_living_room", "state": "heat", "attributes": {"friendly_name": "Climate"}},
    {"entity_id": "mock.cover_garage_door", "state": "closed", "attributes": {"friendly_name": "Garage Door"}},
]

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

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
            
        return (response.content, response.status_code, response.headers.items())
    except requests.exceptions.RequestException as e:
        print(f"HA Proxy Connection Error: {str(e)}")
        return jsonify({"error": f"Could not connect to Home Assistant: {str(e)}"}), 502
    except Exception as e:
        print(f"HA Proxy Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        script_path = '/app/generate_tiles_api.py'
        
        if not os.path.exists(script_path):
            print(f"ERROR: Script not found at {script_path}", flush=True)
            return jsonify({"error": f"Script not found at {script_path}"}), 500

        # Run the existing generation script
        process = subprocess.Popen(
            ['python3', script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/app' # Ensure CWD is correct for relative imports
        )
        stdout, stderr = process.communicate(input=request.get_data(as_text=True))
        
        if process.returncode != 0:
            print(f"Generation Error: {stderr}", flush=True)
            return jsonify({"error": stderr or "Generation failed"}), 500
            
        return stdout, 200, {'Content-Type': 'application/json'}
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
        
        base_dir = "/config/esphome"
        if not os.path.exists(base_dir):
            # Ensure base dir exists
            os.makedirs(base_dir, exist_ok=True)
            
        full_path = os.path.join(base_dir, path.lstrip('/'))
        
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
                    "path": os.path.relpath(item_path, base_dir).replace('\\', '/')
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
            
        base_dir = "/config/esphome"
        full_path = os.path.join(base_dir, path.lstrip('/'))
        
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
        # path is relative to /config/esphome
        rel_path = data.get('path', 'monitor_config/tiles.yaml')
        
        # Security: prevent directory traversal
        if '..' in rel_path:
            return jsonify({"error": "Invalid path"}), 400

        base_dir = "/config/esphome"
        target_path = os.path.join(base_dir, rel_path.lstrip('/'))
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, 'w') as f:
            yaml.dump(config_data, f, sort_keys=False)
            
        return jsonify({"success": True, "path": rel_path})
    except Exception as e:
        print(f"Save Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/load', methods=['GET'])
def load_config():
    try:
        # path is relative to /config/esphome
        rel_path = request.args.get('path', 'monitor_config/tiles.yaml')
        
        # Security: prevent directory traversal
        if '..' in rel_path:
            return jsonify({"error": "Invalid path"}), 400

        base_dir = "/config/esphome"
        target_path = os.path.join(base_dir, rel_path.lstrip('/'))
        
        if os.path.exists(target_path):
            with open(target_path, 'r') as f:
                return jsonify(yaml.safe_load(f))
        
        return jsonify({"error": f"Config file {rel_path} not found"}), 404
    except Exception as e:
        print(f"Load Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/schema')
def get_schema():
    schema_path = '/app/esphome/custom_components/tile_ui/schema.json'
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Schema not found"}), 404

@app.route('/api/scripts')
def get_scripts():
    # This replicates the logic from vite.config.ts
    try:
        lib_path = '/app/esphome/lib/lib.yaml'
        if not os.path.exists(lib_path):
            return jsonify({"error": "lib.yaml not found"}), 404

        # Custom YAML loader to handle !secret, !lambda, !include
        class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
            pass
        def ignore_unknown(loader, node):
            return None
        SafeLoaderIgnoreUnknown.add_constructor('!secret', ignore_unknown)
        SafeLoaderIgnoreUnknown.add_constructor('!lambda', ignore_unknown)
        SafeLoaderIgnoreUnknown.add_constructor('!include', ignore_unknown)

        with open(lib_path, 'r') as f:
            doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}

        scripts = doc.get('script', [])
        
        # Standard colors
        colors = [
            {'id': 'Color::BLACK', 'value': '#000000'},
            {'id': 'Color::WHITE', 'value': '#FFFFFF'},
            {'id': 'Color::RED', 'value': '#FF0000'},
            {'id': 'Color::GREEN', 'value': '#00FF00'},
            {'id': 'Color::BLUE', 'value': '#0000FF'},
            {'id': 'Color::YELLOW', 'value': '#FFFF00'},
            {'id': 'Color::ORANGE', 'value': '#FFA500'},
            {'id': 'Color::PURPLE', 'value': '#800080'},
        ]

        # Add custom colors from lib.yaml
        for c in doc.get('color', []):
            value = '#000000'
            if 'hex' in c:
                hex_val = c['hex'].replace('#', '')
                if len(hex_val) == 6:
                    # BGR to RGB conversion as in vite.config.ts
                    r, g, b = hex_val[4:6], hex_val[2:4], hex_val[0:2]
                    value = f"#{r}{g}{b}"
                else:
                    value = f"#{hex_val}"
            elif all(k in c for k in ('red', 'green', 'blue')):
                # Simplified RGB handling
                value = f"rgb({c['red']}, {c['green']}, {c['blue']})"
            colors.append({'id': c['id'], 'value': value})

        # Fonts from base file
        fonts = []
        base_path = '/app/esphome/lib/3248s035_base.yaml'
        if os.path.exists(base_path):
            with open(base_path, 'r') as f:
                base_doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown) or {}
                fonts = [f['id'] for f in base_doc.get('font', [])]

        # Icons from mdi_glyphs.yaml
        icons = []
        glyphs_path = '/app/esphome/lib/mdi_glyphs.yaml'
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

        display_scripts = []
        action_scripts = []

        for s in scripts:
            if 'id' in s:
                if s['id'].startswith('tile_'):
                    params = s.get('parameters', {})
                    param_list = [
                        {'name': k, 'type': v}
                        for k, v in params.items()
                        if k not in ('x', 'y', 'entities')
                    ]
                    display_scripts.append({'id': s['id'], 'params': param_list})
                else:
                    action_scripts.append(s['id'])

        globals_list = [
            g['id'] for g in doc.get('globals', [])
            if g.get('type') == 'bool'
        ]

        return jsonify({
            "display": display_scripts,
            "action": action_scripts,
            "colors": colors,
            "fonts": fonts,
            "icons": icons,
            "globals": globals_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
