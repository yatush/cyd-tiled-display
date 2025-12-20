"""
Test script for tile_ui C++ generation.
Run this script directly to see the generated C++ code for a sample configuration or a specific YAML file.
Usage: python3 custom_components/tile_ui/test_output.py [path/to/tiles.yaml]
"""
import sys
import os
import argparse
import yaml
from unittest.mock import MagicMock

# 1. Setup paths to allow importing custom_components.tile_ui
# Assuming script is at custom_components/tile_ui/test_output.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir) # tile_ui
grandparent_dir = os.path.dirname(parent_dir) # custom_components
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

# 2. Mock esphome dependencies BEFORE importing tile_ui
# This is necessary because tile_ui/__init__.py imports esphome modules
mock_esphome = MagicMock()
sys.modules['esphome'] = mock_esphome
sys.modules['esphome.codegen'] = mock_esphome.codegen
sys.modules['esphome.const'] = mock_esphome.const
sys.modules['esphome.core'] = mock_esphome.core

# Use real voluptuous for config_validation to enable schema checks
try:
    import voluptuous as vol
    # Create a mock that delegates to voluptuous for schema-related things
    mock_cv = MagicMock()
    mock_cv.Schema = vol.Schema
    mock_cv.Optional = vol.Optional
    mock_cv.Required = vol.Required
    mock_cv.Any = vol.Any
    mock_cv.All = vol.All
    mock_cv.Invalid = vol.Invalid
    mock_cv.string = str
    mock_cv.boolean = bool
    mock_cv.int_ = int
    mock_cv.ensure_list = lambda x: x if isinstance(x, list) else [x]
    
    sys.modules['esphome.config_validation'] = mock_cv
    mock_esphome.config_validation = mock_cv
    print("Using real voluptuous for validation.")
except ImportError:
    print("Warning: voluptuous not found. Schema validation will be skipped.")
    sys.modules['esphome.config_validation'] = mock_esphome.config_validation

# 3. Mock validation to avoid needing full ESPHome config/scripts
# We mock the module 'tile_ui.validation' so that when it is imported inside functions, it gets our mock
# mock_validation = MagicMock()
# sys.modules['tile_ui.validation'] = mock_validation
# # The validate_tiles_config function should do nothing (pass validation)
# mock_validation.validate_tiles_config = MagicMock(return_value=None)

# 4. Import the real module
try:
    import tile_ui
    from tile_ui import generate_init_tiles_cpp
    from tile_ui.data_collection import load_tiles_yaml
    from tile_ui.schema import screens_list_schema
except ImportError as e:
    print(f"Error importing tile_ui: {e}")
    print("Make sure you are running from the esphome directory (e.g., python custom_components/tile_ui/test_output.py)")
    sys.exit(1)

# Mock ESPHome YAML tags for local loading
def mock_constructor(loader, node):
    return node.value

yaml.SafeLoader.add_constructor('!secret', mock_constructor)
yaml.SafeLoader.add_constructor('!lambda', mock_constructor)

def test_generation(file_path=None):
    print("Testing Tile UI C++ Generation (using real component logic)...\n")

    screens = []
    if file_path:
        print(f"Loading configuration from: {file_path}")
        try:
            # Use the real loader from data_collection
            config = load_tiles_yaml(file_path)
            screens = config.get("screens", [])
            if not screens:
                print("No 'screens' found in configuration.")
                return
        except Exception as e:
            print(f"Error loading YAML: {e}")
            return
    else:
        print("Using built-in sample configuration.")
        # Sample Screen Configuration
        screens = [
            {
                "id": "main_screen",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "cycle_entity": {
                            "x": 0,
                            "y": 0,
                            "display": ["fan_icon_script"],
                            "dynamic_entity": "fan_entity_var",
                            "options": [
                                {"entity": "fan.low", "label": "Low"},
                                {"entity": "fan.high", "label": "High"}
                            ]
                        }
                    },
                    {
                        "move_page": {
                            "x": 1,
                            "y": 0,
                            "display": ["settings_icon"],
                            "destination": "main_screen"
                        }
                    }
                ]
            }
        ]

    # Run Schema Validation
    print("Running Schema Validation...")
    try:
        screens = screens_list_schema(screens)
        print("Schema Validation Passed.")
    except Exception as e:
        print(f"Schema Validation Failed: {e}")
        return

    # Generate the C++ code using the real function from __init__.py
    # We pass None for available_scripts/globals because we mocked validation
    try:
        cpp_lambdas = generate_init_tiles_cpp(screens, available_scripts=None, available_globals=None)
        
        combined_lambda = "\n".join(cpp_lambdas)
        
        # Replicate the wrapper logic from __init__.py
        stmt = f"""
App.scheduler.set_timeout(nullptr, "tile_ui_init", 2000, [=]() {{
{combined_lambda}
}});
"""
        print(stmt)
        print("\nGeneration Complete.")
        
    except Exception as e:
        print(f"Error during generation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test Tile UI C++ Generation')
    parser.add_argument('file', nargs='?', help='Path to tiles.yaml file')
    args = parser.parse_args()
    
    test_generation(args.file)
