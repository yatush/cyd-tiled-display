"""Comprehensive validation for tile configuration.

This module handles all validation logic including:
- Screen structure validation
- Tile type and position validation
- Script and global variable validation
- Dynamic entity validation
- Activation variable validation
"""
from typing import Any

from .script_types import validate_script_type
from .data_collection import (
    collect_referenced_scripts,
    collect_referenced_globals,
    collect_dynamic_entities
)
from .schema import (
    VALID_TILE_TYPES,
    VALID_FLAGS,
    TileType,
    SCHEMA_DEF,
)

__all__ = [
    "validate_tiles_config",
]


def validate_tiles_config(
    screens: list[dict],
    available_scripts: dict | None = None,
    available_globals: set | None = None
) -> None:
    """Validate the complete tiles configuration.
    
    Performs all validations:
    - Screen IDs are unique and non-empty
    - Screen flags are valid
    - Exactly one screen with BASE flag
    - All non-TEMPORARY screens can navigate back to BASE screen via move_page tiles
    - Screens are not empty (have at least one tile)
    - No duplicate x,y positions within screens (except conditional cycle_entity tiles)
    - Coordinates are non-negative integers
    - Valid tile types only
    - Valid move_page destinations
    - Valid activation_var names (match dynamic entities)
    - Required fields present for each tile type
    - Action tiles have at least perform or location_perform
    - All referenced scripts are available and have correct types
    - All referenced boolean globals in conditions are available
    
    Args:
        screens: List of screen configurations
        available_scripts: Dict of available scripts with parameters
        available_globals: Set of available boolean globals
    
    Raises:
        ValueError: With detailed error messages if validation fails
    """
    
    # Collect all screen IDs, dynamic entities, and validate BASE flag
    valid_screen_ids = set()
    valid_dynamic_entities = set()
    base_screen_count = 0
    seen_screen_ids = set()
    
    # PASS 1: Validate screen structure and collect IDs
    for idx, screen in enumerate(screens):
        screen_id = screen.get("id", "")
        
        # Validate screen has ID
        if not screen_id:
            raise ValueError(f"Screen at index {idx} has no 'id' field")
        
        # Validate screen ID is unique
        if screen_id in seen_screen_ids:
            raise ValueError(f"Duplicate screen ID: '{screen_id}'. Screen IDs must be unique.")
        seen_screen_ids.add(screen_id)
        valid_screen_ids.add(screen_id)
        
        flags = screen.get("flags", [])
        
        # Validate screen flags are valid
        if flags:
            invalid_flags = [flag for flag in flags if flag not in VALID_FLAGS]
            if invalid_flags:
                raise ValueError(
                    f"Screen '{screen_id}': Invalid flag(s): {', '.join(invalid_flags)}. "
                    f"Valid flags are: {', '.join(sorted(VALID_FLAGS))}"
                )
        
        if "BASE" in flags:
            base_screen_count += 1
        
        tiles = screen.get("tiles", [])
        
        # Validate screen is not empty
        if not tiles or len(tiles) == 0:
            raise ValueError(f"Screen '{screen_id}': has no tiles. Each screen must have at least one tile.")
        
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            
            # Validate tile type is known
            if tile_type not in VALID_TILE_TYPES:
                raise ValueError(
                    f"Screen '{screen_id}': Unknown tile type '{tile_type}'. "
                    f"Valid tile types are: {', '.join(sorted(VALID_TILE_TYPES))}"
                )
            
            config = tile[tile_type]
            
            # Validate against schema
            validate_tile_schema(tile_type, config, screen_id)

            x = config.get("x", 0)
            y = config.get("y", 0)
            
            # Validate coordinates are non-negative integers
            if not isinstance(x, int) or x < 0:
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile: x coordinate must be a non-negative integer, got {x}")
            if not isinstance(y, int) or y < 0:
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile: y coordinate must be a non-negative integer, got {y}")
            
            try:
                x_span = int(config.get("x_span", 1))
                y_span = int(config.get("y_span", 1))
            except (ValueError, TypeError):
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile: spans must be integers")
            
            # Validate bounds if screen dimensions are known
            screen_rows = screen.get("rows")
            screen_cols = screen.get("cols")
            
            if screen_cols is not None:
                if x + x_span > screen_cols:
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}) with span {x_span} "
                        f"exceeds screen width of {screen_cols}"
                    )
            
            if screen_rows is not None:
                if y + y_span > screen_rows:
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}) with span {y_span} "
                        f"exceeds screen height of {screen_rows}"
                    )
            
            # Collect dynamic entities from various tile types
            if tile_type == TileType.HA_ACTION.value or tile_type == TileType.TITLE.value:
                entities_config = config.get("entities", "")
                collect_dynamic_entities(entities_config, valid_dynamic_entities)
            
            if tile_type == TileType.TOGGLE_ENTITY.value:
                dynamic_entity = config.get("dynamic_entity", "")
                if dynamic_entity:
                    valid_dynamic_entities.add(dynamic_entity)
            
            if tile_type == TileType.CYCLE_ENTITY.value:
                dynamic_entity = config.get("dynamic_entity", "")
                if dynamic_entity:
                    valid_dynamic_entities.add(dynamic_entity)
    
    # Validate exactly one BASE screen
    if base_screen_count == 0:
        raise ValueError("No screen with 'BASE' flag found. Exactly one screen must have the BASE flag.")
    elif base_screen_count > 1:
        raise ValueError(f"Multiple screens with 'BASE' flag found ({base_screen_count}). Only one screen must have the BASE flag.")
    
    # Find the BASE screen ID
    base_screen_id = None
    for screen in screens:
        flags = screen.get("flags", [])
        if "BASE" in flags:
            base_screen_id = screen.get("id")
            break
    
    # Validate all screens can navigate back to BASE screen
    _validate_base_screen_reachability(screens, base_screen_id, valid_screen_ids)
    
    # PASS 2: Validate tile content and relationships
    for screen in screens:
        screen_id = screen.get("id", "")
        tiles = screen.get("tiles", [])
        
        _validate_tile_positions(screen_id, tiles)
        
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            config = tile[tile_type]
            x = config.get("x", 0)
            y = config.get("y", 0)
            
            # Validate required fields for each tile type
            _validate_tile_fields(screen_id, tile_type, config, x, y)
            
            # Validate activation_var dynamic_entity is a valid dynamic entity
            activation_var = config.get("activation_var", None)
            if activation_var:
                var_name = activation_var.get("dynamic_entity", "")
                
                if var_name and var_name not in valid_dynamic_entities:
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                        f"activation_var dynamic_entity '{var_name}' is not a valid dynamic entity. "
                        f"Valid dynamic entities are: {', '.join(sorted(valid_dynamic_entities))}"
                    )
            
            # Validate dynamic_entry dynamic_entity is a valid dynamic entity
            dynamic_entry = config.get("dynamic_entry", None)
            if dynamic_entry:
                entry_name = dynamic_entry.get("dynamic_entity", "")
                
                if entry_name and entry_name not in valid_dynamic_entities:
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                        f"dynamic_entry dynamic_entity '{entry_name}' is not a valid dynamic entity. "
                        f"Valid dynamic entities are: {', '.join(sorted(valid_dynamic_entities))}"
                    )
            
            # Validate move_page destination is a valid screen ID
            if tile_type == TileType.MOVE_PAGE.value:
                destination = config.get("destination", "")
                if destination and destination not in valid_screen_ids:
                    raise ValueError(
                        f"Screen '{screen_id}', move_page tile at ({x}, {y}): "
                        f"destination '{destination}' is not a valid screen ID. "
                        f"Valid screen IDs are: {', '.join(sorted(valid_screen_ids))}"
                    )
    
    # Validate all referenced scripts are available with correct types
    if available_scripts is not None:
        _validate_script_references(screens, available_scripts)
    
    # Validate all referenced globals are available
    if available_globals is not None:
        _validate_global_references(screens, available_globals)


