import unittest
from unittest.mock import MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Mock esphome.config_validation for schema import
try:
    import esphome.config_validation as cv
except ImportError:
    # Create module structure
    esphome = MagicMock()
    sys.modules["esphome"] = esphome
    cv_mock = MagicMock()
    cv_mock.Invalid = ValueError
    sys.modules["esphome.config_validation"] = cv_mock
    sys.modules["esphome.codegen"] = MagicMock()
    sys.modules["esphome.const"] = MagicMock()
    sys.modules["esphome.core"] = MagicMock()

from tile_ui.tile_generation import generate_tile_cpp

class TestTileGeneration(unittest.TestCase):
    
    def test_ha_action_tile(self):
        config = {
            "ha_action": {
                "x": 0, "y": 0,
                "display": "icon",
                "perform": "action1",
                "entities": "sensor.1"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn("new HAActionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(icon).execute(arg0, arg1, arg2, arg3, arg4); } }, { [](std::vector<std::string> arg0) { id(action1).execute(arg0); } }, {\"sensor.1\"})", cpp)
    
    def test_ha_action_tile_complex(self):
        config = {
            "ha_action": {
                "x": 1, "y": 1,
                "display": ["icon"],
                "perform": ["p1"],
                "location_perform": ["l1"],
                "entities": [{"dynamic_entity": "dyn"}]
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        expected_args = "1, 1, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(icon).execute(arg0, arg1, arg2, arg3, arg4); } }, { [](std::vector<std::string> arg0) { id(p1).execute(arg0); } }, { [](float arg0, float arg1, std::vector<std::string> arg2) { id(l1).execute(arg0, arg1, arg2); } }, {\"#{dyn}\"}"
        self.assertIn(f"new HAActionTile({expected_args})", cpp)

    def test_title_tile(self):
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "label",
                "entities": "sensor.time"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new TitleTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(label).execute(arg0, arg1, arg2, arg3, arg4); } }, {"sensor.time"})', cpp)

    def test_move_page_tile(self):
        config = {
            "move_page": {
                "x": 0, "y": 0,
                "display": "arrow",
                "destination": "screen2"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new MovePageTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(arrow).execute(arg0, arg1, arg2, arg3); } }, &id(screen2))', cpp)
        
    def test_move_page_tile_dynamic(self):
        config = {
            "move_page": {
                "x": 0, "y": 0,
                "display": "arrow",
                "destination": "screen2",
                "dynamic_entry": {
                    "dynamic_entity": "var",
                    "value": "val1, val2"
                }
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn('setDynamicEntry("var", {"val1", "val2"})', cpp)

    def test_function_tile(self):
        config = {
            "function": {
                "x": 0, "y": 0,
                "display": "btn",
                "on_press": "press_cb"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(btn).execute(arg0, arg1, arg2, arg3); } }, []() { id(press_cb).execute(); })', cpp)
        
        # With on_release
        config["function"]["on_release"] = "release_cb"
        cpp = generate_tile_cpp(config)
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(btn).execute(arg0, arg1, arg2, arg3); } }, []() { id(press_cb).execute(); }, []() { id(release_cb).execute(); })', cpp)

    def test_toggle_entity_tile(self):
        config = {
            "toggle_entity": {
                "x": 0, "y": 0,
                "display": "icon",
                "dynamic_entity": "state_var",
                "entity": "light.living_room",
                "presentation_name": "Living Room"
            }
        }
        cpp = generate_tile_cpp(config)
        expected = 'new ToggleEntityTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::string arg4, bool arg5) { id(icon).execute(arg0, arg1, arg2, arg3, arg4, arg5); } }, "state_var", {"light.living_room"}, "Living Room", false)'
        self.assertIn(expected, cpp)

    def test_cycle_entity_tile(self):
        config = {
            "cycle_entity": {
                "x": 0, "y": 0,
                "display": "icon",
                "dynamic_entity": "mode_var",
                "options": [
                    {"entity": "mode1", "label": "Mode 1"},
                    {"entity": "mode2", "label": "Mode 2"}
                ]
            }
        }
        cpp = generate_tile_cpp(config)
        options_cpp = '{ { {"mode1"}, "Mode 1" }, { {"mode2"}, "Mode 2" } }'
        self.assertIn(f'new CycleEntityTile(0, 0, {{ [](int arg0, int arg1, int arg2, int arg3, std::string arg4, std::vector<std::string> arg5) {{ id(icon).execute(arg0, arg1, arg2, arg3, arg4, arg5); }} }}, "mode_var", {options_cpp}, false)', cpp)

    def test_modifiers(self):
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "d",
                "entities": "e",
                "omit_frame": True
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn("->omitFrame()", cpp)

    def test_activation_var_modifiers(self):
        # Single value
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "d",
                "entities": "e",
                "activation_var": {
                    "dynamic_entity": "state",
                    "value": "on"
                }
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn('->setActivationVar("state", {"on"})', cpp)

        # Multiple values
        config["title"]["activation_var"]["value"] = "on, off"
        cpp = generate_tile_cpp(config)
        self.assertIn('->setActivationVar("state", {"on", "off"})', cpp)

if __name__ == '__main__':
    unittest.main()
