"""Comprehensive validation for tile configuration.

This module handles all validation logic including:
- Screen structure validation
- Tile type and position validation
- Script and global variable validation
- Dynamic entity validation
- Activation variable validation
"""
from .script_types import validate_script_type
from .data_collection import (
    collect_referenced_scripts,
    collect_referenced_globals,
    collect_dynamic_entities
)


def validate_tiles_config(screens, available_scripts=None, available_globals=None):
    """Validate the complete tiles configuration.
    
    Performs all validations:
    - Screen IDs are unique and non-empty
    - Screen flags are valid
    - Exactly one screen with BASE flag
    - Screens are not empty (have at least one tile)
    - No duplicate x,y positions within screens (except conditional cycle_entity tiles)
    - Coordinates are non-negative integers
    - Valid tile types only
    - Valid move_page destinations
    - Valid activation_var names (match dynamic entities)
    - Required fields present for each tile type
    - Action tiles have at least perform or location_perform
    - No empty strings in lists (display, perform, location_perform, entities)
    - All referenced scripts are available and have correct types
    - All referenced boolean globals in conditions are available
    
    Args:
        screens: List of screen configurations
        available_scripts: Dict of available scripts with parameters
        available_globals: Set of available boolean globals
    
    Raises:
        ValueError: With detailed error messages if validation fails
    """
    # Valid ESPhome flags that can be used
    VALID_FLAGS = {"BASE", "TEMPORARY", "FAST_REFRESH"}
    VALID_TILE_TYPES = {"ha_action", "move_page", "title", "function", "toggle_entity", "cycle_entity"}
    
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
            x = config.get("x", 0)
            y = config.get("y", 0)
            
            # Validate coordinates are non-negative integers
            if not isinstance(x, int) or x < 0:
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile: x coordinate must be a non-negative integer, got {x}")
            if not isinstance(y, int) or y < 0:
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile: y coordinate must be a non-negative integer, got {y}")
            
            # Collect dynamic entities from various tile types
            if tile_type == "ha_action" or tile_type == "title":
                entities_config = config.get("entities", "")
                collect_dynamic_entities(entities_config, valid_dynamic_entities)
            
            if tile_type == "toggle_entity":
                dynamic_entity = config.get("dynamic_entity", "")
                if dynamic_entity:
                    valid_dynamic_entities.add(dynamic_entity)
            
            if tile_type == "cycle_entity":
                dynamic_entity = config.get("dynamic_entity", "")
                if dynamic_entity:
                    valid_dynamic_entities.add(dynamic_entity)
    
    # Validate exactly one BASE screen
    if base_screen_count == 0:
        raise ValueError("No screen with 'BASE' flag found. Exactly one screen must have the BASE flag.")
    elif base_screen_count > 1:
        raise ValueError(f"Multiple screens with 'BASE' flag found ({base_screen_count}). Only one screen must have the BASE flag.")
    
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
    
    # Validate all referenced scripts are available with correct types
    if available_scripts is not None:
        _validate_script_references(screens, available_scripts)
    
    # Validate all referenced globals are available
    if available_globals is not None:
        _validate_global_references(screens, available_globals)


def _validate_tile_positions(screen_id, tiles):
    """Validate no duplicate x,y positions in this screen (with exceptions for conditional tiles)."""
    positions = {}
    for tile in tiles:
        tile_type = list(tile.keys())[0]
        config = tile[tile_type]
        x = config.get("x", 0)
        y = config.get("y", 0)
        pos_key = (x, y)
        
        # Allow duplicate positions for cycle_entity tiles with activation_var (conditional display)
        is_conditional_cycle = tile_type == "cycle_entity" and config.get("activation_var") is not None
        
        if pos_key in positions and not is_conditional_cycle:
            raise ValueError(
                f"Screen '{screen_id}': Duplicate tile position ({x}, {y}). "
                f"Already has {positions[pos_key]}, cannot add another tile at same position."
            )
        
        # Only track position if not a conditional cycle_entity
        if not is_conditional_cycle:
            positions[pos_key] = tile_type


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
            validate_script_type(script_id, script_info, expected_type, context)


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


def _validate_tile_fields(screen_id, tile_type, config, x, y):
    """Validate required fields for each tile type.
    
    Args:
        screen_id: ID of the screen containing the tile
        tile_type: Type of the tile
        config: Tile configuration dict
        x: X coordinate
        y: Y coordinate
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    if tile_type == "ha_action":
        entities = config.get("entities", "")
        display = config.get("display", [])
        perform = config.get("perform", [])
        location_perform = config.get("location_perform", [])
        
        if not entities:
            raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): 'entities' field is required")
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
        
        # Check for empty strings in perform/location_perform lists
        if perform and isinstance(perform, list):
            empty_items = [i for i, item in enumerate(perform) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): 'perform' list contains empty values at indices {empty_items}")
        
        if location_perform and isinstance(location_perform, list):
            empty_items = [i for i, item in enumerate(location_perform) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): 'location_perform' list contains empty values at indices {empty_items}")
        
        if (not perform or len(perform) == 0) and (not location_perform or len(location_perform) == 0):
            raise ValueError(
                f"Screen '{screen_id}', ha_action tile at ({x}, {y}): "
                f"At least one of 'perform' or 'location_perform' must be specified"
            )
    
    elif tile_type == "title":
        entities = config.get("entities", "")
        display = config.get("display", [])
        
        if not entities:
            raise ValueError(f"Screen '{screen_id}', title tile at ({x}, {y}): 'entities' field is required")
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', title tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', title tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
    
    elif tile_type == "move_page":
        display = config.get("display", [])
        destination = config.get("destination", "")
        
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', move_page tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', move_page tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
        
        if not destination:
            raise ValueError(f"Screen '{screen_id}', move_page tile at ({x}, {y}): 'destination' field is required")
    
    elif tile_type == "function":
        display = config.get("display", [])
        on_press = config.get("on_press", "")
        
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', function tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', function tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
        
        if not on_press:
            raise ValueError(f"Screen '{screen_id}', function tile at ({x}, {y}): 'on_press' field is required")
    
    elif tile_type == "toggle_entity":
        display = config.get("display", [])
        dynamic_entity = config.get("dynamic_entity", "")
        entity = config.get("entity", "")
        presentation_name = config.get("presentation_name", "")
        
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
        
        if not dynamic_entity:
            raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}): 'dynamic_entity' field is required")
        if not entity:
            raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}): 'entity' field is required")
        if not presentation_name:
            raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}): 'presentation_name' field is required")
    
    elif tile_type == "cycle_entity":
        display = config.get("display", [])
        dynamic_entity = config.get("dynamic_entity", "")
        options = config.get("options", [])
        
        if not display or len(display) == 0:
            raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): 'display' field is required")
        
        # Check for empty strings in display list
        if isinstance(display, list):
            empty_items = [i for i, item in enumerate(display) if not isinstance(item, str) or not item.strip()]
            if empty_items:
                raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): 'display' list contains empty values at indices {empty_items}")
        
        if not dynamic_entity:
            raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): 'dynamic_entity' field is required")
        if not options or len(options) == 0:
            raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): 'options' field is required with at least one option")
        
        for option in options:
            if not isinstance(option, dict):
                raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): options must be dicts")
            if "entity" not in option or "label" not in option:
                raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): each option must have 'entity' and 'label' fields")
