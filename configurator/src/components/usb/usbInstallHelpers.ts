import { apiFetch } from '../../utils/api';

// Types for Web Serial API (not in standard TS lib)
declare global {
  interface Navigator {
    serial?: {
      getPorts(): Promise<SerialPort[]>;
      requestPort(options?: {
        filters?: Array<{ usbVendorId?: number; usbProductId?: number }>;
      }): Promise<SerialPort>;
      addEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
    };
  }
  interface SerialPort {
    getInfo(): { usbVendorId?: number; usbProductId?: number };
    open(options: { baudRate: number }): Promise<void>;
    close(): Promise<void>;
    readable: ReadableStream | null;
    writable: WritableStream | null;
  }
}

export const ESP_VENDOR_IDS = [
  0x10C4, // Silicon Labs CP210x
  0x1A86, // QinHeng CH340
  0x0403, // FTDI
  0x303A, // Espressif USB JTAG/Serial
];

export interface DeviceListEntry {
  filename: string;
  device_name: string;
  friendly_name: string;
  screen_type: string | null;
}

export type UsbStatus =
  | 'idle'
  | 'saving'
  | 'compiling'
  | 'compiled'
  | 'downloading'
  | 'flashing'
  | 'success'
  | 'error';

export type ConfigMode = 'existing' | 'new';

export function generateEncryptionKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

/** Load device settings from an existing YAML file on the server. */
export async function loadDeviceInfo(filename: string) {
  try {
    const res = await apiFetch(`/load?path=${encodeURIComponent(filename)}`);
    if (!res.ok) return null;
    const data = await res.json();

    let screenType: string | null = null;
    const deviceBase = data?.packages?.device_base;
    if (typeof deviceBase === 'string') {
      if (deviceBase.includes('2432s028')) screenType = '2432s028';
      else if (deviceBase.includes('3248s035')) screenType = '3248s035';
    }

    let otaPassword: string | undefined;
    if (data?.ota) {
      if (Array.isArray(data.ota)) {
        const esphomeOta = data.ota.find((o: any) => o.platform === 'esphome');
        if (esphomeOta?.password) otaPassword = esphomeOta.password;
      } else if (data.ota?.password) {
        otaPassword = data.ota.password;
      }
    }

    const isHeadlessHub =
      Boolean(
        data?.packages &&
          typeof data.packages === 'object' &&
          Object.values(data.packages).some(
            (v: any) => typeof v === 'string' && v.includes('headless_hub_base.yaml')
          )
      ) || data?.espnow_fan_bridge?.role === 'hub';

    return {
      deviceName: data?.substitutions?.device_name || data?.esphome?.name || '',
      friendlyName: data?.substitutions?.friendly_name || data?.esphome?.friendly_name || '',
      screenType: screenType || '2432s028',
      encryptionKey: data?.api?.encryption?.key || '',
      otaPassword,
      ipAddress: data?.wifi?.use_address || undefined,
      isHeadlessHub,
    };
  } catch (e) {
    console.error('Failed to load device info:', e);
    return null;
  }
}
