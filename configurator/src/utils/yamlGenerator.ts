import yaml from 'js-yaml';
import type { Config, Page, Tile } from '../types';

// ---------------------------------------------------------------------------
// Known-field allowlists derived from schema.json.
// Any tile field not in this set is a stale/removed property and will be
// silently stripped before the YAML is emitted. Update these when schema.json
// changes.
// ---------------------------------------------------------------------------
const COMMON_TILE_FIELDS = new Set([
  'x', 'y', 'x_span', 'y_span',
  'display', 'display_assets',
  'fill_color', 'border_color', 'border_width', 'border_radius',
  'requires_fast_refresh', 'activation_var',
]);

const TYPE_SPECIFIC_FIELDS: Record<string, Set<string>> = {
  ha_action:     new Set(['entities', 'perform', 'location_perform', 'long_perform', 'long_destination', 'long_dynamic_entity', 'display_page_if_no_entity']),
  blind_position: new Set(['entities']),
  move_page:     new Set(['destination', 'dynamic_entry', 'entities']),
  toggle_entity: new Set(['dynamic_entity', 'entity', 'presentation_name', 'initially_chosen']),
  title:         new Set(['entities']),
  cycle_entity:  new Set(['dynamic_entity', 'options', 'reset_on_leave']),
  function:      new Set(['on_press', 'on_release']),
};

const SCREEN_FIELDS = new Set([
  'id', 'rows', 'cols', 'flags', 'time_color', 'background', 'tiles',
]);

/** Synchronize known tile and screen fields at runtime with the schema.json payload from /api/schema. */
export function registerTileSchema(schema: {
  screen?: { name: string }[];
  common?: { name: string }[];
  types?: { type: string; fields?: { name: string }[] }[];
} | null | undefined): void {
  if (!schema || typeof schema !== 'object') return;
  if (Array.isArray(schema.screen)) {
    for (const field of schema.screen) {
      if (field?.name) SCREEN_FIELDS.add(field.name);
    }
  }
  if (Array.isArray(schema.common)) {
    for (const field of schema.common) {
      if (field?.name) COMMON_TILE_FIELDS.add(field.name);
    }
  }
  if (Array.isArray(schema.types)) {
    for (const typeDef of schema.types) {
      if (!typeDef?.type) continue;
      const fields = new Set<string>(
        (typeDef.fields || []).map(f => f?.name).filter((n): n is string => Boolean(n))
      );
      TYPE_SPECIFIC_FIELDS[typeDef.type] = fields;
    }
  }
}

export function unknownPageFields(page: Record<string, unknown>): string[] {
  return Object.keys(page).filter(key => !SCREEN_FIELDS.has(key));
}

export function unknownTileFields(tile: Record<string, unknown>, type: string): string[] {
  if (!Object.prototype.hasOwnProperty.call(TYPE_SPECIFIC_FIELDS, type)) throw new Error(`Unknown tile type: ${type}`);
  const typeFields = TYPE_SPECIFIC_FIELDS[type];
  return Object.keys(tile).filter(key => !COMMON_TILE_FIELDS.has(key) && !typeFields.has(key));
}

/** Strip any tile fields not recognised by the current schema, logging a warning for each. */
function stripUnknownTileFields(tile: Record<string, any>, type: string): Record<string, any> {
  const typeFields = TYPE_SPECIFIC_FIELDS[type] ?? new Set<string>();
  const result: Record<string, any> = {};
  for (const [k, v] of Object.entries(tile)) {
    // __id is an internal UI field added by includeIds — always pass through
    if (k === '__id' || COMMON_TILE_FIELDS.has(k) || typeFields.has(k)) {
      result[k] = v;
    } else {
      console.warn(`[yamlGenerator] Stripping unknown field "${k}" from tile type "${type}" at (${tile.x}, ${tile.y})`);
    }
  }
  return result;
}

