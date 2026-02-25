import sys
import os
import yaml
import json
from pathlib import Path

# Add the external_components directory to sys.path so we can import tile_ui
repo_root = Path(__file__).parent.parent
tile_ui_path = repo_root / "esphome" / "external_components"
sys.path.append(str(tile_ui_path))

# Mock esphome module to prevent import errors
class MockEsphome:
    def __getattr__(self, name):
        return MockEsphome()
    def __call__(self, *args, **kwargs):
        return MockEsphome()

sys.modules['esphome'] = MockEsphome()
sys.modules['esphome.codegen'] = MockEsphome()
sys.modules['esphome.config_validation'] = MockEsphome()
sys.modules['esphome.const'] = MockEsphome()
sys.modules['esphome.core'] = MockEsphome()
sys.modules['esphome.components'] = MockEsphome()
sys.modules['esphome.components.display'] = MockEsphome()

# Minimal implementation of voluptuous and esphome.config_validation
# to support schema validation without external dependencies.

class Invalid(Exception):
    def __init__(self, message, path=None):
        super().__init__(message)
        self.msg = message
        self.path = path or []
    def __str__(self):
        return self.msg

class Marker:
    def __init__(self, schema, default=None, msg=None):
        self.schema = schema
        self.default = default
        self.msg = msg
    def __hash__(self):
        return hash(self.schema)
    def __eq__(self, other):
        return isinstance(other, Marker) and self.schema == other.schema

class Required(Marker):
    pass

class Optional(Marker):
    pass

PREVENT_EXTRA = 1

class Schema:
    def __init__(self, schema, extra=None):
        self.schema = schema
        self.extra = extra

    def __call__(self, data):
        if not isinstance(data, dict):
            raise Invalid(f"expected dict, got {type(data).__name__}")
        
        out = {}
        schema_map = {}
        for k, v in self.schema.items():
            key_name = k.schema if isinstance(k, Marker) else k
            schema_map[key_name] = (k, v)

        if self.extra == PREVENT_EXTRA:
            for k in data:
                if k not in schema_map:
                    raise Invalid(f"extra keys not allowed: {k}")

        for key_name, (key_schema, validator) in schema_map.items():
            if key_name in data:
                value = data[key_name]
                try:
                    if isinstance(validator, Schema):
                        out[key_name] = validator(value)
                    elif callable(validator):
                        out[key_name] = validator(value)
                    elif isinstance(validator, type):
                        if not isinstance(value, validator):
                            raise Invalid(f"expected {validator.__name__}, got {type(value).__name__}")
                        out[key_name] = value
                    else:
                        if value != validator:
                            raise Invalid(f"expected {validator}, got {value}")
                        out[key_name] = value
                except Invalid as e:
                    raise Invalid(f"Invalid value for '{key_name}': {e}")
                except Exception as e:
                    raise Invalid(f"Validation error for '{key_name}': {e}")
            else:
                if isinstance(key_schema, Required) or not isinstance(key_schema, Optional):
                     raise Invalid(f"required key not provided: {key_name}")
        return out

def Any(*validators):
    def validate(val):
        errors = []
        for v in validators:
            try:
                if callable(v):
                    return v(val)
                elif isinstance(v, type):
                    if isinstance(val, v):
                        return val
                    else:
                        raise Invalid(f"expected {v.__name__}")
                else:
                    if val == v:
                        return val
                    else:
                        raise Invalid(f"expected {v}")
            except (Invalid, ValueError, TypeError) as e:
                errors.append(str(e))
        raise Invalid(f"no valid option found: {'; '.join(errors)}")
    return validate

def All(*validators):
    def validate(val):
        for v in validators:
            if callable(v):
                val = v(val)
            elif isinstance(v, type):
                if not isinstance(val, v):
                    raise Invalid(f"expected {v.__name__}")
            else:
                if val != v:
                    raise Invalid(f"expected {v}")
        return val
    return validate

class MockVoluptuousModule:
    def __init__(self):
        self.Schema = Schema
        self.Required = Required
        self.Optional = Optional
        self.Any = Any
        self.All = All
        self.PREVENT_EXTRA = PREVENT_EXTRA
        self.Invalid = Invalid

class MockConfigValidation:
    Invalid = Invalid
    
    def string(self, value):
        if not isinstance(value, str):
            raise Invalid(f"Expected string, got {type(value).__name__}")
        return value
        
    def boolean(self, value):
        if not isinstance(value, bool):
            raise Invalid(f"Expected boolean, got {type(value).__name__}")
        return value
        
    def Any(self, *validators):
        return Any(*validators)

