"""Schema validation for tile configuration."""
import json
import os
import sys
from enum import Enum
from typing import Any

import esphome.config_validation as cv

# If an older generate_tiles_api.py injected a synthetic MockVoluptuousModule
# into sys.modules['voluptuous'], remove it so we either import the real
# voluptuous package or use the complete fallback implementation below.
if "voluptuous" in sys.modules and not hasattr(sys.modules["voluptuous"], "__file__"):
    del sys.modules["voluptuous"]

try:
    from voluptuous import (
        PREVENT_EXTRA, Required, Optional, Schema, All,
        Any as Vol_Any, Invalid as _VolInvalid,
    )
    if isinstance(getattr(cv, "Invalid", None), type) and not issubclass(cv.Invalid, _VolInvalid):
        class _SchemaInvalid(cv.Invalid, _VolInvalid):
            def __init__(self, message, path=None, *args, **kwargs):
                _VolInvalid.__init__(self, message, path=path, *args, **kwargs)
    else:
        _SchemaInvalid = getattr(cv, "Invalid", _VolInvalid)
except ImportError:
    _SchemaInvalid = getattr(cv, "Invalid", ValueError)
    PREVENT_EXTRA = 1
    _NO_DEFAULT = object()

    class _Marker:
        def __init__(self, schema, default=_NO_DEFAULT, msg=None):
            self.schema = schema
            self.default = default
            self.msg = msg

        def __hash__(self):
            return hash(self.schema)

        def __eq__(self, other):
            return isinstance(other, _Marker) and self.schema == other.schema

    class Required(_Marker):
        pass

    class Optional(_Marker):
        pass

    def _run_validator(validator, value):
        if isinstance(validator, Schema):
            return validator(value)
        if isinstance(validator, list):
            if not isinstance(value, list):
                raise cv.Invalid(f"expected a list, got {type(value).__name__}")
            if not validator:
                return value
            return [Vol_Any(*validator)(item) for item in value]
        if isinstance(validator, type):
            if not isinstance(value, validator):
                raise cv.Invalid(f"expected {validator.__name__}, got {type(value).__name__}")
            return value
        if callable(validator):
            return validator(value)
        if value != validator:
            raise cv.Invalid(f"expected {validator}, got {value}")
        return value

    class Schema:
        def __init__(self, schema, extra=None):
            self.schema = schema
            self.extra = extra

        def __call__(self, data):
            if not isinstance(data, dict):
                raise cv.Invalid(f"must be a dict, got {type(data).__name__}")
            out = {}
            schema_map = {}
            for k, v in self.schema.items():
                key_name = k.schema if isinstance(k, _Marker) else k
                schema_map[key_name] = (k, v)
            if self.extra == PREVENT_EXTRA:
                for k in data:
                    if k not in schema_map:
                        raise cv.Invalid(f"extra keys not allowed: {k}")
            for key_name, (key_schema, validator) in schema_map.items():
                if key_name in data:
                    try:
                        out[key_name] = _run_validator(validator, data[key_name])
                    except cv.Invalid as e:
                        raise cv.Invalid(f"Invalid value for '{key_name}': {e}")
                    except Exception as e:
                        raise cv.Invalid(f"Validation error for '{key_name}': {e}")
                else:
                    if isinstance(key_schema, Optional):
                        if key_schema.default is not _NO_DEFAULT:
                            out[key_name] = key_schema.default
                    else:
                        raise cv.Invalid(f"required key not provided: {key_name}")
            return out

    def Vol_Any(*validators):
        def validate(val):
            errors = []
            for v in validators:
                try:
                    return _run_validator(v, val)
                except (cv.Invalid, ValueError, TypeError) as e:
                    errors.append(str(e))
            raise cv.Invalid(f"no valid option found: {'; '.join(errors)}")
        return validate

    def All(*validators):
        def validate(val):
            for v in validators:
                val = _run_validator(v, val)
            return val
        return validate

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
    BLIND_POSITION = "blind_position"
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
    "dynamic_entities_schema",
    "get_validator",
]