const transformConditionLogic = (value: any): any => {
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) {
        return {
            operator: 'OR',
            conditions: value.map(transformConditionLogic)
        };
    }
    if (typeof value === 'object' && value !== null) {
        if (value.or) {
            return {
                operator: 'OR',
                conditions: value.or.map(transformConditionLogic)
            };
        }
        if (value.and) {
            return {
                operator: 'AND',
                conditions: value.and.map(transformConditionLogic)
            };
        }
        if (value.not) {
            return {
                operator: 'NOT',
                conditions: [transformConditionLogic(value.not)]
            };
        }
    }
    return value;
};

const serializeTile = ({ id, ...rest }: Tile, includeIds: boolean, retainUnknown = false) => {
        // Clean up empty fields
        const tile: any = { ...rest };
        if (includeIds) tile.__id = id; // Internal ID for preview highlighting
        
        // Handle display: convert single item array to string if preferred, or keep as list
        if (Array.isArray(tile.display) && tile.display.length === 1) {
           // Optional: flatten single item arrays if that's the convention
           // tile.display = tile.display[0];
        }
        
        // Remove undefined/empty optional fields to keep YAML clean
        Object.keys(tile).forEach(key => {
          if (tile[key] === undefined || tile[key] === '' || (Array.isArray(tile[key]) && tile[key].length === 0)) {
            delete tile[key];
          }
        });

        // Transform condition logic for requires_fast_refresh
        if (tile.requires_fast_refresh) {
            tile.requires_fast_refresh = transformConditionLogic(tile.requires_fast_refresh);
        }

        // Remove deprecated legacy fields that are superseded by the 'display_assets' list.
        if (!retainUnknown) delete tile.state_images;

        // Transform condition logic inside display_assets entries
        if (Array.isArray(tile.display_assets)) {
            tile.display_assets = tile.display_assets.map((entry: any) => {
                if (!entry) return entry;
                let result = { ...entry };

                // Transform image-selection condition
                if (result.condition != null && result.condition !== '') {
                    result.condition = transformConditionLogic(result.condition);
                } else if ('condition' in result && (result.condition == null || result.condition === '')) {
                    const { condition: _c, ...rest } = result;
                    result = rest;
                }



                return result;
            });
        }

        // Handle display params transformation (icon quoting, color/size id wrapping)
        if (Array.isArray(tile.display)) {
            tile.display = tile.display.map((d: any) => {
                if (typeof d === 'object') {
                    const scriptName = Object.keys(d)[0];
                    const params = d[scriptName];
                    const newParams = { ...params };
                    
                    // Handle icon quoting - handled by regex post-processing for reliability
                    /*
                    if (newParams.icon) {
                        const iconVal = newParams.icon;
                        if (typeof iconVal === 'string' && iconVal.startsWith('\\U') && !iconVal.startsWith('"')) {
                            newParams.icon = `"${iconVal}"`;
                        }
                    }
                    */

                    // Handle color/size id wrapping
                    ['color', 'size'].forEach(param => {
                        if (newParams[param]) {
                            const val = newParams[param];
                            if (typeof val === 'string' && 
                                !val.startsWith('id(') && 
                                !val.startsWith('Color::') &&
                                /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(val)) {
                                newParams[param] = `id(${val})`;
                            }
                        }
                    });

                    return { [scriptName]: newParams };
                }
                return d;
            });
        }
        
        // Wrap tile type in object key
        const type = tile.type;
        delete tile.type;

        // Strip any stale/removed fields before serializing
        const cleanedTile = retainUnknown ? tile : stripUnknownTileFields(tile, type);

        return { [type]: cleanedTile };
};

