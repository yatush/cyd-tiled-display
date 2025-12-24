"""
Tile utilities - helper functions for formatting and building C++ expressions.
"""
from typing import Any

__all__ = [
    "format_display_list",
    "format_functions_list",
    "format_entity_value",
    "format_entity_cpp",
    "build_fast_refresh_lambda",
    "get_tile_modifiers",
    "flags_to_cpp",
]


def _get_cpp_type(param_type):
    if param_type == 'int': return 'int'
    if param_type == 'float': return 'float'
    if param_type == 'bool': return 'bool'
    if param_type == 'string': return 'std::string'
    if param_type == 'string[]': return 'std::vector<std::string>'
    return 'auto'

def _get_default_value(param_type):
    if param_type == 'int': return '0'
    if param_type == 'float': return '0.0f'
    if param_type == 'bool': return 'false'
    if param_type == 'string': return '""'
    if param_type == 'string[]': return '{}'
    return '{}'

def _generate_lambda(script_id, available_scripts, expected_params, static_params=None):
    # Generate lambda args
    lambda_args = []
    param_map = {}
    
    for i, (p_name, p_type) in enumerate(expected_params):
        lambda_args.append(f"{_get_cpp_type(p_type)} arg{i}")
        
        if isinstance(p_name, list):
            for name in p_name:
                param_map[name] = i
        else:
            param_map[p_name] = i
            
    lambda_sig = ", ".join(lambda_args)
    
    # Determine script args
    script_args = []
    script_info = available_scripts.get(script_id) if available_scripts else None
    
    if script_info:
        script_params = script_info.get('parameters', {})
        
        for param_name, param_type in script_params.items():
            # 1. Check static params (from YAML)
            if static_params and param_name in static_params:
                script_args.append(str(static_params[param_name]))
                continue

            # 2. Map standard parameters by name to lambda arguments
            if param_name in param_map:
                idx = param_map[param_name]
                script_args.append(f"arg{idx}")
            else:
                # Fallback: use default value
                script_args.append(_get_default_value(param_type))
    else:
        # Fallback: pass all expected args (legacy behavior, or tests)
        script_args = [f"arg{i}" for i in range(len(expected_params))]
        
        # Debug/Warning:
        import sys
        print(f"WARNING: Script '{script_id}' not found in available_scripts. Generating call with all {len(expected_params)} arguments: {script_args}", file=sys.stderr)

    return f"[]({lambda_sig}) {{ id({script_id}).execute({', '.join(script_args)}); }}"


def format_display_list(display, available_scripts=None, expected_params=None):
    """Format display entities as C++ initializer list of lambdas."""
    if isinstance(display, str):
        display = [display]
    elif not isinstance(display, list):
        display = []
    
    lambdas = []
    for item in display:
        if not item:
            continue
            
        if isinstance(item, str):
            lambdas.append(_generate_lambda(item, available_scripts, expected_params))
        elif isinstance(item, dict):
            # Handle dictionary format: { script_id: { param: val } }
            for script_id, params in item.items():
                lambdas.append(_generate_lambda(script_id, available_scripts, expected_params, params))
            
    return f"{{ {', '.join(lambdas)} }}"


def format_functions_list(functions, available_scripts=None, expected_params=None):
    """Format function list as C++ initializer list of lambdas."""
    return format_display_list(functions, available_scripts, expected_params)


def format_single_function(function_id, available_scripts=None, expected_params=None):
    """Format a single function as a C++ lambda."""
    if not function_id:
        return "nullptr"
    
    if not expected_params:
        expected_params = []
        
    return _generate_lambda(function_id, available_scripts, expected_params)