def _validate_tile_positions(screen_id, tiles):
    """Validate tile positions and stacking rules.
    
    Rules:
    1. Multiple tiles can exist at the same (x, y) position.
    2. If multiple tiles exist at the same position, they MUST all have an 'activation_var'.
    3. All tiles at the same position MUST use the same 'dynamic_entity' in their 'activation_var'.
    4. Tiles with spans occupy multiple grid cells. Overlap rules apply to all occupied cells.
    """
    # Map each grid cell to the list of tiles occupying it
    grid_cells = {} # (x, y) -> list of (tile_type, config)
    
    for tile in tiles:
        tile_type = list(tile.keys())[0]
        config = tile[tile_type]
        
        try:
            x = int(config.get("x", 0))
            y = int(config.get("y", 0))
            x_span = int(config.get("x_span", 1))
            y_span = int(config.get("y_span", 1))
        except (ValueError, TypeError):
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile: coordinates and spans must be integers")
        
        if x_span < 1:
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): x_span must be at least 1")
        if y_span < 1:
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): y_span must be at least 1")
            
        # Add tile to all cells it occupies
        for i in range(x_span):
            for j in range(y_span):
                pos_key = (x + i, y + j)
                if pos_key not in grid_cells:
                    grid_cells[pos_key] = []
                grid_cells[pos_key].append((tile_type, config))

    for pos_key, tile_list in grid_cells.items():
        if len(tile_list) > 1:
            x, y = pos_key
            
            # Check if all have activation_var
            for t_type, t_config in tile_list:
                if not t_config.get("activation_var"):
                    raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) but "
                        f"{t_type} tile is missing 'activation_var'. "
                        f"All overlapping tiles must have an 'activation_var' to control visibility."
                    )
            
            # Check if all have the same dynamic_entity and unique value sets
            first_var = tile_list[0][1].get("activation_var", {}).get("dynamic_entity")
            seen_value_sets = [] # List of sets of values
            
            for t_type, t_config in tile_list:
                act_var = t_config.get("activation_var", {})
                current_var = act_var.get("dynamic_entity")
                
                if current_var != first_var:
                    raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) must use the same "
                        f"activation variable (dynamic_entity). Found '{first_var}' and '{current_var}'."
                    )
                
                # Check for duplicate value sets (ignore order)
                val = act_var.get("value", "")
                if isinstance(val, str):
                    current_vals = set(v.strip() for v in val.split(","))
                else:
                    current_vals = {str(val)}
            
                if current_vals in seen_value_sets:
                     val_str = ", ".join(sorted(list(current_vals)))
                     raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) have the same "
                        f"exact activation values: [{val_str}] for variable '{first_var}'. "
                        f"Each overlapping tile must have a unique set of activation values."
                    )
                seen_value_sets.append(current_vals)


