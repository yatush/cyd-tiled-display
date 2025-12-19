"""
Tile utilities - helper functions for formatting and building C++ expressions.
"""


def format_display_list(display):
    """Format display entities as C++ initializer list."""
    if isinstance(display, str):
        display = [display]
    elif not isinstance(display, list):
        display = []
    
    entities = ", ".join(f"&id({entity})" for entity in display if entity)
    return f"{{ {entities} }}"


def format_functions_list(functions):
    """Format function list as C++ initializer list."""
    if isinstance(functions, str):
        functions = [functions]
    elif not isinstance(functions, list):
        functions = []
    
    return ", ".join(f"&id({func})" for func in functions if func)


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
        var_name = activation_var.get("name", None)
        var_value = activation_var.get("value", None)
        
        if var_name and var_value:
            method_chains.append(f'setActivationVar("{var_name}", "{var_value}")')
        else:
            raise ValueError(f"activation_var must have both 'name' and 'value' fields")
    
    return method_chains


def flags_to_cpp(flags):
    """Convert flag list to C++ format."""
    if not flags:
        return "{}"
    return "{" + ", ".join(flags) + "}"
