"""Tile generation functions - converts YAML tile configs to C++ code."""
import copy
from typing import Any

from .tile_utils import (
    format_display_list, format_functions_list, format_entity_value,
    build_fast_refresh_lambda, build_expression, format_entity_cpp, get_tile_modifiers,
    flags_to_cpp, format_single_function
)
from .schema import TileType

__all__ = [
    "generate_tile_cpp",
    "generate_action_tile",
    "generate_title_tile",
    "generate_move_page_tile",
    "generate_function_tile",
    "generate_toggle_entity_tile",
    "generate_cycle_entity_tile",
    "compute_image_variants",
    "apply_image_variants",
]

# ---------------------------------------------------------------------------
# Per-page-size image variant helpers
# ---------------------------------------------------------------------------

def compute_image_variants(screens: list) -> dict:
    """
    Scan screens and return a mapping ``(img_id, rows, cols) -> variant_id``.

    * When an image appears in only one page layout (rows×cols), the
      variant_id is kept as the original image ID (no suffix).
    * When the same image appears in multiple layouts a unique suffix
      ``_r{rows}c{cols}`` is appended so that ESPHome can declare
      separate, correctly-sized image objects for each layout.
    """
    img_sizes: dict = {}  # img_id -> set of (rows, cols)
    for screen in screens:
        rows = screen.get('rows', 2)
        cols = screen.get('cols', 2)
        for tile_obj in screen.get('tiles', []):
            if not isinstance(tile_obj, dict):
                continue
            for _tname, tdata in tile_obj.items():
                if not isinstance(tdata, dict):
                    continue
                for entry in (tdata.get('images') or []):
                    if isinstance(entry, dict) and entry.get('image'):
                        img_sizes.setdefault(entry['image'], set()).add((rows, cols))

    variant_id: dict = {}  # (img_id, rows, cols) -> variant_id
    for iid, sizes in img_sizes.items():
        sorted_sizes = sorted(sizes)
        if len(sorted_sizes) == 1:
            r, c = sorted_sizes[0]
            variant_id[(iid, r, c)] = iid
        else:
            for (r, c) in sorted_sizes:
                variant_id[(iid, r, c)] = f"{iid}_r{r}c{c}"

    return variant_id


def apply_image_variants(screens: list, variant_id: dict) -> list:
    """
    Return a deep copy of ``screens`` where every tile’s image references
    have been replaced with their per-layout variant IDs.
    """
    result = copy.deepcopy(screens)
    for screen in result:
        rows = screen.get('rows', 2)
        cols = screen.get('cols', 2)
        for tile_obj in screen.get('tiles', []):
            if not isinstance(tile_obj, dict):
                continue
            for _tname, tdata in tile_obj.items():
                if not isinstance(tdata, dict):
                    continue
                timages = tdata.get('images')
                if isinstance(timages, list):
                    tdata['images'] = [
                        {**e, 'image': variant_id.get((e['image'], rows, cols), e['image'])}
                        if isinstance(e, dict) and e.get('image') else e
                        for e in timages
                    ]
    return result

# ---------------------------------------------------------------------------
# Image lambda helpers
# ---------------------------------------------------------------------------

_CPP_TYPE_MAP = {
    'int': 'int',
    'float': 'float',
    'bool': 'bool',
    'string': 'std::string',
    'string[]': 'std::vector<std::string>',
}


def _cpp_param_type(p_type: str) -> str:
    return _CPP_TYPE_MAP.get(p_type, 'auto')


def _build_lambda_sig(expected_params) -> str:
    """Build a C++ lambda parameter list string from expected_params."""
    args = []
    for i, (_, p_type) in enumerate(expected_params):
        args.append(f"{_cpp_param_type(p_type)} arg{i}")
    return ", ".join(args)


