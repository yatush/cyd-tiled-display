import unittest
from unittest.mock import MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Mock esphome.config_validation for schema import
try:
    import esphome.config_validation as cv
except ImportError:
    # Create module structure
    esphome = MagicMock()
    sys.modules["esphome"] = esphome
    cv_mock = MagicMock()
    cv_mock.Invalid = ValueError
    sys.modules["esphome.config_validation"] = cv_mock
    sys.modules["esphome.codegen"] = MagicMock()
    sys.modules["esphome.const"] = MagicMock()
    sys.modules["esphome.core"] = MagicMock()

from tile_ui.tile_generation import generate_tile_cpp

class TestTileGeneration(unittest.TestCase):
    
    def test_ha_action_tile(self):
        config = {
            "ha_action": {
                "x": 0, "y": 0,
                "display": "icon",
                "perform": "action1",
                "entities": "sensor.1"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn("new HAActionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(icon).execute(arg0, arg1, arg2, arg3, arg4); } }, { [](std::vector<std::string> arg0) { id(action1).execute(arg0); } }, {\"sensor.1\"})", cpp)
    
    def test_ha_action_tile_complex(self):
        config = {
            "ha_action": {
                "x": 1, "y": 1,
                "display": ["icon"],
                "perform": ["p1"],
                "location_perform": ["l1"],
                "entities": [{"dynamic_entity": "dyn"}]
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        expected_args = "1, 1, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(icon).execute(arg0, arg1, arg2, arg3, arg4); } }, { [](std::vector<std::string> arg0) { id(p1).execute(arg0); } }, { [](float arg0, float arg1, std::vector<std::string> arg2) { id(l1).execute(arg0, arg1, arg2); } }, {\"#{dyn}\"}"
        self.assertIn(f"new HAActionTile({expected_args})", cpp)

    def test_title_tile(self):
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "label",
                "entities": "sensor.time"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new TitleTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(label).execute(arg0, arg1, arg2, arg3, arg4); } }, {"sensor.time"})', cpp)

    def test_move_page_tile(self):
        config = {
            "move_page": {
                "x": 0, "y": 0,
                "display": "arrow",
                "destination": "screen2"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new MovePageTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(arrow).execute(arg0, arg1, arg2, arg3); } }, &id(screen2))', cpp)
        
    def test_move_page_tile_dynamic(self):
        config = {
            "move_page": {
                "x": 0, "y": 0,
                "display": "arrow",
                "destination": "screen2",
                "dynamic_entry": {
                    "dynamic_entity": "var",
                    "value": "val1, val2"
                }
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn('setDynamicEntry("var", {"val1", "val2"})', cpp)

    def test_function_tile(self):
        config = {
            "function": {
                "x": 0, "y": 0,
                "display": "btn",
                "on_press": "press_cb"
            }
        }
        cpp = generate_tile_cpp(config)
        # Updated expectation for lambda generation
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(btn).execute(arg0, arg1, arg2, arg3); } }, []() { id(press_cb).execute(); })', cpp)
        
        # With on_release
        config["function"]["on_release"] = "release_cb"
        cpp = generate_tile_cpp(config)
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3) { id(btn).execute(arg0, arg1, arg2, arg3); } }, []() { id(press_cb).execute(); }, []() { id(release_cb).execute(); })', cpp)

    def test_toggle_entity_tile(self):
        config = {
            "toggle_entity": {
                "x": 0, "y": 0,
                "display": "icon",
                "dynamic_entity": "state_var",
                "entity": "light.living_room",
                "presentation_name": "Living Room"
            }
        }
        cpp = generate_tile_cpp(config)
        expected = 'new ToggleEntityTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::string arg4, bool arg5) { id(icon).execute(arg0, arg1, arg2, arg3, arg4, arg5); } }, "state_var", {"light.living_room"}, "Living Room", false)'
        self.assertIn(expected, cpp)

    def test_cycle_entity_tile(self):
        config = {
            "cycle_entity": {
                "x": 0, "y": 0,
                "display": "icon",
                "dynamic_entity": "mode_var",
                "options": [
                    {"entity": "mode1", "label": "Mode 1"},
                    {"entity": "mode2", "label": "Mode 2"}
                ]
            }
        }
        cpp = generate_tile_cpp(config)
        options_cpp = '{ { {"mode1"}, "Mode 1" }, { {"mode2"}, "Mode 2" } }'
        self.assertIn(f'new CycleEntityTile(0, 0, {{ [](int arg0, int arg1, int arg2, int arg3, std::string arg4, std::vector<std::string> arg5) {{ id(icon).execute(arg0, arg1, arg2, arg3, arg4, arg5); }} }}, "mode_var", {options_cpp}, false)', cpp)

    def test_modifiers(self):
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "d",
                "entities": "e",
                "omit_frame": True
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn("->omitFrame()", cpp)

    def test_activation_var_modifiers(self):
        # Single value
        config = {
            "title": {
                "x": 0, "y": 0,
                "display": "d",
                "entities": "e",
                "activation_var": {
                    "dynamic_entity": "state",
                    "value": "on"
                }
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn('->setActivationVar("state", {"on"})', cpp)

        # Multiple values
        config["title"]["activation_var"]["value"] = "on, off"
        cpp = generate_tile_cpp(config)
        self.assertIn('->setActivationVar("state", {"on", "off"})', cpp)

class TestImageAnimation(unittest.TestCase):
    """Tests for animation in image tiles (direction=none, extra_images, etc.)"""

    def setUp(self):
        self.scripts = {'act': {'parameters': {'entities': 'string[]'}}}
        self.base = {'x': 0, 'y': 0, 'entities': [{'entity': 'e1'}], 'perform': ['act']}

    def _generate(self, images):
        from tile_ui.tile_generation import generate_action_tile
        config = {**self.base, 'images': images}
        return generate_action_tile(config, self.scripts, 's')

    def test_no_animation_uses_static(self):
        cpp = self._generate([{'image': 'img_a'}])
        self.assertIn('make_image_draw(&id(img_a))', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)
        self.assertNotIn('image_slot', cpp)

    def test_direction_none_single_image(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'none', 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a))', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)
        self.assertNotIn('_idx', cpp)

    def test_direction_set_calls_anim(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'left_right', 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a), ImageDirection::left_right, 3000U)', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)

    def test_direction_right_left_enum(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'right_left', 'duration': 2}}])
        self.assertIn('make_image_draw(&id(img_a), ImageDirection::right_left, 2000U)', cpp)

    def test_direction_up_down_enum(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'up_down', 'duration': 1}}])
        self.assertIn('make_image_draw(&id(img_a), ImageDirection::up_down, 1000U)', cpp)

    def test_direction_down_up_enum(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'down_up', 'duration': 1}}])
        self.assertIn('make_image_draw(&id(img_a), ImageDirection::down_up, 1000U)', cpp)

    def test_extra_images_none_direction_cycles_static(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'direction': 'none', 'duration': 6, 'extra_images': ['img_b', 'img_c']
        }}])
        # per_ms = 6000 // 3 = 2000, direction none → no direction/duration args
        self.assertIn('make_image_draw({&id(img_a), &id(img_b), &id(img_c)}, 6000U)', cpp)
        self.assertNotIn('_per_ms', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)

    def test_extra_images_directional_cycles_animated(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'direction': 'left_right', 'duration': 6, 'extra_images': ['img_b', 'img_c']
        }}])
        # per_ms = 6000 // 3 = 2000, total duration_ms = 6000
        self.assertIn('make_image_draw({&id(img_a), &id(img_b), &id(img_c)}, ImageDirection::left_right, 6000U)', cpp)
        self.assertNotIn('_per_ms', cpp)

    def test_extra_images_two_images(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'direction': 'left_right', 'duration': 4, 'extra_images': ['img_b']
        }}])
        # per_ms = 4000 // 2 = 2000, total duration_ms = 4000
        self.assertIn('make_image_draw({&id(img_a), &id(img_b)}, ImageDirection::left_right, 4000U)', cpp)
        self.assertNotIn('_per_ms', cpp)

    def test_fast_refresh_set_when_animated(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'left_right', 'duration': 3}}])
        self.assertIn('setRequiresFastRefreshFunc', cpp)
        self.assertIn('return true', cpp)

if __name__ == '__main__':
    unittest.main()
