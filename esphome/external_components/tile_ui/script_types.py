"""Script type detection and validation for tile UI component.

This module handles:
- Script type classification (display, action, location_action)
- Script parameter signature validation
- Script type matching against expected usage contexts
"""
from typing import Any

__all__ = [
    "get_script_type",
    "validate_script_type",
]

def get_script_type(parameters):
    """Determine the script type based on its parameter signature (types only).
    
    Script types are determined by parameter count and types, not parameter names.
    Parameter names are just conventions and don't affect the C++ type signature.
    
    Args:
        parameters: Dict of script parameters (e.g., {x: int, y: int, entities: string[]})
                   Can be empty dict {} for no-parameter scripts
    
    Returns:
        String: 'display', 'action', 'location_action', 'display_simple', 'display_toggle', 'display_cycle', or 'unknown'
    """
    if not isinstance(parameters, dict):
        return 'unknown'
    
    param_types = [type_str for _, type_str in parameters.items()] if parameters else []
    param_count = len(param_types)
    
    # Check for 7-parameter scripts
    if param_count == 7:
        # Icon display script: int, int, int, int, string, Color, font
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            param_types[2] == 'int' and
            param_types[3] == 'int' and
            ('string' in str(param_types[4]).lower()) and
            ('Color' in str(param_types[5])) and
            ('font' in str(param_types[6]).lower())):
            return 'display_icon'

    # Check for 6-parameter scripts
    if param_count == 6:
        # Toggle display script: int, int, int, int, string, bool
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            param_types[2] == 'int' and
            param_types[3] == 'int' and
            ('string' in str(param_types[4]).lower()) and
            ('bool' in str(param_types[5]).lower())):
            return 'display_toggle'
        
        # Cycle display script: int, int, int, int, string, string[]
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            param_types[2] == 'int' and
            param_types[3] == 'int' and
            ('string' in str(param_types[4]).lower()) and
            ('string[]' in str(param_types[5]) or 'vector' in str(param_types[5]).lower())):
            return 'display_cycle'

    # Check for 5-parameter scripts
    if param_count == 5:
        # Display script: int, int, int, int, string[]
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            param_types[2] == 'int' and
            param_types[3] == 'int' and
            ('string[]' in str(param_types[4]) or 'vector' in str(param_types[4]).lower())):
            return 'display'

    # Check for 4-parameter scripts
    if param_count == 4:
        # Simple display script: int, int, int, int
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            param_types[2] == 'int' and
            param_types[3] == 'int'):
            return 'display_simple'

    # Check for 3-parameter scripts
    if param_count == 3:
        # Location action script: float, float, string[]
        if (param_types[0] == 'float' and 
            param_types[1] == 'float' and
            ('string[]' in str(param_types[2]) or 'vector' in str(param_types[2]).lower())):
            return 'location_action'
    
    # Check for 1-parameter scripts: string[] only
    if param_count == 1:
        if 'string[]' in str(param_types[0]) or 'vector' in str(param_types[0]).lower():
            # Could be an action or a condition
            return 'action'
    
    # Scripts with no parameters are treated as action scripts (most flexible)
    if param_count == 0:
        return 'action'
    
    return 'unknown'


def _are_types_compatible(actual, expected):
    actual = str(actual).lower()
    expected = str(expected).lower()
    
    if 'int' in actual and 'int' in expected: return True
    if 'float' in actual and 'float' in expected: return True
    if 'bool' in actual and 'bool' in expected: return True
    
    is_actual_vector = 'string[]' in actual or 'vector' in actual
    is_expected_vector = 'string[]' in expected or 'vector' in expected
    
    if is_actual_vector and is_expected_vector: return True
    if not is_actual_vector and not is_expected_vector and 'string' in actual and 'string' in expected: return True
    
    return False

def validate_script_type(script_id, script_info, expected_type, context, provided_params=None):
    """Validate that a script has the expected type.
    
    Args:
        script_id: ID of the script being validated
        script_info: Dict with 'parameters' field
        expected_type: Expected script type ('display', 'action', or 'location_action')
        context: String describing where script is used (for error messages)
        provided_params: Dict of parameters provided in the configuration (optional)
    
    Raises:
        ValueError: If script type doesn't match expected type
    """
    if script_info is None:
        raise ValueError(f"{context}: Script '{script_id}' not found in available scripts")
    
    parameters = script_info.get('parameters', {})
    provided_params = provided_params or {}
    
    # Filter out provided parameters to check only the remaining ones against expected signature
    remaining_param_types = []
    for name, type_str in parameters.items():
        if name not in provided_params:
            remaining_param_types.append(type_str)
            
    # Map expected_type to expected parameter types
    expected_params_map = {
        'display': ['int', 'int', 'int', 'int', 'string[]'],
        'action': ['string[]'],
        'location_action': ['float', 'float', 'string[]'],
        'display_simple': ['int', 'int', 'int', 'int'],
        'display_toggle': ['int', 'int', 'int', 'int', 'string', 'bool'],
        'display_cycle': ['int', 'int', 'int', 'int', 'string', 'string[]'],
        'condition': ['string[]'],
    }
    
    expected_params = expected_params_map.get(expected_type)
    
    # If we don't know the expected type, fall back to old strict check (or just pass?)
    if not expected_params:
        actual_type = get_script_type(parameters)
        if actual_type != expected_type:
             raise ValueError(
                f"{context}: Script '{script_id}' is a '{actual_type}' script but expected '{expected_type}'. "
                f"Parameters: {parameters}"
            )
        return

    # Enforce coordinates are required if expected_params implies them
    if expected_params and len(expected_params) >= 4:
        first_four = expected_params[:4]
        if first_four == ['int', 'int', 'int', 'int']:
             # Check original parameters for x_start, x_end, y_start, y_end
             required_coords = ['x_start', 'x_end', 'y_start', 'y_end']
             missing_coords = [p for p in required_coords if p not in parameters]
             if missing_coords:
                 # Fallback to checking first four types if names are not standard (unlikely but possible)
                 if len(remaining_param_types) < 4:
                    raise ValueError(
                        f"{context}: Script '{script_id}' must have coordinate parameters ({', '.join(required_coords)}) for type '{expected_type}'. Missing: {', '.join(missing_coords)}"
                    )
    
    # Enforce x and y are required for location_action
    if expected_params and len(expected_params) >= 2:
        first_two = expected_params[:2]
        if first_two == ['float', 'float']:
            if 'x' not in parameters or 'y' not in parameters:
                 if len(remaining_param_types) < 2:
                    raise ValueError(
                        f"{context}: Script '{script_id}' must have at least 2 parameters (x, y) for type '{expected_type}'. "
                    )

    # Check compatibility of remaining parameters
    for i, actual_param_type in enumerate(remaining_param_types):
        if i >= len(expected_params):
            raise ValueError(
                f"{context}: Script '{script_id}' has too many parameters remaining after applying provided arguments. "
                f"Expected at most {len(expected_params)} ({', '.join(expected_params)}), "
                f"got {len(remaining_param_types)} ({', '.join(remaining_param_types)})."
            )
        
        expected_param_type = expected_params[i]
        if not _are_types_compatible(actual_param_type, expected_param_type):
             raise ValueError(
                 f"{context}: Script '{script_id}' parameter {i+1} (of remaining) type mismatch. "
                 f"Expected {expected_param_type}, got {actual_param_type}."
             )
    
    # If we get here, the script has <= parameters than expected, and types match.
    # This is valid because we fill missing parameters with defaults.
