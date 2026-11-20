import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateYaml } from '../src/utils/yamlGenerator.ts';
import { parseYamlToConfig } from '../src/utils/yamlParser.ts';
import {
  applyDynamicEntityListChange,
  updateDynamicEntityFixedValues,
} from '../src/utils/tileUtils.ts';

const samplePages = [
  {
    id: 'main',
    rows: 2,
    cols: 3,
    flags: ['BASE'],
    tiles: [
      {
        id: 't1',
        type: 'ha_action',
        x: 0,
        y: 0,
        display: ['tile_lights'],
        perform: ['action_lights'],
        entities: [{ dynamic_entity: 'LIGHT' }],
      },
      {
        id: 't2',
        type: 'blind_position',
        x: 1,
        y: 0,
        entities: [{ dynamic_entity: 'BLINDS' }],
      },
    ],
  },
];

test('fixed dynamic_entities serialize at top of YAML and survive round-trip', () => {
  const config = {
    pages: samplePages,
    dynamic_entities: ['LIGHT', 'BLINDS', 'ACTIVE_FAN'],
    dynamic_entity_values: {
      LIGHT: ['light.bedroom_main'],
      BLINDS: ['cover.bedroom_left', 'cover.bedroom_right'],
    },
  };

  const yamlText = generateYaml(config);
  assert.ok(
    yamlText.startsWith('dynamic_entities:\n'),
    `Expected dynamic_entities at top of YAML, got:\n${yamlText}`
  );
  assert.match(yamlText, /- LIGHT: light\.bedroom_main/);
  assert.match(yamlText, /- BLINDS:\n\s+- cover\.bedroom_left\n\s+- cover\.bedroom_right/);
  assert.match(yamlText, /- ACTIVE_FAN/);

  // Device-save mode (includeInternalKeys = false) also emits dynamic_entities
  const deviceYaml = generateYaml(config, false, false);
  assert.ok(deviceYaml.startsWith('dynamic_entities:\n'));
  assert.match(deviceYaml, /- LIGHT: light\.bedroom_main/);

  const parsed = parseYamlToConfig(yamlText);
  assert.deepEqual(parsed.dynamic_entities, ['LIGHT', 'BLINDS', 'ACTIVE_FAN']);
  assert.deepEqual(parsed.dynamic_entity_values, {
    LIGHT: ['light.bedroom_main'],
    BLINDS: ['cover.bedroom_left', 'cover.bedroom_right'],
  });
});

test('empty fixed dynamic_entity emits empty array so backend validation catches it', () => {
  const config = {
    pages: samplePages,
    dynamic_entities: ['LIGHT'],
    dynamic_entity_values: {
      LIGHT: [''],
    },
  };
  const yamlText = generateYaml(config);
  assert.match(yamlText, /- LIGHT: \[\]/);
});

test('applyDynamicEntityListChange and updateDynamicEntityFixedValues keep fixed map in sync', () => {
  let config = {
    pages: samplePages,
    dynamic_entities: ['LIGHT', 'BLINDS'],
    dynamic_entity_values: {
      LIGHT: ['light.bedroom'],
    },
  };

  // Rename LIGHT -> ROOM_LIGHT
  config = applyDynamicEntityListChange(config, ['ROOM_LIGHT', 'BLINDS']);
  assert.deepEqual(config.dynamic_entity_values, { ROOM_LIGHT: ['light.bedroom'] });
  assert.equal(config.pages[0].tiles[0].entities[0].dynamic_entity, 'ROOM_LIGHT');

  // Bind BLINDS to fixed entities
  config = updateDynamicEntityFixedValues(config, 'BLINDS', ['cover.b1', 'cover.b2']);
  assert.deepEqual(config.dynamic_entity_values, {
    ROOM_LIGHT: ['light.bedroom'],
    BLINDS: ['cover.b1', 'cover.b2'],
  });

  // Switch ROOM_LIGHT back to runtime
  config = updateDynamicEntityFixedValues(config, 'ROOM_LIGHT', null);
  assert.deepEqual(config.dynamic_entity_values, {
    BLINDS: ['cover.b1', 'cover.b2'],
  });

  // Remove BLINDS from dynamic_entities -> dynamic_entity_values cleaned up completely
  config = applyDynamicEntityListChange(config, ['ROOM_LIGHT']);
  assert.equal(config.dynamic_entity_values, undefined);
});

test('fixed dynamic_entities with optional labels and cycle_entity options round-trip and rename cleanly', () => {
  let config = {
    pages: [
      {
        id: 'main',
        rows: 2,
        cols: 3,
        flags: ['BASE'],
        tiles: [
          {
            id: 't1',
            type: 'cycle_entity',
            x: 0,
            y: 0,
            display: ['tile_cover_name'],
            dynamic_entity: 'ACTIVE_COVER',
            options: [
              { entity: '*', label: 'ALL' },
              { dynamic_entity: 'BLINDS' },
            ],
          },
        ],
      },
    ],
    dynamic_entities: ['ACTIVE_COVER', 'BLINDS'],
    dynamic_entity_values: {
      BLINDS: [
        { entity: 'cover.bedroom_left', label: 'PR1' },
        'cover.bedroom_right',
      ],
    },
  };

  const yamlText = generateYaml(config);
  assert.match(yamlText, /- entity: cover\.bedroom_left\n\s+label: PR1/);
  assert.match(yamlText, /- cover\.bedroom_right/);
  assert.match(yamlText, /- dynamic_entity: BLINDS/);

  const parsed = parseYamlToConfig(yamlText);
  assert.deepEqual(parsed.dynamic_entity_values, {
    BLINDS: [
      { entity: 'cover.bedroom_left', label: 'PR1' },
      'cover.bedroom_right',
    ],
  });
  assert.deepEqual(parsed.pages[0].tiles[0].options, [
    { entity: '*', label: 'ALL' },
    { dynamic_entity: 'BLINDS' },
  ]);

  // Rename BLINDS -> ROOM_BLINDS updates both dynamic_entity_values and cycle_entity option
  config = applyDynamicEntityListChange(config, ['ACTIVE_COVER', 'ROOM_BLINDS']);
  assert.equal(config.pages[0].tiles[0].options[1].dynamic_entity, 'ROOM_BLINDS');
  assert.deepEqual(config.dynamic_entity_values.ROOM_BLINDS, [
    { entity: 'cover.bedroom_left', label: 'PR1' },
    'cover.bedroom_right',
  ]);
});