def _validate_base_screen_reachability(screens, base_screen_id, valid_screen_ids):
    """Validate that all non-TEMPORARY screens can navigate back to the BASE screen.
    
    Builds a directed graph of screen connections via move_page tiles and checks
    that every non-TEMPORARY screen has a path to the BASE screen.
    
    Note: TEMPORARY screens automatically return to the BASE screen, so they are
    not required to have explicit move_page navigation back to BASE.
    
    Args:
        screens: List of screen configurations
        base_screen_id: ID of the BASE screen
        valid_screen_ids: Set of all valid screen IDs
        
    Raises:
        ValueError: If any non-TEMPORARY screen cannot reach the BASE screen
    """
    from collections import deque
    
    # Collect TEMPORARY screen IDs
    temporary_screen_ids = set()
    for screen in screens:
        flags = screen.get("flags", [])
        if "TEMPORARY" in flags:
            temporary_screen_ids.add(screen.get("id", ""))
    
    # Build a graph: screen_id -> set of screens it can navigate to
    navigation_graph = {screen_id: set() for screen_id in valid_screen_ids}
    
    for screen in screens:
        screen_id = screen.get("id", "")
        tiles = screen.get("tiles", [])
        
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            if tile_type == TileType.MOVE_PAGE.value:
                config = tile[tile_type]
                destination = config.get("destination", "")
                if destination and destination in valid_screen_ids:
                    navigation_graph[screen_id].add(destination)
    
    # For each non-TEMPORARY, non-BASE screen, check if it can reach BASE screen
    # (either directly, via TEMPORARY screens, or via other navigation)
    unreachable_screens = []
    
    for screen_id in valid_screen_ids:
        # Skip BASE screen (it's the target)
        if screen_id == base_screen_id:
            continue
        
        # Skip TEMPORARY screens (they automatically return to BASE)
        if screen_id in temporary_screen_ids:
            continue
        
        # BFS to find if we can reach BASE screen or a TEMPORARY screen from this screen
        visited = set()
        queue = deque([screen_id])
        can_reach_base = False
        
        while queue:
            current = queue.popleft()
            # Reached BASE directly
            if current == base_screen_id:
                can_reach_base = True
                break
            # Reached a TEMPORARY screen (which will auto-return to BASE)
            if current in temporary_screen_ids:
                can_reach_base = True
                break
            
            if current in visited:
                continue
            visited.add(current)
            
            for neighbor in navigation_graph.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        if not can_reach_base:
            unreachable_screens.append(screen_id)
    
    if unreachable_screens:
        raise ValueError(
            f"The following screens cannot navigate back to the BASE screen '{base_screen_id}': "
            f"{', '.join(sorted(unreachable_screens))}. "
            f"Each non-TEMPORARY screen must have a path (via move_page tiles) to reach the BASE screen or a TEMPORARY screen."
        )


