"""Tile generation functions - converts YAML tile configs to C++ code."""
from .tile_utils import (
    format_display_list, format_functions_list, format_entity_value,
    build_fast_refresh_lambda, format_entity_cpp, get_tile_modifiers,
    flags_to_cpp
)


def _generate_base_tile_args(config):
    """Extract base tile arguments (x, y, display)."""
    x = config.get("x", 0)
    y = config.get("y", 0)
    display = config.get("display", [])
    display_cpp = format_display_list(display)
    return x, y, display_cpp


def _apply_modifiers(tile_cpp, config, extra_modifiers=None):
    """Apply common modifiers to the tile C++ object."""
    method_chains = []
    if extra_modifiers:
        method_chains.extend(extra_modifiers)
        
    method_chains.extend(get_tile_modifiers(config))
    
    if method_chains:
        tile_cpp = f'({tile_cpp})'
        for method in method_chains:
            tile_cpp += f'->{method}'
    
    return tile_cpp


def generate_action_tile(config):
    """Generate C++ for an action tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
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
                f"Tile at ({x}, {y}): display_page_if_no_entity requires at least one dynamic_entity"
            )
    
    perform_cpp = format_functions_list(perform)
    location_perform_cpp = format_functions_list(location_perform)
    entity_cpp = format_entity_cpp(entity_values)
    
    args = [str(x), str(y), display_cpp]
    
    if perform_cpp and location_perform_cpp:
        args.append(f"{{ {perform_cpp} }}")
        args.append(f"{{ {location_perform_cpp} }}")
    elif perform_cpp:
        args.append(f"{{ {perform_cpp} }}")
    elif location_perform_cpp:
        args.append("{}")
        args.append(f"{{ {location_perform_cpp} }}")
    
    args.append(entity_cpp)
    
    tile_cpp = f'new HAActionTile({", ".join(args)})'
    
    modifiers = []
    # Apply specific modifiers before common ones
    if display_page:
        modifiers.append(f'setDisplayPageIfNoEntity(&id({display_page}))')
    
    fast_refresh_lambda = build_fast_refresh_lambda(requires_fast_refresh)
    if fast_refresh_lambda:
        modifiers.append(f'setRequiresFastRefreshFunc({fast_refresh_lambda})')
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers)
    tile_cpp += ','
    return tile_cpp


def generate_title_tile(config):
    """Generate C++ for a title tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
    entities_config = config.get("entities", "")
    entity_values = format_entity_value(entities_config)
    entity_cpp = format_entity_cpp(entity_values)
    
    tile_cpp = f'new TitleTile({x}, {y}, {display_cpp}, {entity_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config)
    tile_cpp += ','
    return tile_cpp


def generate_move_page_tile(config):
    """Generate C++ for a move page tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
    destination = config.get("destination", "")
    dynamic_entry = config.get("dynamic_entry", None)
    
    tile_cpp = f'new MovePageTile({x}, {y}, {display_cpp}, &id({destination}))'
    
    modifiers = []
    if dynamic_entry:
        dynamic_entity = dynamic_entry.get("dynamic_entity", "")
        value = dynamic_entry.get("value", "")
        if dynamic_entity and value:
            modifiers.append(f'setDynamicEntry("{dynamic_entity}", {{ "{value}" }})')
        else:
            raise ValueError(f"dynamic_entry at ({x}, {y}) must have both 'dynamic_entity' and 'value'")
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers)
    tile_cpp += ','
    return tile_cpp


def generate_function_tile(config):
    """Generate C++ for a function tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
    on_press = config.get("on_press", "nullptr")
    on_release = config.get("on_release", "nullptr")
    
    if on_release != "nullptr":
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, &id({on_press}), &id({on_release}))'
    else:
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, &id({on_press}))'
    
    tile_cpp = _apply_modifiers(tile_cpp, config)
    tile_cpp += ','
    return tile_cpp


def generate_toggle_entity_tile(config):
    """Generate C++ for a toggle entity tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
    dynamic_entity = config.get("dynamic_entity", "")
    entity = config.get("entity", "")
    presentation_name = config.get("presentation_name", "")
    initially_chosen = config.get("initially_chosen", False)
    
    if not dynamic_entity:
        raise ValueError(f"toggle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not entity:
        raise ValueError(f"toggle_entity tile at ({x}, {y}) must have 'entity' field")
    if not presentation_name:
        raise ValueError(f"toggle_entity tile at ({x}, {y}) must have 'presentation_name' field")
    
    initially_chosen_cpp = "true" if initially_chosen else "false"
    
    tile_cpp = f'new ToggleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", "{entity}", "{presentation_name}", {initially_chosen_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config)
    tile_cpp += ','
    return tile_cpp


def generate_cycle_entity_tile(config):
    """Generate C++ for a cycle entity tile."""
    x, y, display_cpp = _generate_base_tile_args(config)
    
    dynamic_entity = config.get("dynamic_entity", "")
    options = config.get("options", [])
    reset_on_leave = config.get("reset_on_leave", False)
    
    if not dynamic_entity:
        raise ValueError(f"cycle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not options or len(options) == 0:
        raise ValueError(f"cycle_entity tile at ({x}, {y}) must have 'options' list with at least one item")
    
    options_cpp_pairs = []
    
    for option_item in options:
        if isinstance(option_item, dict):
            entity = option_item.get("entity", "")
            label = option_item.get("label", "")
            if entity and label:
                options_cpp_pairs.append(f'{{ "{entity}", "{label}" }}')
            else:
                raise ValueError(f"Each option item must have both 'entity' and 'label' fields at ({x}, {y})")
        else:
            raise ValueError(f"Options must be dicts with 'entity' and 'label' fields at ({x}, {y})")
    
    options_cpp = "{ " + ", ".join(options_cpp_pairs) + " }"
    reset_on_leave_cpp = "true" if reset_on_leave else "false"
    
    tile_cpp = f'new CycleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", {options_cpp}, {reset_on_leave_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config)
    tile_cpp += ','
    return tile_cpp


def generate_tile_cpp(tile):
    """Generate C++ code for a single tile."""
    if "ha_action" in tile:
        return generate_action_tile(tile["ha_action"])
    elif "move_page" in tile:
        return generate_move_page_tile(tile["move_page"])
    elif "title" in tile:
        return generate_title_tile(tile["title"])
    elif "function" in tile:
        return generate_function_tile(tile["function"])
    elif "toggle_entity" in tile:
        return generate_toggle_entity_tile(tile["toggle_entity"])
    elif "cycle_entity" in tile:
        return generate_cycle_entity_tile(tile["cycle_entity"])
    else:
        return f'// Unknown tile structure: {list(tile.keys())}'
