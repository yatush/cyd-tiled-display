import yaml from 'js-yaml';
import type { Config, Page, Tile } from '../types';

/** Map legacy 'direction' string to from/to position pair. */
const _DIRECTION_TO_FROM_TO: Record<string, { from: [number,number]; to: [number,number] }> = {
    none:       { from: [0.5, 0.5], to: [0.5, 0.5] },
    left_right: { from: [0.0, 0.5], to: [1.0, 0.5] },
    right_left: { from: [1.0, 0.5], to: [0.0, 0.5] },
    up_down:    { from: [0.5, 0.0], to: [0.5, 1.0] },
    down_up:    { from: [0.5, 1.0], to: [0.5, 0.0] },
};

function _normalizePos(pos: any): [number, number] {
    if (Array.isArray(pos) && pos.length === 2 && typeof pos[0] === 'number') return [pos[0], pos[1]];
    return [0.5, 0.5]; // default to center
}

/** Normalize an icon value from YAML: strip legacy surrounding double-quotes
 * (e.g. '"\U0000f05a"' → '\U0000f05a') and re-encode decoded non-ASCII single
 * glyphs (e.g. from double-quoted "\U0000f05a") back to '\U0000f05a'. */
function _normalizeIconValue(v: any): any {
    if (typeof v !== 'string') return v;
    const val = v.startsWith('"') && v.endsWith('"') && v.length > 2
        ? v.substring(1, v.length - 1)
        : v;
    const chars = Array.from(val);
    if (chars.length === 1) {
        const cp = chars[0].codePointAt(0)!;
        if (cp > 127) {
            return `\\U${cp.toString(16).padStart(8, '0')}`;
        }
    }
    return val;
}

/** Migrate an animation object (or step within it) from legacy direction → from/to, and normalize positions to [x,y]. */
function _migrateStep(step: any): any {
    if (!step || typeof step !== 'object') return step;
    let migrated: any;
    if ('direction' in step) {
        const { direction, ...rest } = step;
        const { from, to } = _DIRECTION_TO_FROM_TO[direction] ?? { from: [0.5, 0.5] as [number,number], to: [0.5, 0.5] as [number,number] };
        migrated = { from, to, ...rest };
    } else {
        // Normalize string/array positions
        migrated = {
            ...step,
            from: _normalizePos(step.from),
            to:   _normalizePos(step.to),
        };
    }
    // Normalize per-step icon value if present
    if ('icon' in migrated) {
        migrated.icon = _normalizeIconValue(migrated.icon);
    }
    return migrated;
}

/** Migrate a full animation config (single-step or multi-step) from legacy to from/to. */
function _migrateAnimation(anim: any): any {
    if (!anim || typeof anim !== 'object') return anim;
    if (Array.isArray(anim.steps)) {
        return { ...anim, steps: anim.steps.map(_migrateStep) };
    }
    return _migrateStep(anim);
}

const transformConditionLogicReverse = (value: any): any => {
    if (typeof value === 'string') return value;
    if (typeof value === 'object' && value !== null) {
        if (value.operator && value.conditions) {
            const op = value.operator.toUpperCase();
            // conditions may be a plain string (single condition) or an array
            const rawConditions = Array.isArray(value.conditions) ? value.conditions : [value.conditions];
            const conditions = rawConditions.map(transformConditionLogicReverse);
            if (op === 'OR') return { or: conditions };
            if (op === 'AND') return { and: conditions };
            if (op === 'NOT') return { not: conditions[0] };
        }
    }
    return value;
};