const formatIcons = (text: string) =>
    text.replace(/icon:\s*['"]*(\\U[0-9a-fA-F]+)['"]*/g, "icon: '$1'");

const serializePage = (page: Page, includeIds: boolean, retainUnknown = false) => {
    const pageExtras: Record<string, any> = {};
    if (retainUnknown) {
      for (const [key, value] of Object.entries(page as Record<string, any>)) {
        if (!SCREEN_FIELDS.has(key) && value !== undefined) {
          pageExtras[key] = value;
        }
      }
    }

    const serializedBg = page.background && page.background.length > 0
      ? page.background.map((entry: any) => {
          const result: any = retainUnknown ? { ...entry } : {};
          if (!retainUnknown) {
            if ('color' in entry && entry.color) result.color = entry.color;
            if ('image' in entry && entry.image) result.image = entry.image;
          }
          if ('condition' in entry && entry.condition !== '' && entry.condition != null) {
            result.condition = transformConditionLogic(entry.condition);
          } else if (retainUnknown && 'condition' in result && (result.condition == null || result.condition === '')) {
            delete result.condition;
          }
          return result;
        }).filter(e => retainUnknown || 'color' in e || 'image' in e)
      : undefined;

    const tilesToSerialize = retainUnknown
      ? page.tiles
      : page.tiles.filter(tile => tile.x < page.cols && tile.y < page.rows);

    return {
      id: page.id,
      rows: page.rows,
      cols: page.cols,
      flags: page.flags && page.flags.length > 0 ? page.flags : undefined,
      time_color: page.time_color || undefined,
      background: serializedBg && serializedBg.length > 0 ? serializedBg : undefined,
      ...pageExtras,
      tiles: tilesToSerialize.map(tile => serializeTile(tile, includeIds, retainUnknown)),
    };
};

export const generateTileYaml = (tile: Tile): string =>
    formatIcons(yaml.dump([serializeTile(tile, false, true)], { lineWidth: -1, noCompatMode: true, sortKeys: false }));

export const generatePageYaml = (page: Page): string =>
    formatIcons(yaml.dump([serializePage(page, false, true)], { lineWidth: -1, noCompatMode: true, sortKeys: false }));

const serializeDynamicEntities = (config: Config): any[] | undefined => {
    const names = config.dynamic_entities || [];
    const fixedValues = config.dynamic_entity_values || {};
    if (names.length === 0) return undefined;

    const items: any[] = [];
    for (const rawName of names) {
        const name = typeof rawName === 'string' ? rawName.trim() : '';
        if (!name) continue;
        if (Object.prototype.hasOwnProperty.call(fixedValues, name)) {
            const vals: any[] = [];
            for (const entry of fixedValues[name] || []) {
                if (typeof entry === 'string') {
                    const ent = entry.trim();
                    if (ent) vals.push(ent);
                } else if (entry && typeof entry === 'object') {
                    const ent = typeof entry.entity === 'string' ? entry.entity.trim() : '';
                    const lbl = typeof entry.label === 'string' ? entry.label.trim() : '';
                    if (ent) {
                        vals.push(lbl ? { entity: ent, label: lbl } : ent);
                    }
                }
            }
            if (vals.length === 0) {
                items.push({ [name]: [] });
            } else if (vals.length === 1 && typeof vals[0] === 'string') {
                items.push({ [name]: vals[0] });
            } else {
                items.push({ [name]: vals });
            }
        } else {
            items.push(name);
        }
    }
    return items.length > 0 ? items : undefined;
};

export const generateYaml = (config: Config, includeIds: boolean = false, _includeInternalKeys: boolean = true) => {
    // Convert internal model to YAML structure expected by Python script
    const screens = config.pages.map(page => serializePage(page, includeIds, false));
    const serializedDynamicEntities = serializeDynamicEntities(config);
    
    const yamlString = yaml.dump({ 
        dynamic_entities: serializedDynamicEntities,
        screens,
        images: config.images && Object.keys(config.images).length > 0 ? config.images : undefined,
        screen_images: config.screen_images && Object.keys(config.screen_images).length > 0 ? config.screen_images : undefined
    }, { lineWidth: -1, noCompatMode: true, sortKeys: false });
    // Ensure icons are formatted as '\U...' for clean single-quoted YAML
    return formatIcons(yamlString);
};
