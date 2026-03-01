"""Schema validation for tile configuration."""
import json
import os
from enum import Enum
from typing import Any

import esphome.config_validation as cv
from voluptuous import PREVENT_EXTRA, Required, Optional, Schema, All

# Load schema.json
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.json")
try:
    with open(SCHEMA_PATH, "r") as f:
        SCHEMA_DEF = json.load(f)
except FileNotFoundError:
    # Fallback or error if schema.json is missing (e.g. in some build environments)
    # For now, we assume it exists as per user request to link them.
    # If this fails in CI/CD, we might need a different strategy.
    raise FileNotFoundError(f"Could not find schema.json at {SCHEMA_PATH}")

class TileType(Enum):
    """Enumeration of valid tile types."""
    HA_ACTION = "ha_action"
    MOVE_PAGE = "move_page"
    TITLE = "title"
    FUNCTION = "function"
    TOGGLE_ENTITY = "toggle_entity"
    CYCLE_ENTITY = "cycle_entity"


VALID_TILE_TYPES: set[str] = {t.value for t in TileType}
VALID_FLAGS: set[str] = {"BASE", "TEMPORARY", "FAST_REFRESH", "OMIT_TIME_WIFI"}

__all__ = [
    "TileType",
    "VALID_TILE_TYPES",
    "VALID_FLAGS",
    "coord_schema",
    "non_empty_string",
    "string_list",
    "entities_list",
    "activation_var_schema",
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
        if "entity" in item and (not isinstance(item["entity"], str) or not item["entity"].strip()):
            raise cv.Invalid("entity must be a non-empty string")
        if "dynamic_entity" in item and (not isinstance(item["dynamic_entity"], str) or not item["dynamic_entity"].strip()):
            raise cv.Invalid("dynamic_entity must be a non-empty string")
    return value


def activation_var_schema(value: Any) -> dict:
    """Validate activation_var configuration."""
    schema = Schema({
        Required("dynamic_entity"): non_empty_string,
        Required("value"): non_empty_string,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def script_item(value: Any) -> Any:
    """Validate a single script item (string or dict)."""
    if isinstance(value, str):
        if not value.strip():
            raise cv.Invalid("String cannot be empty")
        return value
    elif isinstance(value, dict):
        if len(value) != 1:
            raise cv.Invalid(f"Dict items must have exactly one key, got {len(value)}")
        key = list(value.keys())[0]
        if not isinstance(key, str) or not key.strip():
            raise cv.Invalid("Dict key must be a non-empty string")
        return value
    else:
        raise cv.Invalid(f"Item must be string or dict, got {type(value).__name__}")


# Helper to map JSON types to validators
def get_validator(field_type: str, object_fields: list = None):
    if field_type == 'number':
        return coord_schema # Assuming all numbers are coords for now
    if field_type == 'string':
        return non_empty_string
    if field_type == 'boolean':
        return bool
    if field_type == 'display_list':
        return display_list
    if field_type == 'entity_list':
        return entities_list
    if field_type == 'script_list':
        return display_list
    if field_type == 'script':
        return script_item
    if field_type == 'page_select':
        return non_empty_string
    if field_type == 'dynamic_entity_select':
        return non_empty_string
    if field_type == 'ha_entity_list':
        return cv.Any(non_empty_string, string_list)
    if field_type == 'object':
        if not object_fields:
            return dict
        
        # Build schema for object
        item_schema = {}
        for f in object_fields:
            key = Optional(f['key']) if f.get('optional') else Required(f['key'])
            item_schema[key] = get_validator(f.get('type', 'string'), f.get('objectFields'))
            
        return Schema(item_schema, extra=PREVENT_EXTRA)
    if field_type == 'object_list':
        if not object_fields:
            return list
        
        # Build schema for object items
        item_schema = {}
        for f in object_fields:
            key = Optional(f['key']) if f.get('optional') else Required(f['key'])
            item_schema[key] = get_validator(f.get('type', 'string'), f.get('objectFields'))
            
        return All(
            list,
            [Schema(item_schema, extra=PREVENT_EXTRA)]
        )
    if field_type == 'condition_logic':
        return cv.Any(dict, non_empty_string)
    return cv.string

def build_tile_schema(tile_type_def):
    """Builds a voluptuous schema from the JSON definition."""
    schema_dict = {}
    
    # Add common fields
    for field in SCHEMA_DEF['common']:
        validator = get_validator(field['type'])
        if field.get('optional'):
            schema_dict[Optional(field['name'])] = validator
        else:
            schema_dict[Required(field['name'])] = validator

    # Add specific fields
    for field in tile_type_def['fields']:
        validator = get_validator(field['type'], field.get('objectFields'))
        
        if field.get('optional'):
            schema_dict[Optional(field['name'])] = validator
        else:
            schema_dict[Required(field['name'])] = validator
    
    return Schema(schema_dict, extra=PREVENT_EXTRA)

# Generate schemas dynamically
TILE_SCHEMAS = {}
for t_def in SCHEMA_DEF['types']:
    TILE_SCHEMAS[t_def['type']] = build_tile_schema(t_def)


def tile_schema(value):
    """Validate tile configuration - one tile type per tile."""
    if not isinstance(value, dict):
        raise cv.Invalid(f"Tile must be a dict, got {type(value).__name__}")
    
    if len(value) != 1:
        raise cv.Invalid(f"Tile must have exactly one type key, got {len(value)}: {list(value.keys())}")
    
    tile_type, tile_config = list(value.items())[0]
    
    if tile_type in TILE_SCHEMAS:
        return {tile_type: TILE_SCHEMAS[tile_type](tile_config)}
    else:
        raise cv.Invalid(f"Unknown tile type: {tile_type}. Valid types: {list(TILE_SCHEMAS.keys())}")


def screen_schema(value):
    """Validate screen configuration."""
    if not isinstance(value, dict):
        raise cv.Invalid(f"Screen must be a dict, got {type(value).__name__}")
    
    if "id" not in value:
        raise cv.Invalid("Screen must have 'id' key")
    
    # Handle ID object (from cv.declare_id) or string
    screen_id = value["id"]
    if hasattr(screen_id, "id"):
        screen_id = str(screen_id)
    else:
        screen_id = non_empty_string(screen_id)
    
    # Validate flags if present
    flags = value.get("flags", [])
    if flags:
        if not isinstance(flags, list):
            raise cv.Invalid(f"flags must be a list, got {type(flags).__name__}")
        for flag in flags:
            if flag not in VALID_FLAGS:
                raise cv.Invalid(f"Invalid flag: {flag}. Valid flags: {VALID_FLAGS}")
    
    # Validate rows/cols if present
    rows = value.get("rows")
    if rows is not None:
        rows = coord_schema(rows)
        
    cols = value.get("cols")
    if cols is not None:
        cols = coord_schema(cols)
    
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
            location = f"Tile {idx}"
            # Try to extract x,y for better error context
            if isinstance(tile, dict) and len(tile) > 0:
                try:
                    # Get the first value (the config dict)
                    tile_cfg = list(tile.values())[0]
                    if isinstance(tile_cfg, dict):
                        x = tile_cfg.get('x')
                        y = tile_cfg.get('y')
                        if x is not None and y is not None:
                            location = f"Tile [{x},{y}]"
                except Exception:
                    pass
            raise cv.Invalid(f"{location}: {str(e)}")
    
    return {
        "id": screen_id,
        "flags": flags,
        "tiles": validated_tiles,
        "rows": rows,
        "cols": cols,
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
