"""Comprehensive validation for tile configuration.

This module handles all validation logic including:
- Screen structure validation
- Tile type and position validation
- Script and global variable validation
- Dynamic entity validation
- Activation variable validation
"""
from typing import Any

from .script_types import script_parameter_defaults, validate_script_type
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
    tile_schema,
    _validate_screen_background,
)

__all__ = [
    "validate_tiles_config",
]


def validate_tiles_config(
    screens: list[dict],
    available_scripts: dict | None = None,
    available_globals: set | None = None,
    declared_dynamic_entities: list[str] | None = None,
    available_images: set | None = None,
    available_screen_images: set | None = None,
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
    - All dynamic_entity references match entries in declared_dynamic_entities (when provided)
    - All image references in tiles point to a known image ID (when available_images provided)
    
    Args:
        screens: List of screen configurations
        available_scripts: Dict of available scripts with parameters
        available_globals: Set of available boolean globals
        declared_dynamic_entities: Explicit list of valid dynamic entity names from the
            top-level ``dynamic_entities`` key.  When provided every ``dynamic_entity``
            reference found in any tile must be present in this list.
        available_images: Set of image IDs present in the global images store.  When
            provided every ``image`` reference inside a tile's ``display_assets`` list is
            checked against this set.
    
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
            
            # Validate that TEMPORARY pages cannot be BASE
            if "TEMPORARY" in flags and "BASE" in flags:
                raise ValueError(
                    f"Screen '{screen_id}': A TEMPORARY page cannot be a BASE page. "
                    f"Remove either the TEMPORARY or BASE flag."
                )
        
        if "BASE" in flags:
            base_screen_count += 1

        try:
            _validate_screen_background(screen.get("background"))
        except Exception as e:
            raise ValueError(f"Screen '{screen_id}': {e}") from e
        
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
            if tile_type in (TileType.HA_ACTION.value, TileType.TITLE.value, TileType.BLIND_POSITION.value):
                entities_config = config.get("entities", "")
                collect_dynamic_entities(entities_config, valid_dynamic_entities)
            if tile_type == TileType.HA_ACTION.value and config.get("long_dynamic_entity"):
                valid_dynamic_entities.add(config["long_dynamic_entity"])
            
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

            # Delegate structural & extra-key checks (PREVENT_EXTRA, animation bounds, etc.) to schema.py
            try:
                tile_schema({tile_type: config})
            except Exception as e:
                raise ValueError(f"Screen '{screen_id}', {tile_type} tile at ({x},{y}): {e}") from e
            
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
                entries = dynamic_entry if isinstance(dynamic_entry, list) else [dynamic_entry]
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    entry_name = entry.get("dynamic_entity", "")
                    if entry_name and entry_name not in valid_dynamic_entities:
                        raise ValueError(
                            f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                            f"dynamic_entry dynamic_entity '{entry_name}' is not a valid dynamic entity. "
                            f"Valid dynamic entities are: {', '.join(sorted(valid_dynamic_entities))}"
                        )
            
            if tile_type == TileType.HA_ACTION.value:
                if config.get("long_dynamic_entity") and not config.get("long_destination"):
                    raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): long_dynamic_entity requires long_destination")
                destination = config.get("long_destination")
                if destination and destination not in valid_screen_ids:
                    raise ValueError(f"Screen '{screen_id}', ha_action tile at ({x}, {y}): long_destination '{destination}' is not a valid screen ID")

            # Validate move_page destination is a valid screen ID
            if tile_type == TileType.MOVE_PAGE.value:
                destination = config.get("destination", "")
                if destination and destination not in valid_screen_ids:
                    raise ValueError(
                        f"Screen '{screen_id}', move_page tile at ({x}, {y}): "
                        f"destination '{destination}' is not a valid screen ID. "
                        f"Valid screen IDs are: {', '.join(sorted(valid_screen_ids))}"
                    )
    
    # Validate all dynamic_entity references against the declared list (when provided)
    if declared_dynamic_entities is not None:
        declared_set = set(declared_dynamic_entities)
        _validate_dynamic_entity_references(screens, declared_set)

    # Validate all referenced scripts are available with correct types
    if available_scripts is not None:
        _validate_script_references(screens, available_scripts)
    
    # Validate all referenced globals are available
    if available_globals is not None:
        _validate_global_references(screens, available_globals)

    # Validate all image references point to known image IDs
    if available_images is not None:
        _validate_image_references(screens, available_images)

    # Validate all screen background image references point to known screen image IDs
    if available_screen_images is not None:
        _validate_screen_image_references(screens, available_screen_images)



from .reference_validation import (
    _validate_image_references,
    _validate_screen_image_references,
    _validate_dynamic_entity_references,
    _validate_tile_positions,
    _validate_base_screen_reachability,
)
from .schema_validation import (
    _validate_script_references,
    _validate_script_parameters,
    _validate_global_references,
    _validate_tile_fields,
    _validate_condition_expression,
    validate_tile_schema,
    validate_field_value,
)
