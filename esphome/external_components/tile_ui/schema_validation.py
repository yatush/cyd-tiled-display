"""Script, global, condition, and tile schema validators."""
from typing import Any

from .script_types import BUILTIN_FONT_PARAMETER_DEFAULTS, script_parameter_defaults, validate_script_type
from .data_collection import collect_referenced_scripts, collect_referenced_globals
from .schema import VALID_TILE_TYPES, TileType, SCHEMA_DEF, tile_schema
from .tile_images import is_image_param_type

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
            provided_params = {
                **script_parameter_defaults(script_id, script_info),
                **(usage.get('params') or {}),
            }
            
            # Validate parameters if provided (check for missing/unknown params first)
            if 'params' in usage:
                _validate_script_parameters(script_id, script_info, provided_params, context)
            
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

    for font_param in BUILTIN_FONT_PARAMETER_DEFAULTS.get(script_id, ()):
        if font_param in provided_params:
            font_val = provided_params[font_param]
            if not isinstance(font_val, str) or not font_val.strip() or font_val.strip() == 'nullptr':
                raise ValueError(f"{context}: Script '{script_id}' requires a valid font for '{font_param}'.")

    for param, param_type in script_params.items():
        if is_image_param_type(param_type) and param in provided_params:
            img_val = provided_params[param]
            if not isinstance(img_val, str) or not img_val.strip():
                raise ValueError(f"{context}: Script '{script_id}' requires a valid image for '{param}'.")
    
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
            if "dynamic_entity" in option:
                if "entity" in option or "label" in option:
                    raise ValueError(
                        f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                        f"option {idx} cannot combine 'dynamic_entity' with 'entity' or 'label'"
                    )
                de = option.get("dynamic_entity")
                if not isinstance(de, str) or not de.strip():
                    raise ValueError(
                        f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                        f"option {idx} 'dynamic_entity' must be a non-empty string"
                    )
                continue
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

    elif tile_type == TileType.MOVE_PAGE.value:
        dynamic_entry = config.get("dynamic_entry")
        if dynamic_entry:
            entries = dynamic_entry if isinstance(dynamic_entry, list) else [dynamic_entry]
            seen_dynamic_entities = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                de = entry.get("dynamic_entity", "")
                if de:
                    if de in seen_dynamic_entities:
                        raise ValueError(
                            f"Screen '{screen_id}', move_page tile at ({x}, {y}): "
                            f"Duplicate dynamic_entity '{de}' in dynamic_entry list"
                        )
                    seen_dynamic_entities.add(de)
                val = entry.get("value")
                if isinstance(val, list):
                    seen_vals = set()
                    for v in val:
                        if isinstance(v, str) and v:
                            if v in seen_vals:
                                raise ValueError(
                                    f"Screen '{screen_id}', move_page tile at ({x}, {y}): "
                                    f"Duplicate entity '{v}' in dynamic_entry value list"
                                )
                            seen_vals.add(v)


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

    # Cross-field: exactly one of 'display' or 'display_assets' must be present
    has_display = bool(tile_config.get('display'))
    has_images = bool(tile_config.get('display_assets'))
    if tile_type == TileType.BLIND_POSITION.value:
        if any(name in tile_config for name in ('display', 'display_assets', 'requires_fast_refresh')):
            raise ValueError(f"{context}: Blind position tiles use a built-in display")
        return
    if has_display and has_images:
        raise ValueError(
            f"{context}: Cannot have both 'display' scripts and 'display_assets'. Use one or the other."
        )
    if not has_display and not has_images:
        raise ValueError(
            f"{context}: Must have either 'display' scripts or 'display_assets'."
        )


def validate_field_value(value: Any, field_def: dict, context: str) -> None:
    """Validate a single field value against its definition."""
    field_type = field_def['type']
    field_name = field_def['name']
    
    if field_type == 'number':
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{context}: Field '{field_name}' must be a non-negative integer, got {value}")
            
    elif field_type == 'script':
         if isinstance(value, str):
             if not value.strip():
                 raise ValueError(f"{context}: Field '{field_name}' must be a non-empty string")
         elif isinstance(value, dict):
             if len(value) != 1:
                  raise ValueError(f"{context}: Field '{field_name}' dict must have exactly one key")
             key = list(value.keys())[0]
             if not isinstance(key, str) or not key.strip():
                 raise ValueError(f"{context}: Field '{field_name}' dict key must be a non-empty string")
         else:
             raise ValueError(f"{context}: Field '{field_name}' must be a string or dict")

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
            if isinstance(item, str):
                if not item.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a non-empty string")
            elif isinstance(item, dict):
                if len(item) != 1:
                     raise ValueError(f"{context}: Field '{field_name}' item {idx} dict must have exactly one key")
                key = list(item.keys())[0]
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} dict key must be a non-empty string")
            else:
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a string or dict")
                
    elif field_type == 'object':
        if not isinstance(value, dict):
            raise ValueError(f"{context}: Field '{field_name}' must be an object (dict)")
        
        object_fields = field_def.get('objectFields', [])
        for f in object_fields:
            key = f['key']
            if key in value:
                # Construct a temporary field def for recursive validation
                temp_def = {'name': f"{field_name}.{key}", 'type': f.get('type', 'string')}
                if 'objectFields' in f:
                    temp_def['objectFields'] = f['objectFields']
                validate_field_value(value[key], temp_def, context)
            elif not f.get('optional', False):
                raise ValueError(f"{context}: Field '{field_name}' missing required key '{key}'")

    elif field_type == 'object_list':
        # Accept a list of objects (or a single object dict for backwards compatibility)
        items = [value] if isinstance(value, dict) else value
        if not isinstance(items, list):
            raise ValueError(f"{context}: Field '{field_name}' must be a list of objects")
        object_fields = field_def.get('objectFields', [])
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be a dict")
            for f in object_fields:
                key = f['key']
                if key in item:
                    temp_def = {'name': f"{field_name}[{idx}].{key}", 'type': f.get('type', 'string')}
                    if 'objectFields' in f:
                        temp_def['objectFields'] = f['objectFields']
                    validate_field_value(item[key], temp_def, context)
                elif not f.get('optional', False):
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} missing required key '{key}'")

    elif field_type == 'condition_logic':
        _validate_condition_expression(value, f"{context} field '{field_name}'")

    elif field_type == 'assets_list':
        if not isinstance(value, list):
            raise ValueError(f"{context}: Field '{field_name}' must be a list")
        if not value:
            raise ValueError(f"{context}: Field '{field_name}' cannot be empty")
        for idx, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must be an object")
            img = entry.get('image')
            icon = entry.get('icon')
            if 'icon' in entry:
                # Entry declared as icon row — the icon value must be non-empty
                if not isinstance(icon, str) or not icon.strip():
                    raise ValueError(f"{context}: Field '{field_name}' item {idx} 'icon' must be a non-empty string (select an icon from the picker)")
            elif not img or not isinstance(img, str) or not img.strip():
                raise ValueError(f"{context}: Field '{field_name}' item {idx} must have a non-empty 'image' or 'icon' key")
            # Validate per-step icon overrides
            anim = entry.get('animation')
            if isinstance(anim, dict) and 'steps' in anim:
                for si, step in enumerate(anim['steps']):
                    if 'icon' in step:
                        step_icon = step.get('icon')
                        if not isinstance(step_icon, str) or not step_icon.strip():
                            raise ValueError(f"{context}: Field '{field_name}' item {idx} step {si} 'icon' must be a non-empty string")
