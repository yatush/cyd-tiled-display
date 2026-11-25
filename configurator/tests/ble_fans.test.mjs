import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from 'js-yaml';

import {
  deriveDefaultBleEntityIds,
  mergeBleFansIntoHaEntities,
  findCandidateForEntity,
  findConfiguredBleFan,
  toggleBleFanForEntity,
  buildTuyaBleFanYamlSections,
  extractBleFansFromDeviceYaml,
  configHasBleProxy,
  getOtherBleFanHosts,
  buildEspNowCydYamlSections,
  extractEspNowFansFromDeviceYaml,
  mergeHubFansIntoHaEntities,
  resolveEffectiveEspNowFans,
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
  assert.deepEqual(singleSections.extraSubstitutions, {
    ble_max_connections: '1',
    display_buffer_size: '20%',
  });
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
  const multiNoProxy = buildTuyaBleFanYamlSections(multi, false);
  assert.deepEqual(multiNoProxy.extraSubstitutions, {
    ble_max_connections: '2',
    display_buffer_size: '20%',
  });
  const parsedMultiNoProxy = load(multiNoProxy.componentSection);
  assert.equal(parsedMultiNoProxy.tuya_ble_fan.max_connections, 2);
  assert.equal(parsedMultiNoProxy.tuya_ble_fan.idle_disconnect_s, 0);

  const multiWithProxy = buildTuyaBleFanYamlSections(multi, true);
  assert.deepEqual(multiWithProxy.extraSubstitutions, {
    ble_max_connections: '3',
    display_buffer_size: '15%',
  });
  const parsedMulti = load(multiWithProxy.componentSection);
  assert.equal(parsedMulti.tuya_ble_fan.max_connections, 2);
  assert.equal(parsedMulti.tuya_ble_fan.idle_disconnect_s, 0);
  assert.equal(parsedMulti.tuya_ble_fan.fans.length, 2);

  // 3 fans + ble_proxy exceeds 2 fan slots -> shared slots with 30s idle disconnect
  const threeFansWithProxy = buildTuyaBleFanYamlSections(
    [...multi, { ...multi[0], name: 'Room 3', device_id: 'bf_3' }],
    true
  );
  const parsedThree = load(threeFansWithProxy.componentSection);
  assert.equal(parsedThree.tuya_ble_fan.max_connections, 2);
  assert.equal(parsedThree.tuya_ble_fan.idle_disconnect_s, 30);
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

test('deriveDefaultBleEntityIds and mergeBleFansIntoHaEntities expose [BLE] entities at top of dropdowns', () => {
  assert.deepEqual(
    deriveDefaultBleEntityIds('office', '/config/esphome/office-cyd.yaml'),
    {
      fan_entity_id: 'fan.office_fan',
      light_entity_id: 'light.office_light',
    }
  );
  assert.deepEqual(
    deriveDefaultBleEntityIds('Living Room', undefined),
    {
      fan_entity_id: 'fan.living_room_fan',
      light_entity_id: 'light.living_room_light',
    }
  );

  const merged = mergeBleFansIntoHaEntities(
    [
      { entity_id: 'light.kitchen', friendly_name: 'Kitchen' },
      { entity_id: 'fan.office_fan', friendly_name: 'Office Fan' },
    ],
    [
      {
        name: 'Office',
        device_id: 'bf_1',
        local_key: 'key_1',
        fan_entity_id: 'fan.office_fan',
        light_entity_id: 'light.office_light',
      },
    ]
  );

  assert.deepEqual(merged, [
    { entity_id: 'fan.office_fan', friendly_name: '[BLE] Office' },
    { entity_id: 'light.office_light', friendly_name: '[BLE] Office Light' },
    { entity_id: 'light.kitchen', friendly_name: 'Kitchen' },
  ]);
});

test('ESP-NOW hub fans are explicitly configured (stateless across computers) and round-trip YAML cleanly without BLE', () => {
  const hubs = [
    {
      filename: 'bedroom-hub.yaml',
      name: 'bedroom-hub',
      friendly_name: 'Bedroom Hub',
      board: 'seeed_xiao_esp32c3',
      fallback_channel: 6,
      fans: [
        {
          name: 'Bedroom Fan',
          device_id: 'bf_bed_1',
          local_key: '0123456789abcdef',
          fan_entity_id: 'fan.bedroom_fan',
          light_entity_id: 'light.bedroom_light',
        },
      ],
    },
  ];

  // Hub fans appear in entity picker when available locally
  const merged = mergeHubFansIntoHaEntities([{ entity_id: 'light.kitchen', friendly_name: 'Kitchen' }], hubs);
  assert.deepEqual(merged, [
    { entity_id: 'fan.bedroom_fan', friendly_name: '[Hub] Bedroom Fan' },
    { entity_id: 'light.bedroom_light', friendly_name: '[Hub] Bedroom Fan Light' },
    { entity_id: 'light.kitchen', friendly_name: 'Kitchen' },
  ]);

  // Without explicit espnow_fans on CYD, local hub files must NOT silently mutate CYD YAML
  const haOnlyCyd = {
    pages: [
      {
        id: 'main',
        rows: 2,
        cols: 3,
        tiles: [{ id: 't1', type: 'ha_action', x: 0, y: 0, entities: ['fan.bedroom_fan'] }],
      },
    ],
  };
  assert.equal(resolveEffectiveEspNowFans(haOnlyCyd, hubs).length, 0);

  // Explicit espnow_fans works identically even when hubs=[] (e.g., on a different computer)
  const explicitCyd = {
    ...haOnlyCyd,
    espnow_fans: [
      {
        name: 'Bedroom Fan',
        fan_entity_id: 'fan.bedroom_fan',
        light_entity_id: 'light.bedroom_light',
      },
    ],
  };
  const effective = resolveEffectiveEspNowFans(explicitCyd, []);
  assert.equal(effective.length, 1);
  assert.equal(effective[0].fan_entity_id, 'fan.bedroom_fan');
  assert.equal(effective[0].light_entity_id, 'light.bedroom_light');

  // Default network_key is deterministic ('cyd_espnow_default') for cross-machine compatibility
  const defaultSections = buildEspNowCydYamlSections(effective, undefined, 6);
  const parsedDefault = load(defaultSections.componentSection);
  assert.equal(parsedDefault.espnow_fan_bridge.network_key, 'cyd_espnow_default');

  const sections = buildEspNowCydYamlSections(effective, 'deadbeef12345678', 6);
  assert.match(sections.packageLine, /espnow_cyd: !include lib\/espnow_cyd\.yaml/);
  const parsed = load(sections.componentSection);
  assert.equal(parsed.espnow_fan_bridge.role, 'cyd');
  assert.equal(parsed.espnow_fan_bridge.network_key, 'deadbeef12345678');
  assert.equal(parsed.espnow_fan_bridge.fallback_channel, 6);
  assert.equal(parsed.espnow_fan_bridge.fans.length, 1);

  const extracted = extractEspNowFansFromDeviceYaml(parsed);
  assert.equal(extracted.fans.length, 1);
  assert.equal(extracted.networkKey, 'deadbeef12345678');
  assert.equal(extracted.fallbackChannel, 6);
});
