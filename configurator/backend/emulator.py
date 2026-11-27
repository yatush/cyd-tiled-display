import os
import json
import time
import signal
import socket
import shutil
import threading
import subprocess
import yaml
from flask import Blueprint, request, jsonify, send_from_directory
from api_proxy import run_proxy_thread
from backend.state import (
    APP_DIR,
    BASE_DIR,
    IS_ADDON,
    SUPERVISOR_TOKEN,
    _DEVICE_CONFIG,
    _DEFAULT_DEVICE,
    _GENERATE_SCRIPT,
    _run_generate_subprocess,
    get_session_id,
)

emulator_bp = Blueprint('emulator', __name__)

emulator_lock = threading.RLock()  # RLock allows re-entrant locking
emulator_state = None  # dict when running, None when stopped

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

@emulator_bp.route('/api/emulator/start', methods=['POST'])
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

@emulator_bp.route('/api/emulator/stop', methods=['POST'])
def stop_emulator():
    _stop_emulator()
    return jsonify({"status": "stopped"})


@emulator_bp.route('/api/debug/emulator', methods=['GET'])
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

@emulator_bp.route('/api/emulator/status', methods=['GET'])
def emulator_status():
    with emulator_lock:
        if emulator_state and is_process_running(emulator_state.get('pid')):
            return jsonify({"status": "running"})
    return jsonify({"status": "stopped"})

@emulator_bp.route('/api/emulator/logs', methods=['GET'])
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


@emulator_bp.route('/novnc/<path:path>')
def serve_novnc(path):
    novnc_dir = os.path.join(APP_DIR, 'novnc')
    return send_from_directory(novnc_dir, path)

# Proxy websocket requests to internal websockify (port 6081)
# This is needed for Cloud Run where we can only expose one port
@emulator_bp.route('/websockify')
def websockify_proxy():
    # This won't work for actual websocket upgrade - we need a different approach
    # Return info for debugging
    return jsonify({"error": "Websocket proxy - this endpoint requires websocket upgrade"}), 400

