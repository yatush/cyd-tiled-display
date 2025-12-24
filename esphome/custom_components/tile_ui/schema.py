"""Schema validation for tile configuration."""
from enum import Enum
from typing import Any

import esphome.config_validation as cv
from voluptuous import PREVENT_EXTRA


class TileType(Enum):
    """Enumeration of valid tile types."""
    HA_ACTION = "ha_action"
    MOVE_PAGE = "move_page"
    TITLE = "title"
    FUNCTION = "function"
    TOGGLE_ENTITY = "toggle_entity"
    CYCLE_ENTITY = "cycle_entity"


VALID_TILE_TYPES: set[str] = {t.value for t in TileType}
VALID_FLAGS: set[str] = {"BASE", "TEMPORARY", "FAST_REFRESH"}

__all__ = [
    "TileType",
    "VALID_TILE_TYPES",
    "VALID_FLAGS",
    "coord_schema",
    "non_empty_string",
    "string_list",
    "entities_list",
    "activation_var_schema",
    "ha_action_schema",
    "move_page_schema",
    "title_schema",
    "function_schema",
    "toggle_entity_schema",
    "cycle_entity_schema",
    "tile_schema",
    "screen_schema",
    "screens_list_schema",
]


def coord_schema(value: Any) -> int:
    """Validate coordinate (non-negative integer)."""
    if not isinstance(value, int):
        raise cv.Invalid(f"Coordinate must be integer, got {type(value).__name__}")
    if value < 0:
        raise cv.Invalid(f"Coordinate must be non-negative, got {value}")
    return value


def non_empty_string(value: Any) -> str:
    """Validate non-empty string."""
    if not isinstance(value, str):
        raise cv.Invalid(f"Must be a string, got {type(value).__name__}")
    if not value.strip():
        raise cv.Invalid("String cannot be empty")
    return value


def string_list(value: Any) -> list[str]:
    """Validate list of non-empty strings."""
    if not isinstance(value, list):
        raise cv.Invalid(f"Must be a list, got {type(value).__name__}")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise cv.Invalid(f"List items must be non-empty strings, got {item}")
    return value


def display_list(value: Any) -> list[Any]:
    """Validate list of display items (strings or dicts)."""
    if not isinstance(value, list):
        raise cv.Invalid(f"Must be a list, got {type(value).__name__}")
    for item in value:
        if isinstance(item, str):
            if not item.strip():
                raise cv.Invalid("String items cannot be empty")
        elif isinstance(item, dict):
            if len(item) != 1:
                raise cv.Invalid(f"Dict items must have exactly one key, got {len(item)}")
            key = list(item.keys())[0]
            if not isinstance(key, str) or not key.strip():
                raise cv.Invalid("Dict key must be a non-empty string")
        else:
            raise cv.Invalid(f"List items must be strings or dicts, got {type(item).__name__}")
    return value


def entities_list(value: Any) -> list[dict]:
    """Validate entities list - can contain dicts with dynamic_entity or entity keys."""
    if not isinstance(value, list):
        raise cv.Invalid(f"entities must be a list, got {type(value).__name__}")
    if not value:
        raise cv.Invalid("entities list cannot be empty")
    for item in value:
        if not isinstance(item, dict):
            raise cv.Invalid(f"entities items must be dicts, got {type(item).__name__}")
        if not any(key in item for key in ["dynamic_entity", "entity"]):
            raise cv.Invalid(f"entities dict must have 'dynamic_entity' or 'entity' key, got {list(item.keys())}")
    return value


