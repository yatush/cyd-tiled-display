"""Data collection and YAML loading for tile UI component.

This module handles:
- Loading YAML tile configuration files
- Collecting available scripts and their parameters
- Collecting available globals
- Collecting referenced scripts and globals from tile configuration
"""
from typing import Any
import os

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

__all__ = [
    "load_tiles_yaml",
    "collect_available_scripts",
    "collect_available_globals",
    "collect_referenced_scripts",
    "collect_referenced_globals",
    "collect_dynamic_entities",
    "parse_dynamic_entities_config",
]


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
    if yaml is None:
        raise ImportError("PyYAML is required to load tiles YAML files")
    
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
    scripts = []
    if 'script' in esphome_config and isinstance(esphome_config['script'], list):
        scripts.extend(esphome_config['script'])
        
    # Also check packages
    packages = esphome_config.get('packages', {})
    if isinstance(packages, dict):
        for _, package_content in packages.items():
            if isinstance(package_content, dict):
                package_scripts = package_content.get('script', [])
                if isinstance(package_scripts, list):
                    scripts.extend(package_scripts)
    
    if scripts:
        for script in scripts:
            if isinstance(script, dict) and 'id' in script:
                script_id = script['id']
                # Handle ID being an object (sometimes happens in ESPHome config objects)
                if hasattr(script_id, 'id'):
                    script_id = script_id.id
                
                parameters = script.get('parameters', {})
                available_scripts[str(script_id)] = {
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
    globals_list = []
    if 'globals' in esphome_config and isinstance(esphome_config['globals'], list):
        globals_list.extend(esphome_config['globals'])

    # Also check packages
    packages = esphome_config.get('packages', {})
    if isinstance(packages, dict):
        for _, package_content in packages.items():
            if isinstance(package_content, dict):
                package_globals = package_content.get('globals', [])
                if isinstance(package_globals, list):
                    globals_list.extend(package_globals)

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
            "location_perform": ("location_perform", "location_action"),
            "long_perform": ("long_perform", "action")
        },
        "function": {
            "on_press": ("on_press", "action"),
            "on_release": ("on_release", "action")
        }
    }
    
    def _collect_from_expression(expression_config, screen_id, tile_type, x, y):
        """Recursively collect script IDs from a condition expression."""
        if not expression_config:
            return
        
        if isinstance(expression_config, str):
            func_name = expression_config
            if func_name not in referenced_scripts:
                referenced_scripts[func_name] = []
            referenced_scripts[func_name].append({
                'type': 'condition',
                'screen': screen_id,
                'tile_type': tile_type,
                'x': x,
                'y': y,
                'usage': 'requires_fast_refresh'
            })
        elif isinstance(expression_config, dict):
            conditions = expression_config.get("conditions")
            if isinstance(conditions, str):
                _collect_from_expression(conditions, screen_id, tile_type, x, y)
            elif isinstance(conditions, list):
                for condition in conditions:
                    _collect_from_expression(condition, screen_id, tile_type, x, y)

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
                    func_name = None
                    params = None
                    
                    if isinstance(func, str) and func:
                        func_name = func
                    elif isinstance(func, dict) and len(func) == 1:
                        func_name = list(func.keys())[0]
                        params = func[func_name]
                    
                    if func_name:
                        if func_name not in referenced_scripts:
                            referenced_scripts[func_name] = []
                        
                        # Determine expected type based on tile type
                        expected_type = 'display'
                        if tile_type == 'function':
                            expected_type = 'display_simple'
                        elif tile_type == 'toggle_entity':
                            expected_type = 'display_toggle'
                        elif tile_type == 'cycle_entity':
                            expected_type = 'display_cycle'

                        referenced_scripts[func_name].append({
                            'type': expected_type,
                            'screen': screen_id,
                            'tile_type': tile_type,
                            'x': x,
                            'y': y,
                            'usage': 'display',
                            'params': params
                        })
            
            # 2. Collect from tile-specific fields
            fields_map = TILE_SCRIPT_FIELDS.get(tile_type, {})
            for field, (usage, expected_type) in fields_map.items():
                values = config.get(field, [])
                if not values:
                    continue
                
                # Handle both single string and list of strings
                if isinstance(values, (str, dict)):
                    values = [values]
                
                for func in values:
                    func_name = None
                    params = None
                    
                    if isinstance(func, str) and func:
                        func_name = func
                    elif isinstance(func, dict) and len(func) == 1:
                        func_name = list(func.keys())[0]
                        params = func[func_name]

                    if func_name:
                        if func_name not in referenced_scripts:
                            referenced_scripts[func_name] = []
                        referenced_scripts[func_name].append({
                            'type': expected_type,
                            'screen': screen_id,
                            'tile_type': tile_type,
                            'x': x,
                            'y': y,
                            'usage': usage,
                            'params': params
                        })
            
            # 3. Collect from requires_fast_refresh (ha_action tiles)
            if tile_type == "ha_action":
                requires_fast_refresh = config.get("requires_fast_refresh")
                if requires_fast_refresh:
                    _collect_from_expression(requires_fast_refresh, screen_id, tile_type, x, y)
            
    return referenced_scripts


