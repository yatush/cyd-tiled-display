import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from 'js-yaml';

import {
  findCandidateForEntity,
  findConfiguredBleFan,
  toggleBleFanForEntity,
  buildTuyaBleFanYamlSections,
  extractBleFansFromDeviceYaml,
  configHasBleProxy,
  getOtherBleFanHosts,
} from '../src/utils/bleFanUtils.ts';
import { getConfigSnapshot } from '../src/utils/fileContext.ts';

const OFFICE_CANDIDATE = {
  name: 'Office Fan',
  device_id: 'bf_office_123',
  local_key: 'secret_office_key',
  product_id: 'vfqiwthdnlkynebk',
  fan_entity_id: 'fan.office_fan',
  light_entity_id: 'light.office_fan_light',
  supported: true,
};

const TV_CANDIDATE = {
  name: 'TV Room Fan',
  device_id: 'bf_tv_456',
  local_key: 'secret_tv_key',
  product_id: 'hceemlamlwxpufpa',
  fan_entity_id: 'fan.tv_room_fan',
  light_entity_id: 'light.tv_room_fan_light',
  supported: true,
};

test('candidate & configured lookup matches both fan and companion light entities', () => {
  assert.equal(findCandidateForEntity('fan.office_fan', [OFFICE_CANDIDATE])?.device_id, 'bf_office_123');
  assert.equal(findCandidateForEntity('light.office_fan_light', [OFFICE_CANDIDATE])?.device_id, 'bf_office_123');
  assert.equal(findCandidateForEntity('fan.office_fan|percentage', [OFFICE_CANDIDATE])?.device_id, 'bf_office_123');

  // Checking BLE from the companion light entity enables both fan and light
  const enabled = toggleBleFanForEntity([], 'light.office_fan_light', true, OFFICE_CANDIDATE);
  assert.equal(enabled.length, 1);
  assert.equal(findConfiguredBleFan('fan.office_fan', enabled)?.device_id, 'bf_office_123');
  assert.equal(findConfiguredBleFan('light.office_fan_light', enabled)?.device_id, 'bf_office_123');

  // Unchecking from the fan entity removes the BLE entry cleanly
  const disabled = toggleBleFanForEntity(enabled, 'fan.office_fan', false, OFFICE_CANDIDATE);
  assert.equal(disabled.length, 0);
});

test('YAML generation emits persistent mode for 1 fan, on-demand for multiple, and bumps max_connections with BLE proxy', () => {
  const empty = buildTuyaBleFanYamlSections([], false);
  assert.equal(empty.packageLine, '');
  assert.equal(empty.componentSection, '');

  const single = toggleBleFanForEntity([], 'fan.office_fan', true, OFFICE_CANDIDATE);
  const singleSections = buildTuyaBleFanYamlSections(single, false);
  assert.match(singleSections.packageLine, /tuya_ble_fan: !include lib\/tuya_ble_fan\.yaml/);
  assert.deepEqual(singleSections.extraSubstitutions, {});
  const parsedSingle = load(singleSections.componentSection);
  assert.equal(parsedSingle.tuya_ble_fan.idle_disconnect_s, 0);
  assert.equal(parsedSingle.tuya_ble_fan.fans.length, 1);
  assert.equal(parsedSingle.tuya_ble_fan.fans[0].light_entity_id, 'light.office_fan_light');
  assert.equal(parsedSingle.tuya_ble_fan.fans[0].expose_to_ha, true);

  // Round-trip extraction from device YAML
  const extracted = extractBleFansFromDeviceYaml(parsedSingle);
  assert.equal(extracted.length, 1);
  assert.equal(extracted[0].device_id, 'bf_office_123');
  assert.equal(extracted[0].light_entity_id, 'light.office_fan_light');

  // Multiple fans + BLE Proxy enabled
  const multi = toggleBleFanForEntity(single, 'fan.tv_room_fan', true, TV_CANDIDATE);
  const multiWithProxy = buildTuyaBleFanYamlSections(multi, true);
  assert.deepEqual(multiWithProxy.extraSubstitutions, { ble_max_connections: '2' });
  const parsedMulti = load(multiWithProxy.componentSection);
  assert.equal(parsedMulti.tuya_ble_fan.idle_disconnect_s, 30);
  assert.equal(parsedMulti.tuya_ble_fan.fans.length, 2);
});

test('configHasBleProxy and getConfigSnapshot track BLE proxy and ble_fans', () => {
  const baseConfig = {
    pages: [{ id: 'p1', rows: 2, cols: 3, tiles: [] }],
  };
  assert.equal(configHasBleProxy(baseConfig), false);

  const withProxy = {
    pages: [{ id: 'p1', rows: 2, cols: 3, tiles: [{ id: 't1', type: 'function', x: 0, y: 0, display: ['tile_ble_proxy'] }] }],
  };
  assert.equal(configHasBleProxy(withProxy), true);

  const withBleFan = {
    ...baseConfig,
    ble_fans: toggleBleFanForEntity([], 'fan.office_fan', true, OFFICE_CANDIDATE),
  };
  assert.notEqual(getConfigSnapshot(baseConfig), getConfigSnapshot(withBleFan));
});

test('headless BLE fan (no tile, no fan_entity_id) serializes and round-trips cleanly', () => {
  const headless = [{
    name: 'Pergula Fan',
    device_id: 'bf_pergula_999',
    local_key: 'secret_pergula_key',
    product_id: 'vfqiwthdnlkynebk',
    fan_entity_id: '',
    light_entity_id: '',
    expose_to_ha: true,
  }];
  const sections = buildTuyaBleFanYamlSections(headless, false);
  assert.match(sections.packageLine, /tuya_ble_fan: !include lib\/tuya_ble_fan\.yaml/);
  const parsed = load(sections.componentSection);
  assert.equal(parsed.tuya_ble_fan.fans.length, 1);
  assert.equal(parsed.tuya_ble_fan.fans[0].name, 'Pergula Fan');
  assert.equal(parsed.tuya_ble_fan.fans[0].fan_entity_id, undefined);
  assert.equal(parsed.tuya_ble_fan.fans[0].expose_to_ha, true);

  const extracted = extractBleFansFromDeviceYaml(parsed);
  assert.equal(extracted.length, 1);
  assert.equal(extracted[0].device_id, 'bf_pergula_999');
  assert.equal(extracted[0].fan_entity_id, '');
});

test('getOtherBleFanHosts excludes current device and flags other CYD hosts', () => {
  const hosts = { bf_office_123: ['office-cyd.yaml', 'cyd-sahar.yaml'] };
  assert.deepEqual(getOtherBleFanHosts('bf_office_123', hosts, '/config/esphome/office-cyd.yaml'), ['cyd-sahar.yaml']);
  assert.deepEqual(getOtherBleFanHosts('bf_office_123', hosts, 'living-cyd.yaml'), ['office-cyd.yaml', 'cyd-sahar.yaml']);
  assert.deepEqual(getOtherBleFanHosts('bf_office_123', { bf_office_123: ['office-cyd.yaml'] }, 'office-cyd.yaml'), []);
});
