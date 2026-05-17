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

        # Fail: TEMPORARY and BASE flags together
        invalid_flags = self.valid_screen.copy()
        invalid_flags["flags"] = ["BASE", "TEMPORARY"]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([invalid_flags])
        self.assertIn("TEMPORARY page cannot be a BASE page", str(cm.exception))

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

    def test_empty_icon_entry_rejected(self):
        """An icon entry with an empty string must be rejected by validation."""
        config = [{
            "id": "main",
            "flags": ["BASE"],
            "tiles": [{
                "ha_action": {
                    "x": 0, "y": 0,
                    "display_assets": [{"icon": ""}],
                }
            }]
        }]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(config)
        self.assertIn("non-empty", str(cm.exception))

    def test_empty_step_icon_rejected(self):
        """A step with an empty icon override must be rejected by validation."""
        config = [{
            "id": "main",
            "flags": ["BASE"],
            "tiles": [{
                "ha_action": {
                    "x": 0, "y": 0,
                    "display_assets": [{
                        "icon": "\\Ue000",
                        "animation": {"steps": [
                            {"from": [0.0, 0.5], "to": [1.0, 0.5], "duration": 2},
                            {"from": [0.5, 0.0], "to": [0.5, 1.0], "duration": 2, "icon": ""},
                        ]},
                    }],
                }
            }]
        }]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(config)
        self.assertIn("non-empty", str(cm.exception))


class TestValidationScreenStructure(unittest.TestCase):
    """Tests for screen-level structural validation."""

    def _base(self, tiles=None):
        return {
            "id": "main",
            "flags": ["BASE"],
            "tiles": tiles or [{"ha_action": {
                "x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["sensor.t"]
            }}],
        }

    def test_screen_missing_id_raises(self):
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([{"flags": ["BASE"], "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"]}}
            ]}])
        self.assertIn("no 'id' field", str(cm.exception))

    def test_invalid_flag_raises(self):
        screen = self._base()
        screen["flags"] = ["BASE", "INVALID_FLAG"]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("Invalid flag", str(cm.exception))
        self.assertIn("INVALID_FLAG", str(cm.exception))

    def test_unknown_tile_type_raises(self):
        screen = self._base(tiles=[{"not_a_real_tile": {"x": 0, "y": 0, "display": ["d"]}}])
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("Unknown tile type", str(cm.exception))

    def test_negative_x_coordinate_raises(self):
        screen = self._base(tiles=[{"ha_action": {
            "x": -1, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"]
        }}])
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("non-negative integer", str(cm.exception))

    def test_negative_y_coordinate_raises(self):
        screen = self._base(tiles=[{"ha_action": {
            "x": 0, "y": -1, "display": ["d"], "perform": ["p"], "entities": ["e"]
        }}])
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("non-negative integer", str(cm.exception))

    def test_tile_exceeds_cols_raises(self):
        screen = self._base(tiles=[{"ha_action": {
            "x": 2, "y": 0, "x_span": 2, "display": ["d"], "perform": ["p"], "entities": ["e"]
        }}])
        screen["cols"] = 3
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("exceeds screen width", str(cm.exception))

    def test_tile_exceeds_rows_raises(self):
        screen = self._base(tiles=[{"ha_action": {
            "x": 0, "y": 1, "y_span": 2, "display": ["d"], "perform": ["p"], "entities": ["e"]
        }}])
        screen["rows"] = 2
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("exceeds screen height", str(cm.exception))

    def test_temporary_screen_reachable_via_temporary(self):
        """A non-BASE screen that links to a TEMPORARY screen is considered reachable."""
        base_screen = self._base()
        temp_screen = {
            "id": "popup",
            "flags": ["TEMPORARY"],
            "tiles": [{"title": {"x": 0, "y": 0, "display": ["d"], "entities": ["e"]}}],
        }
        detail_screen = {
            "id": "detail",
            "tiles": [
                {"title": {"x": 0, "y": 0, "display": ["d"], "entities": ["e"]}},
                {"move_page": {"x": 0, "y": 1, "display": ["b"], "destination": "popup"}},
            ],
        }
        # Should pass: detail → popup (TEMPORARY auto-returns to BASE)
        validate_tiles_config([base_screen, temp_screen, detail_screen])

    def test_move_page_to_unknown_destination_raises(self):
        # Use BASE screen so reachability check doesn't fire before destination check
        screen = {
            "id": "main",
            "flags": ["BASE"],
            "tiles": [
                {"move_page": {"x": 0, "y": 0, "display": ["b"], "destination": "nonexistent"}},
            ],
        }
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([screen])
        self.assertIn("nonexistent", str(cm.exception))