def _build_image_lambda(config: dict, expected_params: list) -> str | None:
    """
    Return a raw C++ lambda string that draws an image (or condition-based image)
    centred within the tile bounds.  Returns None when 'images' is absent.

    'images' (list): each entry is {image: <img_id>, condition?: <condition_expr>}.
        Entries are evaluated in order; first matching condition wins.
        An entry without 'condition' is an unconditional fallback (drawn always,
        treated as the final 'else' clause).
    """
    images = config.get("images")
    if not images or not isinstance(images, list):
        # Legacy single-image fallback (old 'image' key)
        legacy_image = config.get("image")
        if legacy_image:
            images = [{"image": legacy_image}]
        else:
            return None

    # Filter out entries missing an image id
    valid_entries = [e for e in images if e.get("image")]
    if not valid_entries:
        return None

    sig = _build_lambda_sig(expected_params)
    param_types = [p_type for (_, p_type) in expected_params]

    # Determine how to bind 'entities' so condition scripts can call execute(entities).
    has_vec = 'string[]' in param_types
    if has_vec:
        vec_idx = param_types.index('string[]')
        entities_binding = f"const std::vector<std::string>& entities = arg{vec_idx};"
    else:
        entities_binding = "const std::vector<std::string> entities{};"

    draw_snippet = (
        "  if (_img != nullptr) {\n"
        "    int _iw = (int)_img->get_width();\n"
        "    int _ih = (int)_img->get_height();\n"
        "    id(disp).image((arg0 + arg1 - _iw) / 2, (arg2 + arg3 - _ih) / 2, _img);\n"
        "  }"
    )

    has_any_condition = any(e.get("condition") for e in valid_entries)

    # -----------------------------------------------------------------------
    # Single unconditional entry — optimised static draw
    # -----------------------------------------------------------------------
    if not has_any_condition and len(valid_entries) == 1:
        img_id = valid_entries[0]["image"]
        body = (
            f"  auto& _img = id({img_id});\n"
            f"  int _iw = (int)_img.get_width();\n"
            f"  int _ih = (int)_img.get_height();\n"
            f"  id(disp).image((arg0 + arg1 - _iw) / 2, (arg2 + arg3 - _ih) / 2, &_img);"
        )
        return f"[=]({sig}) {{\n{body}\n}}"

    # -----------------------------------------------------------------------
    # if / else-if chain; first unconditional entry becomes the final else
    # -----------------------------------------------------------------------
    cond_parts = []
    keyword = "if"
    fallback_img = None

    for entry in valid_entries:
        img_id = entry["image"]
        cond_expr = entry.get("condition")
        if not cond_expr:
            # First unconditional entry = catch-all else
            fallback_img = img_id
            break
        expr = build_expression(cond_expr)
        if not expr:
            continue
        cond_parts.append(f"  {keyword} ({expr}) {{ _img = &id({img_id}); }}")
        keyword = "else if"

    if not cond_parts and fallback_img is None:
        return None

    body_lines = []
    if has_any_condition:
        body_lines.append(f"  {entities_binding}")
    body_lines.append("  esphome::image::Image* _img = nullptr;")
    body_lines.extend(cond_parts)
    if fallback_img:
        body_lines.append(f"  else {{ _img = &id({fallback_img}); }}")
    body_lines.append(draw_snippet)

    body = "\n".join(body_lines)
    return f"[=]({sig}) {{\n{body}\n}}"


def _override_display_with_image(display_cpp: str, config: dict, expected_params: list) -> str:
    """
    If config has 'image' or 'state_images', replace the display list entirely
    with the image draw lambda (ignoring any 'display' scripts).
    Otherwise return the original display_cpp unchanged.
    """
    lam = _build_image_lambda(config, expected_params)
    if not lam:
        return display_cpp
    return f"{{ {lam} }}"


# Keep old name as alias so any external callers aren't broken
_append_image_lambda = _override_display_with_image


def _generate_base_tile_args(config, available_scripts, expected_display_params):
    """Extract base tile arguments (x, y, display)."""
    x = config.get("x", 0)
    y = config.get("y", 0)
    display = config.get("display", [])
    display_cpp = format_display_list(display, available_scripts, expected_display_params)
    return x, y, display_cpp