def format_entity_value(entity_config):
    """Format entity value(s) for C++ constructor."""
    if not entity_config:
        return ""
    
    def format_single_entity(entity):
        """Helper to format a single entity."""
        if isinstance(entity, str):
            return entity
        
        if isinstance(entity, dict):
            if "dynamic_entity" in entity:
                name = entity["dynamic_entity"]
                sensor = entity.get("sensor", None)
                if sensor:
                    return f"#{{{name}}}|{sensor}"
                return f"#{{{name}}}"
            
            if "entity" in entity:
                entity_name = entity["entity"]
                sensor = entity.get("sensor", None)
                if sensor:
                    return f"{entity_name}|{sensor}"
                return entity_name
            
            return ""
        
        return ""
    
    if isinstance(entity_config, str):
        return entity_config
    
    if isinstance(entity_config, dict):
        return format_single_entity(entity_config)
    
    if isinstance(entity_config, list):
        formatted = []
        for entity in entity_config:
            formatted_entity = format_single_entity(entity)
            if formatted_entity:
                formatted.append(formatted_entity)
        return formatted
    
    return ""


def build_expression(expression_config):
    """Build C++ expression from expression config."""
    if not expression_config:
        return None
    
    if isinstance(expression_config, str):
        return f"id({expression_config})"
    
    if isinstance(expression_config, list):
        raise ValueError("List format is not allowed. Use dict format with 'operator' field.")
    
    if not isinstance(expression_config, dict):
        return None
    
    op = expression_config.get("operator", None)
    items = expression_config.get("items", [])
    
    if items:
        if not op:
            raise ValueError("'operator' field must be specified when using nested expressions")
        
        op = op.upper()
        
        if op == "NOT":
            raise ValueError("NOT operator cannot be used with 'items' - it only works with single functions")
        
        op_str = " || " if op == "OR" else " && "
        sub_expressions = []
        
        for item in items:
            sub_expr = build_expression(item)
            if sub_expr:
                if " || " in sub_expr or " && " in sub_expr:
                    sub_expr = f"({sub_expr})"
                sub_expressions.append(sub_expr)
        
        if sub_expressions:
            return op_str.join(sub_expressions)
    
    funcs = expression_config.get("funcs", [])
    if funcs:
        if op and op.upper() == "NOT":
            if len(funcs) != 1:
                raise ValueError("NOT operator only accepts exactly one function")
            return f"!id({funcs[0]})"
        
        if len(funcs) == 1:
            return f"id({funcs[0]})"
        
        if not op:
            raise ValueError("'operator' field is required when specifying multiple functions")
        
        op = op.upper()
        op_str = " || " if op == "OR" else " && "
        expressions = op_str.join(f"id({func})" for func in funcs if func)
        return expressions if expressions else None
    
    conditions = expression_config.get("conditions", [])
    if conditions:
        # Treat 'conditions' as an implicit OR of boolean globals/functions
        return " || ".join(f"id({cond})" for cond in conditions if cond)
    
    return None


def build_fast_refresh_lambda(requires_fast_refresh):
    """Build C++ lambda for setRequiresFastRefreshFunc."""
    expression = build_expression(requires_fast_refresh)
    if expression:
        return f"[]() {{ return {expression}; }}"
    return None


def format_entity_cpp(entity_values):
    """Format entity values as C++ initializer list."""
    if isinstance(entity_values, list):
        return "{" + ", ".join(f'"{e}"' for e in entity_values) + "}"
    else:
        return "{" + f'"{entity_values}"' + "}"


def get_tile_modifiers(config):
    """Get common tile modifier method chains."""
    method_chains = []
    
    if config.get("omit_frame", False):
        method_chains.append('omitFrame()')
    
    activation_var = config.get("activation_var", None)
    if activation_var:
        var_name = activation_var.get("dynamic_entity", None)
        var_value = activation_var.get("value", None)
        
        if var_name and var_value:
            if isinstance(var_value, str) and "," in var_value:
                values = [v.strip() for v in var_value.split(",")]
                values_cpp = "{" + ", ".join(f'"{v}"' for v in values) + "}"
                method_chains.append(f'setActivationVar("{var_name}", {values_cpp})')
            else:
                method_chains.append(f'setActivationVar("{var_name}", {{ "{var_value}" }})')
        else:
            raise ValueError(f"activation_var must have both 'dynamic_entity' and 'value' fields")
    
    return method_chains


def flags_to_cpp(flags):
    """Convert flag list to C++ format."""
    if not flags:
        return "{}"
    return "{" + ", ".join(flags) + "}"
