import { dump } from 'js-yaml';
import type { BleFanConfig, Config, TuyaBleCandidate } from '../types';

export function normalizeEntityId(raw: string | undefined | null): string {
  if (!raw || typeof raw !== 'string') return '';
  return raw.trim().split('|')[0].trim();
}

export function findCandidateForEntity(
  entityId: string | undefined | null,
  candidates: TuyaBleCandidate[] = []
): TuyaBleCandidate | undefined {
  const norm = normalizeEntityId(entityId);
  if (!norm) return undefined;
  return candidates.find(
    c => normalizeEntityId(c.fan_entity_id) === norm || (c.light_entity_id && normalizeEntityId(c.light_entity_id) === norm)
  );
}

export function findConfiguredBleFan(
  entityId: string | undefined | null,
  bleFans: BleFanConfig[] = []
): BleFanConfig | undefined {
  const norm = normalizeEntityId(entityId);
  if (!norm) return undefined;
  return bleFans.find(
    f => normalizeEntityId(f.fan_entity_id) === norm || (f.light_entity_id && normalizeEntityId(f.light_entity_id) === norm)
  );
}

export function upsertBleFan(
  bleFans: BleFanConfig[] = [],
  nextFan: BleFanConfig
): BleFanConfig[] {
  const normFan = normalizeEntityId(nextFan.fan_entity_id);
  const normLight = normalizeEntityId(nextFan.light_entity_id);
  const idx = bleFans.findIndex(
    f =>
      (normFan && normalizeEntityId(f.fan_entity_id) === normFan) ||
      (normLight && f.light_entity_id && normalizeEntityId(f.light_entity_id) === normLight) ||
      (nextFan.device_id && f.device_id === nextFan.device_id)
  );
  if (idx >= 0) {
    const copy = [...bleFans];
    copy[idx] = { ...copy[idx], ...nextFan };
    return copy;
  }
  return [...bleFans, nextFan];
}

export function removeBleFanForEntity(
  bleFans: BleFanConfig[] = [],
  entityId: string
): BleFanConfig[] {
  const norm = normalizeEntityId(entityId);
  if (!norm) return bleFans;
  return bleFans.filter(
    f => normalizeEntityId(f.fan_entity_id) !== norm && normalizeEntityId(f.light_entity_id) !== norm
  );
}

export function toggleBleFanForEntity(
  bleFans: BleFanConfig[] = [],
  entityId: string,
  enabled: boolean,
  candidate?: TuyaBleCandidate
): BleFanConfig[] {
  const norm = normalizeEntityId(entityId);
  if (!norm) return bleFans;

  if (!enabled) {
    return removeBleFanForEntity(bleFans, norm);
  }

  if (candidate) {
    return upsertBleFan(bleFans, {
      name: candidate.name || candidate.fan_entity_id || norm,
      device_id: candidate.device_id,
      local_key: candidate.local_key,
      product_id: candidate.product_id || '',
      fan_entity_id: candidate.fan_entity_id || norm,
      light_entity_id: candidate.light_entity_id || '',
      expose_to_ha: true,
    });
  }

  // Fallback for manual entry when not auto-discovered from tuya_local
  const existing = findConfiguredBleFan(norm, bleFans);
  if (existing) return bleFans;
  const baseName = norm.includes('.') ? norm.split('.')[1].replace(/_/g, ' ') : norm;
  return upsertBleFan(bleFans, {
    name: baseName,
    device_id: '',
    local_key: '',
    product_id: '',
    fan_entity_id: norm.startsWith('fan.') ? norm : '',
    light_entity_id: norm.startsWith('light.') ? norm : '',
    expose_to_ha: true,
  });
}

export function configHasBleProxy(config: Config): boolean {
  return (
    config.pages?.some(page =>
      page.tiles?.some(tile => {
        const displayList = Array.isArray(tile.display)
          ? tile.display
          : tile.display
          ? [tile.display]
          : [];
        const hasBleDisplay = displayList.some(
          (d: any) =>
            d === 'tile_ble_proxy' ||
            (typeof d === 'object' && d !== null && 'tile_ble_proxy' in d)
        );
        const hasBleAction =
          tile.on_press === 'action_toggle_ble_proxy' ||
          tile.on_release === 'action_toggle_ble_proxy';
        return hasBleDisplay || hasBleAction;
      })
    ) || false
  );
}

