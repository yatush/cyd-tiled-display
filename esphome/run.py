#!/usr/bin/env python3
"""
Wrapper for `esphome run` / `esphome compile` that automatically
creates placeholder images and images.yaml declarations for any image
IDs referenced in tile_ui display_assets that aren't yet defined.

Usage (from the esphome/ directory):
    python3 run.py test_device.yaml                   # → esphome run test_device.yaml
    python3 run.py compile test_device.yaml           # → esphome compile test_device.yaml
    python3 run.py run test_device.yaml --device COM3 # any extra args are forwarded

Why this exists:
    ESPHome reads images.yaml *before* any Python hooks run, so placeholder
    images must be present prior to `esphome run`.  This script handles that
    in one step so you don't need the configurator just to do a CLI build.
"""

import os
import re
import struct
import sys
import zlib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
LIB_DIR     = os.path.join(SCRIPT_DIR, "lib")
IMAGES_DIR  = os.path.join(SCRIPT_DIR, "images")   # ESPHome resolves relative to device yaml
IMAGES_YAML = os.path.join(LIB_DIR, "images.yaml")
SECRETS_YAML = os.path.join(SCRIPT_DIR, "secrets.yaml")

# ---------------------------------------------------------------------------
# Minimal 1×1 transparent PNG
# ---------------------------------------------------------------------------

def _make_transparent_png() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(c[4:]) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1×1 RGBA
    idat = zlib.compress(bytes([0, 0, 0, 0, 0]))           # filter=0, RGBA=(0,0,0,0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )

# ---------------------------------------------------------------------------
# Loose YAML loader (ignores !include / !secret / other ESPHome tags)
# ---------------------------------------------------------------------------

def _load_yaml_loose(path: str) -> dict:
    import yaml

    class _Loader(yaml.SafeLoader):
        pass

    def _ignore(loader, tag_suffix, node):
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_scalar(node)

    def _include(loader, node):
        rel = loader.construct_scalar(node)
        base = (
            os.path.dirname(loader.stream.name)
            if hasattr(loader.stream, "name")
            else os.getcwd()
        )
        full = os.path.join(base, rel)
        if os.path.exists(full):
            return _load_yaml_loose(full) or {}
        return {}

    _Loader.add_constructor("!include", _include)
    _Loader.add_multi_constructor("!", _ignore)

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=_Loader) or {}
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# Collect image references from tile_ui screens
# ---------------------------------------------------------------------------

def _collect_image_refs(screens: list) -> set:
    """Return set of (img_id, rows, cols) from all display_assets entries."""
    refs = set()
    for screen in screens or []:
        if not isinstance(screen, dict):
            continue
        rows = int(screen.get("rows", 2))
        cols = int(screen.get("cols", 2))
        for tile_obj in screen.get("tiles") or []:
            if not isinstance(tile_obj, dict):
                continue
            for tdata in tile_obj.values():
                if not isinstance(tdata, dict):
                    continue
                for entry in tdata.get("display_assets") or []:
                    if not isinstance(entry, dict):
                        continue
                    img = entry.get("image")
                    if img and img != "none":
                        refs.add((img, rows, cols))
                    # Also check per-step image overrides inside animation
                    anim = entry.get("animation")
                    if isinstance(anim, dict):
                        for step in anim.get("steps") or []:
                            if isinstance(step, dict):
                                simg = step.get("image")
                                if simg and simg != "none":
                                    refs.add((simg, rows, cols))
    return refs

# ---------------------------------------------------------------------------
# Compute variant IDs (mirrors tile_generation.compute_image_variants)
# ---------------------------------------------------------------------------

def _compute_variant_ids(refs: set) -> dict:
    """Return (img_id, rows, cols) → variant_id.

    Falls back to the tile_ui module when available; otherwise uses a
    pure reimplementation so the script works without the full venv.
    """
    sys.path.insert(0, SCRIPT_DIR)
    # Build the screens list needed by compute_image_variants
    # (we synthesise minimal screen dicts from the refs set)
    from collections import defaultdict
    img_sizes: dict = defaultdict(set)
    for img_id, rows, cols in refs:
        img_sizes[img_id].add((rows, cols))

    variant_id = {}
    for iid, sizes in img_sizes.items():
        sorted_sizes = sorted(sizes)
        if len(sorted_sizes) == 1:
            r, c = sorted_sizes[0]
            variant_id[(iid, r, c)] = iid
        else:
            for r, c in sorted_sizes:
                variant_id[(iid, r, c)] = f"{iid}_r{r}c{c}"
    return variant_id