class TestValidationTilePositions(unittest.TestCase):
    """Tests for tile position overlap and stacking rules."""

    def _screen(self, tiles):
        return {"id": "main", "flags": ["BASE"], "tiles": tiles}

    def test_overlapping_tiles_without_activation_var_raises(self):
        tiles = [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"]}},
            {"title": {"x": 0, "y": 0, "display": ["d"], "entities": ["e"]}},
        ]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self._screen(tiles)])
        self.assertIn("activation_var", str(cm.exception))

    def test_overlapping_tiles_different_dynamic_entity_raises(self):
        tiles = [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"],
                           "entities": ["e"], "activation_var": {"dynamic_entity": "var_a", "value": "on"}}},
            {"title": {"x": 0, "y": 0, "display": ["d"],
                       "entities": ["e"], "activation_var": {"dynamic_entity": "var_b", "value": "off"}}},
        ]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self._screen(tiles)])
        self.assertIn("same activation variable", str(cm.exception))

    def test_overlapping_tiles_duplicate_values_raises(self):
        tiles = [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"],
                           "entities": ["e"], "activation_var": {"dynamic_entity": "var_a", "value": "on"}}},
            {"title": {"x": 0, "y": 0, "display": ["d"],
                       "entities": ["e"], "activation_var": {"dynamic_entity": "var_a", "value": "on"}}},
        ]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self._screen(tiles)])
        self.assertIn("same exact activation values", str(cm.exception))

    def test_overlapping_tiles_valid_stacking_passes(self):
        # Both tiles reference 'state' as a dynamic_entity so it's registered in valid_dynamic_entities
        tiles = [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"],
                           "entities": [{"dynamic_entity": "state"}],
                           "activation_var": {"dynamic_entity": "state", "value": "on"}}},
            {"title": {"x": 0, "y": 0, "display": ["d"],
                       "entities": [{"dynamic_entity": "state"}],
                       "activation_var": {"dynamic_entity": "state", "value": "off"}}},
        ]
        validate_tiles_config([self._screen(tiles)], declared_dynamic_entities=["state"])

    def test_invalid_x_span_raises(self):
        tiles = [{"ha_action": {"x": 0, "y": 0, "x_span": 0, "display": ["d"], "perform": ["p"], "entities": ["e"]}}]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config([self._screen(tiles)])
        self.assertIn("x_span", str(cm.exception))


class TestValidationImageReferences(unittest.TestCase):
    """Tests for available_images validation."""

    def _screen_with_image(self, img_id):
        return [{
            "id": "main", "flags": ["BASE"],
            "tiles": [{"ha_action": {
                "x": 0, "y": 0,
                "display_assets": [{"image": img_id}],
                "perform": ["p"], "entities": ["e"],
            }}],
        }]

    def test_known_image_passes(self):
        validate_tiles_config(self._screen_with_image("my_img"), available_images={"my_img"})

    def test_unknown_image_raises(self):
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen_with_image("missing_img"), available_images={"other_img"})
        self.assertIn("missing_img", str(cm.exception))
        self.assertIn("not defined in the images store", str(cm.exception))

    def test_image_none_is_skipped(self):
        validate_tiles_config(self._screen_with_image("none"), available_images=set())

    def test_available_images_none_skips_check(self):
        # Passing available_images=None means the check is skipped entirely
        validate_tiles_config(self._screen_with_image("any_image"), available_images=None)


class TestValidationDynamicEntityReferences(unittest.TestCase):
    """Tests for declared_dynamic_entities validation."""

    def _base_tile(self):
        return {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"],
                               "entities": [{"dynamic_entity": "temp_sensor"}]}}

    def test_declared_entity_passes(self):
        screens = [{"id": "main", "flags": ["BASE"], "tiles": [self._base_tile()]}]
        validate_tiles_config(screens, declared_dynamic_entities=["temp_sensor"])

    def test_undeclared_entity_raises(self):
        screens = [{"id": "main", "flags": ["BASE"], "tiles": [self._base_tile()]}]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(screens, declared_dynamic_entities=["other_entity"])
        self.assertIn("temp_sensor", str(cm.exception))
        self.assertIn("not declared in dynamic_entities", str(cm.exception))

    def test_activation_var_undeclared_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0, "display": ["d"], "perform": ["p"],
            "entities": ["sensor.t"],
            "activation_var": {"dynamic_entity": "unknown_var", "value": "on"},
        }}
        screens = [{"id": "main", "flags": ["BASE"], "tiles": [tile]}]
        # The cross-field check (activation_var var not in valid_dynamic_entities) fires first;
        # declared_dynamic_entities check fires only if that passes.  Test both code paths.
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(screens)
        self.assertIn("unknown_var", str(cm.exception))


