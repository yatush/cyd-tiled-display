"""Tests for compute_image_variants and apply_image_variants in tile_generation."""
import unittest

from tile_ui.tile_generation import compute_image_variants, apply_image_variants


def _screen(sid, rows, cols, *image_ids):
    """Build a minimal screen dict with ha_action tiles that each reference one image."""
    tiles = [
        {"ha_action": {"x": i, "y": 0, "display_assets": [{"image": img_id}]}}
        for i, img_id in enumerate(image_ids)
    ]
    return {"id": sid, "rows": rows, "cols": cols, "tiles": tiles}


class TestComputeImageVariants(unittest.TestCase):

    def test_empty_screens(self):
        self.assertEqual(compute_image_variants([]), {})

    def test_no_images(self):
        screens = [{"id": "s", "rows": 2, "cols": 2, "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display": ["d"]}}
        ]}]
        self.assertEqual(compute_image_variants(screens), {})

    def test_single_image_single_layout(self):
        """Image used in only one layout → original ID kept (no suffix)."""
        screens = [_screen("s", 2, 2, "img_cat")]
        vmap = compute_image_variants(screens)
        self.assertEqual(vmap, {("img_cat", 2, 2): "img_cat"})

    def test_single_image_multiple_layouts(self):
        """Same image on 2×2 and 3×4 pages → gets suffixed IDs."""
        screens = [_screen("a", 2, 2, "img_cat"), _screen("b", 3, 4, "img_cat")]
        vmap = compute_image_variants(screens)
        self.assertEqual(vmap[("img_cat", 2, 2)], "img_cat_r2c2")
        self.assertEqual(vmap[("img_cat", 3, 4)], "img_cat_r3c4")
        self.assertEqual(len(vmap), 2)

    def test_multiple_images_same_layout(self):
        """Two different images on the same layout → both keep original IDs."""
        screens = [_screen("s", 2, 4, "img_a", "img_b")]
        vmap = compute_image_variants(screens)
        self.assertEqual(vmap[("img_a", 2, 4)], "img_a")
        self.assertEqual(vmap[("img_b", 2, 4)], "img_b")

    def test_default_rows_cols(self):
        """Screens without explicit rows/cols default to 2×2."""
        screens = [{"id": "s", "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display_assets": [{"image": "img_x"}]}}
        ]}]
        vmap = compute_image_variants(screens)
        self.assertIn(("img_x", 2, 2), vmap)

    def test_multiple_images_across_layouts(self):
        """img_a on two layouts (suffixed), img_b on one layout (unchanged)."""
        screens = [
            _screen("p1", 2, 2, "img_a", "img_b"),
            _screen("p2", 3, 3, "img_a"),
        ]
        vmap = compute_image_variants(screens)
        self.assertEqual(vmap[("img_a", 2, 2)], "img_a_r2c2")
        self.assertEqual(vmap[("img_a", 3, 3)], "img_a_r3c3")
        self.assertEqual(vmap[("img_b", 2, 2)], "img_b")  # only one layout → unchanged

    def test_ignores_entries_without_image_key(self):
        """Tiles with images list entries lacking an 'image' key are ignored."""
        screens = [{"id": "s", "rows": 2, "cols": 2, "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display_assets": [{"condition": "some.entity"}]}}
        ]}]
        self.assertEqual(compute_image_variants(screens), {})


