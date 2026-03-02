"""Tests for data_collection.py — YAML loading and config introspection helpers."""
import os
import tempfile
import textwrap
import unittest

from tile_ui.data_collection import (
    load_tiles_yaml,
    collect_available_scripts,
    collect_available_globals,
    collect_referenced_scripts,
    collect_referenced_globals,
    collect_dynamic_entities,
)


# ---------------------------------------------------------------------------
# load_tiles_yaml
# ---------------------------------------------------------------------------

class TestLoadTilesYaml(unittest.TestCase):

    def test_loads_valid_yaml(self):
        content = textwrap.dedent("""\
            - id: main
              flags: [BASE]
              tiles: []
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = load_tiles_yaml(path)
            self.assertIsInstance(result, list)
            self.assertEqual(result[0]['id'], 'main')
        finally:
            os.unlink(path)

    def test_raises_on_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_tiles_yaml('/nonexistent/path/tiles.yaml')

    def test_handles_utf8_bom(self):
        content = '\ufeff- id: bom_screen\n  tiles: []\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml',
                                         encoding='utf-8-sig', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = load_tiles_yaml(path)
            self.assertEqual(result[0]['id'], 'bom_screen')
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# collect_available_scripts
# ---------------------------------------------------------------------------

class TestCollectAvailableScripts(unittest.TestCase):

    def _config(self, *scripts):
        return {'script': list(scripts)}

    def test_empty_config(self):
        self.assertEqual(collect_available_scripts({}), {})

    def test_single_script(self):
        cfg = self._config({'id': 'draw_icon', 'parameters': {'x_start': 'int', 'x_end': 'int'}})
        result = collect_available_scripts(cfg)
        self.assertIn('draw_icon', result)
        self.assertEqual(result['draw_icon']['parameters']['x_start'], 'int')

    def test_multiple_scripts(self):
        cfg = self._config(
            {'id': 'script_a', 'parameters': {}},
            {'id': 'script_b', 'parameters': {'entities': 'string[]'}},
        )
        result = collect_available_scripts(cfg)
        self.assertIn('script_a', result)
        self.assertIn('script_b', result)

    def test_script_without_parameters(self):
        cfg = self._config({'id': 'no_params'})
        result = collect_available_scripts(cfg)
        self.assertEqual(result['no_params']['parameters'], {})

    def test_scripts_from_packages(self):
        cfg = {
            'packages': {
                'base': {'script': [{'id': 'pkg_script', 'parameters': {'x_start': 'int'}}]}
            }
        }
        result = collect_available_scripts(cfg)
        self.assertIn('pkg_script', result)

    def test_scripts_from_both_sections(self):
        cfg = {
            'script': [{'id': 'direct', 'parameters': {}}],
            'packages': {
                'pkg': {'script': [{'id': 'from_pkg', 'parameters': {}}]}
            }
        }
        result = collect_available_scripts(cfg)
        self.assertIn('direct', result)
        self.assertIn('from_pkg', result)


# ---------------------------------------------------------------------------
# collect_available_globals
# ---------------------------------------------------------------------------

class TestCollectAvailableGlobals(unittest.TestCase):

    def test_empty_config(self):
        self.assertEqual(collect_available_globals({}), set())

    def test_boolean_global(self):
        cfg = {'globals': [{'id': 'my_flag', 'type': 'bool'}]}
        result = collect_available_globals(cfg)
        self.assertIn('my_flag', result)

    def test_non_boolean_global_excluded(self):
        cfg = {'globals': [
            {'id': 'flag', 'type': 'bool'},
            {'id': 'counter', 'type': 'int'},
        ]}
        result = collect_available_globals(cfg)
        self.assertIn('flag', result)
        self.assertNotIn('counter', result)

    def test_globals_from_packages(self):
        cfg = {
            'packages': {
                'p': {'globals': [{'id': 'pkg_flag', 'type': 'bool'}]}
            }
        }
        result = collect_available_globals(cfg)
        self.assertIn('pkg_flag', result)


# ---------------------------------------------------------------------------
# collect_referenced_scripts
# ---------------------------------------------------------------------------

class TestCollectReferencedScripts(unittest.TestCase):

    def _ha_screen(self, display='draw', perform='action', location_perform=None,
                   rfr=None, entities='sensor.test'):
        tile = {
            'ha_action': {
                'x': 0, 'y': 0,
                'display': display,
                'perform': perform,
                'entities': entities,
            }
        }
        if location_perform:
            tile['ha_action']['location_perform'] = location_perform
        if rfr:
            tile['ha_action']['requires_fast_refresh'] = rfr
        return [{'id': 'main', 'flags': ['BASE'], 'tiles': [tile]}]

    def test_display_script_collected(self):
        refs = collect_referenced_scripts(self._ha_screen(display='draw_icon'))
        self.assertIn('draw_icon', refs)
        self.assertEqual(refs['draw_icon'][0]['type'], 'display')

    def test_perform_script_collected(self):
        refs = collect_referenced_scripts(self._ha_screen(perform='do_action'))
        self.assertIn('do_action', refs)
        self.assertEqual(refs['do_action'][0]['type'], 'action')

    def test_location_perform_collected(self):
        refs = collect_referenced_scripts(
            self._ha_screen(location_perform='loc_action'))
        self.assertIn('loc_action', refs)
        self.assertEqual(refs['loc_action'][0]['type'], 'location_action')

    def test_requires_fast_refresh_collected(self):
        refs = collect_referenced_scripts(
            self._ha_screen(rfr='cond_script'))
        self.assertIn('cond_script', refs)
        self.assertEqual(refs['cond_script'][0]['type'], 'condition')

    def test_function_tile_on_press(self):
        screens = [{'id': 'main', 'flags': ['BASE'], 'tiles': [
            {'function': {'x': 0, 'y': 0, 'display': 'btn', 'on_press': 'press_cb'}}
        ]}]
        refs = collect_referenced_scripts(screens)
        self.assertIn('btn', refs)
        self.assertIn('press_cb', refs)
        self.assertEqual(refs['press_cb'][0]['type'], 'action')

    def test_list_display_scripts(self):
        refs = collect_referenced_scripts(
            self._ha_screen(display=['draw_a', 'draw_b']))
        self.assertIn('draw_a', refs)
        self.assertIn('draw_b', refs)

    def test_display_type_for_move_page(self):
        screens = [{'id': 'main', 'flags': ['BASE'], 'tiles': [
            {'move_page': {'x': 0, 'y': 0, 'display': 'arrow', 'destination': 'p2'}}
        ]}]
        refs = collect_referenced_scripts(screens)
        self.assertEqual(refs['arrow'][0]['type'], 'display_simple')

    def test_display_type_for_toggle_entity(self):
        screens = [{'id': 'main', 'flags': ['BASE'], 'tiles': [
            {'toggle_entity': {'x': 0, 'y': 0, 'display': 'tog', 'dynamic_entity': 'v', 'entity': 'light.x'}}
        ]}]
        refs = collect_referenced_scripts(screens)
        self.assertEqual(refs['tog'][0]['type'], 'display_toggle')

    def test_display_type_for_cycle_entity(self):
        screens = [{'id': 'main', 'flags': ['BASE'], 'tiles': [
            {'cycle_entity': {'x': 0, 'y': 0, 'display': 'cyc', 'dynamic_entity': 'v',
                              'options': [{'entity': 'a', 'label': 'A'}]}}
        ]}]
        refs = collect_referenced_scripts(screens)
        self.assertEqual(refs['cyc'][0]['type'], 'display_cycle')

    def test_requires_fast_refresh_nested_expression(self):
        rfr = {'operator': 'AND', 'conditions': ['cond_a', 'cond_b']}
        refs = collect_referenced_scripts(self._ha_screen(rfr=rfr))
        self.assertIn('cond_a', refs)
        self.assertIn('cond_b', refs)


# ---------------------------------------------------------------------------
# collect_referenced_globals (returns empty set — future API)
# ---------------------------------------------------------------------------

class TestCollectReferencedGlobals(unittest.TestCase):

    def test_always_returns_empty_set(self):
        screens = [{'id': 'main', 'tiles': []}]
        self.assertEqual(collect_referenced_globals(screens), set())


# ---------------------------------------------------------------------------
# collect_dynamic_entities
# ---------------------------------------------------------------------------

class TestCollectDynamicEntities(unittest.TestCase):

    def test_static_string_does_nothing(self):
        s = set()
        collect_dynamic_entities('sensor.test', s)
        self.assertEqual(s, set())

    def test_dict_with_dynamic_entity(self):
        s = set()
        collect_dynamic_entities({'dynamic_entity': 'my_var'}, s)
        self.assertIn('my_var', s)

    def test_dict_without_dynamic_entity(self):
        s = set()
        collect_dynamic_entities({'entity': 'sensor.x'}, s)
        self.assertEqual(s, set())

    def test_list_extracts_dynamic_entities(self):
        s = set()
        collect_dynamic_entities([
            'sensor.static',
            {'dynamic_entity': 'var_a'},
            {'entity': 'sensor.y'},
            {'dynamic_entity': 'var_b'},
        ], s)
        self.assertEqual(s, {'var_a', 'var_b'})

    def test_empty_list(self):
        s = set()
        collect_dynamic_entities([], s)
        self.assertEqual(s, set())


if __name__ == '__main__':
    unittest.main()
