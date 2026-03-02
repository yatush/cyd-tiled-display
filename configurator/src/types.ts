export interface Tile {
  id: string;
  type: string;
  x: number;
  y: number;
  x_span?: number;
  y_span?: number;
  [key: string]: any;
}

export interface Page {
  id: string;
  tiles: Tile[];
  rows: number;
  cols: number;
  flags?: string[];
}

export interface ImageEntry {
  data: string;        // base64-encoded PNG data (no data-URI prefix)
  filename: string;    // original filename, used for the ESPHome file: path
  type?: string;       // 'RGB565' | 'RGBA' | 'GRAYSCALE', default 'RGB565'
}

export interface Config {
  pages: Page[];
  dynamic_entities?: string[];
  project_name?: string;
  project_path?: string;
  images?: Record<string, ImageEntry>;
}

export interface HaEntity {
  entity_id: string;
  friendly_name?: string;
}
