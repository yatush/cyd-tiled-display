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

export interface Config {
  pages: Page[];
  dynamic_entities?: string[];
  project_name?: string;
  project_path?: string;
  images?: Record<string, ImageEntry>;
  screen_images?: Record<string, ScreenImageEntry>;
}

export interface HaEntity {
  entity_id: string;
  friendly_name?: string;
}