class TestValidationGlobalReferences(unittest.TestCase):
    """Tests for available_globals parameter.

    Note: collect_referenced_globals() currently always returns an empty set
    (all conditions have been migrated to scripts), so _validate_global_references
    is effectively a no-op and the available_globals parameter has no effect.
    These tests verify that passing the parameter does not break validation.
    """

    def _base_screen(self):
        return [{"id": "main", "flags": ["BASE"], "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"]}}
        ]}]

    def test_available_globals_set_does_not_affect_validation(self):
        validate_tiles_config(self._base_screen(), available_globals={"is_day", "is_night"})

    def test_available_globals_none_does_not_affect_validation(self):
        validate_tiles_config(self._base_screen(), available_globals=None)


class TestValidationScriptReferences(unittest.TestCase):
    """Tests for available_scripts validation."""

    def _screen(self, perform):
        return [{"id": "main", "flags": ["BASE"], "tiles": [
            {"ha_action": {
                "x": 0, "y": 0, "display": ["d"],
                "perform": [perform],
                "entities": ["sensor.t"],
            }}
        ]}]

    def test_known_script_passes(self):
        # Display scripts require coordinate parameters; perform scripts require entities
        scripts = {
            "draw_it": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int", "entities": "string[]"}},
            "my_action": {"parameters": {"entities": "string[]"}},
        }
        screens = [{"id": "main", "flags": ["BASE"], "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display": ["draw_it"],
                           "perform": ["my_action"], "entities": ["sensor.t"]}}
        ]}]
        validate_tiles_config(screens, available_scripts=scripts)

    def test_unknown_script_raises(self):
        # 'draw_it' display script is known but 'missing_action' perform script is not
        scripts = {
            "draw_it": {"parameters": {"x_start": "int", "x_end": "int", "y_start": "int", "y_end": "int", "entities": "string[]"}},
            "other_action": {"parameters": {}},
        }
        screens = [{"id": "main", "flags": ["BASE"], "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display": ["draw_it"],
                           "perform": ["missing_action"], "entities": ["sensor.t"]}}
        ]}]
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(screens, available_scripts=scripts)
        self.assertIn("missing_action", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))


class TestValidateTileFields(unittest.TestCase):
    """Tests for cycle_entity and condition expression validation."""

    def _screen(self, tile):
        return [{"id": "main", "flags": ["BASE"], "tiles": [tile]}]

    def test_cycle_entity_option_missing_entity_raises(self):
        tile = {"cycle_entity": {
            "x": 0, "y": 0, "display": ["d"],
            "dynamic_entity": "mode",
            "options": [{"label": "Mode 1"}],   # entity key missing
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("entity", str(cm.exception))

    def test_cycle_entity_option_missing_label_raises(self):
        tile = {"cycle_entity": {
            "x": 0, "y": 0, "display": ["d"],
            "dynamic_entity": "mode",
            "options": [{"entity": "mode1"}],   # label key missing
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("label", str(cm.exception))

    def test_cycle_entity_option_not_dict_raises(self):
        tile = {"cycle_entity": {
            "x": 0, "y": 0, "display": ["d"],
            "dynamic_entity": "mode",
            "options": ["not_a_dict"],
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("must be a dict", str(cm.exception))

    def test_requires_fast_refresh_invalid_operator_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"],
            "requires_fast_refresh": {"operator": "XOR", "conditions": ["g1"]},
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("XOR", str(cm.exception))

    def test_requires_fast_refresh_unknown_key_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"],
            "requires_fast_refresh": {"operator": "AND", "conditions": ["g1"], "extra": True},
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("Unknown keys", str(cm.exception))

    def test_requires_fast_refresh_empty_conditions_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"],
            "requires_fast_refresh": {"operator": "AND", "conditions": []},
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("cannot be empty", str(cm.exception))

    def test_requires_fast_refresh_not_with_two_conditions_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0, "display": ["d"], "perform": ["p"], "entities": ["e"],
            "requires_fast_refresh": {"operator": "NOT", "conditions": ["g1", "g2"]},
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("NOT operator", str(cm.exception))


class TestValidateTileSchema(unittest.TestCase):
    """Tests for validate_tile_schema (cross-field checks)."""

    def _screen(self, tile):
        return [{"id": "main", "flags": ["BASE"], "tiles": [tile]}]

    def test_both_display_and_display_assets_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0,
            "display": ["d"],
            "display_assets": [{"image": "img"}],
            "perform": ["p"], "entities": ["e"],
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("Cannot have both", str(cm.exception))

    def test_neither_display_nor_display_assets_raises(self):
        tile = {"ha_action": {
            "x": 0, "y": 0,
            "perform": ["p"], "entities": ["e"],
        }}
        with self.assertRaises(ValueError) as cm:
            validate_tiles_config(self._screen(tile))
        self.assertIn("Must have either", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
