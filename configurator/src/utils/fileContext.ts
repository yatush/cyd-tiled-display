import type { Config } from '../types';

export interface DeviceFileMeta {
  deviceName: string;
  friendlyName: string;
  screenType: string;
  encryptionKey: string;
  otaPassword?: string;
  ipAddress?: string;
}

export interface FileContext {
  kind: 'device' | 'screen' | 'local';
  path: string;
  deviceMeta?: DeviceFileMeta;
}

const FILE_CONTEXT_KEY = 'cyd_file_context';
const SAVED_SNAPSHOT_KEY = 'cyd_saved_snapshot';

/**
 * Produce a canonical string representation of the editable parts of a Config
 * so dirty detection ignores transient metadata like `project_path`.
 */
export function getConfigSnapshot(config: Config): string {
  return JSON.stringify({
    pages: config.pages || [],
    dynamic_entities: config.dynamic_entities || [],
    images: config.images || {},
    screen_images: config.screen_images || {},
  });
}

/**
 * Extract ESPHome device metadata from a parsed device YAML object.
 */
export function extractDeviceMetaFromYamlData(data: any): DeviceFileMeta | null {
  if (!data || typeof data !== 'object') return null;

  let screenType: string | null = null;
  const deviceBase = data?.packages?.device_base;
  if (typeof deviceBase === 'string') {
    if (deviceBase.includes('2432s028')) screenType = '2432s028';
    else if (deviceBase.includes('3248s035')) screenType = '3248s035';
  }

  let otaPassword: string | undefined;
  if (data?.ota) {
    if (Array.isArray(data.ota)) {
      const esphomeOta = data.ota.find((o: any) => o?.platform === 'esphome');
      if (esphomeOta?.password) otaPassword = esphomeOta.password;
    } else if (data.ota?.password) {
      otaPassword = data.ota.password;
    }
  }

  const deviceName = data?.substitutions?.device_name || data?.esphome?.name || '';
  const friendlyName = data?.substitutions?.friendly_name || data?.esphome?.friendly_name || deviceName;
  const encryptionKey = data?.api?.encryption?.key || '';
  const ipAddress = data?.wifi?.use_address || undefined;

  if (!deviceName && !encryptionKey && !screenType) return null;

  return {
    deviceName,
    friendlyName,
    screenType: screenType || '2432s028',
    encryptionKey,
    otaPassword,
    ipAddress,
  };
}

export function loadStoredFileContext(): FileContext | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    const raw = localStorage.getItem(FILE_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.path === 'string' && ['device', 'screen', 'local'].includes(parsed.kind)) {
      return parsed as FileContext;
    }
    return null;
  } catch {
    return null;
  }
}

export function saveStoredFileContext(ctx: FileContext | null): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (ctx) {
      localStorage.setItem(FILE_CONTEXT_KEY, JSON.stringify(ctx));
    } else {
      localStorage.removeItem(FILE_CONTEXT_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

export function loadStoredSnapshot(): string | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(SAVED_SNAPSHOT_KEY);
  } catch {
    return null;
  }
}

export function saveStoredSnapshot(snapshot: string | null): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (snapshot !== null) {
      localStorage.setItem(SAVED_SNAPSHOT_KEY, snapshot);
    } else {
      localStorage.removeItem(SAVED_SNAPSHOT_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

export function getDisplayFileName(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}
