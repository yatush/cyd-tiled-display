import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from tile_ui.validation import validate_tiles_config

class TestValidation(unittest.TestCase):
    
    def setUp(self):
        self.valid_screen = {
            "id": "main",
            "flags": ["BASE"],
            "tiles": [
                {"ha_action": {
                    "x": 0, "y": 0,
                    "display": ["icon"],
                    "perform": ["action"],
                    "entities": ["sensor.test"]
                }}
            ]
        }
        
    def test_validate_base_screen(self):
        # Should pass
        validate_tiles_config([self.valid_screen])
        
        # Fail: No BASE screen
        invalid_screen = self.valid_screen.copy()
        invalid_screen["flags"] = []
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([invalid_screen])
        self.assertIn("No screen with 'BASE' flag found", str(cm.exception))
        
        # Fail: Two BASE screens (same ID triggers duplicate ID check first)
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self.valid_screen, self.valid_screen])
        self.assertIn("Duplicate screen ID", str(cm.exception))

        # Fail: Two BASE screens (different IDs trigger multiple BASE check)
        screen2 = self.valid_screen.copy()
        screen2["id"] = "main2"
        # Since main2 is not reachable from main (and main is BASE), this might trigger reachability error?
        # No, main2 has BASE flag too. So both are BASE.
        # Check happens before reachability.
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self.valid_screen, screen2])
        self.assertIn("Multiple screens with 'BASE' flag found", str(cm.exception))

    def test_validate_reachability(self):
        # Screen 2 cannot reach BASE
        screen2 = {
            "id": "screen2",
            "tiles": [
                {"title": {"x": 0, "y": 0, "entities": ["t"], "display": ["t"]}}
            ]
        }
        
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self.valid_screen, screen2])
        self.assertIn("cannot navigate back to the BASE", str(cm.exception))
        
        # Fix: Add return navigation
        screen2_fixed = screen2.copy()
        screen2_fixed["tiles"].append({
            "move_page": {
                "x": 0, "y": 1,
                "display": ["back"],
                "destination": "main"
            }
        })
        validate_tiles_config([self.valid_screen, screen2_fixed])

    def test_validate_tile_fields(self):
        # Invalid ha_action (no perform/location_perform)
        invalid_action = {
            "id": "main",
            "flags": ["BASE"],
            "tiles": [
                {"ha_action": {
                    "x": 0, "y": 0,
                    "display": ["icon"],
                    "entities": ["sensor.test"]
                    # perform missing
                }}
            ]
        }
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([invalid_action])
        self.assertIn("At least one of 'perform' or 'location_perform'", str(cm.exception))
        
        # Invalid function (no on_press/on_release)
        invalid_func = {
            "id": "main",
            "flags": ["BASE"],
            "tiles": [
                {"function": {
                    "x": 0, "y": 0,
                    "display": ["icon"],
                    # on_press/release missing
                }}
            ]
        }
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([invalid_func])
        self.assertIn("at least one of 'on_press' or 'on_release'", str(cm.exception))

if __name__ == '__main__':
    unittest.main()