def _apply_modifiers(tile_cpp, config, extra_modifiers=None, screen_id=None):
    """Apply common modifiers to the tile C++ object."""
    method_chains = []
    if extra_modifiers:
        method_chains.extend(extra_modifiers)
        
    method_chains.extend(get_tile_modifiers(config, screen_id))
    
    if method_chains:
        tile_cpp = f'({tile_cpp})'
        for method in method_chains:
            tile_cpp += f'->{method}'
    
    return tile_cpp


def generate_action_tile(config, available_scripts, screen_id=None):
    """Generate C++ for an action tile."""
    # HAActionTile display: int, int, vector<string>
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    entities_config = config.get("entities", "")
    entity_values = format_entity_value(entities_config)
    perform = config.get("perform", [])
    location_perform = config.get("location_perform", [])
    display_page = config.get("display_page_if_no_entity", None)
    requires_fast_refresh = config.get("requires_fast_refresh", None)
    
    if display_page:
        has_dynamic_entity = False
        if isinstance(entities_config, list):
            for entity in entities_config:
                if isinstance(entity, dict) and "dynamic_entity" in entity:
                    has_dynamic_entity = True
                    break
        elif isinstance(entities_config, dict) and "dynamic_entity" in entities_config:
            has_dynamic_entity = True
        
        if not has_dynamic_entity:
            raise ValueError(
                f"Screen '{screen_id}', Tile at ({x}, {y}): display_page_if_no_entity requires at least one dynamic_entity"
            )
    
    # HAActionTile perform: vector<string>
    perform_cpp = format_functions_list(perform, available_scripts, [('entities', 'string[]')])
    # HAActionTile location_perform: float, float, vector<string>
    location_perform_cpp = format_functions_list(location_perform, available_scripts, [('x', 'float'), ('y', 'float'), ('entities', 'string[]')])
    entity_cpp = format_entity_cpp(entity_values)
    
    args = [str(x), str(y), display_cpp]
    
    if perform and location_perform:
        args.append(perform_cpp)
        args.append(location_perform_cpp)
    elif perform:
        args.append(perform_cpp)
    elif location_perform:
        args.append("{}")
        args.append(location_perform_cpp)
    
    args.append(entity_cpp)
    
    tile_cpp = f'new HAActionTile({", ".join(args)})'
    
    modifiers = []
    # Apply specific modifiers before common ones
    if display_page:
        modifiers.append(f'setDisplayPageIfNoEntity(&id({display_page}))')
    
    x = config.get("x", "?")
    y = config.get("y", "?")
    context = f"Screen '{screen_id}', Tile at ({x}, {y})" if screen_id else f"Tile at ({x}, {y})"
    
    fast_refresh_lambda = build_fast_refresh_lambda(requires_fast_refresh, context)
    if fast_refresh_lambda:
        modifiers.append(f'setRequiresFastRefreshFunc({fast_refresh_lambda})')
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_title_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a title tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    entities_config = config.get("entities", "")
    entity_values = format_entity_value(entities_config)
    entity_cpp = format_entity_cpp(entity_values)
    requires_fast_refresh = config.get("requires_fast_refresh", None)
    
    tile_cpp = f'new TitleTile({x}, {y}, {display_cpp}, {entity_cpp})'
    
    modifiers = []
    context = f"Screen '{screen_id}', Tile at ({x}, {y})" if screen_id else f"Tile at ({x}, {y})"
    fast_refresh_lambda = build_fast_refresh_lambda(requires_fast_refresh, context)
    if fast_refresh_lambda:
        modifiers.append(f'setRequiresFastRefreshFunc({fast_refresh_lambda})')
        
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_move_page_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a move page tile."""
    # MovePageTile display: int, int, string, Color, font
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    destination = config.get("destination", "")
    dynamic_entry = config.get("dynamic_entry", None)
    
    tile_cpp = f'new MovePageTile({x}, {y}, {display_cpp}, &id({destination}))'
    
    modifiers = []
    if dynamic_entry:
        dynamic_entity = dynamic_entry.get("dynamic_entity", "")
        value = dynamic_entry.get("value", "")
        if dynamic_entity and value:
            values_cpp = format_entity_cpp(value)
            modifiers.append(f'setDynamicEntry("{dynamic_entity}", {values_cpp})')
        else:
            raise ValueError(f"Screen '{screen_id}', Tile at ({x}, {y}): dynamic_entry must have both 'dynamic_entity' and 'value'")
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_function_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a function tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    on_press = config.get("on_press", None)
    on_release = config.get("on_release", None)
    
    on_press_cpp = format_single_function(on_press, available_scripts, []) if on_press else "nullptr"
    on_release_cpp = format_single_function(on_release, available_scripts, []) if on_release else "nullptr"
    
    if on_release:
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, {on_press_cpp}, {on_release_cpp})'
    else:
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, {on_press_cpp})'
    
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_toggle_entity_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a toggle entity tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), (['name', 'presentation_name'], 'string'), ('is_on', 'bool')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    dynamic_entity = config.get("dynamic_entity", "")
    entity = config.get("entity", "")
    presentation_name = config.get("presentation_name", "")
    initially_chosen = config.get("initially_chosen", False)
    
    if not dynamic_entity:
        raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not entity:
        raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}) must have 'entity' field")
    
    initially_chosen_cpp = "true" if initially_chosen else "false"
    
    entities_cpp = format_entity_cpp(entity)
    
    tile_cpp = f'new ToggleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", {entities_cpp}, "{presentation_name}", {initially_chosen_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_cycle_entity_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a cycle entity tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('name', 'string'), (['options', 'entities'], 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    dynamic_entity = config.get("dynamic_entity", "")
    options = config.get("options", [])
    reset_on_leave = config.get("reset_on_leave", False)
    
    if not dynamic_entity:
        raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not options or len(options) == 0:
        raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}) must have 'options' list with at least one item")
    
    options_cpp_pairs = []
    
    for option_item in options:
        if isinstance(option_item, dict):
            entity = option_item.get("entity", "")
            label = option_item.get("label", "")
            if entity and label:
                entities_cpp = format_entity_cpp(entity)
                options_cpp_pairs.append(f'{{ {entities_cpp}, "{label}" }}')
            else:
                raise ValueError(f"Screen '{screen_id}', each option item must have both 'entity' and 'label' fields at ({x}, {y})")
        else:
            raise ValueError(f"Screen '{screen_id}', options must be dicts with 'entity' and 'label' fields at ({x}, {y})")
    
    options_cpp = "{ " + ", ".join(options_cpp_pairs) + " }"
    reset_on_leave_cpp = "true" if reset_on_leave else "false"
    
    tile_cpp = f'new CycleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", {options_cpp}, {reset_on_leave_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_tile_cpp(tile: dict, available_scripts=None, screen_id=None) -> str:
    """Generate C++ code for a single tile."""
    if TileType.HA_ACTION.value in tile:
        return generate_action_tile(tile[TileType.HA_ACTION.value], available_scripts, screen_id)
    elif TileType.MOVE_PAGE.value in tile:
        return generate_move_page_tile(tile[TileType.MOVE_PAGE.value], available_scripts, screen_id)
    elif TileType.TITLE.value in tile:
        return generate_title_tile(tile[TileType.TITLE.value], available_scripts, screen_id)
    elif TileType.FUNCTION.value in tile:
        return generate_function_tile(tile[TileType.FUNCTION.value], available_scripts, screen_id)
    elif TileType.TOGGLE_ENTITY.value in tile:
        return generate_toggle_entity_tile(tile[TileType.TOGGLE_ENTITY.value], available_scripts, screen_id)
    elif TileType.CYCLE_ENTITY.value in tile:
        return generate_cycle_entity_tile(tile[TileType.CYCLE_ENTITY.value], available_scripts, screen_id)
    else:
        return f'// Unknown tile structure: {list(tile.keys())}'
