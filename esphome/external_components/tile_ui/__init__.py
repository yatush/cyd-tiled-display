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
from .tile_utils import flags_to_cpp
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
        
        lines.extend([
            "};",
            "view_ptr->addScreen(",
            f"  new TiledScreen(&id({screen_id}), {flags_cpp}, {rows_cpp}, {cols_cpp}, tiles_{screen_id})",
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
        lambda_str = f"[](esphome::display::Display &it) {{ id(draw_page).execute(); }}"
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
            if (!id(render_diffs)) {{
                id(disp).fill(Color::BLACK);
            }}
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
