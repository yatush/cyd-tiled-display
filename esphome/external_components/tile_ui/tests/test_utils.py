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
    build_expression,
    format_entity_cpp,
    get_tile_modifiers,
    flags_to_cpp,
    format_single_function,
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
            "[](std::vector<std::string> entities) -> bool { return (id(cond1).execute(entities), id(script_output)); }"
        )
        
        # NOT operator
        config = {"operator": "NOT", "conditions": "cond1"}
        self.assertEqual(
            build_fast_refresh_lambda(config), 
            "[](std::vector<std::string> entities) -> bool { return !(id(cond1).execute(entities), id(script_output)); }"
        )
        
        # AND operator
        config = {"operator": "AND", "conditions": ["cond1", "cond2"]}
        self.assertEqual(
            build_fast_refresh_lambda(config), 
            "[](std::vector<std::string> entities) -> bool { return (id(cond1).execute(entities), id(script_output)) && (id(cond2).execute(entities), id(script_output)); }"
        )

    def test_get_tile_modifiers(self):
        # Empty config
        self.assertEqual(get_tile_modifiers({}), [])
        
        # omit_frame
        self.assertEqual(get_tile_modifiers({"omit_frame": True}), ["omitFrame()"])
        
        # fill_color: plain string (backward compat)
        self.assertEqual(
            get_tile_modifiers({"fill_color": "blue_gray"}),
            ["addFillColor(id(blue_gray))"]
        )

        # fill_color: single-entry list, no condition
        self.assertEqual(
            get_tile_modifiers({"fill_color": [{"color": "blue_gray"}]}),
            ["addFillColor(id(blue_gray))"]
        )

        # fill_color: multi-entry list with condition
        result = get_tile_modifiers({
            "fill_color": [
                {"color": "blue_gray"},
                {"color": "red", "condition": "is_on"},
            ]
        })
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "addFillColor(id(blue_gray))")
        self.assertIn("addFillColor(id(red),", result[1])
        self.assertIn("is_on", result[1])

        # activation_var
        config = {
            "activation_var": {
                "dynamic_entity": "screen_state",
                "value": "on"
            }
        }
        self.assertEqual(
            get_tile_modifiers(config), 
            ['setActivationVar("screen_state", {"on"})']
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

    def test_flags_to_cpp_empty(self):
        self.assertEqual(flags_to_cpp([]), "{}")
        self.assertEqual(flags_to_cpp(None), "{}")

    def test_flags_to_cpp_values(self):
        self.assertEqual(flags_to_cpp(["BASE"]), "{BASE}")
        self.assertEqual(flags_to_cpp(["BASE", "DETAIL"]), "{BASE, DETAIL}")


class TestBuildExpression(unittest.TestCase):

    def _leaf(self, name):
        return f"(id({name}).execute(entities), id(script_output))"

    def test_string_leaf(self):
        self.assertEqual(build_expression("cond"), self._leaf("cond"))

    def test_none_returns_none(self):
        self.assertIsNone(build_expression(None))
        self.assertIsNone(build_expression(""))

    def test_and_two_conditions(self):
        result = build_expression({"operator": "AND", "conditions": ["a", "b"]})
        self.assertEqual(result, f"{self._leaf('a')} && {self._leaf('b')}")

    def test_or_two_conditions(self):
        result = build_expression({"operator": "OR", "conditions": ["a", "b"]})
        self.assertEqual(result, f"{self._leaf('a')} || {self._leaf('b')}")

    def test_not_single_string(self):
        result = build_expression({"operator": "NOT", "conditions": "cond"})
        self.assertEqual(result, f"!{self._leaf('cond')}")

    def test_not_single_list(self):
        result = build_expression({"operator": "NOT", "conditions": ["cond"]})
        self.assertEqual(result, f"!({self._leaf('cond')})")

    def test_not_multiple_conditions_raises(self):
        with self.assertRaises(ValueError, msg="NOT with multiple conditions should raise"):
            build_expression({"operator": "NOT", "conditions": ["a", "b"]})

    def test_nested_and_or(self):
        # (a AND b) OR c
        inner = {"operator": "AND", "conditions": ["a", "b"]}
        result = build_expression({"operator": "OR", "conditions": [inner, "c"]})
        inner_expr = f"{self._leaf('a')} && {self._leaf('b')}"
        # inner expr contains &&, so gets wrapped in () by precedence logic
        self.assertIn(inner_expr, result)
        self.assertIn(" || ", result)

    def test_single_condition_list_no_op_appended(self):
        # AND with one element just returns that element without operator
        result = build_expression({"operator": "AND", "conditions": ["only"]})
        self.assertEqual(result, self._leaf("only"))

    def test_empty_conditions_list_returns_none(self):
        self.assertIsNone(build_expression({"operator": "AND", "conditions": []}))

    def test_default_operator_is_and(self):
        result = build_expression({"conditions": ["x", "y"]})
        self.assertIn(" && ", result)


class TestFormatSingleFunction(unittest.TestCase):

    def test_none_returns_nullptr(self):
        self.assertEqual(format_single_function(None), "nullptr")
        self.assertEqual(format_single_function(""), "nullptr")

    def test_simple_no_params(self):
        result = format_single_function("my_script")
        self.assertIn("id(my_script).execute()", result)

    def test_with_expected_params(self):
        result = format_single_function(
            "draw_icon",
            available_scripts={"draw_icon": {"parameters": {"x_start": "int"}}},
            expected_params=[("x_start", "int")],
        )
        self.assertIn("id(draw_icon).execute(", result)
        self.assertIn("arg0", result)

    def test_with_static_params(self):
        # Script called via dict with static value
        scripts = {"draw_label": {"parameters": {"label": "string"}}}
        result = format_single_function(
            "draw_label",
            available_scripts=scripts,
            expected_params=[],
        )
        # label not in expected_params — gets default value
        self.assertIn("id(draw_label).execute(", result)


if __name__ == '__main__':
    unittest.main()