class TestApplyImageVariants(unittest.TestCase):

    def _base_screens(self):
        return [
            {"id": "p1", "rows": 2, "cols": 2, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display_assets": [{"image": "img_a"}]}}
            ]},
            {"id": "p2", "rows": 3, "cols": 4, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display_assets": [{"image": "img_a"}]}}
            ]},
        ]

    def test_returns_deep_copy(self):
        """Original screens must not be mutated."""
        screens = self._base_screens()
        vmap = compute_image_variants(screens)
        result = apply_image_variants(screens, vmap)
        # Original unchanged
        self.assertEqual(screens[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_a")
        # Copy changed
        self.assertEqual(result[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_a_r2c2")
        self.assertEqual(result[1]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_a_r3c4")

    def test_single_layout_id_unchanged(self):
        screens = [_screen("s", 2, 2, "img_cat")]
        vmap = compute_image_variants(screens)
        result = apply_image_variants(screens, vmap)
        # No suffix because only one layout
        self.assertEqual(result[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_cat")

    def test_entries_without_image_key_preserved(self):
        """Non-image entries in the display_assets list must pass through unchanged."""
        screens = [{"id": "s", "rows": 2, "cols": 2, "tiles": [
            {"ha_action": {"x": 0, "y": 0, "display_assets": [
                {"image": "img_a"},
                {"condition": "sensor.open"},   # no 'image' key
            ]}}
        ]}]
        vmap = compute_image_variants(screens)
        result = apply_image_variants(screens, vmap)
        images = result[0]["tiles"][0]["ha_action"]["display_assets"]
        self.assertEqual(images[0]["image"], "img_a")
        self.assertNotIn("image", images[1])  # untouched

    def test_conditional_image_entries_substituted(self):
        """Conditional entries that DO have 'image' are also substituted."""
        screens = [
            {"id": "p1", "rows": 2, "cols": 2, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display_assets": [
                    {"image": "img_a", "condition": "sensor.on"},
                ]}}
            ]},
            _screen("p2", 3, 3, "img_a"),
        ]
        vmap = compute_image_variants(screens)
        result = apply_image_variants(screens, vmap)
        # Both layouts differ → variant IDs used
        self.assertEqual(result[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_a_r2c2")
        self.assertEqual(result[0]["tiles"][0]["ha_action"]["display_assets"][0]["condition"], "sensor.on")

    def test_empty_variant_map(self):
        """Empty variant map → returned screens are structurally equal to originals."""
        screens = [_screen("s", 2, 2, "img_a")]
        result = apply_image_variants(screens, {})
        # Image key not in empty map → falls back to original id
        self.assertEqual(result[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_a")

    def test_display_script_image_params_variants(self):
        """Images passed via display script Image* parameters participate in variant computation and substitution."""
        scripts = {
            "tile_lights_images": {
                "parameters": {
                    "x_start": "int",
                    "x_end": "int",
                    "y_start": "int",
                    "y_end": "int",
                    "entities": "string[]",
                    "image_off": "esphome::image::Image*",
                    "image_on": "esphome::image::Image*",
                }
            }
        }
        screens = [
            {"id": "p1", "rows": 2, "cols": 2, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display": [
                    {"tile_lights_images": {"image_off": "img_off", "image_on": "img_on"}}
                ]}}
            ]},
            {"id": "p2", "rows": 3, "cols": 4, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display": [
                    {"tile_lights_images": {"image_off": "img_off", "image_on": "none"}}
                ]}}
            ]},
        ]
        vmap = compute_image_variants(screens, available_scripts=scripts)
        self.assertEqual(vmap[("img_off", 2, 2)], "img_off_r2c2")
        self.assertEqual(vmap[("img_off", 3, 4)], "img_off_r3c4")
        self.assertEqual(vmap[("img_on", 2, 2)], "img_on")
        self.assertNotIn(("none", 3, 4), vmap)

        result = apply_image_variants(screens, vmap, available_scripts=scripts)
        self.assertEqual(
            result[0]["tiles"][0]["ha_action"]["display"][0]["tile_lights_images"],
            {"image_off": "img_off_r2c2", "image_on": "img_on"},
        )
        self.assertEqual(
            result[1]["tiles"][0]["ha_action"]["display"][0]["tile_lights_images"],
            {"image_off": "img_off_r3c4", "image_on": "none"},
        )
        # Original unmutated
        self.assertEqual(
            screens[0]["tiles"][0]["ha_action"]["display"][0]["tile_lights_images"]["image_off"],
            "img_off",
        )

    def test_spanned_tile_variants(self):
        """Spanned tiles track (x_span, y_span) so images resize to the full spanned tile dimensions."""
        scripts = {
            "tile_lights_images": {
                "parameters": {
                    "x_start": "int",
                    "x_end": "int",
                    "y_start": "int",
                    "y_end": "int",
                    "entities": "string[]",
                    "image_off": "esphome::image::Image*",
                    "image_on": "esphome::image::Image*",
                }
            }
        }
        # Single spanned tile -> unsuffixed variant ID with 5-tuple key carrying span
        screens_single = [
            {"id": "p1", "rows": 5, "cols": 4, "tiles": [
                {"ha_action": {
                    "x": 1, "y": 0, "x_span": 3, "y_span": 3,
                    "display": [{"tile_lights_images": {"image_off": "img_off", "image_on": "img_on"}}],
                }}
            ]}
        ]
        vmap = compute_image_variants(screens_single, available_scripts=scripts)
        self.assertEqual(vmap, {
            ("img_off", 5, 4, 3, 3): "img_off",
            ("img_on", 5, 4, 3, 3): "img_on",
        })

        # Same image on both 1x1 and 3x3 tiles on the same page -> distinct suffixed variants
        screens_mixed = [
            {"id": "p1", "rows": 5, "cols": 4, "tiles": [
                {"ha_action": {"x": 0, "y": 0, "display_assets": [{"image": "img_off"}]}},
                {"ha_action": {
                    "x": 1, "y": 0, "x_span": 3, "y_span": 3,
                    "display": [{"tile_lights_images": {"image_off": "img_off", "image_on": "img_on"}}],
                }},
            ]}
        ]
        vmap_mixed = compute_image_variants(screens_mixed, available_scripts=scripts)
        self.assertEqual(vmap_mixed[("img_off", 5, 4)], "img_off_r5c4")
        self.assertEqual(vmap_mixed[("img_off", 5, 4, 3, 3)], "img_off_r5c4_s3x3")
        self.assertEqual(vmap_mixed[("img_on", 5, 4, 3, 3)], "img_on")

        applied = apply_image_variants(screens_mixed, vmap_mixed, available_scripts=scripts)
        self.assertEqual(applied[0]["tiles"][0]["ha_action"]["display_assets"][0]["image"], "img_off_r5c4")
        self.assertEqual(
            applied[0]["tiles"][1]["ha_action"]["display"][0]["tile_lights_images"],
            {"image_off": "img_off_r5c4_s3x3", "image_on": "img_on"},
        )


if __name__ == "__main__":
    unittest.main()