def _validate_script_references(screens, available_scripts):
    """Validate all referenced scripts are available with correct types."""
    referenced_scripts = collect_referenced_scripts(screens)
    
    for script_id, usages in referenced_scripts.items():
        # Check if script is defined
        script_info = None
        for script_key in available_scripts:
            if str(script_key) == str(script_id):
                script_info = available_scripts[script_key]
                break
        
        if script_info is None:
            available_script_names = [str(s) for s in available_scripts.keys()]
            raise ValueError(
                f"Script '{script_id}' is referenced in the tile configuration but not defined. "
                f"Available scripts are: {', '.join(sorted(available_script_names)) if available_script_names else 'None'}"
            )
        
        # Validate each usage has correct script type
        for usage in usages:
            expected_type = usage['type']
            context = (
                f"Screen '{usage['screen']}', {usage['tile_type']} tile at ({usage['x']}, {usage['y']}), "
                f"{usage.get('usage', 'display')}"
            )
            provided_params = usage.get('params', {})
            
            # Validate parameters if provided (check for missing/unknown params first)
            if 'params' in usage:
                _validate_script_parameters(script_id, script_info, usage['params'], context)
            
            validate_script_type(script_id, script_info, expected_type, context, provided_params)


def _validate_script_parameters(script_id, script_info, provided_params, context):
    """Validate that provided parameters match the script definition."""
    script_params = script_info.get('parameters', {})
    provided_params = provided_params or {}
    
    # Check for unknown parameters
    for param in provided_params:
        if param not in script_params:
            raise ValueError(
                f"{context}: Unknown parameter '{param}' provided for script '{script_id}'. "
                f"Valid parameters are: {', '.join(sorted(script_params.keys()))}"
            )
    
    # Check for missing required parameters
    # Implicit parameters are those that are automatically provided by the system
    implicit_params = {
        'x', 'y', 'entities', 'name', 'presentation_name', 'is_on', 'options', 'state',
        'x_start', 'x_end', 'y_start', 'y_end'
    }
    
    for param, param_type in script_params.items():
        if param not in implicit_params and param not in provided_params:
            # If it's not implicit and not provided, it's missing
            # Note: We assume all script parameters are required unless they have a default value
            # But ESPHome script parameters don't support default values in the definition easily accessible here
            # So we assume they are required.
            raise ValueError(
                f"{context}: Missing required parameter '{param}' for script '{script_id}'."
            )


def _validate_global_references(screens, available_globals):
    """Validate all referenced globals are available."""
    referenced_globals = collect_referenced_globals(screens)
    # Convert ID objects to strings for comparison
    available_global_names = {str(global_id) for global_id in available_globals}
    missing_globals = referenced_globals - available_global_names
    
    if missing_globals:
        raise ValueError(
            f"The following boolean global variables are referenced in condition expressions but not defined: {', '.join(sorted(missing_globals))}. "
            f"Available boolean globals are: {', '.join(sorted(str(g) for g in available_globals)) if available_globals else 'None'}"
        )


