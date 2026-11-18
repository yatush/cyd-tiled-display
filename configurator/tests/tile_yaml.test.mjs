import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTileYaml, parsePageYaml } from '../src/utils/tileYaml.ts';
import { generateTileYaml, generatePageYaml, generateYaml } from '../src/utils/yamlGenerator.ts';
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
  assert.match(pageYaml, /icon: '\\U0000f05a'/);
  assert.match(text, /icon: '\\U0000f05a'/);
  assert.doesNotMatch(pageYaml, /'"\\U0000f05a"'/);
  assert.doesNotMatch(text, /'"\\U0000f05a"'/);
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

test('long-press configuration and dynamic destination survive tile YAML', () => {
  const tile = { id: 'one', type: 'ha_action', x: 0, y: 0, entities: [{ entity: 'fan.office' }],
    display: ['tile_fan'], perform: ['action_fan_power'], long_destination: 'fan_settings',
    long_dynamic_entity: 'FAN', long_perform: ['custom_action'] };
  assert.deepEqual(parseTileYaml(generateTileYaml(tile), tile.id), tile);
  assert.deepEqual(getTileDynamicEntities(tile), ['FAN']);
});

test('page YAML round-trips id, grid, flags, time_color, background conditions, and tiles preserving tile ids', () => {
  const page = {
    id: 'living',
    rows: 4,
    cols: 3,
    flags: ['BASE', 'OMIT_TIME_WIFI'],
    time_color: 'white',
    background: [
      {
        color: 'black',
        condition: {
          and: [{ entity: 'binary_sensor.night', state: 'on' }],
        },
      },
      { color: 'navy' },
    ],
    tiles: [
      {
        id: 'existing-tile-id',
        type: 'ha_action',
        x: 0,
        y: 0,
        entities: [{ entity: 'light.sofa' }],
        display: ['tile_light'],
        perform: ['toggle'],
      },
    ],
  };

  const text = generatePageYaml(page);
  assert.match(text, /operator: AND/);
  const parsed = parsePageYaml(text, page, ['other']);
  assert.deepEqual(parsed, page);

  const withAddedTile = `${text}    - function:\n        x: 1\n        y: 0\n        on_press: fn_extra\n`;
  const parsedExpanded = parsePageYaml(withAddedTile, page, ['other']);
  assert.equal(parsedExpanded.tiles.length, 2);
  assert.equal(parsedExpanded.tiles[0].id, 'existing-tile-id');
  assert.ok(parsedExpanded.tiles[1].id && parsedExpanded.tiles[1].id !== 'existing-tile-id');
});

test('page YAML accepts indented blocks and screens wrapper', () => {
  const currentPage = { id: 'old', rows: 2, cols: 2, tiles: [{ id: 't0', type: 'function', x: 0, y: 0, on_press: 'p' }] };

  const indented = `
    id: sub
    rows: 2
    cols: 3
    tiles:
      - function:
          x: 2
          y: 1
          on_press: fn1
  `;
  const parsedIndented = parsePageYaml(indented, currentPage, ['other']);
  assert.equal(parsedIndented.id, 'sub');
  assert.equal(parsedIndented.cols, 3);
  assert.equal(parsedIndented.tiles[0].id, 't0');
  assert.equal(parsedIndented.tiles[0].x, 2);

  const wrapped = `
    screens:
      - id: wrapped_id
        rows: 3
        cols: 2
        tiles: []
  `;
  const parsedWrapped = parsePageYaml(wrapped, currentPage, ['other']);
  assert.equal(parsedWrapped.id, 'wrapped_id');
  assert.equal(parsedWrapped.rows, 3);
  assert.deepEqual(parsedWrapped.tiles, []);
});

