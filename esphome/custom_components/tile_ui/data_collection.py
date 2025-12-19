"""Data collection and YAML loading for tile UI component.

This module handles:
- Loading YAML tile configuration files
- Collecting available scripts and their parameters
- Collecting available globals
- Collecting referenced scripts and globals from tile configuration
"""
import yaml
import os


def load_tiles_yaml(tiles_file_path):
    """Load and parse the tiles.yaml file.
    
    Args:
        tiles_file_path: Path to the tiles.yaml file
        
    Returns:
        Parsed YAML as dictionary
        
    Raises:
        FileNotFoundError: If tiles file doesn't exist
    """
    if not os.path.exists(tiles_file_path):
        raise FileNotFoundError(f"Tiles file not found: {tiles_file_path}")
    
    # Open with utf-8-sig to handle UTF-8 BOM
    with open(tiles_file_path, 'r', encoding='utf-8-sig') as f:
        return yaml.safe_load(f)


def collect_available_scripts(esphome_config):
    """Extract all available script IDs and their parameter signatures from ESPhome configuration.
    
    Script types are categorized by their parameter signature:
    - Display scripts: takes (int, int, string[]) - x, y, entity_names
    - Action scripts: takes (string[]) - entity_names only
    - Location action scripts: takes (float, float, string[]) - x, y (floats), entity_names
    
    Args:
        esphome_config: ESPhome config dict with parsed scripts
    
    Returns:
        Dict mapping script ID to script info dict with 'parameters' field:
        {
            'script_id': {'parameters': {...}},
            ...
        }
    """
    available_scripts = {}
    
    # Get scripts from the 'script:' section
    scripts = esphome_config.get('script', [])
    if scripts:
        for script in scripts:
            if isinstance(script, dict) and 'id' in script:
                script_id = script['id']
                parameters = script.get('parameters', {})
                available_scripts[script_id] = {
                    'parameters': parameters if isinstance(parameters, dict) else {}
                }
    
    return available_scripts


def collect_available_globals(esphome_config):
    """Extract all available boolean global variable IDs from the ESPhome configuration.
    
    Boolean globals are used in condition expressions throughout the tile configuration.
    Only boolean-type globals are considered valid for conditions.
    
    Args:
        esphome_config: ESPhome config dict with parsed globals
    
    Returns:
        Set of boolean global variable IDs
    """
    available_globals = set()
    
    # Get globals from the 'globals:' section
    globals_list = esphome_config.get('globals', [])
    if globals_list:
        for global_var in globals_list:
            if isinstance(global_var, dict) and 'id' in global_var:
                # Only include boolean-type globals
                var_type = global_var.get('type', '')
                if 'bool' in str(var_type):
                    available_globals.add(global_var['id'])
    
    return available_globals


def collect_referenced_scripts(screens):
    """Collect all script IDs referenced in the tile configuration with their usage context.
    
    Scripts can be referenced in:
    - display list (all tile types) - should be display scripts
    - perform list (ha_action tiles) - should be action scripts
    - location_perform list (ha_action tiles) - should be location_action scripts
    - on_press and on_release (function tiles) - should be action scripts
    
    Args:
        screens: List of screen configurations
    
    Returns:
        Dict mapping script ID to list of context info dicts:
        {
            'script_id': [
                {'type': 'display', 'screen': 'screen_id', 'tile_type': 'ha_action', 'x': 0, 'y': 0},
                ...
            ],
            ...
        }
    """
    referenced_scripts = {}
    
    # Configuration for script fields per tile type
    # field_name: (usage_type, expected_script_type)
    TILE_SCRIPT_FIELDS = {
        "ha_action": {
            "perform": ("perform", "action"),
            "location_perform": ("location_perform", "location_action")
        },
        "function": {
            "on_press": ("on_press", "action"),
            "on_release": ("on_release", "action")
        }
    }
    
    for screen in screens:
        screen_id = screen.get("id", "")
        tiles = screen.get("tiles", [])
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            config = tile[tile_type]
            x = config.get("x", 0)
            y = config.get("y", 0)
            
            # 1. Collect from display list (common to all tile types)
            display = config.get("display", [])
            if display:
                for func in (display if isinstance(display, list) else [display]):
                    if isinstance(func, str) and func:
                        if func not in referenced_scripts:
                            referenced_scripts[func] = []
                        referenced_scripts[func].append({
                            'type': 'display',
                            'screen': screen_id,
                            'tile_type': tile_type,
                            'x': x,
                            'y': y,
                            'usage': 'display'
                        })
            
            # 2. Collect from tile-specific fields
            fields_map = TILE_SCRIPT_FIELDS.get(tile_type, {})
            for field, (usage, expected_type) in fields_map.items():
                values = config.get(field, [])
                if not values:
                    continue
                
                # Handle both single string and list of strings
                if isinstance(values, str):
                    values = [values]
                
                for func in values:
                    if isinstance(func, str) and func:
                        if func not in referenced_scripts:
                            referenced_scripts[func] = []
                        referenced_scripts[func].append({
                            'type': expected_type,
                            'screen': screen_id,
                            'tile_type': tile_type,
                            'x': x,
                            'y': y,
                            'usage': usage
                        })
            
    return referenced_scripts
    
    return referenced_scripts


def collect_referenced_globals(screens):
    """Collect all boolean global variable IDs referenced in condition expressions.
    
    Conditions are used in various places, currently:
    - requires_fast_refresh: Determines if a tile needs frequent updates
    
    Args:
        screens: List of screen configurations
    
    Returns:
        Set of referenced boolean global variable IDs
    """
    referenced_globals = set()
    
    def _collect_from_expression(expression_config):
        """Recursively collect global IDs from a condition expression."""
        if not expression_config:
            return
        
        if isinstance(expression_config, str):
            referenced_globals.add(expression_config)
        elif isinstance(expression_config, dict):
            # Check for direct conditions list
            conditions = expression_config.get("conditions", [])
            if conditions:
                for condition in conditions:
                    if isinstance(condition, str):
                        referenced_globals.add(condition)
            
            # Check for nested items
            items = expression_config.get("items", [])
            if items:
                for item in items:
                    _collect_from_expression(item)
    
    for screen in screens:
        tiles = screen.get("tiles", [])
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            config = tile[tile_type]
            
            # Collect from ha_action tiles' requires_fast_refresh
            if tile_type == "ha_action":
                requires_fast_refresh = config.get("requires_fast_refresh", None)
                _collect_from_expression(requires_fast_refresh)
    
    return referenced_globals


def collect_dynamic_entities(entities_config, entity_set):
    """Collect all dynamic entity names from entity config.
    
    Args:
        entities_config: Entity configuration (string, dict, or list)
        entity_set: Set to add dynamic entity names to
    """
    if isinstance(entities_config, str):
        return
    
    if isinstance(entities_config, dict):
        if "dynamic_entity" in entities_config:
            entity_set.add(entities_config["dynamic_entity"])
        return
    
    if isinstance(entities_config, list):
        for entity in entities_config:
            if isinstance(entity, dict) and "dynamic_entity" in entity:
                entity_set.add(entity["dynamic_entity"])
