import unittest
from unittest.mock import MagicMock
import sys
import os

# Add parent directory to path to allow importing tile_ui modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Mock esphome.config_validation if not available, or use it if present
try:
    import esphome.config_validation as cv
    Invalid = cv.Invalid
except ImportError:
    cv = MagicMock()
    cv.Invalid = ValueError
    cv.Schema = lambda x, **kwargs: lambda y: y  # Mock schema to return input
    Invalid = ValueError
    
    # Patch sys.modules so tile_ui.schema can import it
    sys.modules["esphome"] = MagicMock()
    sys.modules["esphome.config_validation"] = cv

# Imports
from tile_ui.schema import (
    coord_schema,
    non_empty_string,
    string_list,
    display_list,
    entities_list,
    activation_var_schema,
    script_item,
    TileType,
    VALID_TILE_TYPES
)

class TestSchema(unittest.TestCase):
    
    def test_coord_schema(self):
        self.assertEqual(coord_schema(0), 0)
        self.assertEqual(coord_schema(100), 100)
        
        with self.assertRaises(Invalid):
            coord_schema(-1)
        with self.assertRaises(Invalid):
            coord_schema("1")
            
    def test_non_empty_string(self):
        self.assertEqual(non_empty_string("test"), "test")
        
        with self.assertRaises(Invalid):
            non_empty_string("")
        with self.assertRaises(Invalid):
            non_empty_string("   ")
        with self.assertRaises(Invalid):
            non_empty_string(123)
            
    def test_string_list(self):
        self.assertEqual(string_list(["a", "b"]), ["a", "b"])
        
        with self.assertRaises(Invalid):
            string_list("not a list")
        with self.assertRaises(Invalid):
            string_list(["a", ""])  # Empty string
        with self.assertRaises(Invalid):
            string_list(["a", 123])  # Non-string
            
    def test_entities_list(self):
        valid = [
            {"dynamic_entity": "val"},
            {"entity": "val"}
        ]
        self.assertEqual(entities_list(valid), valid)
        
        with self.assertRaises(Invalid):
            entities_list([])  # Empty list
        with self.assertRaises(Invalid):
            entities_list([{}])  # Empty dict
        with self.assertRaises(Invalid):
            entities_list([{"other": "val"}])  # Missing required keys

    def test_tile_types(self):
        self.assertIn("ha_action", VALID_TILE_TYPES)
        self.assertIn("move_page", VALID_TILE_TYPES)
        self.assertEqual(len(VALID_TILE_TYPES), 6)

    # --- display_list ---

    def test_display_list_string_items(self):
        self.assertEqual(display_list(["icon", "label"]), ["icon", "label"])

    def test_display_list_single_key_dict(self):
        item = {"draw_icon": {"x": 0}}
        self.assertEqual(display_list([item]), [item])

    def test_display_list_empty_string_rejected(self):
        with self.assertRaises(Invalid):
            display_list([""])

    def test_display_list_multi_key_dict_rejected(self):
        with self.assertRaises(Invalid):
            display_list([{"a": 1, "b": 2}])

    def test_display_list_non_list_rejected(self):
        with self.assertRaises(Invalid):
            display_list("not_a_list")

    def test_display_list_wrong_item_type_rejected(self):
        with self.assertRaises(Invalid):
            display_list([42])

    # --- activation_var_schema ---

    def test_activation_var_schema_valid(self):
        val = {"dynamic_entity": "screen_state", "value": "on"}
        result = activation_var_schema(val)
        self.assertEqual(result["dynamic_entity"], "screen_state")

    def test_activation_var_schema_missing_key(self):
        with self.assertRaises(Exception):  # voluptuous raises Invalid/Error
            activation_var_schema({"dynamic_entity": "x"})   # missing value

    def test_activation_var_schema_extra_key_rejected(self):
        with self.assertRaises(Exception):
            activation_var_schema(
                {"dynamic_entity": "x", "value": "on", "extra": "bad"}
            )

    # --- script_item ---

    def test_script_item_string(self):
        self.assertEqual(script_item("my_script"), "my_script")

    def test_script_item_single_key_dict(self):
        item = {"my_script": {"x": 0}}
        self.assertEqual(script_item(item), item)

    def test_script_item_empty_string_rejected(self):
        with self.assertRaises(Invalid):
            script_item("")

    def test_script_item_multi_key_dict_rejected(self):
        with self.assertRaises(Invalid):
            script_item({"a": 1, "b": 2})

    def test_script_item_wrong_type_rejected(self):
        with self.assertRaises(Invalid):
            script_item(123)

if __name__ == '__main__':
    unittest.main()
