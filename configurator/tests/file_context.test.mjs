import test from 'node:test';
import assert from 'node:assert/strict';
import {
  getConfigSnapshot,
  extractDeviceMetaFromYamlData,
  getDisplayFileName,
} from '../src/utils/fileContext.ts';

test('getConfigSnapshot ignores project_path changes and detects tile edits', () => {
  const base = {
    project_path: 'a.yaml',
    pages: [{ id: 'main', rows: 2, cols: 3, flags: ['BASE'], tiles: [] }],
    dynamic_entities: ['FAN'],
    images: {},
    screen_images: {},
  };
  const renamedPath = { ...base, project_path: 'b.yaml' };
  assert.equal(getConfigSnapshot(base), getConfigSnapshot(renamedPath));

  const edited = {
    ...base,
    pages: [
      {
        id: 'main',
        rows: 2,
        cols: 3,
        flags: ['BASE'],
        tiles: [{ id: 't1', type: 'ha_action', x: 0, y: 0 }],
      },
    ],
  };
  assert.notEqual(getConfigSnapshot(base), getConfigSnapshot(edited));
});

test('extractDeviceMetaFromYamlData parses CYD device metadata and ignores non-device objects', () => {
  const yamlData = {
    substitutions: { device_name: 'living_cyd', friendly_name: 'Living CYD' },
    packages: { device_base: 'lib/3248s035_base.yaml', lib: 'lib/lib.yaml' },
    api: { encryption: { key: 'abc123==' } },
    ota: [{ platform: 'esphome', password: 'secret' }],
    wifi: { use_address: '192.168.1.50' },
  };
  assert.deepEqual(extractDeviceMetaFromYamlData(yamlData), {
    deviceName: 'living_cyd',
    friendlyName: 'Living CYD',
    screenType: '3248s035',
    encryptionKey: 'abc123==',
    otaPassword: 'secret',
    ipAddress: '192.168.1.50',
  });

  assert.equal(extractDeviceMetaFromYamlData({ screens: [] }), null);
  assert.equal(extractDeviceMetaFromYamlData(null), null);
});

test('getDisplayFileName returns basename of nested paths', () => {
  assert.equal(getDisplayFileName('monitor_config/tiles.yaml'), 'tiles.yaml');
  assert.equal(getDisplayFileName('living_room.yaml'), 'living_room.yaml');
});
