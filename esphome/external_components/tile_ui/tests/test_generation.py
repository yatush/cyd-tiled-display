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
        self.assertIn('new MovePageTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(arrow).execute(arg0, arg1, arg2, arg3, arg4); } }, &id(screen2))', cpp)
        
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
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(btn).execute(arg0, arg1, arg2, arg3, arg4); } }, []() { id(press_cb).execute(); })', cpp)
        
        # With on_release
        config["function"]["on_release"] = "release_cb"
        cpp = generate_tile_cpp(config)
        self.assertIn('new FunctionTile(0, 0, { [](int arg0, int arg1, int arg2, int arg3, std::vector<std::string> arg4) { id(btn).execute(arg0, arg1, arg2, arg3, arg4); } }, []() { id(press_cb).execute(); }, []() { id(release_cb).execute(); })', cpp)

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
                "fill_color": "red"
            }
        }
        cpp = generate_tile_cpp(config)
        self.assertIn("->addFillColor(id(red))", cpp)

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
    """Tests for animation in image tiles (from/to positions, multi-step, etc.)"""

    def setUp(self):
        self.scripts = {'act': {'parameters': {'entities': 'string[]'}}}
        self.base = {'x': 0, 'y': 0, 'entities': [{'entity': 'e1'}], 'perform': ['act']}

    def _generate(self, images):
        from tile_ui.tile_generation import generate_action_tile
        config = {**self.base, 'display_assets': images}
        return generate_action_tile(config, self.scripts, 's')

    def test_no_animation_uses_static(self):
        cpp = self._generate([{'image': 'img_a'}])
        self.assertIn('make_image_draw(&id(img_a))', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)
        self.assertNotIn('image_slot', cpp)

    def test_same_position_is_static(self):
        """from == to at center means no animation — same as having no animation block."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.5, 0.5], 'to': [0.5, 0.5], 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a))', cpp)
        self.assertNotIn('0.0f', cpp)

    def test_same_position_non_center_uses_position(self):
        """from == to at a non-center position should draw at that position."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.0, 0.0], 'to': [0.0, 0.0], 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.0f, 0.0f, 0.0f, 3000U)', cpp)

    def test_same_position_bottom_right_uses_position(self):
        """from == to at bottom-right corner."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [1.0, 1.0], 'to': [1.0, 1.0], 'duration': 2}}])
        self.assertIn('make_image_draw(&id(img_a), 1.0f, 1.0f, 1.0f, 1.0f, 2000U)', cpp)

    def test_from_left_to_right_generates_left_right(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.5f, 1.0f, 0.5f, 3000U)', cpp)
        self.assertNotIn('draw_image_anim', cpp)
        self.assertNotIn('draw_image_static', cpp)

    def test_from_right_to_left_generates_right_left(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [1.0, 0.5], 'to': [0.0, 0.5], 'duration': 2}}])
        self.assertIn('make_image_draw(&id(img_a), 1.0f, 0.5f, 0.0f, 0.5f, 2000U)', cpp)

    def test_from_top_to_bottom_generates_up_down(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 1}}])
        self.assertIn('make_image_draw(&id(img_a), 0.5f, 0.0f, 0.5f, 1.0f, 1000U)', cpp)

    def test_from_bottom_to_top_generates_down_up(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.5, 1.0], 'to': [0.5, 0.0], 'duration': 1}}])
        self.assertIn('make_image_draw(&id(img_a), 0.5f, 1.0f, 0.5f, 0.0f, 1000U)', cpp)

    def test_diagonal_generates_true_diagonal(self):
        """[0,0] → [1,1]: both axes move simultaneously."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.0, 0.0], 'to': [1.0, 1.0], 'duration': 2}}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.0f, 1.0f, 1.0f, 2000U)', cpp)

    def test_diagonal_partial_generates_correct_positions(self):
        """[0,0] → [0.5,1]: x=0→0.5, y=0→1."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.0, 0.0], 'to': [0.5, 1.0], 'duration': 2}}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.0f, 0.5f, 1.0f, 2000U)', cpp)

    def test_legacy_direction_field_still_works(self):
        """Legacy 'direction' key in animation dict maps to position fracs."""
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'left_right', 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.5f, 1.0f, 0.5f, 3000U)', cpp)

    def test_legacy_direction_none_still_static(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'direction': 'none', 'duration': 3}}])
        self.assertIn('make_image_draw(&id(img_a))', cpp)
        self.assertNotIn('0.0f', cpp)

    def test_fast_refresh_set_when_animated(self):
        cpp = self._generate([{'image': 'img_a', 'animation': {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 3}}])
        self.assertIn('setRequiresFastRefreshFunc', cpp)
        self.assertIn('return true', cpp)

    # ---- multi-step animation tests ----------------------------------------

    def test_multi_step_two_steps_root_image(self):
        """Two steps, both using the root image."""
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'steps': [
                {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 3},
                {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 2},
            ]
        }}])
        # total = 5000ms; lambda required for time dispatch
        self.assertIn('[=]', cpp)
        self.assertIn('millis() % 5000U', cpp)
        self.assertIn('if (_t < 3000U)', cpp)
        # [0,0.5]→[1,0.5]
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.5f, 1.0f, 0.5f, 3000U, 5000U, 0U)', cpp)
        self.assertIn('else', cpp)
        # [0.5,0]→[0.5,1]
        self.assertIn('make_image_draw(&id(img_a), 0.5f, 0.0f, 0.5f, 1.0f, 2000U, 5000U, 3000U)', cpp)

    def test_multi_step_three_steps_dispatch(self):
        """Three steps produce correct if/else-if/else time dispatch."""
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'steps': [
                {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 2},
                {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 3},
                {'from': [1.0, 0.5], 'to': [0.0, 0.5], 'duration': 1},
            ]
        }}])
        self.assertIn('millis() % 6000U', cpp)
        self.assertIn('if (_t < 2000U)', cpp)
        self.assertIn('else if (_t < 5000U)', cpp)

    def test_single_step_in_steps_array_is_bare_expr(self):
        """A steps array with exactly one entry behaves identically to single-step."""
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'steps': [{'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 3}]
        }}])
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.5f, 1.0f, 0.5f, 3000U)', cpp)
        self.assertNotIn('[=]', cpp)
        self.assertNotIn('millis() % ', cpp)

    def test_multi_step_fast_refresh(self):
        """Multi-step animation still sets the fast refresh callback."""
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'steps': [
                {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 2},
                {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 2},
            ]
        }}])
        self.assertIn('setRequiresFastRefreshFunc', cpp)
        self.assertIn('return true', cpp)

    def test_multi_step_per_step_image_override(self):
        """Step 1+ can override the image used via the 'image' field."""
        cpp = self._generate([{'image': 'img_a', 'animation': {
            'steps': [
                {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 3},
                {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 2, 'image': 'img_b'},
            ]
        }}])
        self.assertIn('millis() % 5000U', cpp)
        self.assertIn('make_image_draw(&id(img_a), 0.0f, 0.5f, 1.0f, 0.5f, 3000U, 5000U, 0U)', cpp)
        self.assertIn('make_image_draw(&id(img_b), 0.5f, 0.0f, 0.5f, 1.0f, 2000U, 5000U, 3000U)', cpp)

    def test_icon_entry_step_image_override(self):
        """For an icon entry, a step with 'image' field uses the image, not the entry icon."""
        cpp = self._generate([{'icon': '\\Ue000', 'icon_color': 'white', 'icon_size': 'big',
                               'animation': {'steps': [
            {'from': [0.0, 0.5], 'to': [1.0, 0.5], 'duration': 2},
            {'from': [0.5, 0.0], 'to': [0.5, 1.0], 'duration': 3, 'image': 'img_b'},
            {'from': [1.0, 0.5], 'to': [0.0, 0.5], 'duration': 2},
        ]}}])
        self.assertIn('millis() % 7000U', cpp)
        self.assertIn('make_icon_draw(', cpp)
        self.assertIn('make_image_draw(&id(img_b), 0.5f, 0.0f, 0.5f, 1.0f, 3000U, 7000U, 2000U)', cpp)

if __name__ == '__main__':
    unittest.main()
