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
                    if isinstance(entry, dict):
                        if entry.get('image'):
                            img_sizes.setdefault(entry['image'], set()).add((rows, cols))
                        anim = entry.get('animation')
                        if isinstance(anim, dict):
                            for extra in (anim.get('extra_images') or []):
                                if extra:
                                    img_sizes.setdefault(extra, set()).add((rows, cols))

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
                    new_entries = []
                    for e in timages:
                        if not isinstance(e, dict):
                            new_entries.append(e)
                            continue
                        ne = dict(e)
                        if ne.get('image'):
                            ne['image'] = variant_id.get((ne['image'], rows, cols), ne['image'])
                        anim = ne.get('animation')
                        if isinstance(anim, dict) and anim.get('extra_images'):
                            ne['animation'] = {
                                **anim,
                                'extra_images': [
                                    variant_id.get((img, rows, cols), img)
                                    if isinstance(img, str) else img
                                    for img in anim['extra_images']
                                ],
                            }
                        new_entries.append(ne)
                    tdata['images'] = new_entries
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


def _get_animation_fast_refresh(config: dict):
    """
    Derive a requires_fast_refresh value from animation settings in the images list.

    Returns:
      None – no animation entries
      True – at least one animation entry (always fast-refresh)
    """
    images = config.get("images")
    if not images or not isinstance(images, list):
        return None

    has_animation = False

    for entry in images:
        if not isinstance(entry, dict):
            continue
        animation = entry.get("animation")
        if animation and isinstance(animation, dict):
            has_animation = True
            break

    return True if has_animation else None


def _build_image_lambda(config: dict, expected_params: list) -> str | None:
    """
    Return a C++ lambda that sets id(image_slot) and calls one of the
    draw_image_* YAML scripts defined in lib_common.yaml.

    Each entry in 'images':
      { image: <id>, condition?: <expr>, animation?: { direction, duration } }
    """
    images = config.get("images")
    if not images or not isinstance(images, list):
        legacy_image = config.get("image")
        if legacy_image:
            images = [{"image": legacy_image}]
        else:
            return None

    valid_entries = [e for e in images if isinstance(e, dict) and e.get("image")]
    if not valid_entries:
        return None

    sig = _build_lambda_sig(expected_params)
    param_types = [p_type for (_, p_type) in expected_params]

    has_vec = 'string[]' in param_types
    if has_vec:
        vec_idx = param_types.index('string[]')
        entities_binding = f"  const std::vector<std::string>& entities = arg{vec_idx};"
    else:
        entities_binding = "  const std::vector<std::string> entities{};"

    has_any_img_condition = any(e.get("condition") for e in valid_entries)
    needs_entities = has_any_img_condition

    def _draw_lines(entry: dict, indent: str) -> list[str]:
        """Lines that set image_slot and call the right draw script."""
        img_id = entry["image"]
        animation = entry.get("animation") if isinstance(entry, dict) else None
        if not animation or not isinstance(animation, dict):
            return [
                f"{indent}id(image_slot) = &id({img_id});",
                f"{indent}id(draw_image_static).execute(arg0, arg1, arg2, arg3);",
            ]
        _DIRECTION_INT = {"left_right": 0, "right_left": 1, "up_down": 2, "down_up": 3}
        direction = animation.get("direction", "left_right")
        duration_ms = int(float(animation.get("duration", 3)) * 1000)
        extra_images = list(animation.get("extra_images") or [])
        all_images = [img_id] + extra_images
        n = len(all_images)
        if n > 1:
            per_ms = duration_ms // n
            lines = [f"{indent}{{"]  # open block
            lines.append(f"{indent}  uint32_t _per_ms = {per_ms}U;")
            lines.append(f"{indent}  int _idx = (int)((millis() / _per_ms) % {n}U);")
            for i, img in enumerate(all_images[:-1]):
                kw = "if" if i == 0 else "else if"
                lines.append(f"{indent}  {kw} (_idx == {i}) id(image_slot) = &id({img});")
            lines.append(f"{indent}  else id(image_slot) = &id({all_images[-1]});")
            if direction == "none":
                lines.append(f"{indent}  id(draw_image_static).execute(arg0, arg1, arg2, arg3);")
            else:
                dir_int = _DIRECTION_INT.get(direction, 0)
                lines.append(f"{indent}  id(draw_image_anim).execute(arg0, arg1, arg2, arg3, {duration_ms}, {dir_int});")
            lines.append(f"{indent}}}")
        else:
            lines = [f"{indent}id(image_slot) = &id({img_id});"]
            if direction == "none":
                lines.append(f"{indent}id(draw_image_static).execute(arg0, arg1, arg2, arg3);")
            else:
                dir_int = _DIRECTION_INT.get(direction, 0)
                lines.append(f"{indent}id(draw_image_anim).execute(arg0, arg1, arg2, arg3, {duration_ms}, {dir_int});")
        return lines

    # -----------------------------------------------------------------------
    # Simple path: single entry with no image-selection condition
    # -----------------------------------------------------------------------
    if not has_any_img_condition and len(valid_entries) == 1:
        body_lines = []
        if needs_entities:
            body_lines.append(entities_binding)
        body_lines.extend(_draw_lines(valid_entries[0], "  "))
        return f"[=]({sig}) {{\n" + "\n".join(body_lines) + "\n}"

    # -----------------------------------------------------------------------
    # if / else-if chain for image selection
    # -----------------------------------------------------------------------
    branches: list[tuple[str, str, dict]] = []
    keyword = "if"
    fallback_entry = None

    for entry in valid_entries:
        cond_expr = entry.get("condition")
        if not cond_expr:
            fallback_entry = entry
            break
        expr = build_expression(cond_expr)
        if not expr:
            continue
        branches.append((keyword, expr, entry))
        keyword = "else if"

    if not branches and fallback_entry is None:
        return None

    body_lines = []
    if needs_entities:
        body_lines.append(entities_binding)

    for kw, expr, entry in branches:
        body_lines.append(f"  {kw} ({expr}) {{")
        body_lines.extend(_draw_lines(entry, "    "))
        body_lines.append("  }")

    if fallback_entry:
        body_lines.append("  else {" if branches else "")
        body_lines.extend(_draw_lines(fallback_entry, "    " if branches else "  "))
        if branches:
            body_lines.append("  }")

    return f"[=]({sig}) {{\n" + "\n".join(filter(None, body_lines)) + "\n}"


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
    requires_fast_refresh = (
        config["requires_fast_refresh"] if "requires_fast_refresh" in config
        else _get_animation_fast_refresh(config)
    )
    
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
    requires_fast_refresh = (
        config["requires_fast_refresh"] if "requires_fast_refresh" in config
        else _get_animation_fast_refresh(config)
    )
    
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
