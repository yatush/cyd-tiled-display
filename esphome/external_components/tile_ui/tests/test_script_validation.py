import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Mock esphome module before importing tile_ui.
# When running under pytest the root conftest.py already provides these mocks;
# only install them here when running the script standalone.
if 'esphome' not in sys.modules:
    import types
    esphome = types.ModuleType('esphome')
    esphome.codegen = MagicMock()
    esphome.config_validation = MagicMock()
    esphome.config_validation.Invalid = ValueError
    esphome.const = MagicMock()
    esphome.core = MagicMock()
    esphome.components = MagicMock()
    esphome.components.display = MagicMock()
    sys.modules['esphome'] = esphome
    sys.modules['esphome.codegen'] = esphome.codegen
    sys.modules['esphome.config_validation'] = esphome.config_validation
    sys.modules['esphome.const'] = esphome.const
    sys.modules['esphome.core'] = esphome.core
    sys.modules['esphome.components'] = esphome.components
    sys.modules['esphome.components.display'] = esphome.components.display

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from tile_ui.validation import validate_tiles_config
from tile_ui.script_types import get_script_type, validate_script_type

class TestScriptValidation(unittest.TestCase):
    
    def setUp(self):
        self.available_scripts = {
            "display_std": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int", "entities": "string[]"}},
            "display_simple": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int"}},
            "display_toggle": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int", "name": "string", "state": "bool"}},
            "display_cycle": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int", "name": "string", "options": "string[]"}},
            "action_std": {"parameters": {"entities": "string[]"}},
            "location_action": {"parameters": {"x": "float", "y": "float", "entities": "string[]"}},
            
            # Invalid/Old signatures
            "display_old": {"parameters": {"x": "int", "y": "int", "entities": "string[]"}},
        }

    def test_get_script_type(self):
        self.assertEqual(get_script_type(self.available_scripts["display_std"]["parameters"]), "display")
        self.assertEqual(get_script_type(self.available_scripts["display_simple"]["parameters"]), "display_simple")
        self.assertEqual(get_script_type(self.available_scripts["display_toggle"]["parameters"]), "display_toggle")
        self.assertEqual(get_script_type(self.available_scripts["display_cycle"]["parameters"]), "display_cycle")
        self.assertEqual(get_script_type(self.available_scripts["action_std"]["parameters"]), "action")
        self.assertEqual(get_script_type(self.available_scripts["location_action"]["parameters"]), "location_action")
        
        # Old signature should now be unknown or mismatched if we strictly check param count
        # display_old has 3 params: int, int, string[] -> matches 'location_action' if we only check types?
        # No, location_action is float, float.
        # display_old is int, int, string[].
        # In my updated get_script_type:
        # 3 params:
        #   if int, int, string[] -> display (Wait, I removed this?)
        
        # Let's check get_script_type implementation again.
        # I removed the 3-param check for display (int, int, string[]).
        # So display_old should return 'unknown' or 'action' (if it falls through)?
        # It falls through to 'unknown' because it has 3 params and doesn't match location_action (float, float).
        self.assertEqual(get_script_type(self.available_scripts["display_old"]["parameters"]), "unknown")

    def test_validate_script_type_display(self):
        # Valid display script
        validate_script_type("display_std", self.available_scripts["display_std"], "display", "test")
        
        # Invalid display script (old signature)
        with self.assertRaises(ValueError) as cm:
            validate_script_type("display_old", self.available_scripts["display_old"], "display", "test")
        self.assertIn("must have coordinate parameters", str(cm.exception))

    def test_validate_script_type_simple(self):
        validate_script_type("display_simple", self.available_scripts["display_simple"], "display_simple", "test")

    def test_validate_script_type_toggle(self):
        validate_script_type("display_toggle", self.available_scripts["display_toggle"], "display_toggle", "test")

    def test_sized_cover_display_accepts_font_and_icon(self):
        from tile_ui.tile_generation import generate_tile_cpp

        params = dict(self.available_scripts["display_toggle"]["parameters"])
        params["is_on"] = params.pop("state")
        params["size"] = "esphome::display::BaseFont*"
        params["icon"] = "string"
        scripts = {"tile_choose_cover_sized": {"parameters": params}}
        tile = {"toggle_entity": {
            "x": 0, "y": 0, "dynamic_entity": "BLINDS", "entity": "cover.lr1",
            "display": [{"tile_choose_cover_sized": {"size": "tiny", "icon": '"\\U0000ec0e"'}}],
        }}
        screens = [{"id": "blinds", "flags": ["BASE"], "tiles": [tile]}]
        validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])
        cpp = generate_tile_cpp(tile, scripts, "blinds")
        self.assertIn('id(tile_choose_cover_sized).execute(arg0, arg1, arg2, arg3, arg4, arg5, &id(tiny), "\\U0000ec0e")', cpp)
        tile["toggle_entity"]["display"] = [{"tile_choose_cover_sized": {"size": "tiny"}}]
        with self.assertRaisesRegex(ValueError, "Missing required parameter 'icon'"):
            validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])

    def test_text_selection_display_accepts_text_and_font(self):
        from tile_ui.tile_generation import generate_tile_cpp

        params = dict(self.available_scripts["display_toggle"]["parameters"])
        params["is_on"] = params.pop("state")
        params["text"] = "string"
        params["size"] = "esphome::display::BaseFont*"
        scripts = {"tile_choose_text": {"parameters": params}}
        tile = {"toggle_entity": {
            "x": 0, "y": 0, "dynamic_entity": "BLINDS", "entity": "cover.lr1",
            "display": [{"tile_choose_text": {"text": "Living Room", "size": "text_small"}}],
        }}
        screens = [{"id": "blinds", "flags": ["BASE"], "tiles": [tile]}]
        validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])
        cpp = generate_tile_cpp(tile, scripts, "blinds")
        self.assertIn('id(tile_choose_text).execute(arg0, arg1, arg2, arg3, arg4, arg5, "Living Room", &id(text_small))', cpp)

    def test_sized_blinds_display_accepts_font_parameter(self):
        from tile_ui.tile_generation import generate_tile_cpp

        params = dict(self.available_scripts["display_std"]["parameters"])
        params["size"] = "esphome::display::BaseFont*"
        scripts = {
            "tile_blinds_up_down_sized": {"parameters": params},
            "action_blinds_up_down": self.available_scripts["location_action"],
        }
        tile = {"ha_action": {
            "x": 0, "y": 0, "entities": [{"dynamic_entity": "BLINDS"}],
            "display": [{"tile_blinds_up_down_sized": {"size": "tiny"}}],
            "location_perform": ["action_blinds_up_down"],
        }}
        screens = [{"id": "blinds", "flags": ["BASE"], "tiles": [tile]}]
        validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])
        cpp = generate_tile_cpp(tile, scripts, "blinds")
        self.assertIn("id(tile_blinds_up_down_sized).execute(arg0, arg1, arg2, arg3, arg4, &id(tiny))", cpp)

    def test_blinds_position_action_accepts_position(self):
        from tile_ui.tile_generation import generate_tile_cpp

        scripts = {
            "display_std": self.available_scripts["display_std"],
            "action_blinds_position": {"parameters": {"entities": "string[]", "position": "int"}},
        }
        tile = {"ha_action": {
            "x": 0, "y": 0, "entities": [{"dynamic_entity": "BLINDS"}],
            "display": ["display_std"],
            "perform": [{"action_blinds_position": {"position": 40}}],
        }}
        screens = [{"id": "blinds", "flags": ["BASE"], "tiles": [tile]}]
        validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])
        cpp = generate_tile_cpp(tile, scripts, "blinds")
        self.assertIn("id(action_blinds_position).execute(arg0, 40)", cpp)
        tile["ha_action"]["perform"] = [{"action_blinds_position": {}}]
        with self.assertRaisesRegex(ValueError, "Missing required parameter 'position'"):
            validate_tiles_config(screens, scripts, declared_dynamic_entities=["BLINDS"])

    def test_validate_script_type_cycle(self):
        validate_script_type("display_cycle", self.available_scripts["display_cycle"], "display_cycle", "test")

    def test_validate_tiles_config_integration(self):
        screens = [{
            "id": "main",
            "flags": ["BASE"],
            "tiles": [
                {"ha_action": {
                    "x": 0, "y": 0,
                    "display": ["display_std"],
                    "perform": ["action_std"],
                    "entities": ["light.test"]
                }}
            ]
        }]
        
        # Should pass
        validate_tiles_config(screens, self.available_scripts)
        
        # Fail with old script
        screens[0]["tiles"][0]["ha_action"]["display"] = ["display_old"]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(screens, self.available_scripts)
        self.assertIn("must have coordinate parameters", str(cm.exception))

if __name__ == '__main__':
    unittest.main()