def coord_schema(value: Any) -> int:
    """Validate coordinate (non-negative integer)."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise _SchemaInvalid(f"Coordinate must be integer, got {type(value).__name__}")
    if value < 0:
        raise _SchemaInvalid(f"Coordinate must be non-negative, got {value}")
    return value


def non_empty_string(value: Any) -> str:
    """Validate non-empty string."""
    if not isinstance(value, str):
        raise _SchemaInvalid(f"Must be a string, got {type(value).__name__}")
    if not value.strip():
        raise _SchemaInvalid("String cannot be empty")
    return value


def string_list(value: Any) -> list[str]:
    """Validate list of non-empty strings."""
    if not isinstance(value, list):
        raise _SchemaInvalid(f"Must be a list, got {type(value).__name__}")
    if not value:
        raise _SchemaInvalid("List cannot be empty")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _SchemaInvalid(f"List items must be non-empty strings, got {item}")
    return value


def display_list(value: Any) -> list[Any]:
    """Validate list of display items (strings or dicts)."""
    if not isinstance(value, list):
        raise _SchemaInvalid(f"Must be a list, got {type(value).__name__}")
    for item in value:
        if isinstance(item, str):
            if not item.strip():
                raise _SchemaInvalid("String items cannot be empty")
        elif isinstance(item, dict):
            if len(item) != 1:
                raise _SchemaInvalid(f"Dict items must have exactly one key, got {len(item)}")
            key = list(item.keys())[0]
            if not isinstance(key, str) or not key.strip():
                raise _SchemaInvalid("Dict key must be a non-empty string")
        else:
            raise _SchemaInvalid(f"List items must be strings or dicts, got {type(item).__name__}")
    return value


def entities_list(value: Any) -> list[dict | str]:
    """Validate entities list - can contain non-empty strings or dicts with dynamic_entity or entity keys."""
    if not isinstance(value, list):
        raise _SchemaInvalid(f"entities must be a list, got {type(value).__name__}")
    if not value:
        raise _SchemaInvalid("entities list cannot be empty")
    for item in value:
        if isinstance(item, str):
            if not item.strip():
                raise _SchemaInvalid("entity string cannot be empty")
            continue
        if not isinstance(item, dict):
            raise _SchemaInvalid(f"entities items must be dicts or strings, got {type(item).__name__}")
        if not any(key in item for key in ["dynamic_entity", "entity"]):
            raise _SchemaInvalid(f"entities dict must have 'dynamic_entity' or 'entity' key, got {list(item.keys())}")
        if "entity" in item and (not isinstance(item["entity"], str) or not item["entity"].strip()):
            raise _SchemaInvalid("entity must be a non-empty string")
        if "dynamic_entity" in item and (not isinstance(item["dynamic_entity"], str) or not item["dynamic_entity"].strip()):
            raise _SchemaInvalid("dynamic_entity must be a non-empty string")
    return value


def ha_entity_list(value: Any) -> str | list[str]:
    """Validate ha_entity_list - a non-empty string or a list of non-empty strings."""
    if isinstance(value, list):
        return string_list(value)
    return non_empty_string(value)


def activation_var_schema(value: Any) -> dict:
    """Validate activation_var configuration."""
    schema = Schema({
        Required("dynamic_entity"): non_empty_string,
        Required("value"): ha_entity_list,
    }, extra=PREVENT_EXTRA)
    return schema(value)


def script_item(value: Any) -> Any:
    """Validate a single script item (string or dict)."""
    if isinstance(value, str):
        if not value.strip():
            raise _SchemaInvalid("String cannot be empty")
        return value
    elif isinstance(value, dict):
        if len(value) != 1:
            raise _SchemaInvalid(f"Dict items must have exactly one key, got {len(value)}")
        key = list(value.keys())[0]
        if not isinstance(key, str) or not key.strip():
            raise _SchemaInvalid("Dict key must be a non-empty string")
        return value
    else:
        raise _SchemaInvalid(f"Item must be string or dict, got {type(value).__name__}")


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
        return ha_entity_list
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
            
        item_validator = Schema(item_schema, extra=PREVENT_EXTRA)
        return Vol_Any(
            All(list, [item_validator]),
            item_validator,
        )
    if field_type == 'color':
        return non_empty_string
    if field_type == 'color_list':
        def _color_list_validator(value):
            # Accept plain string (backward compat) or list of {color, condition?} entries
            if isinstance(value, str):
                if not value.strip():
                    raise _SchemaInvalid("Color string cannot be empty")
                return value
            if isinstance(value, list):
                if not value:
                    raise _SchemaInvalid("color_list cannot be empty")
                _entry_schema = Schema({
                    Required('color'): non_empty_string,
                    Optional('condition'): Vol_Any(dict, str),
                }, extra=PREVENT_EXTRA)
                return [_entry_schema(entry) for entry in value]
            raise _SchemaInvalid(f"fill_color must be a string or list, got {type(value).__name__}")
        return _color_list_validator
    if field_type == 'int_list':
        def _int_list_validator(value):
            # Accept plain int (single unconditional value) or list of {value, condition?} entries
            if isinstance(value, int):
                return value
            if isinstance(value, list):
                if not value:
                    raise _SchemaInvalid("int_list cannot be empty")
                _entry_schema = Schema({
                    Required('value'): int,
                    Optional('condition'): Vol_Any(dict, str),
                }, extra=PREVENT_EXTRA)
                return [_entry_schema(entry) for entry in value]
            raise _SchemaInvalid(f"int_list must be an int or list, got {type(value).__name__}")
        return _int_list_validator
    if field_type == 'condition_logic':
        return Vol_Any(dict, non_empty_string, bool)

    def _valid_anim_position(value):
        # Only [x, y] fractional lists are accepted; named strings are no longer supported
        if isinstance(value, (list, tuple)) and len(value) == 2:
            x, y = value
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise _SchemaInvalid(f"animation position [x, y] must contain numbers, got {value!r}")
            if not (0.0 <= float(x) <= 1.0) or not (0.0 <= float(y) <= 1.0):
                raise _SchemaInvalid(f"animation position [x, y] values must be in 0.0–1.0, got {value!r}")
            return [float(x), float(y)]
        raise _SchemaInvalid(f"animation position must be an [x, y] list with values in 0.0–1.0, got {value!r}")

    def _valid_anim_direction(value):
        """Legacy direction field — accepted for backward-compat with old YAML files."""
        valid = ('none', 'left_right', 'right_left', 'up_down', 'down_up')
        if value not in valid:
            raise _SchemaInvalid(f"animation direction must be one of {valid}, got '{value}'")
        return value

    def _positive_number(value):
        if not isinstance(value, (int, float)) or value <= 0:
            raise _SchemaInvalid(f"duration must be a positive number, got {value}")
        return value

    if field_type == 'assets_list':
        # List of entries, each being either an image entry or an icon entry.
        # Image entry: {image: str, condition?: str|dict, animation?: ...}
        # Icon entry:  {icon: str, icon_color?: str, icon_size?: str, condition?: str|dict, animation?: ...}
        # Animation step accepts the new from/to positions OR the legacy direction field.
        _new_step = Schema({
            Optional('from', default=[0.5, 0.5]): _valid_anim_position,
            Optional('to', default=[0.5, 0.5]): _valid_anim_position,
            Required('duration'): _positive_number,
            Optional('image'): str,
            Optional('icon'): non_empty_string,
            Optional('icon_color'): non_empty_string,
            Optional('icon_size'): non_empty_string,
        }, extra=PREVENT_EXTRA)
        _legacy_step = Schema({
            Required('direction'): _valid_anim_direction,
            Required('duration'): _positive_number,
            Optional('image'): str,
            Optional('icon'): non_empty_string,
            Optional('icon_color'): non_empty_string,
            Optional('icon_size'): non_empty_string,
        }, extra=PREVENT_EXTRA)
        animation_step_schema = Vol_Any(_new_step, _legacy_step)

        _new_single = Schema({
            Optional('from', default=[0.5, 0.5]): _valid_anim_position,
            Optional('to', default=[0.5, 0.5]): _valid_anim_position,
            Required('duration'): _positive_number,
        }, extra=PREVENT_EXTRA)
        _legacy_single = Schema({
            Required('direction'): _valid_anim_direction,
            Required('duration'): _positive_number,
        }, extra=PREVENT_EXTRA)
        animation_schema = Vol_Any(
            # single-step new format
            _new_single,
            # single-step legacy format
            _legacy_single,
            # multi-step
            Schema({
                Required('steps'): All(list, [animation_step_schema]),
            }, extra=PREVENT_EXTRA),
        )
        _image_entry_schema = Schema({
            Required('image'): non_empty_string,
            Optional('condition'): Vol_Any(dict, non_empty_string, str),
            Optional('animation'): animation_schema,
        }, extra=PREVENT_EXTRA)
        _icon_entry_schema = Schema({
            Required('icon'): non_empty_string,
            Optional('icon_color'): non_empty_string,
            Optional('icon_size'): non_empty_string,
            Optional('condition'): Vol_Any(dict, non_empty_string, str),
            Optional('animation'): animation_schema,
        }, extra=PREVENT_EXTRA)

        def _validate_image_or_icon_entry(value):
            if not isinstance(value, dict):
                raise _SchemaInvalid("Each display assets entry must be a mapping")
            has_image = 'image' in value
            has_icon = 'icon' in value
            if has_image and has_icon:
                raise _SchemaInvalid("An entry cannot have both 'image' and 'icon'")
            if not has_image and not has_icon:
                raise _SchemaInvalid("Each entry must have either 'image' or 'icon'")
            if has_image:
                return _image_entry_schema(value)
            return _icon_entry_schema(value)

        return All(list, [_validate_image_or_icon_entry])
    if field_type in ('image_select', 'state_image_map'):
        # Legacy field types — accept anything for backward compat
        return Vol_Any(str, list, dict)
    return str

def build_tile_schema(tile_type_def):
    """Builds a voluptuous schema from the JSON definition."""
    schema_dict = {}
    
    # Add common fields
    for field in SCHEMA_DEF['common']:
        if tile_type_def['type'] == 'blind_position' and field['name'] in (
            'display', 'display_assets', 'requires_fast_refresh'
        ):
            continue
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
    
    # Add deprecated keys for backward compatibility (old 'image' / 'state_images')
    schema_dict[Optional('image')] = Vol_Any(str)
    schema_dict[Optional('state_images')] = Vol_Any(list, dict)

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
    
    # Validate time_color if present
    time_color = value.get("time_color")
    if time_color is not None:
        if not isinstance(time_color, str):
            raise cv.Invalid(f"time_color must be a string, got {type(time_color).__name__}")

    return {
        "id": screen_id,
        "flags": flags,
        "tiles": validated_tiles,
        "rows": rows,
        "cols": cols,
        "background": _validate_screen_background(value.get("background")),
        "time_color": time_color,
    }


def _validate_screen_background(background):
    """Validate the optional screen-level background list."""
    if background is None:
        return None
    if not isinstance(background, list):
        raise cv.Invalid("background must be a list")
    result = []
    for idx, entry in enumerate(background):
        if not isinstance(entry, dict):
            raise cv.Invalid(f"background[{idx}] must be a dict")
        has_color = "color" in entry
        has_image = "image" in entry
        if has_color and has_image:
            raise cv.Invalid(f"background[{idx}] cannot have both 'color' and 'image'")
        if not has_color and not has_image:
            raise cv.Invalid(f"background[{idx}] must have 'color' or 'image'")
        if has_color and not isinstance(entry["color"], str):
            raise cv.Invalid(f"background[{idx}].color must be a string")
        if has_image and not isinstance(entry["image"], str):
            raise cv.Invalid(f"background[{idx}].image must be a string")
        condition = entry.get("condition")
        if condition is not None and not isinstance(condition, (str, dict)):
            raise cv.Invalid(f"background[{idx}].condition must be a string or dict")
        result.append({k: v for k, v in entry.items()})
    return result


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


def dynamic_entities_schema(value: Any) -> Any:
    """Validate top-level dynamic_entities configuration (runtime names and/or fixed values)."""
    from .data_collection import parse_dynamic_entities_config
    try:
        parse_dynamic_entities_config(value)
    except ValueError as e:
        raise _SchemaInvalid(str(e))
    return value