const scanForDynamicEntities = (obj: any, set: Set<string>) => {
    if (!obj || typeof obj !== 'object') return;
    
    if (obj.dynamic_entity && typeof obj.dynamic_entity === 'string') {
        set.add(obj.dynamic_entity);
    }
    if (obj.long_dynamic_entity && typeof obj.long_dynamic_entity === 'string') {
        set.add(obj.long_dynamic_entity);
    }
    
    Object.values(obj).forEach(val => {
        if (Array.isArray(val)) {
            val.forEach(item => {
                if (typeof item === 'string') {
                    // Check if string contains #{VAR} format (if we ever use it in YAML)
                    const match = item.match(/#\{([^}]+)\}/);
                    if (match) set.add(match[1]);
                } else {
                    scanForDynamicEntities(item, set);
                }
            });
        } else if (typeof val === 'object' && val !== null) {
            scanForDynamicEntities(val, set);
        } else if (typeof val === 'string') {
            const match = val.match(/#\{([^}]+)\}/);
            if (match) set.add(match[1]);
        }
    });
};

export const getTileDynamicEntities = (tile: Tile): string[] => {
    const entities = new Set<string>();
    scanForDynamicEntities(tile, entities);
    return Array.from(entities);
};

export const convertParsedYamlToConfig = (parsed: any): Config => {
    if (!parsed || !parsed.screens || !Array.isArray(parsed.screens)) {
      throw new Error("Invalid YAML: 'screens' array is missing.");
    }

    const pages: Page[] = parsed.screens.map((screen: any) => {
      const tiles: Tile[] = [];
      
      if (screen.tiles && Array.isArray(screen.tiles)) {
        screen.tiles.forEach((tileItem: any) => {
          // Each tile item should be a dict with one key (the type)
          const type = Object.keys(tileItem)[0];
          const props = tileItem[type];
          
          if (type && props) {
            // Transform requires_fast_refresh back to internal format
            if (props.requires_fast_refresh) {
                props.requires_fast_refresh = transformConditionLogicReverse(props.requires_fast_refresh);
            }

            // Transform condition logic in display_assets entries back to internal format
            if (Array.isArray(props.display_assets)) {
                props.display_assets = props.display_assets.map((entry: any) => {
                    if (!entry) return entry;
                    let result = { ...entry };

                    // Reverse-transform image-selection condition
                    if (result.condition != null) {
                        result.condition = transformConditionLogicReverse(result.condition);
                    }

                    // Migrate legacy 'direction' field to from/to positions.
                    if (result.animation && typeof result.animation === 'object') {
                        result.animation = _migrateAnimation(result.animation);
                    }

                    // Normalize icon value: strip surrounding double quotes added by YAML generator
                    // e.g. '"\U0000f05a"' → '\U0000f05a' (bare escape string for IconPicker)
                    if ('icon' in result) {
                        result.icon = _normalizeIconValue(result.icon);
                    }

                    return result;
                });
            }

            // Strip id() from color and size in display scripts
            if (Array.isArray(props.display)) {
                props.display = props.display.map((d: any) => {
                    if (typeof d === 'object') {
                        const scriptId = Object.keys(d)[0];
                        const params = d[scriptId];
                        const newParams = { ...params };
                        ['color', 'size'].forEach(p => {
                            if (typeof newParams[p] === 'string' && newParams[p].startsWith('id(') && newParams[p].endsWith(')')) {
                                newParams[p] = newParams[p].substring(3, newParams[p].length - 1);
                            }
                        });
                        if ('icon' in newParams) {
                            newParams.icon = _normalizeIconValue(newParams.icon);
                        }
                        return { [scriptId]: newParams };
                    }
                    return d;
                });
            }

            tiles.push({
              id: Math.random().toString(36).substr(2, 9),
              type,
              ...props
            });
          }
        });
      }

      return {
        id: screen.id || 'unknown',
        rows: screen.rows || 2,
        cols: screen.cols || 3,
        flags: screen.flags || [],
        background: Array.isArray(screen.background)
          ? screen.background.map((entry: any) => {
              if (!entry || typeof entry !== 'object') return entry;
              const result = { ...entry };
              if (result.condition != null) {
                result.condition = transformConditionLogicReverse(result.condition);
              }
              return result;
            })
          : undefined,
        time_color: screen.time_color || undefined,
        tiles
      };
    });

    // Extract dynamic entities (both runtime names and fixed entity bindings)
    const dynamicEntities = new Set<string>();
    const dynamicEntityValues: Record<string, string[]> = {};

    const normalizeFixedVals = (rawVal: any): string[] => {
        if (typeof rawVal === 'string') {
            return rawVal.includes(',')
                ? rawVal.split(',').map(s => s.trim()).filter(Boolean)
                : (rawVal.trim() ? [rawVal.trim()] : []);
        }
        if (Array.isArray(rawVal)) {
            return rawVal.map(v => (typeof v === 'string' ? v.trim() : '')).filter(Boolean);
        }
        return [];
    };

    // Preserve explicit dynamic_entity_values if present (e.g. JSON config)
    if (parsed.dynamic_entity_values && typeof parsed.dynamic_entity_values === 'object') {
        for (const [k, v] of Object.entries(parsed.dynamic_entity_values)) {
            const name = k.trim();
            if (name) {
                dynamicEntities.add(name);
                dynamicEntityValues[name] = normalizeFixedVals(v);
            }
        }
    }

    // Support top-level dynamic_entities declaration (list of strings/dicts, or mapping)
    if (parsed.dynamic_entities && Array.isArray(parsed.dynamic_entities)) {
        parsed.dynamic_entities.forEach((de: any) => {
            if (typeof de === 'string') {
                const name = de.trim();
                if (name) dynamicEntities.add(name);
            } else if (de && typeof de === 'object') {
                const keys = Object.keys(de);
                if ('name' in de && keys.every(k => k === 'name' || k === 'entities' || k === 'value')) {
                    const name = typeof de.name === 'string' ? de.name.trim() : '';
                    if (name) {
                        dynamicEntities.add(name);
                        const rawVal = 'entities' in de ? de.entities : de.value;
                        if (rawVal !== undefined && rawVal !== null) {
                            dynamicEntityValues[name] = normalizeFixedVals(rawVal);
                        }
                    }
                } else if (keys.length === 1) {
                    const name = keys[0].trim();
                    if (name) {
                        dynamicEntities.add(name);
                        const rawVal = de[keys[0]];
                        if (rawVal !== null && rawVal !== undefined) {
                            dynamicEntityValues[name] = normalizeFixedVals(rawVal);
                        }
                    }
                }
            }
        });
    } else if (parsed.dynamic_entities && typeof parsed.dynamic_entities === 'object') {
        for (const [rawKey, rawVal] of Object.entries(parsed.dynamic_entities)) {
            const name = rawKey.trim();
            if (!name) continue;
            dynamicEntities.add(name);
            if (rawVal !== null && rawVal !== undefined) {
                dynamicEntityValues[name] = normalizeFixedVals(rawVal);
            }
        }
    }

    // Recursively scan all pages and tiles for dynamic entities
    pages.forEach(p => {
        p.tiles.forEach(t => {
            scanForDynamicEntities(t, dynamicEntities);
        });
    });

    const hasFixedValues = Object.keys(dynamicEntityValues).length > 0;
    const result: Config = {
      ...parsed,
      pages,
      dynamic_entities: Array.from(dynamicEntities),
      ...(hasFixedValues ? { dynamic_entity_values: dynamicEntityValues } : {}),
      images: (parsed.images && typeof parsed.images === 'object') ? parsed.images : undefined
    };
    if (!hasFixedValues) {
        delete (result as any).dynamic_entity_values;
    }
    delete (result as any).screens;
    return result;
};

export const parseYamlToConfig = (yamlString: string): Config => {
  try {
    const parsed = yaml.load(yamlString) as any;
    return convertParsedYamlToConfig(parsed);
  } catch (e) {
    console.error("YAML Parse Error", e);
    throw e;
  }
};