# ---------------------------------------------------------------------------
# images.yaml helpers
# ---------------------------------------------------------------------------

def _declared_ids(images_yaml_path: str) -> set:
    """Parse images.yaml and return set of values of `id:` keys."""
    ids = set()
    if not os.path.exists(images_yaml_path):
        return ids
    with open(images_yaml_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r"^\s+id:\s+(\S+)", line)
            if m:
                ids.add(m.group(1))
    return ids

def _images_yaml_has_image_key(content: str) -> bool:
    return bool(re.search(r"^image:", content, re.MULTILINE))

# ---------------------------------------------------------------------------
# Screen dimension detection
# ---------------------------------------------------------------------------

def _screen_dims(device_yaml: dict) -> tuple:
    """Guess screen W×H from the package device_base filename."""
    for v in (device_yaml.get("packages") or {}).values():
        if isinstance(v, str):
            if "3248s035" in v:
                return 480, 320
            if "2432s028" in v:
                return 320, 240
    return 480, 320  # safe default

# ---------------------------------------------------------------------------
# Main pre-processing step
# ---------------------------------------------------------------------------

def ensure_placeholder_images(device_yaml_path: str) -> "tuple[int, list[str]]":
    """
    Scan *device_yaml_path* for image references in tile_ui screens.
    For each image not yet declared in images.yaml:
      - create a PNG in images/ (real data from YAML or 1×1 placeholder)
      - append a declaration to lib/images.yaml

    Returns (num_added, list_of_newly_created_png_paths).
    """
    device_yaml = _load_yaml_loose(device_yaml_path)
    if not isinstance(device_yaml, dict):
        return 0

    # tile_ui may be inline or come from an included package
    tile_ui_conf = device_yaml.get("tile_ui") or {}
    screens = tile_ui_conf.get("screens") or []
    images_data = tile_ui_conf.get("images") or {}

    refs = _collect_image_refs(screens)
    if not refs:
        return 0, []

    declared = _declared_ids(IMAGES_YAML)
    screen_w, screen_h = _screen_dims(device_yaml)

    _TILE_PAD = 10
    _FIXED_PAD = 5

    variant_id = _compute_variant_ids(refs)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    import base64 as _b64
    new_decls: list[str] = []
    written: set = set()
    created_files: list[str] = []

    for (img_id, rows, cols), vid in sorted(variant_id.items()):
        if vid in declared:
            continue

        # --- determine PNG filename / data from the images dict when available ---
        img_entry = images_data.get(img_id) or {}
        filename = img_entry.get("filename", f"{img_id}.png")
        stem, _ = os.path.splitext(os.path.basename(filename))
        png_name = f"{stem}.png"
        png_path = os.path.join(IMAGES_DIR, png_name)
        img_type = img_entry.get("type", "RGB565")
        img_data_b64 = img_entry.get("data", "")

        if not os.path.exists(png_path) and png_name not in written:
            if img_data_b64:
                with open(png_path, "wb") as f:
                    f.write(_b64.b64decode(img_data_b64))
                print(f"  [run.py] Extracted image     images/{png_name}")
            else:
                with open(png_path, "wb") as f:
                    f.write(_make_transparent_png())
                print(f"  [run.py] Created placeholder  images/{png_name}")
            written.add(png_name)
            created_files.append(png_path)

        # --- compute resize target for this tile grid ---
        tile_w = (screen_w - (cols + 1) * _TILE_PAD) // cols
        tile_h = (screen_h - (rows + 1) * _TILE_PAD) // rows
        img_w  = max(8, tile_w - _FIXED_PAD * 2)
        img_h  = max(8, tile_h - _FIXED_PAD * 2)

        if img_type == "RGBA":
            type_lines = "    type: RGB\n    transparency: alpha_channel"
        else:
            type_lines = f"    type: {img_type}"

        new_decls.append(
            f"  - file: images/{png_name}\n"
            f"    id: {vid}\n"
            f"    resize: {img_w}x{img_h}\n"
            f"{type_lines}"
        )
        declared.add(vid)

    if not new_decls:
        return 0, created_files

    # --- ensure none_transparent base entry exists ---
    none_path = _ensure_none_transparent()
    if none_path:
        created_files.append(none_path)

    # --- read current images.yaml ---
    content = ""
    if os.path.exists(IMAGES_YAML):
        with open(IMAGES_YAML, "r", encoding="utf-8") as f:
            content = f.read().rstrip("\n")

    if not _images_yaml_has_image_key(content):
        # Fresh/empty images.yaml (e.g. just `{}` or blank)
        content = "image:"

    updated = content + "\n" + "\n".join(new_decls) + "\n"
    os.makedirs(os.path.dirname(IMAGES_YAML), exist_ok=True)
    with open(IMAGES_YAML, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"  [run.py] Updated lib/images.yaml — added {len(new_decls)} declaration(s)")
    return len(new_decls), created_files


