import sys
import os
import yaml
import json
from pathlib import Path

# Add the external_components directory to sys.path so we can import tile_ui
repo_root = Path(__file__).parent.parent
tile_ui_path = repo_root / "esphome" / "external_components"
user_components = os.environ.get("CYD_COMPONENTS_DIR")
if user_components and (Path(user_components) / "tile_ui" / "__init__.py").is_file():
    sys.path.insert(0, user_components)
else:
    sys.path.append(str(tile_ui_path))

# Mock esphome module if not installed to allow standalone import of tile_ui
if 'esphome' not in sys.modules:
    class MockEsphome:
        def __getattr__(self, name):
            return MockEsphome()
        def __call__(self, *args, **kwargs):
            return MockEsphome()

    try:
        from voluptuous import Invalid as _Invalid
    except ImportError:
        class _Invalid(Exception):
            pass

    class _MockConfigValidation(MockEsphome):
        Invalid = _Invalid

        def string(self, value):
            if not isinstance(value, str):
                raise _Invalid(f"Expected string, got {type(value).__name__}")
            return value

        def boolean(self, value):
            if not isinstance(value, bool):
                raise _Invalid(f"Expected boolean, got {type(value).__name__}")
            return value

    _mock_esphome = MockEsphome()
    _mock_cv = _MockConfigValidation()
    _mock_esphome.config_validation = _mock_cv
    sys.modules['esphome'] = _mock_esphome
    sys.modules['esphome.codegen'] = MockEsphome()
    sys.modules['esphome.config_validation'] = _mock_cv
    sys.modules['esphome.const'] = MockEsphome()
    sys.modules['esphome.core'] = MockEsphome()
    sys.modules['esphome.components'] = MockEsphome()
    sys.modules['esphome.components.display'] = MockEsphome()

try:
    from tile_ui import generate_init_tiles_cpp
    from tile_ui.validation import validate_tiles_config
    from tile_ui.data_collection import collect_available_scripts, collect_available_globals
except ImportError as e:
    print(json.dumps({"error": f"Failed to import tile_ui: {e}"}))
    sys.exit(1)


def create_safe_yaml_loader(include_base_dir=None):
    """Create a yaml.SafeLoader subclass that safely handles ESPHome YAML tags (!secret, !lambda, !include)."""
    base_path = Path(include_base_dir) if include_base_dir else None

    class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
        pass

    def _ignore_unknown(loader, node):
        return None

    def _ignore_any_tag(loader, tag_suffix, node):
        return None

    def _include_constructor(loader, node):
        filename = loader.construct_scalar(node)
        if base_path is not None:
            include_path = base_path / filename
            if include_path.exists():
                with open(include_path, 'r', encoding='utf-8', errors='replace') as f_inc:
                    return yaml.load(f_inc, Loader=SafeLoaderIgnoreUnknown)
            return None
        return filename

    SafeLoaderIgnoreUnknown.add_constructor('!secret', _ignore_unknown)
    SafeLoaderIgnoreUnknown.add_constructor('!lambda', _ignore_unknown)
    SafeLoaderIgnoreUnknown.add_constructor('!include', _include_constructor)
    SafeLoaderIgnoreUnknown.add_multi_constructor('!', _ignore_any_tag)
    return SafeLoaderIgnoreUnknown


