import yaml from 'js-yaml';
import { Config } from '../types';

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

export const generateYaml = (config: Config, includeIds: boolean = false) => {
    // Convert internal model to YAML structure expected by Python script
    const screens = config.pages.map(page => ({
      id: page.id,
      rows: page.rows,
      cols: page.cols,
      flags: page.flags && page.flags.length > 0 ? page.flags : undefined,
      tiles: page.tiles
        .filter(tile => tile.x < page.cols && tile.y < page.rows)
        .map(({ id, ...rest }) => {
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
        return { [type]: tile };
      })
    }));
    
    const yamlString = yaml.dump({ 
        screens,
        dynamic_entities: config.dynamic_entities && config.dynamic_entities.length > 0 ? config.dynamic_entities : undefined
    }, { lineWidth: -1, noCompatMode: true, sortKeys: false });
    // Ensure icons are formatted as '"\U..."' for ESPHome compatibility
    return yamlString.replace(/icon:\s*['"]?(\\U[0-9a-fA-F]+)['"]?/g, "icon: '\"$1\"'");
};
