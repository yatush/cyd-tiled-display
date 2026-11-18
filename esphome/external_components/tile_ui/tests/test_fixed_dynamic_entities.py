"""Tests for fixed values in dynamic_entities across parsing, validation, and C++ codegen."""
import os
import tempfile
import unittest
from unittest.mock import patch

from tile_ui import generate_init_tiles_cpp, load_tiles_config
from tile_ui.data_collection import parse_dynamic_entities_config
from tile_ui.schema import dynamic_entities_schema
from tile_ui.validation import validate_tiles_config


class TestParseDynamicEntitiesConfig(unittest.TestCase):
    def test_none_returns_none_and_empty_fixed(self):
        names, fixed = parse_dynamic_entities_config(None)
        self.assertIsNone(names)
        self.assertEqual(fixed, {})

    def test_mixed_list_formats(self):
        raw = [
            "ACTIVE_FAN",
            {"LIGHT": "light.bedroom_main"},
            {"BLINDS": ["cover.bed_left", "cover.bed_right"]},
            {"name": "AC", "value": "climate.bedroom"},
            {"name": "ROOM", "entities": None},
        ]
        names, fixed = parse_dynamic_entities_config(raw)
        self.assertEqual(names, ["ACTIVE_FAN", "LIGHT", "BLINDS", "AC", "ROOM"])
        self.assertEqual(
            fixed,
            {
                "LIGHT": ["light.bedroom_main"],
                "BLINDS": ["cover.bed_left", "cover.bed_right"],
                "AC": ["climate.bedroom"],
            },
        )

    def test_mapping_shorthand(self):
        names, fixed = parse_dynamic_entities_config({
            "LIGHT": "light.kitchen",
            "BLINDS": ["cover.k1", "cover.k2"],
            "RUNTIME_VAR": None,
        })
        self.assertEqual(names, ["LIGHT", "BLINDS", "RUNTIME_VAR"])
        self.assertEqual(fixed, {"LIGHT": ["light.kitchen"], "BLINDS": ["cover.k1", "cover.k2"]})

    def test_rejects_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "Duplicate dynamic entity declaration: 'LIGHT'"):
            parse_dynamic_entities_config(["LIGHT", {"LIGHT": "light.bed"}])

    def test_rejects_empty_fixed_list_or_string(self):
        with self.assertRaisesRegex(ValueError, "cannot have an empty entity list"):
            parse_dynamic_entities_config([{"LIGHT": []}])
        with self.assertRaisesRegex(ValueError, "at least one non-empty entity ID"):
            parse_dynamic_entities_config([{"LIGHT": "   "}])

    def test_rejects_placeholder_inside_fixed_value(self):
        with self.assertRaisesRegex(ValueError, "cannot contain dynamic placeholders"):
            parse_dynamic_entities_config([{"LIGHT": "#{OTHER_VAR}"}])

    def test_schema_validator_wraps_errors(self):
        valid = ["FAN", {"LIGHT": "light.bed"}]
        self.assertEqual(dynamic_entities_schema(valid), valid)
        with self.assertRaises(Exception):
            dynamic_entities_schema([{"LIGHT": []}])


