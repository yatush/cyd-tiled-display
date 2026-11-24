import { dump } from 'js-yaml';
import type { BleFanConfig, Config, HaEntity, TuyaBleCandidate } from '../types';

export function normalizeEntityId(raw: string | undefined | null): string {
  if (!raw || typeof raw !== 'string') return '';
  return raw.trim().split('|')[0].trim();
}

export function slugifyEspHomeId(value: string | undefined | null): string {
  if (!value || typeof value !== 'string') return '';
  const base = value.replace(/\\/g, '/').split('/').pop() || value;
  return base
    .toLowerCase()
    .replace(/\.ya?ml$/i, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function deriveDefaultBleEntityIds(
  fanName: string | undefined | null,
  deviceNameOrPath?: string | null
): { fan_entity_id: string; light_entity_id: string } {
  const fanSlug = slugifyEspHomeId(fanName);
  if (!fanSlug) {
    return { fan_entity_id: '', light_entity_id: '' };
  }
  const deviceSlug = slugifyEspHomeId(deviceNameOrPath);
  const prefix = deviceSlug ? `${deviceSlug}_${fanSlug}` : fanSlug;
  return {
    fan_entity_id: `fan.${prefix}`,
    light_entity_id: `light.${prefix}_light`,
  };
}

export function mergeBleFansIntoHaEntities(
  haEntities: HaEntity[] = [],
  bleFans: BleFanConfig[] = []
): HaEntity[] {
  if (!bleFans || bleFans.length === 0) return haEntities;

  const bleLabelById = new Map<string, string>();
  for (const fan of bleFans) {
    const labelBase = (fan.name || '').trim() || 'BLE Fan';
    const fanId = normalizeEntityId(fan.fan_entity_id);
    const lightId = normalizeEntityId(fan.light_entity_id);
    if (fanId) {
      bleLabelById.set(fanId, `[BLE] ${labelBase}`);
    }
    if (lightId) {
      bleLabelById.set(lightId, `[BLE] ${labelBase} Light`);
    }
  }

  if (bleLabelById.size === 0) return haEntities;

  const bleEntries: HaEntity[] = [];
  const restEntries: HaEntity[] = [];
  const seen = new Set<string>();

  for (const [entity_id, friendly_name] of bleLabelById.entries()) {
    seen.add(entity_id);
    bleEntries.push({ entity_id, friendly_name });
  }

  for (const e of haEntities) {
    const norm = normalizeEntityId(e.entity_id);
    if (seen.has(norm)) continue;
    restEntries.push(e);
  }

  return [...bleEntries, ...restEntries];
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

export interface BleResourcePlan {
  fanCount: number;
  fanSlots: number;
  proxySlots: number;
  totalConnections: number;
  persistent: boolean;
  idleDisconnectS: number;
  displayBufferSize: string; // e.g. "40%", "30%", "20%"
}

export function computeBleResourcePlan(
  fanCount: number,
  hasBleProxy: boolean = false
): BleResourcePlan {
  const count = Math.max(0, Math.floor(fanCount || 0));
  const maxFanSlots = hasBleProxy ? 2 : 3;
  const fanSlots = count > 0 ? Math.min(count, maxFanSlots) : 1;
  const proxySlots = hasBleProxy ? 1 : 0;
  const totalConnections = Math.min(3, fanSlots + proxySlots);
  const persistent = count > 0 && count <= fanSlots;
  const idleDisconnectS = persistent ? 0 : 30;
  const displayBufferSize = totalConnections >= 3 ? '15%' : '20%';

  return {
    fanCount: count,
    fanSlots,
    proxySlots,
    totalConnections,
    persistent,
    idleDisconnectS,
    displayBufferSize,
  };
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

  const plan = computeBleResourcePlan(validFans.length, hasBleProxy);

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
      max_connections: plan.fanSlots,
      idle_disconnect_s: plan.idleDisconnectS,
      fans: serializedFans,
    },
  };

  return {
    packageLine: '\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml',
    extraSubstitutions: {
      ble_max_connections: String(plan.totalConnections),
      display_buffer_size: plan.displayBufferSize,
    },
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
