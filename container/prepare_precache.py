#!/usr/bin/env python3
"""
Prepare pre-cache assets from test_device.yaml.

Reads the tile_ui section from test_device.yaml, then:
  1. Writes lib/test_device_tiles.yaml  – the tiles_file used for both
     pre-cache ESPHome compiles.
  2. Writes lib/images.yaml and lib/images/*.png  – ESPHome image
     declarations with resized PNGs so the compile resolves image IDs.

Called by vnc_startup.sh before the emulator pre-compilation loop.
"""

import os
import sys
import yaml

# ── Paths (absolute so the script works from any working directory) ──────────
# In the Docker container the script is deployed as /app/prepare_precache.py
# (same directory as toolchain_setup.py).  During development it lives in
# docker_debug/ inside the repo.  We detect which environment we're in so
# the correct esphome/ and configurator/ directories are resolved.
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))

# Docker layout:  /app/prepare_precache.py   → APP_DIR = /app
# Dev layout:     .../container/prepare_precache.py  → APP_DIR = repo root
if os.path.isdir(os.path.join(_SCRIPT_DIR, 'esphome')):
    APP_DIR = _SCRIPT_DIR                          # Docker: /app
else:
    APP_DIR = os.path.dirname(_SCRIPT_DIR)         # Dev: repo root

ESPHOME_DIR  = os.path.join(APP_DIR, 'esphome')
LIB_DIR      = os.path.join(ESPHOME_DIR, 'lib')
IMAGES_DIR   = os.path.join(LIB_DIR, 'images')
TEST_DEVICE  = os.path.join(ESPHOME_DIR, 'test_device.yaml')
TILES_FILE   = os.path.join(LIB_DIR, 'test_device_tiles.yaml')
IMAGES_YAML  = os.path.join(LIB_DIR, 'images.yaml')

# The generate_tiles_api module lives in /app/configurator
sys.path.insert(0, os.path.join(APP_DIR, 'configurator'))

def _extract_tile_ui(path: str) -> dict:
    """Return the parsed tile_ui dict from an ESPHome YAML file.

    Standard yaml.safe_load cannot handle ESPHome-specific tags such as
    !include or !secret.  Those tags only appear in the top-level ESPHome
    stanzas; the tile_ui: block itself is plain YAML.  We therefore locate
    the tile_ui: top-level key by scanning for it as a line starting at
    column 0, then parse only from that point onward.
    """
    with open(path, 'r') as fh:
        lines = fh.readlines()

    start = next(
        (i for i, l in enumerate(lines) if l.startswith('tile_ui:')),
        None,
    )
    if start is None:
        raise RuntimeError(f"No top-level 'tile_ui:' key found in {path}")

    section_text = ''.join(lines[start:])
    return yaml.safe_load(section_text).get('tile_ui', {})


def run(screen_w: int = 480, screen_h: int = 320) -> bool:
    """Generate test_device_tiles.yaml, images.yaml, and image PNGs.

    Returns True on success.  Failures are printed but not raised so that
    the caller (vnc_startup.sh) can continue gracefully with ``|| true``.
    """
    print(f"[prepare_precache] Reading tile_ui from {TEST_DEVICE}")
    try:
        tile_ui = _extract_tile_ui(TEST_DEVICE)
    except Exception as exc:
        print(f"[prepare_precache] ERROR extracting tile_ui: {exc}")
        return False

    screens          = tile_ui.get('screens', [])
    images           = tile_ui.get('images', {})
    dynamic_entities = tile_ui.get('dynamic_entities', [])

    if not screens:
        print("[prepare_precache] WARNING: no screens found in tile_ui config")

    # ── 1. Write test_device_tiles.yaml ──────────────────────────────────────
    tiles_config = {
        'screens':          screens,
        'dynamic_entities': dynamic_entities,
        # images are NOT read from tiles_file by the tile_ui component, but
        # including them is harmless and keeps the file self-documenting.
        'images':           images,
    }
    os.makedirs(LIB_DIR, exist_ok=True)
    with open(TILES_FILE, 'w') as fh:
        yaml.dump(tiles_config, fh, default_flow_style=False, allow_unicode=True)
    print(f"[prepare_precache] Wrote {TILES_FILE}")

    # ── 2. Generate images.yaml + PNG files via generate_tiles_api ───────────
    try:
        from generate_tiles_api import generate_cpp_from_yaml  # type: ignore
    except ImportError as exc:
        print(f"[prepare_precache] ERROR importing generate_tiles_api: {exc}")
        return False

    # Build the tiles-file-format input_data (screens + images at top level,
    # same layout the server passes to generate_cpp_from_yaml).
    input_data = yaml.dump(
        {'screens': screens, 'images': images, 'dynamic_entities': dynamic_entities},
        default_flow_style=False,
        allow_unicode=True,
    )

    print(f"[prepare_precache] Generating images.yaml for {screen_w}x{screen_h}")
    result = generate_cpp_from_yaml(
        input_data,
        user_lib_dir=LIB_DIR,
        images_dir=IMAGES_DIR,
        screen_w=screen_w,
        screen_h=screen_h,
    )

    if not result.get('success'):
        print(f"[prepare_precache] ERROR from generate_cpp_from_yaml: {result.get('error')}")
        return False

    images_yaml_content = result.get('images_yaml', '')
    with open(IMAGES_YAML, 'w') as fh:
        fh.write(images_yaml_content if images_yaml_content else '# no images\n')
    print(f"[prepare_precache] Wrote {IMAGES_YAML}")
    return True


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