def activation_var_schema(value: Any) -> dict:
    """Validate activation_var configuration."""
    schema = cv.Schema({
        cv.Required("dynamic_entity"): non_empty_string,
        cv.Required("value"): non_empty_string,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def ha_action_schema(value):
    """Validate ha_action tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Required("entities"): entities_list,
        cv.Optional("perform"): string_list,
        cv.Optional("location_perform"): string_list,
        cv.Optional("display_page_if_no_entity"): non_empty_string,
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("activation_var"): activation_var_schema,
        cv.Optional("omit_frame"): bool,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def dynamic_entry_schema(value):
    """Validate dynamic_entry configuration."""
    schema = cv.Schema({
        cv.Required("dynamic_entity"): non_empty_string,
        cv.Required("value"): non_empty_string,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def move_page_schema(value):
    """Validate move_page tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Required("destination"): non_empty_string,
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("activation_var"): activation_var_schema,
        cv.Optional("dynamic_entry"): dynamic_entry_schema,
        cv.Optional("omit_frame"): bool,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def title_schema(value):
    """Validate title tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Required("entities"): entities_list,
        cv.Optional("omit_frame"): bool,
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("activation_var"): activation_var_schema,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def function_schema(value):
    """Validate function tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Optional("on_press"): non_empty_string,
        cv.Optional("on_release"): non_empty_string,
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("activation_var"): activation_var_schema,
        cv.Optional("omit_frame"): bool,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def toggle_entity_schema(value):
    """Validate toggle_entity tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Required("dynamic_entity"): non_empty_string,
        cv.Required("entity"): non_empty_string,
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("presentation_name"): non_empty_string,
        cv.Optional("initially_chosen"): bool,
        cv.Optional("activation_var"): activation_var_schema,
        cv.Optional("omit_frame"): bool,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def cycle_entity_schema(value):
    """Validate cycle_entity tile configuration."""
    schema = cv.Schema({
        cv.Required("x"): coord_schema,
        cv.Required("y"): coord_schema,
        cv.Required("display"): display_list,
        cv.Required("dynamic_entity"): non_empty_string,
        cv.Required("options"): cv.All(
            list,
            [cv.Schema({
                cv.Required("entity"): non_empty_string,
                cv.Required("label"): non_empty_string,
            }, extra=PREVENT_EXTRA)]
        ),
        cv.Optional("requires_fast_refresh"): cv.Any(dict, non_empty_string),
        cv.Optional("reset_on_leave"): bool,
        cv.Optional("activation_var"): activation_var_schema,
        cv.Optional("omit_frame"): bool,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def tile_schema(value):
    """Validate tile configuration - one tile type per tile."""
    if not isinstance(value, dict):
        raise cv.Invalid(f"Tile must be a dict, got {type(value).__name__}")
    
    if len(value) != 1:
        raise cv.Invalid(f"Tile must have exactly one type key, got {len(value)}: {list(value.keys())}")
    
    tile_type, tile_config = list(value.items())[0]
    
    if tile_type == TileType.HA_ACTION.value:
        return {tile_type: ha_action_schema(tile_config)}
    elif tile_type == TileType.MOVE_PAGE.value:
        return {tile_type: move_page_schema(tile_config)}
    elif tile_type == TileType.TITLE.value:
        return {tile_type: title_schema(tile_config)}
    elif tile_type == TileType.FUNCTION.value:
        return {tile_type: function_schema(tile_config)}
    elif tile_type == TileType.TOGGLE_ENTITY.value:
        return {tile_type: toggle_entity_schema(tile_config)}
    elif tile_type == TileType.CYCLE_ENTITY.value:
        return {tile_type: cycle_entity_schema(tile_config)}
    else:
        raise cv.Invalid(f"Unknown tile type: {tile_type}. Valid types: {VALID_TILE_TYPES}")


def screen_schema(value):
    """Validate screen configuration."""
    if not isinstance(value, dict):
        raise cv.Invalid(f"Screen must be a dict, got {type(value).__name__}")
    
    if "id" not in value:
        raise cv.Invalid("Screen must have 'id' key")
    
    screen_id = non_empty_string(value["id"])
    
    # Validate flags if present
    flags = value.get("flags", [])
    if flags:
        if not isinstance(flags, list):
            raise cv.Invalid(f"flags must be a list, got {type(flags).__name__}")
        for flag in flags:
            if flag not in VALID_FLAGS:
                raise cv.Invalid(f"Invalid flag: {flag}. Valid flags: {VALID_FLAGS}")
    
    # Validate tiles
    if "tiles" not in value:
        raise cv.Invalid("Screen must have 'tiles' key")
    
    tiles = value["tiles"]
    if not isinstance(tiles, list):
        raise cv.Invalid(f"tiles must be a list, got {type(tiles).__name__}")
    if not tiles:
        raise cv.Invalid("tiles list cannot be empty")
    
    validated_tiles = []
    for idx, tile in enumerate(tiles):
        try:
            validated_tiles.append(tile_schema(tile))
        except cv.Invalid as e:
            raise cv.Invalid(f"Tile {idx}: {str(e)}")
    
    return {
        "id": screen_id,
        "flags": flags,
        "tiles": validated_tiles,
    }


def screens_list_schema(value):
    """Validate list of screens."""
    if not isinstance(value, list):
        raise cv.Invalid(f"screens must be a list, got {type(value).__name__}")
    if not value:
        raise cv.Invalid("screens list cannot be empty")
    
    validated = []
    for idx, item in enumerate(value):
        try:
            validated.append(screen_schema(item))
        except cv.Invalid as e:
            raise cv.Invalid(f"Screen {idx}: {str(e)}")
    
    return validated