def _validate_tile_fields(
    screen_id: str,
    tile_type: str,
    config: dict,
    x: int,
    y: int
) -> None:
    """Validate tile-specific business logic that schema cannot enforce.
    
    Note: Basic field presence and type checks are handled by schema.py.
    This function handles cross-field validation and business rules.
    
    Args:
        screen_id: ID of the screen containing the tile
        tile_type: Type of the tile
        config: Tile configuration dict
        x: X coordinate
        y: Y coordinate
        
    Raises:
        ValueError: If business logic validation fails
    """
    if tile_type == TileType.HA_ACTION.value:
        perform = config.get("perform", [])
        location_perform = config.get("location_perform", [])
        
        # Business rule: at least one action must be specified
        if (not perform or len(perform) == 0) and (not location_perform or len(location_perform) == 0):
            raise ValueError(
                f"Screen '{screen_id}', ha_action tile at ({x}, {y}): "
                f"At least one of 'perform' or 'location_perform' must be specified"
            )
            
        requires_fast_refresh = config.get("requires_fast_refresh")
        if requires_fast_refresh:
             _validate_condition_expression(requires_fast_refresh, f"Screen '{screen_id}', ha_action tile at ({x}, {y}), requires_fast_refresh")
    
    elif tile_type == TileType.FUNCTION.value:
        on_press = config.get("on_press", "")
        on_release = config.get("on_release", "")
        
        # Business rule: at least one callback must be specified
        if not on_press and not on_release:
            raise ValueError(
                f"Screen '{screen_id}', function tile at ({x}, {y}): "
                f"at least one of 'on_press' or 'on_release' must be specified"
            )
    
    elif tile_type == TileType.CYCLE_ENTITY.value:
        options = config.get("options", [])
        
        # Validate each option has required fields (detailed check beyond schema)
        for idx, option in enumerate(options):
            if not isinstance(option, dict):
                raise ValueError(
                    f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                    f"option {idx} must be a dict"
                )
            if "entity" not in option:
                raise ValueError(
                    f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                    f"option {idx} missing 'entity' field"
                )
            if "label" not in option:
                raise ValueError(
                    f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                    f"option {idx} missing 'label' field"
                )


def _validate_condition_expression(expression, context):
    """Validate condition expression structure recursively."""
    if not expression:
        return

    if isinstance(expression, str):
        return  # Valid single global/function

    if isinstance(expression, dict):
        # Check for unknown keys
        valid_keys = {'conditions', 'operator'}
        unknown_keys = set(expression.keys()) - valid_keys
        if unknown_keys:
             raise ValueError(f"{context}: Unknown keys in condition expression: {', '.join(sorted(unknown_keys))}")

        conditions = expression.get("conditions")
        operator = expression.get("operator")
        
        if operator and operator.upper() not in ["AND", "OR", "NOT"]:
             raise ValueError(f"{context}: Invalid operator '{operator}'. Must be AND, OR, or NOT")

        if conditions is None:
             raise ValueError(f"{context}: Condition expression must have 'conditions' field")

        if isinstance(conditions, str):
            # Single condition is fine
            pass
        elif isinstance(conditions, list):
            if len(conditions) == 0:
                raise ValueError(f"{context}: 'conditions' list cannot be empty")
            
            if len(conditions) > 1 and not operator:
                 raise ValueError(f"{context}: 'operator' field is required when specifying multiple conditions")
            
            if operator and operator.upper() == "NOT" and len(conditions) != 1:
                 raise ValueError(f"{context}: NOT operator only accepts exactly one condition")

            for idx, item in enumerate(conditions):
                _validate_condition_expression(item, f"{context} condition {idx}")
        else:
            raise ValueError(f"{context}: 'conditions' must be a string or a list")

        return

    raise ValueError(f"{context}: Invalid condition expression type {type(expression).__name__}. Use string or dict with 'conditions' field.")