def collect_referenced_globals(screens):
    """Collect all boolean global variable IDs referenced in condition expressions.
    
    Note: Currently all conditions have been migrated to use scripts (functions)
    instead of globals. This function remains for future use if globals are
    re-introduced in other contexts.
    
    Args:
        screens: List of screen configurations
    
    Returns:
        Set of referenced boolean global variable IDs
    """
    return set()


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


def _normalize_fixed_entity_values(name: str, raw_val: Any) -> list[str]:
    """Validate and normalize fixed entity value(s) for a dynamic entity."""
    if isinstance(raw_val, str):
        values = [v.strip() for v in raw_val.split(",")] if "," in raw_val else [raw_val.strip()]
    elif isinstance(raw_val, list):
        if not raw_val:
            raise ValueError(f"Fixed dynamic entity '{name}' cannot have an empty entity list")
        values = []
        for item in raw_val:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Fixed dynamic entity '{name}' list items must be non-empty strings, got {item!r}"
                )
            values.append(item.strip())
    else:
        raise ValueError(
            f"Fixed dynamic entity '{name}' must map to an entity string or list of entity strings, "
            f"got {type(raw_val).__name__}"
        )

    if not values or any(not v for v in values):
        raise ValueError(f"Fixed dynamic entity '{name}' must specify at least one non-empty entity ID")

    for ent in values:
        if "#{" in ent:
            raise ValueError(
                f"Fixed dynamic entity '{name}' value '{ent}' cannot contain dynamic placeholders"
            )
    return values


def parse_dynamic_entities_config(
    dynamic_entities_config: Any,
) -> tuple[list[str] | None, dict[str, list[str]]]:
    """Normalize top-level ``dynamic_entities`` configuration.

    Supports:
    - ``None`` -> ``(None, {})`` (no explicit declaration)
    - List of mixed entries:
      - ``"VAR"`` -> runtime dynamic entity
      - ``{"VAR": "domain.entity"}`` or ``{"VAR": ["domain.e1", "domain.e2"]}`` -> fixed dynamic entity
      - ``{"name": "VAR", "entities": [...]}`` / ``{"name": "VAR", "value": ...}`` -> object form
    - Dict mapping ``{"VAR": "domain.entity", ...}`` -> convenience mapping form

    Returns:
        Tuple of ``(declared_names, fixed_values)`` where ``declared_names`` preserves
        declaration order and ``fixed_values`` maps fixed variable names to their entity lists.
    """
    if dynamic_entities_config is None:
        return None, {}

    declared_names: list[str] = []
    seen_names: set[str] = set()
    fixed_values: dict[str, list[str]] = {}

    def _register(raw_name: Any, fixed_raw: Any = None, has_fixed: bool = False) -> None:
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError(f"Dynamic entity name must be a non-empty string, got {raw_name!r}")
        name = raw_name.strip()
        if name in seen_names:
            raise ValueError(f"Duplicate dynamic entity declaration: '{name}'")
        seen_names.add(name)
        declared_names.append(name)
        if has_fixed:
            fixed_values[name] = _normalize_fixed_entity_values(name, fixed_raw)

    if isinstance(dynamic_entities_config, dict):
        for k, v in dynamic_entities_config.items():
            if v is None:
                _register(k, has_fixed=False)
            else:
                _register(k, v, has_fixed=True)
        return declared_names, fixed_values

    if not isinstance(dynamic_entities_config, list):
        raise ValueError(
            f"dynamic_entities must be a list, got {type(dynamic_entities_config).__name__}"
        )

    for entry in dynamic_entities_config:
        if isinstance(entry, str):
            _register(entry, has_fixed=False)
        elif isinstance(entry, dict):
            if "name" in entry and set(entry.keys()).issubset({"name", "entities", "value"}):
                if "entities" in entry and "value" in entry:
                    raise ValueError(
                        f"Dynamic entity '{entry.get('name')}' cannot specify both 'entities' and 'value'"
                    )
                has_val = ("entities" in entry and entry["entities"] is not None) or (
                    "value" in entry and entry["value"] is not None
                )
                raw_val = entry.get("entities") if "entities" in entry else entry.get("value")
                _register(entry["name"], raw_val, has_fixed=has_val)
            elif len(entry) == 1:
                name, raw_val = next(iter(entry.items()))
                if raw_val is None:
                    raise ValueError(
                        f"Fixed dynamic entity '{name}' must specify at least one non-empty entity ID"
                    )
                _register(name, raw_val, has_fixed=True)
            else:
                raise ValueError(
                    f"Invalid dynamic_entities dict entry {entry!r}: expected single-key "
                    f"'{{VAR: entity_or_list}}' or '{{name: VAR, entities: [...]}}'"
                )
        else:
            raise ValueError(
                f"dynamic_entities items must be strings or dicts, got {type(entry).__name__}"
            )

    return declared_names, fixed_values
