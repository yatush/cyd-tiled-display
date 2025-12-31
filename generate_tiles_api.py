import sys
import os
import yaml
import json
from pathlib import Path

# Add the custom_components directory to sys.path so we can import tile_ui
repo_root = Path(__file__).parent
tile_ui_path = repo_root / "esphome" / "custom_components"
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

# Mock voluptuous since it's not installed but imported by schema.py
sys.modules['voluptuous'] = MockEsphome()

try:
    # Import only what we need, avoiding __init__.py if possible or relying on mocks
    # Since __init__.py imports esphome, the mocks above are crucial.
    from tile_ui import generate_init_tiles_cpp
    from tile_ui.validation import validate_tiles_config
    from tile_ui.data_collection import collect_available_scripts, collect_available_globals
except ImportError as e:
    print(json.dumps({"error": f"Failed to import tile_ui: {e}"}))
    sys.exit(1)

def main():
    try:
        # Read YAML from stdin
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"error": "No input data provided"}))
            return

        config = yaml.safe_load(input_data)
        screens = config.get("screens", [])

        # Load lib.yaml to get available scripts and globals
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
                    available_scripts = collect_available_scripts(lib_doc)
                    available_globals = collect_available_globals(lib_doc)

        # Validate
        try:
            validate_tiles_config(screens, available_scripts, available_globals)
        except ValueError as e:
            print(json.dumps({"error": str(e), "type": "validation_error"}))
            return

        # Generate
        cpp_lambdas = generate_init_tiles_cpp(screens, available_scripts, available_globals)
        
        print(json.dumps({
            "success": True,
            "cpp": cpp_lambdas,
            "message": f"Successfully generated {len(cpp_lambdas)} initialization blocks."
        }))

    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": "unexpected_error"
        }))

if __name__ == "__main__":
    main()
