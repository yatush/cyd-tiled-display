import { dump } from 'js-yaml';
import type { BleFanConfig, Config, EspNowFanLink, HaEntity, HeadlessHubConfig, TuyaBleCandidate } from '../types';

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
  _deviceNameOrPath?: string | null
): { fan_entity_id: string; light_entity_id: string } {
  const fanSlug = slugifyEspHomeId(fanName);
  if (!fanSlug) {
    return { fan_entity_id: '', light_entity_id: '' };
  }
  return {
    fan_entity_id: `fan.${fanSlug}_fan`,
    light_entity_id: `light.${fanSlug}_light`,
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

export interface ExtractedEspNowConfig {
  fans: EspNowFanLink[];
  networkKey?: string;
  fallbackChannel?: number;
}

export function extractEspNowFansFromDeviceYaml(rawData: any): ExtractedEspNowConfig {
  const bridge = rawData?.espnow_fan_bridge;
  if (!bridge || typeof bridge !== 'object') {
    return { fans: [] };
  }
  const rawFans = Array.isArray(bridge.fans) ? bridge.fans : [];
  const fans: EspNowFanLink[] = rawFans
    .filter((f: any) => f && typeof f === 'object' && (f.fan_entity_id || f.light_entity_id || f.name))
    .map((f: any) => ({
      name: String(f.name || f.fan_entity_id || f.light_entity_id || ''),
      fan_entity_id: f.fan_entity_id ? String(f.fan_entity_id) : '',
      light_entity_id: f.light_entity_id ? String(f.light_entity_id) : '',
    }));
  const networkKey = bridge.network_key ? String(bridge.network_key) : undefined;
  const fallbackChannel =
    typeof bridge.fallback_channel === 'number' && bridge.fallback_channel >= 1 && bridge.fallback_channel <= 13
      ? bridge.fallback_channel
      : undefined;
  return { fans, networkKey, fallbackChannel };
}

export function mergeHubFansIntoHaEntities(
  haEntities: HaEntity[] = [],
  hubs: HeadlessHubConfig[] = []
): HaEntity[] {
  if (!hubs || hubs.length === 0) return haEntities;

  const hubLabelById = new Map<string, string>();
  for (const hub of hubs) {
    for (const fan of hub.fans || []) {
      const labelBase = (fan.name || '').trim() || 'Hub Fan';
      const fanId = normalizeEntityId(fan.fan_entity_id);
      const lightId = normalizeEntityId(fan.light_entity_id);
      if (fanId) hubLabelById.set(fanId, `[Hub] ${labelBase}`);
      if (lightId) hubLabelById.set(lightId, `[Hub] ${labelBase} Light`);
    }
  }
  if (hubLabelById.size === 0) return haEntities;

  const hubEntries: HaEntity[] = [];
  const seen = new Set<string>();
  for (const [entity_id, friendly_name] of hubLabelById.entries()) {
    seen.add(entity_id);
    hubEntries.push({ entity_id, friendly_name });
  }
  const restEntries = haEntities.filter(e => !seen.has(normalizeEntityId(e.entity_id)));
  return [...hubEntries, ...restEntries];
}

export function collectReferencedEntityIds(config: Config): Set<string> {
  const refs = new Set<string>();
  for (const page of config.pages || []) {
    for (const tile of page.tiles || []) {
      if (Array.isArray((tile as any).entities)) {
        for (const item of (tile as any).entities) {
          const val = typeof item === 'string' ? item : item?.entity;
          const norm = normalizeEntityId(val);
          if (norm) refs.add(norm);
        }
      }
      if (typeof (tile as any).entity === 'string') {
        const norm = normalizeEntityId((tile as any).entity);
        if (norm) refs.add(norm);
      }
      if (Array.isArray((tile as any).options)) {
        for (const opt of (tile as any).options) {
          const norm = normalizeEntityId(opt?.entity);
          if (norm) refs.add(norm);
        }
      }
    }
  }
  if (config.dynamic_entity_values) {
    for (const entries of Object.values(config.dynamic_entity_values)) {
      for (const entry of entries || []) {
        const val = typeof entry === 'string' ? entry : (entry as any)?.entity;
        const norm = normalizeEntityId(val);
        if (norm) refs.add(norm);
      }
    }
  }
  return refs;
}

export const DEFAULT_ESPNOW_NETWORK_KEY = 'cyd_espnow_default';

export function findConfiguredEspNowFan(
  entityId: string | undefined | null,
  espnowFans: EspNowFanLink[] = []
): EspNowFanLink | undefined {
  const norm = normalizeEntityId(entityId);
  if (!norm) return undefined;
  return (espnowFans || []).find(
    f =>
      normalizeEntityId(f.fan_entity_id) === norm ||
      (f.light_entity_id && normalizeEntityId(f.light_entity_id) === norm)
  );
}

export function toggleEspNowFanForEntity(
  espnowFans: EspNowFanLink[] = [],
  entityId: string,
  enabled: boolean,
  candidate?: TuyaBleCandidate
): EspNowFanLink[] {
  const norm = normalizeEntityId(entityId);
  if (!norm) return espnowFans || [];

  const filtered = (espnowFans || []).filter(
    f =>
      normalizeEntityId(f.fan_entity_id) !== norm &&
      normalizeEntityId(f.light_entity_id) !== norm
  );
  if (!enabled) {
    return filtered;
  }

  if (candidate) {
    const defaults = deriveDefaultBleEntityIds(candidate.name || candidate.device_id);
    return [
      ...filtered,
      {
        name: candidate.name || candidate.fan_entity_id || norm,
        fan_entity_id: candidate.fan_entity_id || defaults.fan_entity_id || (norm.startsWith('fan.') ? norm : ''),
        light_entity_id: candidate.light_entity_id || defaults.light_entity_id || (norm.startsWith('light.') ? norm : ''),
      },
    ];
  }

  const baseName = norm.includes('.') ? norm.split('.')[1].replace(/_/g, ' ') : norm;
  // Derive companion light entity if this is fan.<slug>_fan -> light.<slug>_light
  let companionLight = '';
  if (norm.startsWith('fan.')) {
    const slug = norm.slice(4);
    if (slug.endsWith('_fan')) {
      companionLight = `light.${slug.slice(0, -4)}_light`;
    }
  }
  return [
    ...filtered,
    {
      name: baseName,
      fan_entity_id: norm.startsWith('fan.') ? norm : '',
      ...(norm.startsWith('light.')
        ? { light_entity_id: norm }
        : companionLight
        ? { light_entity_id: companionLight }
        : {}),
    },
  ];
}

/**
 * Return explicitly configured ESP-NOW fans for this CYD, excluding any fan
 * that is also configured for local BLE on this same CYD.
 * Intentionally stateless: never silently injects fans from local hub files.
 */
export function resolveEffectiveEspNowFans(
  config: Config,
  _hubs: HeadlessHubConfig[] = []
): EspNowFanLink[] {
  const localBleIds = new Set<string>();
  for (const bf of config.ble_fans || []) {
    if (bf.fan_entity_id) localBleIds.add(normalizeEntityId(bf.fan_entity_id));
    if (bf.light_entity_id) localBleIds.add(normalizeEntityId(bf.light_entity_id));
  }

  const byKey = new Map<string, EspNowFanLink>();
  for (const link of config.espnow_fans || []) {
    const fanId = normalizeEntityId(link.fan_entity_id);
    const lightId = normalizeEntityId(link.light_entity_id);
    if (!fanId && !lightId) continue;
    if ((fanId && localBleIds.has(fanId)) || (lightId && localBleIds.has(lightId))) continue;
    const key = fanId || lightId;
    if (!byKey.has(key)) {
      byKey.set(key, {
        name: (link.name || fanId || lightId).trim(),
        fan_entity_id: fanId,
        ...(lightId ? { light_entity_id: lightId } : {}),
      });
    }
  }

  return Array.from(byKey.values());
}

export function resolveEffectiveEspNowShellys(
  config: Config,
  bleHubs: HeadlessHubConfig[] = [],
  discoveredShellys: import('../types').DiscoveredShellyDevice[] = []
): import('../types').ShellyBackupItem[] {
  const referenced = collectReferencedEntityIds(config);

  const out: import('../types').ShellyBackupItem[] = [];
  const seen = new Set<string>();

  // 1. Auto-match against HA-discovered Shelly devices (zero hub assignment required)
  for (const dev of discoveredShellys || []) {
    for (const ent of dev.entities || []) {
      const eid = (ent.entity_id || '').trim();
      if (!eid || !referenced.has(eid) || seen.has(eid)) continue;
      seen.add(eid);
      out.push({
        name: ent.name || dev.name || eid,
        mac_address: dev.mac_address,
        channel: ent.channel || 0,
        kind: ent.kind || 'switch',
        entity_id: eid,
        ip: dev.ip || '',
      });
    }
  }

  // 2. Include any legacy hub-assigned Shellys as fallback
  for (const hub of bleHubs || []) {
    for (const sh of hub.shellys || []) {
      const eid = (sh.entity_id || '').trim();
      if (!eid || !referenced.has(eid) || seen.has(eid)) continue;
      seen.add(eid);
      out.push(sh);
    }
  }
  return out;
}

export function resolveEffectiveEspNowClimates(
  config: Config,
  bleHubs: HeadlessHubConfig[] = []
): import('../types').EspNowClimateLink[] {
  const referenced = collectReferencedEntityIds(config);
  const out: import('../types').EspNowClimateLink[] = [];
  const seen = new Set<string>();

  for (const hub of bleHubs || []) {
    const ac = hub.gree_ac;
    if (!ac || !ac.enabled || !ac.name?.trim()) continue;
    const slug = slugifyEspHomeId(ac.name);
    if (!slug) continue;
    const eid = `climate.${slug}`;
    if (!referenced.has(eid) || seen.has(eid)) continue;
    seen.add(eid);
    out.push({
      name: ac.name.trim(),
      entity_id: eid,
    });
  }
  return out;
}

export interface EspNowCydYamlSections {
  packageLine: string;
  componentSection: string;
}

export function buildEspNowCydYamlSections(
  espnowFans: EspNowFanLink[] = [],
  networkKey?: string,
  fallbackChannel: number = 1,
  espnowShellys: import('../types').ShellyBackupItem[] = [],
  espnowClimates: import('../types').EspNowClimateLink[] = []
): EspNowCydYamlSections {
  const validFans = (espnowFans || []).filter(
    f => f && (f.fan_entity_id?.trim() || f.light_entity_id?.trim())
  );
  const validShellys = (espnowShellys || []).filter(
    s => s && s.mac_address?.trim() && s.entity_id?.trim()
  );
  const validClimates = (espnowClimates || []).filter(
    c => c && c.entity_id?.trim()
  );
  if (validFans.length === 0 && validShellys.length === 0 && validClimates.length === 0) {
    return { packageLine: '', componentSection: '' };
  }

  const serializedFans = validFans.map(f => {
    const entry: Record<string, any> = {
      name: (f.name || f.fan_entity_id || f.light_entity_id || '').trim(),
    };
    if (f.fan_entity_id?.trim()) entry.fan_entity_id = f.fan_entity_id.trim();
    if (f.light_entity_id?.trim()) entry.light_entity_id = f.light_entity_id.trim();
    return entry;
  });

  const serializedShellys = validShellys.map(s => ({
    name: (s.name || s.entity_id).trim(),
    mac_address: s.mac_address.trim().toLowerCase().replace(/[^0-9a-f]/g, ''),
    channel: Number.isFinite(s.channel) ? s.channel : 0,
    kind: s.kind || (s.entity_id.startsWith('cover.') ? 'cover' : 'switch'),
    entity_id: s.entity_id.trim(),
  }));

  const serializedClimates = validClimates.map(c => ({
    name: (c.name || c.entity_id).trim(),
    entity_id: c.entity_id.trim(),
  }));

  const effectiveKey = networkKey?.trim() || DEFAULT_ESPNOW_NETWORK_KEY;
  const bridgeInner: Record<string, any> = {
    role: 'cyd',
    network_key: effectiveKey,
    fallback_channel: Math.max(1, Math.min(13, Math.floor(fallbackChannel || 1))),
  };
  if (serializedFans.length > 0) {
    bridgeInner.fans = serializedFans;
  }
  if (serializedShellys.length > 0) {
    bridgeInner.shellys = serializedShellys;
  }
  if (serializedClimates.length > 0) {
    bridgeInner.climates = serializedClimates;
  }

  const bridgeBlock: Record<string, any> = {
    espnow_fan_bridge: bridgeInner,
  };

  return {
    packageLine: '\n  espnow_cyd: !include lib/espnow_cyd.yaml',
    componentSection: dump(bridgeBlock, { lineWidth: -1, noCompatMode: true, sortKeys: false }),
  };
}
