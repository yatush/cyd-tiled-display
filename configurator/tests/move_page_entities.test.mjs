import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateYaml } from '../src/utils/yamlGenerator.ts';
import { parseYamlToConfig } from '../src/utils/yamlParser.ts';

test('move page display entities survive YAML round trip', () => {
  const entities = [{ entity: 'climate.living' }, { dynamic_entity: 'AC' }];
  const config = {
    dynamic_entities: ['AC'],
    pages: [{
      id: 'main', rows: 1, cols: 1, flags: ['BASE'],
      tiles: [{ id: 'tile', type: 'move_page', x: 0, y: 0,
        destination: 'main', display: ['tile_ac'], entities }],
    }],
  };
  const restored = parseYamlToConfig(generateYaml(config));
  assert.deepEqual(restored.pages[0].tiles[0].entities, entities);
});
