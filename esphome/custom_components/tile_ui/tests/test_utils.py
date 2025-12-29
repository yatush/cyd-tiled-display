import unittest
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from tile_ui.tile_utils import (
    format_display_list,
    format_functions_list,
    format_entity_value,
    build_fast_refresh_lambda,
    format_entity_cpp,
    get_tile_modifiers,
    flags_to_cpp
)

class TestTileUtils(unittest.TestCase):
    
    def test_format_display_list(self):
        self.assertEqual(format_display_list("icon", {}, []), "{ []() { id(icon).execute(); } }")
        self.assertEqual(format_display_list(["icon"], {}, []), "{ []() { id(icon).execute(); } }")
        self.assertEqual(format_display_list(["icon", "label"], {}, []), "{ []() { id(icon).execute(); }, []() { id(label).execute(); } }")
        self.assertEqual(format_display_list([], {}, []), "{  }")
        self.assertEqual(format_display_list(None, {}, []), "{  }")

    def test_format_functions_list(self):
        self.assertEqual(format_functions_list("func", {}, []), "{ []() { id(func).execute(); } }")
        self.assertEqual(format_functions_list(["f1", "f2"], {}, []), "{ []() { id(f1).execute(); }, []() { id(f2).execute(); } }")
        self.assertEqual(format_functions_list([], {}, []), "{  }")

    def test_format_entity_value(self):
        # String
        self.assertEqual(format_entity_value("sensor.test"), "sensor.test")
        
        # Dict with dynamic entity
        self.assertEqual(
            format_entity_value({"dynamic_entity": "temp"}), 
            "#{temp}"
        )
        self.assertEqual(
            format_entity_value({"dynamic_entity": "temp", "sensor": "state"}), 
            "#{temp}|state"
        )
        
        # Dict with static entity
        self.assertEqual(
            format_entity_value({"entity": "sensor.test"}), 
            "sensor.test"
        )
        self.assertEqual(
            format_entity_value({"entity": "sensor.test", "sensor": "unit"}), 
            "sensor.test|unit"
        )
        
        # List of mixed types
        input_list = [
            "sensor.1",
            {"dynamic_entity": "dyn"},
            {"entity": "sensor.2"}
        ]
        expected = ["sensor.1", "#{dyn}", "sensor.2"]
        self.assertEqual(format_entity_value(input_list), expected)

    def test_format_entity_cpp(self):
        self.assertEqual(format_entity_cpp("val"), '{"val"}')
        self.assertEqual(format_entity_cpp(["v1", "v2"]), '{"v1", "v2"}')

    def test_build_fast_refresh_lambda(self):
        # Single function (leaf)
        config = "cond1"
        self.assertEqual(
            build_fast_refresh_lambda(config), 
            "[](std::vector<std::string> entities) { return id(cond1).execute(entities); }"
        )
        
        # NOT operator
        config = {"operator": "NOT", "conditions": "cond1"}
        self.assertEqual(
            build_fast_refresh_lambda(config), 
            "[](std::vector<std::string> entities) { return !id(cond1).execute(entities); }"
        )
        
        # AND operator
        config = {"operator": "AND", "conditions": ["cond1", "cond2"]}
        self.assertEqual(
            build_fast_refresh_lambda(config), 
            "[](std::vector<std::string> entities) { return id(cond1).execute(entities) && id(cond2).execute(entities); }"
        )

    def test_get_tile_modifiers(self):
        # Empty config
        self.assertEqual(get_tile_modifiers({}), [])
        
        # omit_frame
        self.assertEqual(get_tile_modifiers({"omit_frame": True}), ["omitFrame()"])
        
        # activation_var
        config = {
            "activation_var": {
                "dynamic_entity": "screen_state",
                "value": "on"
            }
        }
        self.assertEqual(
            get_tile_modifiers(config), 
            ['setActivationVar("screen_state", { "on" })']
        )
        
        # activation_var with multiple values
        config = {
            "activation_var": {
                "dynamic_entity": "mode",
                "value": "a, b"
            }
        }
        self.assertEqual(
            get_tile_modifiers(config), 
            ['setActivationVar("mode", {"a", "b"})']
        )

    def test_flags_to_cpp(self):
        self.assertEqual(flags_to_cpp([]), "{}")
        self.assertEqual(flags_to_cpp(["BASE"]), "{BASE}")
        self.assertEqual(flags_to_cpp(["BASE", "TEMPORARY"]), "{BASE, TEMPORARY}")

if __name__ == '__main__':
    unittest.main()
