import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTileYaml } from '../src/utils/tileYaml.ts';
import { generateTileYaml, generateYaml } from '../src/utils/yamlGenerator.ts';
import { getTileDynamicEntities } from '../src/utils/yamlParser.ts';

test('pasted tile accepts common indentation and preserves nested YAML', () => {
  const text = `      - ha_action:
          x: 1
          y: 0
          entities:
            - dynamic_entity: LIGHT
            - light.kitchen
          display:
            - tile_lights:
                color: id(white)
          perform:
            - action_lights
          requires_fast_refresh:
            operator: AND
            conditions:
              - check_light
`;
  const tile = parseTileYaml(text, 'existing-id');
  assert.equal(tile.id, 'existing-id');
  assert.deepEqual(tile.entities, [{ dynamic_entity: 'LIGHT' }, 'light.kitchen']);
  assert.deepEqual(tile.display, [{ tile_lights: { color: 'white' } }]);
  assert.deepEqual(tile.requires_fast_refresh, { and: ['check_light'] });
  assert.deepEqual(getTileDynamicEntities(tile), ['LIGHT']);
  assert.deepEqual(parseTileYaml(generateTileYaml(tile), tile.id), tile);
});

test('standalone tile output matches the existing generator and handles unplaced tiles', () => {
  const tile = { id: 'one', type: 'function', x: -1, y: -1, on_press: 'action_press',
    display_assets: [{ icon: '\\U0000f05a', condition: { or: ['a', 'b'] } }] };
  const text = generateTileYaml(tile);
  const pageYaml = generateYaml({ pages: [{ id: 'main', rows: 1, cols: 1, tiles: [tile] }] });
  assert.match(pageYaml, /operator: OR/);
  assert.match(text, /operator: OR/);
  assert.deepEqual(parseTileYaml(text, tile.id), tile);
});

test('dedenting preserves multiline scalar content', () => {
  const text = `    - function:
        x: 0
        y: 0
        on_press:
          action_message:
            message: |
              first line
                second line
`;
  const tile = parseTileYaml(text, 'one');
  assert.equal(tile.on_press.action_message.message, 'first line\n  second line\n');
  assert.deepEqual(parseTileYaml(generateTileYaml(tile), 'one'), tile);
});

test('rejects invalid YAML and unsafe or unsupported tile structures', () => {
  assert.throws(() => parseTileYaml('  - function:\n      x: [\n', 'id'), /Line \d+, column \d+:/);
  assert.throws(() => parseTileYaml('- function: {x: 0, y: 0}\n- title: {x: 0, y: 0}', 'id'), /exactly one tile/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: 0, typo: value}', 'id'), /Unsupported field.*typo/);
  assert.throws(() => parseTileYaml('other: {x: 0, y: 0}', 'id'), /Unknown tile type/);
  assert.throws(() => parseTileYaml('toString: {x: 0, y: 0}', 'id'), /Unknown tile type/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: nope}', 'id'), /y must be/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: 0, fill_color: [red]}', 'id'), /fill_color/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: 0, fill_color: [{color: 1}]}', 'id'), /color/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: 0, requires_fast_refresh: {or: bad}}', 'id'), /or must be a list/);
  assert.throws(() => parseTileYaml('function: {x: 0, y: 0, display_assets: [{icon: a, animation: {steps: [null]}}]}', 'id'), /steps must be a list of mappings/);
  assert.throws(() => parseTileYaml('function: &a {x: 0, y: 0, activation_var: *a}', 'id'), /Recursive YAML aliases/);
});

test('unsupported existing fields are visible instead of silently discarded in the editor', () => {
  const text = generateTileYaml({ id: 'one', type: 'function', x: 0, y: 0, old_field: 'value' });
  assert.match(text, /old_field: value/);
  assert.throws(() => parseTileYaml(text, 'one'), /Unsupported field.*old_field/);
});
