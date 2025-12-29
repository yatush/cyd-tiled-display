"""Tile generation functions - converts YAML tile configs to C++ code."""
from typing import Any

from .tile_utils import (
    format_display_list, format_functions_list, format_entity_value,
    build_fast_refresh_lambda, format_entity_cpp, get_tile_modifiers,
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
]


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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int'), ('entities', 'string[]')])
    
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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int'), ('entities', 'string[]')])
    
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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int')])
    
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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int')])
    
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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int'), (['name', 'presentation_name'], 'string'), ('is_on', 'bool')])
    
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
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, [('x', 'int'), ('y', 'int'), ('name', 'string'), (['options', 'entities'], 'string[]')])
    
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
