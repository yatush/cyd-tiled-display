#!/usr/bin/env python3
"""
Wrapper for `esphome run` / `esphome compile` that handles small setup tasks
then forwards all arguments to esphome unchanged.

Usage (from the esphome/ directory):
    python3 run.py test_device.yaml                   # -> esphome run test_device.yaml
    python3 run.py compile test_device.yaml           # -> esphome compile test_device.yaml
    python3 run.py run test_device.yaml --device COM3 # any extra args are forwarded

Why this exists:
    Ensures none_transparent.png is present in images/ (it is declared inline in
    lib_common.yaml so it must exist before esphome reads the config) and creates
    a placeholder secrets.yaml when needed.  Tile images are registered at codegen
    time by tile_ui's _register_images -- no pre-processing of images.yaml required.
"""

import os
import re
import struct
import sys
import zlib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR   = os.path.join(SCRIPT_DIR, "images")
SECRETS_YAML = os.path.join(SCRIPT_DIR, "secrets.yaml")

# ---------------------------------------------------------------------------
# Minimal 1x1 transparent PNG
# ---------------------------------------------------------------------------

def _make_transparent_png() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(c[4:]) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1 RGBA
    idat = zlib.compress(bytes([0, 0, 0, 0, 0]))           # filter=0, RGBA=(0,0,0,0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def _ensure_none_transparent():
    """Create images/none_transparent.png if it doesn't exist.

    lib_common.yaml references this file directly, so it must exist before
    ESPHome parses the config (before any Python codegen hooks run).
    """
    png_path = os.path.join(IMAGES_DIR, "none_transparent.png")
    if not os.path.exists(png_path):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        with open(png_path, "wb") as f:
            f.write(_make_transparent_png())
        print(f"  [run.py] Created  images/none_transparent.png")


def _ensure_secrets(device_yaml_path: str):
    """Create a placeholder secrets.yaml next to the device YAML if missing."""
    secrets_path = os.path.join(os.path.dirname(device_yaml_path), "secrets.yaml")
    if os.path.exists(secrets_path):
        return

    refs: set[str] = set()
    try:
        with open(device_yaml_path, "r", encoding="utf-8") as f:
            raw = f.read()
        for inc_path in re.findall(r"!include\s+(\S+)", raw):
            full = os.path.join(os.path.dirname(device_yaml_path), inc_path)
            if os.path.exists(full):
                with open(full, "r", encoding="utf-8") as f:
                    raw += f.read()
        refs = set(re.findall(r"!secret\s+(\S+)", raw))
    except Exception:
        refs = {"wifi_ssid", "wifi_password"}

    if not refs:
        return

    lines = [f'{k}: "placeholder"' for k in sorted(refs)]
    with open(secrets_path, "w", encoding="utf-8") as f:
        f.write("# Auto-generated placeholder secrets -- replace with real values\n")
        f.write("\n".join(lines) + "\n")
    print(f"  [run.py] Created placeholder  secrets.yaml ({', '.join(sorted(refs))})")
    print("  [run.py] Edit secrets.yaml to set your real WiFi credentials before flashing.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    known_cmds = {
        "run", "compile", "upload", "logs", "clean",
        "version", "dashboard", "config", "wizard",
    }

    esphome_cmd = "run"
    device_yaml_arg: str | None = None

    for a in args:
        if a in known_cmds:
            esphome_cmd = a
        elif a.endswith(".yaml") and not a.startswith("-"):
            device_yaml_arg = a
            break

    device_yaml_path: str | None = None
    if device_yaml_arg:
        for base in [os.getcwd(), SCRIPT_DIR]:
            candidate = os.path.join(base, device_yaml_arg)
            if os.path.exists(candidate):
                device_yaml_path = candidate
                break

    # --- pre-processing ---
    _ensure_none_transparent()

    if device_yaml_path:
        _ensure_secrets(device_yaml_path)
    elif device_yaml_arg:
        print(f"[run.py] Warning: could not find '{device_yaml_arg}' -- skipping secrets check.")

    # --- build final esphome command ---
    if args[0] not in known_cmds:
        esphome_args = ["esphome", esphome_cmd] + args
    else:
        esphome_args = ["esphome"] + args

    print(f"[run.py] Running: {' '.join(esphome_args)}\n")
    import subprocess
    result = subprocess.run(esphome_args)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
