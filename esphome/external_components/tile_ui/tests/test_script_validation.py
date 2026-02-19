import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Mock esphome module before importing tile_ui
import types
esphome = types.ModuleType('esphome')
esphome.codegen = MagicMock()
esphome.config_validation = MagicMock()
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

# Mock voluptuous
voluptuous = MagicMock()
sys.modules['voluptuous'] = voluptuous

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
