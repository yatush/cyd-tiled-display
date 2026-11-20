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


class TestFixedDynamicEntityLabelsAndCycleEntity(unittest.TestCase):
    def test_parse_fixed_entities_with_optional_labels(self):
        from tile_ui.data_collection import (
            format_entity_label,
            parse_dynamic_entities_with_labels,
        )

        raw = [
            "ACTIVE_COVER",
            {
                "ROOM_COVERS": [
                    {"entity": "cover.living_room_left", "label": "PR1"},
                    "cover.living_room_right",
                    {"entity": "cover.kitchen_main", "label": "  "},
                ]
            },
            {"SINGLE": {"entity": "light.desk_lamp", "label": "Desk"}},
        ]
        names, entries = parse_dynamic_entities_with_labels(raw)
        self.assertEqual(names, ["ACTIVE_COVER", "ROOM_COVERS", "SINGLE"])
        self.assertEqual(
            entries,
            {
                "ROOM_COVERS": [
                    ("cover.living_room_left", "PR1"),
                    ("cover.living_room_right", None),
                    ("cover.kitchen_main", None),
                ],
                "SINGLE": [("light.desk_lamp", "Desk")],
            },
        )
        # parse_dynamic_entities_config still returns plain entity IDs
        _, plain = parse_dynamic_entities_config(raw)
        self.assertEqual(
            plain,
            {
                "ROOM_COVERS": [
                    "cover.living_room_left",
                    "cover.living_room_right",
                    "cover.kitchen_main",
                ],
                "SINGLE": ["light.desk_lamp"],
            },
        )

        # Fallback label formatting
        self.assertEqual(format_entity_label("light.living_room"), "Living Room")
        self.assertEqual(format_entity_label("cover.bedroom_left|position"), "Bedroom Left")
        self.assertEqual(format_entity_label("LR"), "LR")

    def test_rejects_invalid_labeled_fixed_entries(self):
        with self.assertRaisesRegex(ValueError, "unsupported key"):
            parse_dynamic_entities_config([{"A": [{"entity": "light.a", "foo": "bar"}]}])
        with self.assertRaisesRegex(ValueError, "non-empty string 'entity'"):
            parse_dynamic_entities_config([{"A": [{"entity": "", "label": "X"}]}])
        with self.assertRaisesRegex(ValueError, "'label' must be a string"):
            parse_dynamic_entities_config([{"A": [{"entity": "light.a", "label": 123}]}])

    def test_cycle_entity_accepts_fixed_dynamic_entity_option_and_generates_cpp(self):
        screens = [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "cycle_entity": {
                            "x": 0,
                            "y": 0,
                            "display": ["tile_cover_name"],
                            "dynamic_entity": "ACTIVE_COVER",
                            "options": [
                                {"entity": "*", "label": "ALL"},
                                {"dynamic_entity": "ROOM_COVERS"},
                            ],
                        }
                    }
                ],
            }
        ]
        declared = [
            "ACTIVE_COVER",
            {
                "ROOM_COVERS": [
                    {"entity": "cover.living_left", "label": "PR1"},
                    "cover.living_right",
                ]
            },
        ]
        lambdas = generate_init_tiles_cpp(screens, dynamic_entities=declared)
        # EMSet initializes ROOM_COVERS with plain entity IDs
        self.assertIn(
            'EMSet(Pointer("ROOM_COVERS"), Pointer(std::vector<std::string>{"cover.living_left", "cover.living_right"}));',
            lambdas[0],
        )
        # CycleEntityTile expands ROOM_COVERS into individual options with custom + fallback labels
        screen_cpp = lambdas[1]
        self.assertIn(
            '{ { {"*"}, "ALL" }, { {"cover.living_left"}, "PR1" }, { {"cover.living_right"}, "Living Right" } }',
            screen_cpp,
        )

    def test_cycle_entity_rejects_non_fixed_or_mixed_dynamic_entity_option(self):
        base_screens = lambda opt: [
            {
                "id": "main",
                "flags": ["BASE"],
                "tiles": [
                    {
                        "cycle_entity": {
                            "x": 0,
                            "y": 0,
                            "display": ["d"],
                            "dynamic_entity": "ACTIVE_COVER",
                            "options": [opt],
                        }
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "is not a fixed dynamic entity"):
            validate_tiles_config(
                base_screens({"dynamic_entity": "RUNTIME_VAR"}),
                declared_dynamic_entities=["ACTIVE_COVER", "RUNTIME_VAR"],
            )
        with self.assertRaisesRegex(ValueError, "is not declared in dynamic_entities"):
            validate_tiles_config(
                base_screens({"dynamic_entity": "MISSING_VAR"}),
                declared_dynamic_entities=["ACTIVE_COVER"],
            )
        with self.assertRaisesRegex(ValueError, "cannot combine 'dynamic_entity' with 'entity' or 'label'"):
            validate_tiles_config(
                base_screens({"dynamic_entity": "ROOM_COVERS", "label": "Oops"}),
                declared_dynamic_entities=["ACTIVE_COVER", {"ROOM_COVERS": ["cover.a"]}],
            )


if __name__ == "__main__":
    unittest.main()
