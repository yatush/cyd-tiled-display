import os
import re
import json
import time
import shutil
import signal
import socket
import threading
import subprocess
import concurrent.futures
from pathlib import Path
import yaml
import requests
from flask import Blueprint, request, jsonify, send_from_directory
import generate_tiles_api
from backend.state import (
    APP_DIR,
    BASE_DIR,
    HA_URL,
    IS_ADDON,
    SUPERVISOR_TOKEN,
    _DEVICE_CONFIG,
    _DEFAULT_DEVICE,
    _resolve_safe_path,
    get_session_id,
    is_headless_hub_yaml,
)

esphome_bp = Blueprint('esphome_builds', __name__)

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

    # Check for headless BLE hub (includes lib/headless_hub_base.yaml which configures OTA)
    is_headless_hub = is_headless_hub_yaml(data, content)
    if is_headless_hub:
        is_device_config = True

    # Check for tile_ui section (CYD-specific marker) — detected during line scan above
    if has_tile_ui:
        is_device_config = True
        is_cyd = True

    # Check for OTA section (required for wireless OTA updates)
    ota_section = data.get('ota')
    has_ota = has_ota_line or is_headless_hub or (ota_section is not None and ota_section is not False)

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
        'is_headless_hub': is_headless_hub,
        'has_ota': has_ota,
    }


def _classify_batch_device(meta, online):
    """Classify a discovered ESPHome device for batch OTA update."""
    if not (meta.get('is_cyd') or meta.get('is_headless_hub')):
        return ('skipped', 'Not a CYD or BLE Hub configuration — no update needed')
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


@esphome_bp.route('/api/esphome/devices', methods=['GET'])
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


@esphome_bp.route('/api/esphome/devices/ping', methods=['POST'])
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


@esphome_bp.route('/api/ha/timezone')
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


@esphome_bp.route('/api/esphome/install', methods=['POST'])
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
        _inject_esphome_idf_tools_path(_install_env)
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


@esphome_bp.route('/api/esphome/install/status')
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


@esphome_bp.route('/api/esphome/install/cancel', methods=['POST'])
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


def _inject_esphome_idf_tools_path(env):
    """Ensure ESPHome 2026.11+ native ESP-IDF compiler bin dirs (xtensa/riscv32) are on PATH.

    In HA add-on mode /root/.cache/esphome/idf is symlinked to /data/.platformio/esphome_idf.
    Explicitly setting IDF_TOOLS_PATH and adding any installed tool bin dirs to PATH prevents
    CMake 'xtensa-esp32-elf-gcc is not a full path and was not found in the PATH' errors.
    """
    import glob as _glob

    idf_roots = ['/root/.cache/esphome/idf', '/data/.platformio/esphome_idf']
    if os.path.isdir('/root/.cache/esphome/idf'):
        env.setdefault('IDF_TOOLS_PATH', '/root/.cache/esphome/idf')

    extra_bins = []
    seen = set()
    for root in idf_roots:
        tools_dir = os.path.join(root, 'tools')
        if not os.path.isdir(tools_dir):
            continue
        for pattern in (
            os.path.join(tools_dir, '*', '*', '*', 'bin'),
            os.path.join(tools_dir, '*', '*', 'bin'),
            os.path.join(tools_dir, '*', '*'),
        ):
            for candidate in sorted(_glob.glob(pattern)):
                if not os.path.isdir(candidate):
                    continue
                real = os.path.realpath(candidate)
                if real in seen:
                    continue
                if os.path.basename(candidate) == 'bin' or any(
                    os.path.isfile(os.path.join(candidate, tool))
                    for tool in ('xtensa-esp32-elf-gcc', 'riscv32-esp-elf-gcc', 'ninja', 'cmake')
                ):
                    seen.add(real)
                    extra_bins.append(candidate)
        if extra_bins:
            break

    if extra_bins:
        cur_path = env.get('PATH', '')
        parts = cur_path.split(':') if cur_path else []
        if parts and parts[0] == '/usr/local/lib/ccache':
            env['PATH'] = ':'.join([parts[0]] + extra_bins + parts[1:])
        else:
            env['PATH'] = ':'.join(extra_bins + parts)
    return env


def _build_esphome_env():
    """Return an environment dict configured with ccache + ESP-IDF tools for fast ESPHome compiles."""
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
    return _inject_esphome_idf_tools_path(env)


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

        # 2. Classify non-CYD/Hub / non-OTA immediately, ping managed+OTA devices in parallel
        to_ping = []
        for idx, d in enumerate(state['devices']):
            if not (d.get('is_cyd') or d.get('is_headless_hub')) or not d.get('has_ota'):
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


@esphome_bp.route('/api/esphome/batch_update/start', methods=['POST'])
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


@esphome_bp.route('/api/esphome/batch_update/status', methods=['GET'])
def get_batch_update_status():
    """Return the current or most recent batch OTA update state."""
    include_logs = request.args.get('include_logs')
    with batch_update_lock:
        if not batch_update_state:
            return jsonify({'phase': 'idle', 'devices': [], 'summary': _batch_summary([])})
        return jsonify(_serialize_batch_state(batch_update_state, include_logs=include_logs))


@esphome_bp.route('/api/esphome/batch_update/cancel', methods=['POST'])
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

@esphome_bp.route('/api/esphome/wifi', methods=['GET'])
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


@esphome_bp.route('/api/esphome/wifi', methods=['POST'])
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

@esphome_bp.route('/api/esphome/compile', methods=['POST'])
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
        _inject_esphome_idf_tools_path(env)

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


@esphome_bp.route('/api/esphome/compile/status')
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


@esphome_bp.route('/api/esphome/compile/cancel', methods=['POST'])
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


@esphome_bp.route('/api/esphome/compile/cleanup', methods=['POST'])
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


@esphome_bp.route('/api/esphome/firmware/<device_name>/manifest.json')
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


@esphome_bp.route('/api/esphome/firmware/<device_name>/<filename>')
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

