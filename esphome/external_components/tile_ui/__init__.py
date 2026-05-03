"""Tile UI ESPhome Component - C++ code generation entry point."""
from typing import Any
import sys
import os

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.core import CORE
from esphome.components.display import DisplayPage
from .data_collection import load_tiles_yaml, collect_available_scripts, collect_available_globals
from .tile_generation import generate_tile_cpp
from .tile_utils import flags_to_cpp, build_expression
from .schema import screens_list_schema

# Configuration constants
DOMAIN = "tile_ui"
CONF_TILES_FILE = "tiles_file"
CONF_SCREENS = "screens"
CONF_DEBUG_OUTPUT = "debug_output"
CONF_SYSTEM_PAGES = "system_pages"

def load_tiles_config(config):
    """Load tiles configuration from file if not present in config."""
    if CONF_SCREENS not in config:
        tiles_file = config.get(CONF_TILES_FILE, "tiles.yaml")
        esphome_dir = CORE.config_path
        tiles_path = os.path.join(os.path.dirname(esphome_dir), tiles_file)
        try:
            tiles_config = load_tiles_yaml(tiles_path)
            config[CONF_SCREENS] = tiles_config.get("screens", [])
            # Also forward images: from the tiles file so _register_images handles
            # them the same way as test_device / CI (one path for everything).
            if "images" not in config and "images" in tiles_config:
                config["images"] = tiles_config["images"]
            if "screen_images" not in config and "screen_images" in tiles_config:
                config["screen_images"] = tiles_config["screen_images"]
        except Exception as e:
            print(f"Error loading tiles config: {e}")
            # Ignore errors here, they will be caught in to_code
            config[CONF_SCREENS] = []
            
    # Ensure system pages are present
    if CONF_SYSTEM_PAGES not in config:
        config[CONF_SYSTEM_PAGES] = [{"id": "calib"}]
        
    return config

CONFIG_SCHEMA = cv.All(
    load_tiles_config,
    cv.Schema({
        cv.Optional(CONF_TILES_FILE): cv.string,
        cv.Optional(CONF_SCREENS): cv.ensure_list(cv.Schema({
            cv.Required(CONF_ID): cv.declare_id(DisplayPage),
        }, extra=cv.ALLOW_EXTRA)),
        cv.Optional(CONF_SYSTEM_PAGES): cv.ensure_list(cv.Schema({
            cv.Required(CONF_ID): cv.declare_id(DisplayPage),
        })),
        cv.Optional(CONF_DEBUG_OUTPUT, default=False): cv.boolean,
    }, extra=cv.ALLOW_EXTRA)
)

__all__ = [
    "DOMAIN",
    "CONFIG_SCHEMA",
    "to_code",
]