def load_merged_lib_doc(user_lib_dir=None, fallback_lib_dir=None, merge_keys=('script', 'globals', 'color')):
    """Load lib.yaml and merge lib_common.yaml, lib_custom.yaml, and ble_proxy.yaml."""
    default_lib_dir = Path(fallback_lib_dir) if fallback_lib_dir else (repo_root / "esphome" / "lib")
    if user_lib_dir and (Path(user_lib_dir) / "lib.yaml").exists():
        lib_path = Path(user_lib_dir) / "lib.yaml"
    else:
        lib_path = default_lib_dir / "lib.yaml"

    if not lib_path.exists():
        return None

    loader_cls = create_safe_yaml_loader(include_base_dir=lib_path.parent)
    with open(lib_path, 'r', encoding='utf-8', errors='replace') as f:
        lib_doc = yaml.load(f, Loader=loader_cls) or {}

    if not isinstance(lib_doc, dict):
        return {}

    for extra_name in ('lib_common.yaml', 'lib_custom.yaml', 'ble_proxy.yaml'):
        candidates = []
        if extra_name in ('lib_custom.yaml', 'ble_proxy.yaml') and user_lib_dir:
            candidates.append(Path(user_lib_dir) / extra_name)
        if lib_path.parent not in [c.parent for c in candidates]:
            candidates.append(lib_path.parent / extra_name)
        extra_path = next((p for p in candidates if p.exists()), None)
        if extra_path:
            try:
                extra_loader = create_safe_yaml_loader(include_base_dir=extra_path.parent)
                with open(extra_path, 'r', encoding='utf-8', errors='replace') as f_extra:
                    extra_doc = yaml.load(f_extra, Loader=extra_loader) or {}
                if isinstance(extra_doc, dict):
                    for key in merge_keys:
                        if key in extra_doc and isinstance(extra_doc[key], list):
                            lib_doc.setdefault(key, [])
                            lib_doc[key].extend(extra_doc[key])
            except Exception as e:
                print(f"Warning: failed loading {extra_name}: {e}", file=sys.stderr)

    return lib_doc


def _make_1px_transparent_png() -> bytes:
    """Return the bytes of a minimal 1×1 RGBA transparent PNG (no external deps)."""
    import struct, zlib
    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = _chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
    idat = _chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00\x00'))  # filter + RGBA(0,0,0,0)
    iend = _chunk(b'IEND', b'')
    return b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend


