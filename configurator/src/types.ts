export interface Tile {
  id: string;
  type: string;
  x: number;
  y: number;
  x_span?: number;
  y_span?: number;
  [key: string]: any;
}

export interface ScreenBgEntry {
  color?: string;
  image?: string;
  condition?: any;
}

export interface Page {
  id: string;
  tiles: Tile[];
  rows: number;
  cols: number;
  flags?: string[];
  background?: ScreenBgEntry[];
  time_color?: string;
}

export interface ImageEntry {
  data: string;        // base64-encoded PNG data (no data-URI prefix)
  filename: string;    // original filename, used for the ESPHome file: path
  type?: string;       // 'RGB565' | 'RGBA' | 'GRAYSCALE', default 'RGB565'
  scale?: number;      // 10–100: percentage of tile area the image fills (default 100, always 5px padding)
}

export interface ScreenImageEntry {
  data: string;        // base64-encoded PNG data (no data-URI prefix)
  filename: string;    // original filename
  type?: string;       // 'RGB565' | 'RGBA', default 'RGB565'
}

export type FixedEntityEntry = string | { entity: string; label?: string };

export interface BleFanConfig {
  name: string;
  device_id: string;
  local_key: string;
  product_id?: string;
  mac_address?: string;
  uuid?: string;
  fan_entity_id: string;
  light_entity_id?: string;
  expose_to_ha?: boolean;
}

export interface TuyaBleCandidate {
  name: string;
  device_id: string;
  local_key: string;
  product_id: string;
  mac_address?: string;
  uuid?: string;
  fan_entity_id: string;
  light_entity_id: string;
  supported: boolean;
}

export interface EspNowFanLink {
  name: string;
  fan_entity_id: string;
  light_entity_id?: string;
}

export interface GreeAcConfig {
  enabled: boolean;
  name: string;
  model: string;
  tx_pin: string;
  rx_pin: string;
  supports_cool: boolean;
  supports_heat: boolean;
  dump_ir: boolean;
}

export interface ShellyBackupItem {
  name: string;
  mac_address: string;
  channel: number;
  kind: 'switch' | 'light' | 'cover';
  entity_id: string;
  ip?: string;
}

export interface DetachedSwitchBinding {
  name: string;
  mac_address: string;
  input_channel: number;
  target_fan_device_id: string;
  target_light_entity_id: string;
}

export interface DiscoveredShellyEntity {
  entity_id: string;
  name: string;
  kind: 'switch' | 'light' | 'cover';
  channel: number;
  cyd_devices?: string[];
}

export interface DiscoveredShellyDevice {
  ha_device_id?: string;
  name: string;
  model: string;
  mac_address: string;
  ip: string;
  area_id?: string;
  area_name?: string;
  entities: DiscoveredShellyEntity[];
  input_entities?: string[];
  used_by_cyds?: string[];
  detached_channels?: number[];
  available_inputs?: number[];
}

export interface DetachedSwitchSuggestion extends DetachedSwitchBinding {
  source: 'automation' | 'area';
  reason: string;
}

export interface HeadlessHubConfig {
  filename: string;
  name: string;
  friendly_name: string;
  board: string;
  fallback_channel: number;
  network_key?: string;
  fans: BleFanConfig[];
  gree_ac?: GreeAcConfig | null;
  shellys?: ShellyBackupItem[];
  detached_switches?: DetachedSwitchBinding[];
}

export interface Config {
  pages: Page[];
  dynamic_entities?: string[];
  dynamic_entity_values?: Record<string, FixedEntityEntry[]>;
  ble_fans?: BleFanConfig[];
  espnow_fans?: EspNowFanLink[];
  espnow_network_key?: string;
  espnow_fallback_channel?: number;
  project_name?: string;
  project_path?: string;
  images?: Record<string, ImageEntry>;
  screen_images?: Record<string, ScreenImageEntry>;
}

export interface HaEntity {
  entity_id: string;
  friendly_name?: string;
}
