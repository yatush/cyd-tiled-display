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

export const parseYamlToConfig = (yamlString: string): Config => {
  try {
    const parsed = yaml.load(yamlString) as any;
    
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
    pages.forEach(p => {
        p.tiles.forEach(t => {
            // Check common fields for dynamic entities
            if (t.dynamic_entity) dynamicEntities.add(t.dynamic_entity);
            
            // Check entities list
            if (Array.isArray(t.entities)) {
                t.entities.forEach((e: any) => {
                    if (typeof e === 'object' && e.dynamic_entity) {
                        dynamicEntities.add(e.dynamic_entity);
                    }
                });
            }
            
            // Check dynamic_entry in move_page
            if (t.dynamic_entry && t.dynamic_entry.dynamic_entity) {
                dynamicEntities.add(t.dynamic_entry.dynamic_entity);
            }
        });
    });

    return {
      pages,
      dynamic_entities: Array.from(dynamicEntities)
    };

  } catch (e) {
    console.error("YAML Parse Error", e);
    throw e;
  }
};
