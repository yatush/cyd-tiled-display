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
        String: 'display', 'action', 'location_action', or 'unknown'
    """
    if not isinstance(parameters, dict):
        return 'unknown'
    
    param_types = [type_str for _, type_str in parameters.items()] if parameters else []
    param_count = len(param_types)
    
    # Check for 3-parameter scripts
    if param_count == 3:
        # Display script: int, int, string[]
        if (param_types[0] == 'int' and 
            param_types[1] == 'int' and
            ('string[]' in str(param_types[2]) or 'vector' in str(param_types[2]).lower())):
            return 'display'
        
        # Location action script: float, float, string[]
        if (param_types[0] == 'float' and 
            param_types[1] == 'float' and
            ('string[]' in str(param_types[2]) or 'vector' in str(param_types[2]).lower())):
            return 'location_action'
    
    # Check for 1-parameter scripts: string[] only
    if param_count == 1:
        if 'string[]' in str(param_types[0]) or 'vector' in str(param_types[0]).lower():
            return 'action'
    
    # Scripts with no parameters are treated as action scripts (most flexible)
    if param_count == 0:
        return 'action'
    
    return 'unknown'


def validate_script_type(script_id, script_info, expected_type, context):
    """Validate that a script has the expected type.
    
    Args:
        script_id: ID of the script being validated
        script_info: Dict with 'parameters' field
        expected_type: Expected script type ('display', 'action', or 'location_action')
        context: String describing where script is used (for error messages)
    
    Raises:
        ValueError: If script type doesn't match expected type
    """
    if script_info is None:
        raise ValueError(f"{context}: Script '{script_id}' not found in available scripts")
    
    parameters = script_info.get('parameters', {})
    actual_type = get_script_type(parameters)
    
    if actual_type == 'unknown':
        raise ValueError(
            f"{context}: Script '{script_id}' has unknown parameter signature. "
            f"Parameters: {parameters}. "
            f"Expected one of: display (int, int, string[]), action (string[]), or location_action (float, float, string[])"
        )
    
    if actual_type != expected_type:
        raise ValueError(
            f"{context}: Script '{script_id}' is a '{actual_type}' script but expected '{expected_type}'. "
            f"Parameters: {parameters}"
        )
