import yaml from 'js-yaml';
import { Config, Page, Tile } from '../types';

/** Map legacy 'direction' string to from/to position pair. */
const _DIRECTION_TO_FROM_TO: Record<string, { from: [number,number]; to: [number,number] }> = {
    none:       { from: [0.5, 0.5], to: [0.5, 0.5] },
    left_right: { from: [0.0, 0.5], to: [1.0, 0.5] },
    right_left: { from: [1.0, 0.5], to: [0.0, 0.5] },
    up_down:    { from: [0.5, 0.0], to: [0.5, 1.0] },
    down_up:    { from: [0.5, 1.0], to: [0.5, 0.0] },
};

/** Named position string → [x, y] fraction tuple. */
const _NAMED_POSITIONS: Record<string, [number, number]> = {
    top_left:      [0.0, 0.0], top_middle:    [0.5, 0.0], top_right:     [1.0, 0.0],
    center_left:   [0.0, 0.5], center_middle: [0.5, 0.5], center_right:  [1.0, 0.5],
    bottom_left:   [0.0, 1.0], bottom_middle: [0.5, 1.0], bottom_right:  [1.0, 1.0],
};

function _normalizePos(pos: any): [number, number] {
    if (Array.isArray(pos) && pos.length === 2 && typeof pos[0] === 'number') return [pos[0], pos[1]];
    if (typeof pos === 'string' && _NAMED_POSITIONS[pos]) return _NAMED_POSITIONS[pos];
    return [0.5, 0.5]; // default to center
}

/** Migrate an animation object (or step within it) from legacy direction → from/to, and normalize positions to [x,y]. */
function _migrateStep(step: any): any {
    if (!step || typeof step !== 'object') return step;
    if ('direction' in step) {
        const { direction, ...rest } = step;
        const { from, to } = _DIRECTION_TO_FROM_TO[direction] ?? { from: [0.5, 0.5] as [number,number], to: [0.5, 0.5] as [number,number] };
        return { from, to, ...rest };
    }
    // Normalize string/array positions
    return {
        ...step,
        from: _normalizePos(step.from),
        to:   _normalizePos(step.to),
    };
}

/** Migrate a full animation config (single-step or multi-step) from legacy to from/to. */
function _migrateAnimation(anim: any): any {
    if (!anim || typeof anim !== 'object') return anim;
    if (Array.isArray(anim.steps)) {
        return { steps: anim.steps.map(_migrateStep) };
    }
    return _migrateStep(anim);
}

const transformConditionLogicReverse = (value: any): any => {
    if (typeof value === 'string') return value;
    if (typeof value === 'object' && value !== null) {
        if (value.operator && value.conditions) {
            const op = value.operator.toUpperCase();
            const conditions = value.conditions.map(transformConditionLogicReverse);
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

            // Transform condition logic in images entries back to internal format
            if (Array.isArray(props.images)) {
                props.images = props.images.map((entry: any) => {
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
                        if (typeof newParams.icon === 'string' && newParams.icon.startsWith('"') && newParams.icon.endsWith('"')) {
                            newParams.icon = newParams.icon.substring(1, newParams.icon.length - 1);
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
        tiles
      };
    });

    // Extract dynamic entities from tiles to populate the list
    const dynamicEntities = new Set<string>();

    // Support top-level dynamic_entities declaration if present
    if (parsed.dynamic_entities && Array.isArray(parsed.dynamic_entities)) {
        parsed.dynamic_entities.forEach((de: any) => {
            if (typeof de === 'string') dynamicEntities.add(de);
        });
    }

    // Recursively scan all pages and tiles for dynamic entities
    pages.forEach(p => {
        p.tiles.forEach(t => {
            scanForDynamicEntities(t, dynamicEntities);
        });
    });

    const result = {
      ...parsed,
      pages,
      dynamic_entities: Array.from(dynamicEntities),
      images: (parsed.images && typeof parsed.images === 'object') ? parsed.images : undefined
    };
    delete result.screens;
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