def generate_cpp_from_yaml(input_data, user_lib_dir=None, images_dir=None, screen_w=320, screen_h=240):
    try:
        if not input_data:
            return {"error": "No input data provided"}

        config = yaml.safe_load(input_data)
        screens = config.get("screens", [])

        # Load lib.yaml (+ lib_common, lib_custom, ble_proxy) to get available scripts and globals
        available_scripts = {}
        available_globals = set()
        lib_doc = load_merged_lib_doc(user_lib_dir=user_lib_dir, merge_keys=('script', 'globals'))
        if lib_doc:
            available_scripts = collect_available_scripts(lib_doc)
            available_globals = collect_available_globals(lib_doc)

        # Validate
        try:
            declared_dynamic_entities = config.get("dynamic_entities") or None
            images = config.get("images") or {}
            screen_images = config.get("screen_images") or {}
            available_images = set(images.keys())
            available_screen_images = set(screen_images.keys())
            validate_tiles_config(
                screens,
                available_scripts,
                available_globals,
                declared_dynamic_entities,
                available_images=available_images,
                available_screen_images=available_screen_images,
            )
        except ValueError as e:
            return {"error": str(e), "type": "validation_error"}

        # ----------------------------------------------------------------
        # Handle images: write source PNGs for debugging and compute the variant
        # map so generate_init_tiles_cpp can emit the correct variant IDs.
        # tile_ui's _register_images now handles ESPHome registration at compile
        # time for all runs (emulator, CI, test_device) — one path for everything.
        # ----------------------------------------------------------------
        import base64 as _base64
        import os as _os
        from tile_ui.tile_generation import compute_image_variants

        # Generate CPP — generate_init_tiles_cpp handles variant substitution.
        cpp_lambdas = generate_init_tiles_cpp(screens, available_scripts, available_globals)

        # Build the variant map so PNG files can be named correctly.
        _variant_id = compute_image_variants(screens)  # (img_id, rows, cols) -> variant_id

        # Write source PNGs (one per unique image ID) for debugging purposes.
        _written_pngs: set = set()  # track which source PNGs have been written

        for (_iid, _rows, _cols), _vid in sorted(_variant_id.items()):
            img_entry = images.get(_iid)
            if not isinstance(img_entry, dict):
                continue

            filename = img_entry.get("filename", f"{_iid}.png")
            img_data = img_entry.get("data", "")
            img_type = img_entry.get("type", "RGB565")
            _stem, _ext = _os.path.splitext(_os.path.basename(filename))
            safe_name = f"{_stem}.png"  # always original, unsuffixed

            # Write source PNG once per image ID (useful for debugging).
            # tile_ui's _register_images handles compile-time registration from
            # the inline base64 data — no YAML declarations needed here.
            if images_dir and img_data and safe_name not in _written_pngs:
                _os.makedirs(images_dir, exist_ok=True)
                try:
                    with open(_os.path.join(images_dir, safe_name), 'wb') as _f:
                        _f.write(_base64.b64decode(img_data))
                    _written_pngs.add(safe_name)
                except Exception as _e:
                    print(f"Warning: failed to write image '{_iid}': {_e}")

        # Screen images (full-screen backgrounds): write PNGs only.
        # ESPHome registration handled by caller if/when screen_images are wired up.
        screen_images = config.get("screen_images") or {}
        for _sid, _sentry in screen_images.items():
            if not isinstance(_sentry, dict):
                continue
            _sfilename = _sentry.get("filename", f"{_sid}.png")
            _sdata = _sentry.get("data", "")
            _stype = _sentry.get("type", "RGB565")
            _sstem, _ = _os.path.splitext(_os.path.basename(_sfilename))
            _ssafe = f"screen_{_sstem}.png"

            if images_dir and _sdata and _ssafe not in _written_pngs:
                _os.makedirs(images_dir, exist_ok=True)
                try:
                    raw_bytes = _base64.b64decode(_sdata)
                    # Cover-crop: scale to fill screen_w × screen_h, center-crop to exact size.
                    try:
                        import io as _io
                        from PIL import Image as _PILImage
                        _img = _PILImage.open(_io.BytesIO(raw_bytes))
                        _src_w, _src_h = _img.size
                        _scale = max(screen_w / _src_w, screen_h / _src_h)
                        _new_w = int(_src_w * _scale + 0.5)
                        _new_h = int(_src_h * _scale + 0.5)
                        _img = _img.resize((_new_w, _new_h), _PILImage.LANCZOS)
                        _left = (_new_w - screen_w) // 2
                        _top = (_new_h - screen_h) // 2
                        _img = _img.crop((_left, _top, _left + screen_w, _top + screen_h))
                        _buf = _io.BytesIO()
                        _img.save(_buf, format='PNG')
                        raw_bytes = _buf.getvalue()
                    except Exception as _crop_e:
                        print(f"Warning: cover-crop failed for screen image '{_sid}': {_crop_e}")
                    with open(_os.path.join(images_dir, _ssafe), 'wb') as _f:
                        _f.write(raw_bytes)
                    _written_pngs.add(_ssafe)
                except Exception as _e:
                    print(f"Warning: failed to write screen image '{_sid}': {_e}")

        return {
            "success": True,
            "cpp": cpp_lambdas,
            "message": f"Successfully generated {len(cpp_lambdas)} initialization blocks."
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": "unexpected_error"
        }

if __name__ == "__main__":
    # Read YAML from stdin; extra params come from env vars set by server.py
    # so this script can be run in a subprocess without blocking the Flask GIL.
    input_data = sys.stdin.read()
    _lib_dir    = os.environ.get('CYD_LIB_DIR')    or None
    _images_dir = os.environ.get('CYD_IMAGES_DIR') or None
    _screen_w   = int(os.environ.get('CYD_SCREEN_W', '320'))
    _screen_h   = int(os.environ.get('CYD_SCREEN_H', '240'))

    # Redirect stdout → stderr during generation so any incidental warning
    # print() calls don't corrupt the JSON result written to stdout.
    # The caller (server.py _run_generate_subprocess) does json.loads(proc.stdout),
    # so stdout must contain exactly one JSON object — nothing else.
    _real_stdout = sys.stdout
    sys.stdout = sys.stderr

    result = generate_cpp_from_yaml(
        input_data,
        user_lib_dir=_lib_dir,
        images_dir=_images_dir,
        screen_w=_screen_w,
        screen_h=_screen_h,
    )

    sys.stdout = _real_stdout
    print(json.dumps(result))
