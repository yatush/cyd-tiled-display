import yaml from 'js-yaml';
import { Config, Page, Tile } from '../types';

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
      dynamic_entities: Array.from(dynamicEntities)
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
