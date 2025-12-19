"""Tile UI ESPhome Component - C++ code generation entry point."""
import esphome.codegen as cg
import esphome.config_validation as cv
import sys
import os
from esphome.const import CONF_ID
from esphome.core import CORE
from .data_collection import load_tiles_yaml, collect_available_scripts, collect_available_globals
from .tile_generation import generate_tile_cpp
from .tile_utils import flags_to_cpp
from .schema import screens_list_schema

# Configuration constants
DOMAIN = "tile_ui"
CONF_TILES_FILE = "tiles_file"
CONF_SCREENS = "screens"
CONF_DEBUG_OUTPUT = "debug_output"

CONFIG_SCHEMA = cv.Schema({
    cv.Optional(CONF_TILES_FILE): cv.string,
    cv.Optional(CONF_SCREENS): cv.Any(list),
    cv.Optional(CONF_DEBUG_OUTPUT, default=False): cv.boolean,
}, extra=cv.ALLOW_EXTRA)


def _print_error(context, message):
    """Print a formatted error message and exit without traceback."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"❌ [tile_ui] {context}:", file=sys.stderr)
    print(f"   {message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


def _print_success(message):
    """Print a formatted success message."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"✅ [tile_ui] Success:", file=sys.stderr)
    print(f"   {message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


def _print_debug(message):
    """Print a formatted debug message."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"🐛 [tile_ui] Debug Output:", file=sys.stderr)
    print(f"{message}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


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
        
        flags_cpp = flags_to_cpp(flags)
        lines = [
            f"// Screen: {screen_id}",
            f"std::vector<Tile*> tiles_{screen_id} = {{",
        ]
        
        for tile in tiles:
            tile_cpp = generate_tile_cpp(tile)
            lines.append(f"  {tile_cpp}")
        
        lines.extend([
            "};",
            "view_ptr->addScreen(",
            f"  new TiledScreen(&id({screen_id}), {flags_cpp}, tiles_{screen_id})",
            ");",
        ])
        lambdas.append("\n".join(lines))
    
    # Generate view finalization
    view_final = [
        "view_ptr->init();",
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
    from esphome.core import CORE
    
    # Try to get screens from inline config first, then fall back to file
    if CONF_SCREENS in config:
        # Inline screens configuration
        screens = config.get(CONF_SCREENS, [])
        # Validate schema for inline screens
        try:
            screens = screens_list_schema(screens)
        except cv.Invalid as e:
            _print_error("Inline Configuration Error", str(e))
            sys.exit(1)
        tiles_config = {"screens": screens}
    else:
        # Load from file
        tiles_file = config.get(CONF_TILES_FILE, "tiles.yaml")
        esphome_dir = CORE.config_path
        tiles_path = os.path.join(os.path.dirname(esphome_dir), tiles_file)
        
        try:
            tiles_config = load_tiles_yaml(tiles_path)
        except Exception as e:
            raise cv.Invalid(f"[tile_ui] Error loading tiles file '{tiles_file}': {str(e)}")
        
        # Validate schema for file-based screens
        screens = tiles_config.get("screens", [])
        try:
            screens = screens_list_schema(screens)
        except cv.Invalid as e:
            _print_error(f"Configuration Error in '{tiles_file}'", str(e))
            sys.exit(1)
    
    available_scripts = collect_available_scripts(CORE.config)
    available_globals = collect_available_globals(CORE.config)
    
    if not screens:
        return
    
    # Validate the configuration
    try:
        validate_tiles_config(screens, available_scripts, available_globals)
    except Exception as e:
        raise cv.Invalid(f"[tile_ui] Configuration validation failed: {str(e)}")
    
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