sys.modules['voluptuous'] = MockVoluptuousModule()
sys.modules['esphome.config_validation'] = MockConfigValidation()

try:
    # Import only what we need, avoiding __init__.py if possible or relying on mocks
    # Since __init__.py imports esphome, the mocks above are crucial.
    from tile_ui import generate_init_tiles_cpp
    from tile_ui.validation import validate_tiles_config
    from tile_ui.data_collection import collect_available_scripts, collect_available_globals
except ImportError as e:
    print(json.dumps({"error": f"Failed to import tile_ui: {e}"}))
    sys.exit(1)

def generate_cpp_from_yaml(input_data, user_lib_dir=None):
    try:
        if not input_data:
            return {"error": "No input data provided"}

        config = yaml.safe_load(input_data)
        screens = config.get("screens", [])

        # Load lib.yaml to get available scripts and globals
        # Prefer user_lib_dir (e.g. /config/esphome/lib in addon mode) over the bundled lib
        if user_lib_dir and (Path(user_lib_dir) / "lib.yaml").exists():
            lib_path = Path(user_lib_dir) / "lib.yaml"
        else:
            lib_path = repo_root / "esphome" / "lib" / "lib.yaml"
        available_scripts = {}
        available_globals = set()

        if lib_path.exists():
            with open(lib_path, 'r') as f:
                # Define custom schema for !secret tag and others
                class SafeLoaderIgnoreUnknown(yaml.SafeLoader):
                    pass
                def ignore_unknown(loader, node):
                    return None
                
                def include_constructor(loader, node):
                    filename = loader.construct_scalar(node)
                    include_path = lib_path.parent / filename
                    if include_path.exists():
                        with open(include_path, 'r') as f_inc:
                            return yaml.load(f_inc, Loader=SafeLoaderIgnoreUnknown)
                    return None

                SafeLoaderIgnoreUnknown.add_constructor('!secret', ignore_unknown)
                SafeLoaderIgnoreUnknown.add_constructor('!lambda', ignore_unknown)
                SafeLoaderIgnoreUnknown.add_constructor('!include', include_constructor)
                
                lib_doc = yaml.load(f, Loader=SafeLoaderIgnoreUnknown)
                if lib_doc:
                    # Merge lib_common.yaml
                    common_lib_path = lib_path.parent / 'lib_common.yaml'
                    if common_lib_path.exists():
                        try:
                            with open(common_lib_path, 'r') as f_common:
                                common_doc = yaml.load(f_common, Loader=SafeLoaderIgnoreUnknown) or {}
                            for key in ['script', 'globals']:
                                if key in common_doc and isinstance(common_doc[key], list):
                                    lib_doc.setdefault(key, [])
                                    lib_doc[key].extend(common_doc[key])
                        except Exception:
                            pass

                    # Merge lib_custom.yaml — check user_lib_dir first (addon mode), then lib_path.parent
                    _custom_candidates = []
                    if user_lib_dir:
                        _custom_candidates.append(Path(user_lib_dir) / 'lib_custom.yaml')
                    if lib_path.parent not in [Path(c).parent for c in _custom_candidates]:
                        _custom_candidates.append(lib_path.parent / 'lib_custom.yaml')
                    custom_lib_path = next((p for p in _custom_candidates if p.exists()), None)
                    if custom_lib_path:
                        try:
                            with open(custom_lib_path, 'r') as f_custom:
                                custom_doc = yaml.load(f_custom, Loader=SafeLoaderIgnoreUnknown) or {}
                            for key in ['script', 'globals']:
                                if key in custom_doc and isinstance(custom_doc[key], list):
                                    lib_doc.setdefault(key, [])
                                    lib_doc[key].extend(custom_doc[key])
                        except Exception:
                            pass

                    available_scripts = collect_available_scripts(lib_doc)
                    available_globals = collect_available_globals(lib_doc)

        # Validate
        try:
            declared_dynamic_entities = config.get("dynamic_entities") or None
            validate_tiles_config(screens, available_scripts, available_globals, declared_dynamic_entities)
        except ValueError as e:
            return {"error": str(e), "type": "validation_error"}

        # Generate
        cpp_lambdas = generate_init_tiles_cpp(screens, available_scripts, available_globals)
        
        return {
            "success": True,
            "cpp": cpp_lambdas,
            "message": f"Successfully generated {len(cpp_lambdas)} initialization blocks."
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": "unexpected_error"
        }

if __name__ == "__main__":
    # Read YAML from stdin
    input_data = sys.stdin.read()
    result = generate_cpp_from_yaml(input_data)
    print(json.dumps(result))