def _print_error(context: str, message: str) -> None:
    """Print a formatted error message and exit without traceback."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"❌ [tile_ui] {context}:", file=sys.stderr)
    print(f"   {message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


def _print_success(message: str) -> None:
    """Print a formatted success message."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"✅ [tile_ui] Success:", file=sys.stderr)
    print(f"   {message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


def _print_debug(message: str) -> None:
    """Print a formatted debug message."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"🐛 [tile_ui] Debug Output:", file=sys.stderr)
    print(f"{message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


def _make_1px_transparent_png() -> bytes:
    """Return the bytes of a minimal 1×1 RGBA transparent PNG (no external deps)."""
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))  # filter + RGBA(0,0,0,0)
    iend = _chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


class _ImageRegistrar:
    """Lazy-loads ESPHome image codegen symbols once and provides shared registration helpers.

    Instantiated once per to_code() call so imports and the declared-ID set are
    built only once regardless of how many image groups are processed.
    """

    _VALID_TYPES = {"BINARY", "GRAYSCALE", "RGB565", "RGB"}

    def __init__(self, prefix: str = "tile_ui_images_"):
        import tempfile
        from esphome.core import ID, CORE as _CORE
        from esphome.const import CONF_ID as _IMAGE_CONF_ID
        from esphome.components.image import (
            write_image, image_ns,
            CONF_ALPHA_CHANNEL, CONF_OPAQUE, CONF_TRANSPARENCY, CONF_INVERT_ALPHA,
        )
        from esphome.const import (
            CONF_FILE, CONF_RESIZE, CONF_RAW_DATA_ID, CONF_TYPE, CONF_DITHER,
            CONF_ID as _CONF_ID,
        )

        self.ID = ID
        self._CORE = _CORE
        self.write_image = write_image
        self.Image_ = image_ns.class_("Image")
        self.CONF_FILE = CONF_FILE
        self.CONF_RESIZE = CONF_RESIZE
        self.CONF_RAW_DATA_ID = CONF_RAW_DATA_ID
        self.CONF_TYPE = CONF_TYPE
        self.CONF_DITHER = CONF_DITHER
        self.CONF_ID = _CONF_ID
        self.CONF_TRANSPARENCY = CONF_TRANSPARENCY
        self.CONF_ALPHA_CHANNEL = CONF_ALPHA_CHANNEL
        self.CONF_OPAQUE = CONF_OPAQUE
        self.CONF_INVERT_ALPHA = CONF_INVERT_ALPHA
        self.tmp_dir = tempfile.mkdtemp(prefix=prefix)

        # Build the set of IDs already declared via the image: component
        # (e.g. none_transparent from lib_common.yaml) so we never re-register them.
        _image_cfg = _CORE.config.get("image", [])
        self._declared_ids: set = set()
        if isinstance(_image_cfg, list):
            for _entry in _image_cfg:
                if isinstance(_entry, dict):
                    _eid = _entry.get(_IMAGE_CONF_ID)
                    if _eid is not None:
                        self._declared_ids.add(str(_eid))

    def already_registered(self, vid: str) -> bool:
        """Return True if *vid* is already known to ESPHome's image component or CORE.variables."""
        if vid in self._declared_ids:
            return True
        probe = self.ID(vid, is_declaration=False)
        return probe in self._CORE.variables

    def map_type(self, raw_type) -> tuple:
        """Return (esh_type, esh_trans) for a raw image type string."""
        rtype = str(raw_type).upper()
        if rtype == "RGBA":
            return "RGB", self.CONF_ALPHA_CHANNEL
        if rtype == "RGB24":
            return "RGB", self.CONF_OPAQUE
        if rtype in self._VALID_TYPES:
            return rtype, self.CONF_OPAQUE
        return "RGB565", self.CONF_OPAQUE

    async def register(self, img_id: str, png_path: str, esh_type: str, esh_trans,
                       resize_val=None) -> bool:
        """Call ESPHome write_image and register the variable. Returns True on success."""
        img_id_obj = self.ID(img_id, is_declaration=True, type=self.Image_)
        raw_data_id = self.ID(f"{img_id}_raw_data", is_declaration=True, type=cg.uint8)
        entry = {
            self.CONF_ID: img_id_obj,
            self.CONF_RAW_DATA_ID: raw_data_id,
            self.CONF_FILE: png_path,
            self.CONF_TYPE: esh_type,
            self.CONF_TRANSPARENCY: esh_trans,
            self.CONF_DITHER: "NONE",
            self.CONF_INVERT_ALPHA: False,
        }
        if resize_val is not None:
            entry[self.CONF_RESIZE] = resize_val
        try:
            prog_arr, w, h, img_type_val, trans_val, _ = await self.write_image(entry)
            cg.new_Pvariable(img_id_obj, prog_arr, w, h, img_type_val, trans_val)
            return True
        except Exception as _e:
            print(f"[tile_ui] Warning: failed to register image '{img_id}': {_e}", file=sys.stderr)
            return False


async def _register_screen_images(screen_images_conf: dict, screen_w: int, screen_h: int) -> None:
    """Register screen_images entries (full-screen backgrounds) via ESPHome's image codegen API.

    Each entry is keyed by the ID used in background: declarations.  A cover-crop
    to screen_w × screen_h is applied when PIL is available.
    """
    import base64
    import io
    import os

    ctx = _ImageRegistrar(prefix="tile_ui_screen_images_")
    registered: set = set()

    for img_id, img_data in screen_images_conf.items():
        if not isinstance(img_data, dict) or ctx.already_registered(img_id):
            continue
        img_b64 = img_data.get("data", "")
        if not img_b64:
            continue

        esh_type, esh_trans = ctx.map_type(img_data.get("type", "RGB565"))
        png_path = os.path.join(ctx.tmp_dir, f"{img_id}.png")
        try:
            raw_bytes = base64.b64decode(img_b64)
            # Cover-crop to screen dimensions when PIL is available.
            try:
                from PIL import Image as _PILImage
                _img = _PILImage.open(io.BytesIO(raw_bytes))
                _src_w, _src_h = _img.size
                _s = max(screen_w / _src_w, screen_h / _src_h)
                _new_w, _new_h = int(_src_w * _s + 0.5), int(_src_h * _s + 0.5)
                _img = _img.resize((_new_w, _new_h), _PILImage.LANCZOS)
                _left, _top = (_new_w - screen_w) // 2, (_new_h - screen_h) // 2
                _img = _img.crop((_left, _top, _left + screen_w, _top + screen_h))
                _buf = io.BytesIO()
                _img.save(_buf, format="PNG")
                raw_bytes = _buf.getvalue()
            except Exception:
                pass  # fall back to raw bytes
            with open(png_path, "wb") as _f:
                _f.write(raw_bytes)
        except Exception as _e:
            print(f"[tile_ui] Warning: could not decode screen image '{img_id}': {_e}", file=sys.stderr)
            continue

        if await ctx.register(img_id, png_path, esh_type, esh_trans):
            registered.add(img_id)

    if registered:
        print(f"[tile_ui] Registered {len(registered)} screen background image(s) from inline tile_ui.screen_images: config", file=sys.stderr)


async def _register_images(images_conf: dict, screens: list, screen_w: int = 480, screen_h: int = 320) -> None:
    """Register tile_ui.images: entries via ESPHome's image codegen API.

    Processes base64 PNG data from inline config, writes temp files, and registers
    each per-layout image variant — skipping any ID already known to ESPHome.
    Resize targets mirror the generate_tiles_api.py formula so flash usage is identical
    to a configurator-generated build.
    """
    import base64
    import os
    from .tile_generation import compute_image_variants

    ctx = _ImageRegistrar(prefix="tile_ui_images_")
    variant_id = compute_image_variants(screens)  # (img_id, rows, cols) -> variant_str
    _TILE_PAD, _FIXED_PAD = 10, 5

    registered: set = set()
    for (img_id, _rows, _cols), vid in variant_id.items():
        if vid in registered or ctx.already_registered(vid):
            registered.add(vid)
            continue

        img_data = images_conf.get(img_id)
        if not isinstance(img_data, dict):
            continue
        img_b64 = img_data.get("data", "")
        if not img_b64:
            continue

        esh_type, esh_trans = ctx.map_type(img_data.get("type", "RGB565"))
        png_path = os.path.join(ctx.tmp_dir, f"{vid}.png")
        try:
            with open(png_path, "wb") as _f:
                _f.write(base64.b64decode(img_b64))
        except Exception as _e:
            print(f"[tile_ui] Warning: could not decode image '{vid}': {_e}", file=sys.stderr)
            continue

        # Compute resize — mirrors generate_tiles_api.py formula:
        #   tile_w = (screen_w - (cols+1)*pad) / cols  ;  max_dim = (tile_dim - 2*FIXED_PAD) * scale
        _scale = max(0.1, min(1.0, (img_data.get("scale") or 100) / 100.0))
        _tile_w = max(8, (screen_w - (_cols + 1) * _TILE_PAD) // _cols)
        _tile_h = max(8, (screen_h - (_rows + 1) * _TILE_PAD) // _rows)
        resize_val = (
            max(8, int((_tile_w - _FIXED_PAD * 2) * _scale)),
            max(8, int((_tile_h - _FIXED_PAD * 2) * _scale)),
        )

        if await ctx.register(vid, png_path, esh_type, esh_trans, resize_val=resize_val):
            registered.add(vid)

    if registered:
        print(f"[tile_ui] Registered {len(registered)} image variant(s) from inline tile_ui.images: config", file=sys.stderr)


CALIB_PAGE_LAMBDA = """
          if (id(touch_calibration).state) {
            id(disp).fill(id(Color::WHITE));
            id(disp).filled_circle(id(last_x), id(last_y), 10, id(red));
            id(disp).printf(id(width) / 2, id(height) / 2 - 15, &id(text_regular), Color::BLACK, TextAlign::CENTER,
                          "x=%d, y=%d", id(last_x), id(last_y));
            id(disp).printf(id(width) / 2, id(height) / 2 + 15, &id(text_regular), Color::BLACK, TextAlign::CENTER,
                          "x_raw=%d, y_raw=%0d", id(last_x_raw), id(last_y_raw));
          }
"""


def generate_init_tiles_cpp(screens, available_scripts=None, available_globals=None, debug=False):
    """Generate separate lambda scripts for each screen and view init."""
    from .validation import validate_tiles_config
    from .tile_generation import compute_image_variants, apply_image_variants

    # Apply per-page-size image variant substitution so that the ESPHome IDs
    # emitted by the lambdas always match the variant IDs registered by _register_images.
    variant_id = compute_image_variants(screens)
    if variant_id:
        screens = apply_image_variants(screens, variant_id)

    validate_tiles_config(screens, available_scripts, available_globals)
    
    lambdas = []
    
    # Generate view initialization
    view_init = [
        "// Initialize view",
        "view_ptr.reset(new View());",
    ]
    lambdas.append("\n".join(view_init))
    
    # Generate each screen as a separate lambda
    for screen in screens:
        screen_id = screen.get("id", "")
        flags = screen.get("flags", [])
        tiles = screen.get("tiles", [])
        rows = screen.get("rows")
        cols = screen.get("cols")
        
        rows_cpp = str(rows) if rows is not None else "id(rows)"
        cols_cpp = str(cols) if cols is not None else "id(cols)"
        
        flags_cpp = flags_to_cpp(flags)
        lines = [
            f"// Screen: {screen_id}",
            f"std::vector<Tile*> tiles_{screen_id} = {{",
        ]
        
        for tile in tiles:
            tile_cpp = generate_tile_cpp(tile, available_scripts, screen_id)
            lines.append(f"  {tile_cpp}")

        # Build background method chains (drawn before tiles at runtime)
        bg_chains = []
        for entry in (screen.get("background") or []):
            if not isinstance(entry, dict):
                continue
            condition = entry.get("condition")
            has_condition = condition and str(condition).strip()
            if has_condition:
                cond_expr = build_expression(condition)
                cond_lambda = (
                    f", [](std::vector<std::string> entities) -> bool"
                    f" {{ return {cond_expr}; }}"
                )
            else:
                cond_lambda = ""
            if "color" in entry and entry["color"] and entry["color"] != "none":
                _c = entry['color']
                # Color(r,g,b) is a C++ constructor — use directly; named globals need id()
                if _c.startswith('Color('):
                    bg_chains.append(f"->addBgColor({_c}{cond_lambda})")
                else:
                    bg_chains.append(f"->addBgColor(id({_c}){cond_lambda})")
            elif "image" in entry and entry["image"] and entry["image"] != "none":
                draw_fn = f"[=]() {{ id(disp).image(0, 0, &id({entry['image']})); }}"
                bg_chains.append(f"->addBgLambda({draw_fn}{cond_lambda})")

        # Build time_color method chain (no conditional, simple color override)
        time_color_val = screen.get("time_color")
        time_color_chain = None
        if time_color_val:
            _tc = str(time_color_val).strip()
            _tc_cpp = _tc if _tc.startswith('Color(') else f'id({_tc})'
            time_color_chain = f"->setTimeColor({_tc_cpp})"

        all_chains = bg_chains[:]
        if time_color_chain:
            all_chains.append(time_color_chain)

        screen_expr = (
            f"  new TiledScreen(&id({screen_id}), {flags_cpp}, {rows_cpp}, {cols_cpp}, tiles_{screen_id})"
        )
        if all_chains:
            screen_expr = (
                f"  (new TiledScreen(&id({screen_id}), {flags_cpp}, {rows_cpp}, {cols_cpp}, tiles_{screen_id}))"
            )
            for chain in all_chains:
                screen_expr += f"\n  {chain}"

        lines.extend([
            "};",
            "view_ptr->addScreen(",
            screen_expr,
            ");",
        ])
        lambdas.append("\n".join(lines))
    
    # Generate view finalization
    view_final = [
        "view_ptr->init();",
        "if (view_ptr->getActiveScreen()) {",
        "  id(rows) = view_ptr->getActiveScreen()->getRows();",
        "  id(cols) = view_ptr->getActiveScreen()->getCols();",
        "}",
        "if (view_ptr->getBaseScreen()) {",
        "  id(disp).show_page(view_ptr->getBaseScreen()->getDisplayPage());",
        "}",
        "ESP_LOGD(\"InitTiles\", \"Tiles initialized\");",
    ]
    lambdas.append("\n".join(view_final))
    
    if debug:
        _print_debug("\n\n".join(lambdas))
    
    return lambdas


def final_validate(config):
    return config

FINAL_VALIDATE_SCHEMA = final_validate


async def to_code(config):
    """Generate and validate YAML tile configuration."""
    from .validation import validate_tiles_config
    
    all_pages = []

    # Register system pages (calib)
    for page_conf in config.get(CONF_SYSTEM_PAGES, []):
        page_id = page_conf[CONF_ID]
        if page_id.id == "calib":
             lambda_str = f"[](esphome::display::Display &it) {{ {CALIB_PAGE_LAMBDA} }}"
             lambda_expr = cg.RawExpression(lambda_str)
             var = cg.new_Pvariable(page_id, lambda_expr)
             all_pages.append(var)

    # Register screen pages
    for screen_conf in config.get(CONF_SCREENS, []):
        screen_id = screen_conf[CONF_ID]
        lambda_str = f"[](esphome::display::Display &it) {{ id(_draw_page).execute(); }}"
        lambda_expr = cg.RawExpression(lambda_str)
        var = cg.new_Pvariable(screen_id, lambda_expr)
        all_pages.append(var)

    # Now generate code to set pages
    if all_pages:
        pages_list = ", ".join([str(p) for p in all_pages])
        stmt = f"""
        std::vector<esphome::display::DisplayPage*> tile_pages = {{{pages_list}}};
        ((esphome::display::Display*)&id(disp))->set_pages(tile_pages);

        auto *page_change_trigger = new esphome::display::DisplayOnPageChangeTrigger((esphome::display::Display*)&id(disp));
        auto *automation = new esphome::Automation<esphome::display::DisplayPage *, esphome::display::DisplayPage *>(page_change_trigger);
        automation->add_action(new esphome::LambdaAction<esphome::display::DisplayPage *, esphome::display::DisplayPage *>([=](esphome::display::DisplayPage *from, esphome::display::DisplayPage *to) {{
            id(change_page_ms) = millis();
            id(disp).fill(Color::BLACK);
            if (view_ptr != nullptr) {{
                Screen* screen = view_ptr->getScreen(to);
                if (screen != nullptr) {{
                    id(rows) = screen->getRows();
                    id(cols) = screen->getCols();
                    screen->onScreenEnter();
                }}
            }}
        }}));
        """
        cg.add(cg.RawStatement(stmt))

    # Try to get screens from inline config first, then fall back to file
    # Note: screens are already loaded into config by load_tiles_config validator
    screens = config.get(CONF_SCREENS, [])
    
    # Validate schema for screens (deep validation)
    try:
        screens = screens_list_schema(screens)
    except cv.Invalid as e:
        _print_error("Schema Validation Failed", str(e))
        sys.exit(1)
    
    available_scripts = collect_available_scripts(CORE.config)
    available_globals = collect_available_globals(CORE.config)
    
    if not screens:
        return
    
    # Validate the configuration
    try:
        validate_tiles_config(screens, available_scripts, available_globals)
    except ValueError as e:
        _print_error("Validation Failed", str(e))
        sys.exit(1)
    except Exception as e:
        _print_error("Unexpected Error", str(e))
        sys.exit(1)

    # Register images from inline tile_ui.images: config.
    # Decodes per-layout image variants from inline base64 data and registers them
    # via ESPHome's image codegen API.  none_transparent is always present via
    # lib_common.yaml's inline image: declaration and is therefore skipped here.

    # Extract screen dimensions once — used by both image registration calls below.
    _screen_w, _screen_h = 480, 320
    _disp_cfg = CORE.config.get("display", [])
    if isinstance(_disp_cfg, list) and _disp_cfg:
        _d = _disp_cfg[0]
        if isinstance(_d, dict):
            try:
                _screen_w = int(_d.get("width", _screen_w))
                _screen_h = int(_d.get("height", _screen_h))
            except (TypeError, ValueError):
                pass

    images_conf = config.get("images", {})
    if images_conf:
        await _register_images(images_conf, screens, screen_w=_screen_w, screen_h=_screen_h)

    # Register screen background images from inline tile_ui.screen_images: config.
    screen_images_conf = config.get("screen_images", {})
    if screen_images_conf:
        await _register_screen_images(screen_images_conf, screen_w=_screen_w, screen_h=_screen_h)

    # Generate C++ initialization code (returns list of lambda strings)
    debug_output = config.get(CONF_DEBUG_OUTPUT, False)
    cpp_lambdas = generate_init_tiles_cpp(screens, available_scripts, available_globals, debug=debug_output)
    
    # Add initialization code directly to setup() with a delay to avoid boot loops
    
    combined_lambda = "\n".join(cpp_lambdas)
    stmt = f"""
    App.scheduler.set_timeout(nullptr, "tile_ui_init", 2000, [=]() {{
        {combined_lambda}
    }});
    """
    cg.add(cg.RawStatement(stmt))
        
    _print_success(f"Injected {len(cpp_lambdas)} tile initialization blocks into setup() (delayed)")
