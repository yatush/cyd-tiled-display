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

export interface Config {
  pages: Page[];
  dynamic_entities?: string[];
  project_name?: string;
  project_path?: string;
}

export interface HaEntity {
  entity_id: string;
  friendly_name?: string;
}
