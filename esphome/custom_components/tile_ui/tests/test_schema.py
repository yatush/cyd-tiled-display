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

# Imports
from tile_ui.schema import (
    coord_schema,
    non_empty_string,
    string_list,
    entities_list,
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

if __name__ == '__main__':
    unittest.main()
