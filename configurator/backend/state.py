import os
import sys
import re
import json
import subprocess
from pathlib import Path
import yaml
from flask import request
import generate_tiles_api

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
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../esphome'))

# APP_DIR: Where the application code lives (e.g. /app)
if os.path.exists('/app'):
    APP_DIR = '/app'
else:
    # Local fallback: use the parent directory (repo root)
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

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

_GENERATE_SCRIPT = os.path.join(os.path.dirname(__file__), '../generate_tiles_api.py')

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


def get_session_id():
    sid = request.headers.get('X-Session-Id', 'default')
    return sid


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


def is_headless_hub_yaml(parsed, raw_text=''):
    """Return True if a parsed ESPHome YAML represents a headless BLE hub."""
    if not isinstance(parsed, dict):
        return False
    packages = parsed.get('packages')
    if isinstance(packages, dict):
        for val in packages.values():
            if isinstance(val, str) and 'headless_hub_base.yaml' in val:
                return True
    bridge = parsed.get('espnow_fan_bridge')
    if isinstance(bridge, dict) and str(bridge.get('role') or '').lower() == 'hub':
        return True
    if raw_text and 'headless_hub_base.yaml' in raw_text:
        return True
    return False


_CACHED_SHELLY_KNOWN_NAMES = {}
