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

export interface HeadlessHubConfig {
  filename: string;
  name: string;
  friendly_name: string;
  board: string;
  fallback_channel: number;
  network_key?: string;
  fans: BleFanConfig[];
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