class TestFixedDynamicEntitiesValidation(unittest.TestCase):
    def test_fixed_entities_valid_in_read_only_tiles_and_activation_var(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "ha_action": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "perform": ["p"],
                            "entities": [{"dynamic_entity": "LIGHT", "sensor": "brightness"}],
                            "activation_var": {"dynamic_entity": "ROOM_MODE", "value": "bedroom"},
                        }
                    },
                    {
                        "blind_position": {
                            "x": 1,
                            "y": 0,
                            "entities": [{"dynamic_entity": "BLINDS"}],
                        }
                    },
                    {
                        "title": {
                            "x": 2,
                            "y": 0,
                            "display": ["d"],
                            "entities": [{"dynamic_entity": "LIGHT"}],
                        }
                    },
                ],
            }
        ]
        declared = [
            {"LIGHT": "light.bedroom"},
            {"BLINDS": ["cover.left", "cover.right"]},
            {"ROOM_MODE": "bedroom"},
        ]
        validate_tiles_config(screens, declared_dynamic_entities=declared)

    def test_rejects_toggle_entity_mutating_fixed_var(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "toggle_entity": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "dynamic_entity": "LIGHT",
                            "entity": "light.other",
                        }
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "cannot modify fixed dynamic entity 'LIGHT'"):
            validate_tiles_config(screens, declared_dynamic_entities=[{"LIGHT": "light.bedroom"}])

    def test_rejects_cycle_entity_mutating_fixed_var(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "cycle_entity": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "dynamic_entity": "LIGHT",
                            "options": [{"entity": "light.a", "label": "A"}],
                        }
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "cannot modify fixed dynamic entity 'LIGHT'"):
            validate_tiles_config(screens, declared_dynamic_entities=[{"LIGHT": "light.bedroom"}])

    def test_rejects_move_page_dynamic_entry_mutating_fixed_var(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "move_page": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "destination": "main",
                            "dynamic_entry": [{"dynamic_entity": "LIGHT", "value": "light.other"}],
                        }
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "cannot modify fixed dynamic entity 'LIGHT'"):
            validate_tiles_config(screens, declared_dynamic_entities=[{"LIGHT": "light.bedroom"}])

    def test_rejects_long_dynamic_entity_mutating_fixed_var(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "ha_action": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "perform": ["p"],
                            "entities": ["fan.office"],
                            "long_destination": "sub",
                            "long_dynamic_entity": "FAN",
                        }
                    }
                ],
            },
            {
                "id": "sub",
                "flags": ["TEMPORARY"],
                "tiles": [
                    {
                        "ha_action": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "perform": ["p"],
                            "entities": [{"dynamic_entity": "FAN"}],
                        }
                    }
                ],
            },
        ]
        with self.assertRaisesRegex(ValueError, "cannot modify fixed dynamic entity 'FAN'"):
            validate_tiles_config(screens, declared_dynamic_entities=[{"FAN": "fan.bedroom"}])

    def test_rejects_display_page_if_no_entity_when_only_fixed_entities_used(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "ha_action": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "perform": ["p"],
                            "entities": [{"dynamic_entity": "LIGHT"}],
                            "display_page_if_no_entity": "main",
                        }
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "display_page_if_no_entity cannot be used"):
            validate_tiles_config(screens, declared_dynamic_entities=[{"LIGHT": "light.bedroom"}])


class TestFixedDynamicEntitiesCodegen(unittest.TestCase):
    def _screens(self):
        return [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "ha_action": {
                            "x": 0,
                            "y": 0,
                            "display": ["tile_lights"],
                            "perform": ["action_lights"],
                            "entities": [{"dynamic_entity": "LIGHT"}],
                        }
                    },
                    {
                        "blind_position": {
                            "x": 1,
                            "y": 0,
                            "entities": [{"dynamic_entity": "BLINDS"}],
                        }
                    },
                ],
            }
        ]

    def test_emits_emset_for_fixed_entities_before_screens(self):
        lambdas = generate_init_tiles_cpp(
            self._screens(),
            dynamic_entities=[
                {"LIGHT": "light.bedroom"},
                {"BLINDS": ["cover.left", "cover.right"]},
                "RUNTIME_ONLY",
            ],
        )
        init_block = lambdas[0]
        self.assertIn("view_ptr.reset(new View());", init_block)
        self.assertIn(
            'EMSet(Pointer("LIGHT"), Pointer(std::vector<std::string>{"light.bedroom"}));',
            init_block,
        )
        self.assertIn(
            'EMSet(Pointer("BLINDS"), Pointer(std::vector<std::string>{"cover.left", "cover.right"}));',
            init_block,
        )
        self.assertNotIn("RUNTIME_ONLY", init_block)

    def test_no_emset_when_only_runtime_dynamic_entities(self):
        lambdas = generate_init_tiles_cpp(
            self._screens(),
            dynamic_entities=["LIGHT", "BLINDS"],
        )
        self.assertNotIn("EMSet(", lambdas[0])

    def test_load_tiles_config_forwards_dynamic_entities_from_tiles_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tiles_path = os.path.join(tmpdir, "room_tiles.yaml")
            device_path = os.path.join(tmpdir, "device.yaml")
            with open(tiles_path, "w", encoding="utf-8") as f:
                f.write(
                    "dynamic_entities:\n"
                    "  - LIGHT: light.bedroom\n"
                    "screens:\n"
                    "  - id: main\n"
                    "    flags: [BASE]\n"
                    "    tiles:\n"
                    "      - ha_action:\n"
                    "          x: 0\n"
                    "          y: 0\n"
                    "          entities:\n"
                    "            - dynamic_entity: LIGHT\n"
                    "          display: [d]\n"
                    "          perform: [p]\n"
                )
            with patch("tile_ui.CORE") as mock_core:
                mock_core.config_path = device_path
                cfg = load_tiles_config({"tiles_file": "room_tiles.yaml"})
                self.assertEqual(cfg["dynamic_entities"], [{"LIGHT": "light.bedroom"}])


if __name__ == "__main__":
    unittest.main()