export function extractBleFansFromDeviceYaml(rawData: any): BleFanConfig[] {
  const fans = rawData?.tuya_ble_fan?.fans;
  if (!Array.isArray(fans)) return [];
  return fans
    .filter((f: any) => f && typeof f === 'object' && (f.device_id || f.fan_entity_id || f.light_entity_id))
    .map((f: any) => ({
      name: String(f.name || f.fan_entity_id || f.device_id || ''),
      device_id: String(f.device_id || ''),
      local_key: String(f.local_key || ''),
      product_id: f.product_id ? String(f.product_id) : '',
      mac_address: f.mac_address ? String(f.mac_address) : '',
      uuid: f.uuid ? String(f.uuid) : '',
      fan_entity_id: f.fan_entity_id ? String(f.fan_entity_id) : '',
      light_entity_id: f.light_entity_id ? String(f.light_entity_id) : '',
      expose_to_ha: f.expose_to_ha !== false,
    }));
}

export interface TuyaBleYamlSections {
  packageLine: string;
  extraSubstitutions: Record<string, string>;
  componentSection: string;
}

export function buildTuyaBleFanYamlSections(
  bleFans: BleFanConfig[] = [],
  hasBleProxy: boolean = false
): TuyaBleYamlSections {
  const validFans = (bleFans || []).filter(
    f => f && f.device_id?.trim() && f.local_key?.trim() && (f.name?.trim() || f.fan_entity_id?.trim() || f.light_entity_id?.trim())
  );
  if (validFans.length === 0) {
    return {
      packageLine: '',
      extraSubstitutions: {},
      componentSection: '',
    };
  }

  const serializedFans = validFans.map(f => {
    const entry: Record<string, any> = {
      name: (f.name || f.fan_entity_id || f.device_id).trim(),
      device_id: f.device_id.trim(),
      local_key: f.local_key.trim(),
    };
    if (f.product_id?.trim()) entry.product_id = f.product_id.trim();
    if (f.mac_address?.trim()) entry.mac_address = f.mac_address.trim();
    if (f.uuid?.trim()) entry.uuid = f.uuid.trim();
    if (f.fan_entity_id?.trim()) entry.fan_entity_id = f.fan_entity_id.trim();
    if (f.light_entity_id?.trim()) entry.light_entity_id = f.light_entity_id.trim();
    entry.expose_to_ha = f.expose_to_ha !== false;
    return entry;
  });

  const tuyaBlock: Record<string, any> = {
    tuya_ble_fan: {
      ...(validFans.length === 1 ? { idle_disconnect_s: 0 } : { idle_disconnect_s: 30 }),
      fans: serializedFans,
    },
  };

  return {
    packageLine: '\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml',
    extraSubstitutions: hasBleProxy ? { ble_max_connections: '2' } : {},
    componentSection: dump(tuyaBlock, { lineWidth: -1, noCompatMode: true, sortKeys: false }),
  };
}

export function getOtherBleFanHosts(
  deviceId: string | undefined | null,
  bleFanHosts: Record<string, string[]> = {},
  currentDevicePath?: string | null
): string[] {
  const id = typeof deviceId === 'string' ? deviceId.trim() : '';
  if (!id) return [];
  const hosts = bleFanHosts?.[id];
  if (!Array.isArray(hosts) || hosts.length === 0) return [];
  const currentBase = currentDevicePath
    ? currentDevicePath.replace(/\\/g, '/').split('/').pop()?.trim().toLowerCase()
    : '';
  return hosts.filter(h => {
    const hBase = h.replace(/\\/g, '/').split('/').pop()?.trim().toLowerCase() || '';
    return !currentBase || hBase !== currentBase;
  });
}