def validate_tile_schema(tile_type: str, tile_config: dict, screen_id: str) -> None:
    """Validate tile configuration against schema.json definition."""
    # Find type definition
    type_def = next((t for t in SCHEMA_DEF['types'] if t['type'] == tile_type), None)
    if not type_def:
        # Should be caught by VALID_TILE_TYPES check, but just in case
        raise ValueError(f"Screen '{screen_id}': Unknown tile type '{tile_type}'")
    
    x = tile_config.get('x', '?')
    y = tile_config.get('y', '?')
    context = f"Screen '{screen_id}', {tile_type} tile at ({x},{y})"

    # Validate common fields
    for field in SCHEMA_DEF['common']:
        name = field['name']
        if name in tile_config:
            validate_field_value(tile_config[name], field, context)
        elif not field.get('optional', False):
            raise ValueError(f"{context} missing required field: '{name}'")
            
    # Validate specific fields
    for field in type_def['fields']:
        name = field['name']
        if name in tile_config:
            validate_field_value(tile_config[name], field, context)
        elif not field.get('optional', False):
            raise ValueError(f"{context} missing required field: '{name}'")


def validate_field_value(value: Any, field_def: dict, context: str) -> None:
    """Validate a single field value against its definition."""
    field_type = field_def['type']
    field_name = field_def['name']
    
    if field_type == 'number':
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{context}: Field '{field_name}' must be a non-negative integer, got {value}")
            
    elif field_type in ['string', 'page_select', 'dynamic_entity_select', 'ha_entity_list']:
        if isinstance(value, list):
            # Allow list of strings for ha_entity_list
            if field_type == 'ha_entity_list':
                for idx, item in enumerate(value):
                    if not isinstance(item, str) or not item.strip():
                        raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a non-empty string")
            else:
                raise ValueError(f"{context}: Field '{field_name}' must be a string, got list")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{context}: Field '{field_name}' must be a non-empty string")
            
    elif field_type == 'boolean':
        if not isinstance(value, bool):
            raise ValueError(f"{context}: Field '{field_name}' must be a boolean, got {value}")
            
    elif field_type == 'display_list':
        if not isinstance(value, list):
            raise ValueError(f"{context}: Field '{field_name}' must be a list")
        if not value:
             raise ValueError(f"{context}: Field '{field_name}' cannot be empty")
        for idx, item in enumerate(value):
            if isinstance(item, str):
                if not item.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} cannot be empty string")
            elif isinstance(item, dict):
                if len(item) != 1:
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} must have exactly one key")
                key = list(item.keys())[0]
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} key must be non-empty string")
            else:
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be string or dict")
                
    elif field_type == 'entity_list':
        if not isinstance(value, list):
            raise ValueError(f"{context}: Field '{field_name}' must be a list")
        if not value:
             raise ValueError(f"{context}: Field '{field_name}' cannot be empty")
        for idx, item in enumerate(value):
            if isinstance(item, str):
                if not item.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} cannot be empty string")
                continue
                
            if not isinstance(item, dict):
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a dict or string")
            if not any(k in item for k in ['entity', 'dynamic_entity']):
                 raise ValueError(f"{context}: Field '{field_name}' item {idx} must have 'entity' or 'dynamic_entity'")
            
            if 'entity' in item and (not isinstance(item['entity'], str) or not item['entity'].strip()):
                 raise ValueError(f"{context}: Field '{field_name}' item {idx} 'entity' must be a non-empty string")
            
            if 'dynamic_entity' in item and (not isinstance(item['dynamic_entity'], str) or not item['dynamic_entity'].strip()):
                 raise ValueError(f"{context}: Field '{field_name}' item {idx} 'dynamic_entity' must be a non-empty string")
                 
    elif field_type == 'script_list':
        if not isinstance(value, list):
            raise ValueError(f"{context}: Field '{field_name}' must be a list")
        for idx, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a non-empty string")
                
    elif field_type == 'object':
        if not isinstance(value, dict):
            raise ValueError(f"{context}: Field '{field_name}' must be an object (dict)")
        
        object_fields = field_def.get('objectFields', [])
        for f in object_fields:
            key = f['key']
            if key in value:
                # Construct a temporary field def for recursive validation
                temp_def = {'name': f"{field_name}.{key}", 'type': f['type']}
                if 'objectFields' in f:
                    temp_def['objectFields'] = f['objectFields']
                validate_field_value(value[key], temp_def, context)
            elif not f.get('optional', False):
                raise ValueError(f"{context}: Field '{field_name}' missing required key '{key}'")

    elif field_type == 'condition_logic':
        _validate_condition_expression(value, f"{context} field '{field_name}'")