def _ensure_none_transparent() -> "str | None":
    """Guarantee that none_transparent.png and its images.yaml entry exist.
    Returns the path of the PNG if it was newly created, else None."""
    png_path = os.path.join(IMAGES_DIR, "none_transparent.png")
    png_created: "str | None" = None
    if not os.path.exists(png_path):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        with open(png_path, "wb") as f:
            f.write(_make_transparent_png())
        png_created = png_path

    os.makedirs(LIB_DIR, exist_ok=True)
    ids = _declared_ids(IMAGES_YAML)
    if "none_transparent" not in ids:
        existing = ""
        if os.path.exists(IMAGES_YAML):
            with open(IMAGES_YAML, "r", encoding="utf-8") as f:
                existing = f.read().rstrip("\n")
        if not _images_yaml_has_image_key(existing):
            existing = "image:"
        decl = (
            "  - file: images/none_transparent.png\n"
            "    id: none_transparent\n"
            "    resize: 8x8\n"
            "    type: RGB\n"
            "    transparency: alpha_channel"
        )
        with open(IMAGES_YAML, "w", encoding="utf-8") as f:
            f.write(existing + "\n" + decl + "\n")

    return png_created


def _ensure_secrets(device_yaml_path: str):
    """Create a placeholder secrets.yaml next to the device YAML if missing."""
    secrets_path = os.path.join(os.path.dirname(device_yaml_path), "secrets.yaml")
    if os.path.exists(secrets_path):
        return

    # Find which secrets the config actually references
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
        f.write("# Auto-generated placeholder secrets — replace with real values\n")
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

    # Determine the device YAML path from args
    # Supported patterns:
    #   run.py test_device.yaml [extra...]
    #   run.py run test_device.yaml [extra...]
    #   run.py compile test_device.yaml [extra...]
    known_cmds = {
        "run", "compile", "upload", "logs", "clean",
        "version", "dashboard", "config", "wizard",
    }

    esphome_cmd = "run"              # default sub-command
    device_yaml_arg: str | None = None

    for a in args:
        if a in known_cmds:
            esphome_cmd = a
        elif a.endswith(".yaml") and not a.startswith("-"):
            device_yaml_arg = a
            break

    # Resolve device YAML to an absolute path
    device_yaml_path: str | None = None
    if device_yaml_arg:
        for base in [os.getcwd(), SCRIPT_DIR]:
            candidate = os.path.join(base, device_yaml_arg)
            if os.path.exists(candidate):
                device_yaml_path = candidate
                break

    # --- save original images.yaml so we can restore it after esphome exits ---
    original_images_yaml: "str | None" = None
    if os.path.exists(IMAGES_YAML):
        with open(IMAGES_YAML, "r", encoding="utf-8") as f:
            original_images_yaml = f.read()

    created_files: list[str] = []

    # --- pre-processing ---
    if device_yaml_path:
        print(f"[run.py] Pre-processing {device_yaml_arg} ...")
        _ensure_secrets(device_yaml_path)
        added, created_files = ensure_placeholder_images(device_yaml_path)
        if added:
            print(f"[run.py] {added} image(s) added — re-run is not needed.")
        else:
            print("[run.py] images.yaml up to date.")
    else:
        if device_yaml_arg:
            print(f"[run.py] Warning: could not find '{device_yaml_arg}' — skipping pre-processing.")

    # --- build final esphome command ---
    # Insert the sub-command before the positional args when it came from our default
    if args[0] not in known_cmds:
        esphome_args = ["esphome", esphome_cmd] + args
    else:
        esphome_args = ["esphome"] + args

    print(f"[run.py] Running: {' '.join(esphome_args)}\n")
    import subprocess
    try:
        result = subprocess.run(esphome_args)
    finally:
        # --- cleanup: remove created files and restore images.yaml ---
        for path in created_files:
            try:
                os.remove(path)
            except OSError:
                pass
        if original_images_yaml is not None:
            with open(IMAGES_YAML, "w", encoding="utf-8") as f:
                f.write(original_images_yaml)
        elif os.path.exists(IMAGES_YAML):
            os.remove(IMAGES_YAML)
        if created_files or original_images_yaml is not None:
            print("\n[run.py] Cleaned up temporary images and restored lib/images.yaml.")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