test('page YAML rejects invalid pages, conflicts, out-of-bounds tiles, and invalid tiles', () => {
  const currentPage = { id: 'p1', rows: 2, cols: 2, tiles: [] };

  assert.throws(() => parsePageYaml(`
screens:
  - id: a
    rows: 2
    cols: 2
    tiles: []
  - id: b
    rows: 2
    cols: 2
    tiles: []
`, currentPage, []));

  assert.throws(() => parsePageYaml(`
id: p1
rows: 2
cols: 2
unknown_page_prop: true
tiles: []
`, currentPage, []));

  assert.throws(() => parsePageYaml(`
id: existing_other
rows: 2
cols: 2
tiles: []
`, currentPage, ['existing_other']));

  assert.throws(() => parsePageYaml(`
id: p1
rows: 2
cols: 2
flags:
  - BASE
  - TEMPORARY
tiles: []
`, currentPage, []));

  assert.throws(() => parsePageYaml(`
id: p1
rows: 2
cols: 2
background:
  - condition:
      eq: [a, b]
tiles: []
`, currentPage, []));

  assert.throws(() => parsePageYaml(`
id: p1
rows: 2
cols: 2
tiles:
  - function:
      x: 2
      y: 0
      on_press: p
`, currentPage, []));

  assert.throws(() => parsePageYaml(`
id: p1
rows: 2
cols: 2
tiles:
  - function:
      x: 0
      y: 0
      on_press: p
      bad_tile_prop: 123
`, currentPage, []));
});

test('unsupported existing page fields remain visible in generated YAML and fail validation', () => {
  const text = generatePageYaml({ id: 'p1', rows: 2, cols: 2, tiles: [], extra_page_field: 'keep_visible' });
  assert.match(text, /extra_page_field: keep_visible/);
  assert.throws(() => parsePageYaml(text, { id: 'p1', rows: 2, cols: 2, tiles: [] }, []));
});

test('icons emit single quotes without inner double quotes and normalize all quote styles', () => {
  const tile = {
    id: 'cover_1',
    type: 'toggle_entity',
    x: 0,
    y: 0,
    dynamic_entity: 'BLINDS',
    entity: ['cover.lr1'],
    display: [{ tile_choose_cover_sized: { size: 'small', icon: '\\U0000e286' } }],
    display_assets: [{ icon: '\\U0000ec0e', icon_color: 'white', icon_size: 'small' }],
  };

  const tileYaml = generateTileYaml(tile);
  const pageYaml = generatePageYaml({ id: 'blinds', rows: 2, cols: 2, tiles: [tile] });

  assert.match(tileYaml, /icon: '\\U0000e286'/);
  assert.match(tileYaml, /icon: '\\U0000ec0e'/);
  assert.match(pageYaml, /icon: '\\U0000e286'/);
  assert.match(pageYaml, /icon: '\\U0000ec0e'/);
  assert.doesNotMatch(tileYaml, /'"\\U/);
  assert.doesNotMatch(pageYaml, /'"\\U/);

  for (const [displayIconYaml, assetIconYaml] of [
    ["'\\U0000e286'", "'\\U0000ec0e'"],
    ['"\\U0000e286"', '"\\U0000ec0e"'],
    ['\'"\\U0000e286"\'', '\'"\\U0000ec0e"\''],
  ]) {
    const parsed = parseTileYaml(`
toggle_entity:
  x: 0
  y: 0
  dynamic_entity: BLINDS
  entity:
    - cover.lr1
  display:
    - tile_choose_cover_sized:
        size: id(small)
        icon: ${displayIconYaml}
  display_assets:
    - icon: ${assetIconYaml}
      icon_color: white
      icon_size: small
`, 'cover_1');
    assert.deepEqual(parsed, tile);
  }
});

test('move_page supports multiple dynamic_entry items in YAML round-trip and entity discovery', () => {
  const tile = {
    id: 'mv_multi',
    type: 'move_page',
    x: 0,
    y: 0,
    destination: 'room',
    display: ['arrow'],
    dynamic_entry: [
      { dynamic_entity: 'AC', value: ['climate.living'] },
      { dynamic_entity: 'FAN', value: ['fan.living', 'fan.desk'] },
    ],
  };

  const text = generateTileYaml(tile);
  assert.deepEqual(parseTileYaml(text, tile.id), tile);
  assert.deepEqual(getTileDynamicEntities(tile), ['AC', 'FAN']);
});
