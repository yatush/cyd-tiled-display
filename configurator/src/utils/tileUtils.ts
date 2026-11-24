import type { Config, FixedEntityEntry, Page, Tile } from '../types';

function copyTileValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(copyTileValue);
  if (value instanceof Date) return new Date(value);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copyTileValue(item)]));
  }
  return value;
}

export function duplicateTile(tile: Tile, page: Page): Tile {
  const width = tile.x_span || 1;
  const height = tile.y_span || 1;
  let x = -1;
  let y = -1;

  for (let row = 0; row <= page.rows - height && y < 0; row++) {
    for (let col = 0; col <= page.cols - width; col++) {
      const occupied = page.tiles.some(t =>
        t.x >= 0 && t.y >= 0 &&
        col < t.x + (t.x_span || 1) && col + width > t.x &&
        row < t.y + (t.y_span || 1) && row + height > t.y
      );
      if (!occupied) {
        x = col;
        y = row;
        break;
      }
    }
  }

  const copy = { ...tile };
  for (const key of Object.keys(copy)) copy[key] = copyTileValue(copy[key]);
  return { ...copy, id: Math.random().toString(36).substr(2, 9), x, y };
}

/**
 * Given an old and new list of dynamic entity names, build a map of renames
 * (old name → new name) and a set of removed names, then apply those changes
 * to every tile in every page so that `dynamic_entity` references stay in sync.
 *
 * Rename detection: if both lists have the same length, elements that differ at
 * the same index are treated as renames.
 * Removal detection: names present in the old list but absent from the new list
 * are cleared (set to '') in all referencing tiles.
 */
export function applyDynamicEntityListChange(
  config: Config,
  newEntities: string[]
): Config {
  const oldEntities = config.dynamic_entities || [];

  // Build rename map and removed set
  const renames: Record<string, string> = {};
  const removed = new Set<string>();

  if (newEntities.length === oldEntities.length) {
    // Same length → positional renames, clears, or re-populates
    for (let i = 0; i < oldEntities.length; i++) {
      if (oldEntities[i] !== newEntities[i] && oldEntities[i] !== '' && newEntities[i] !== '') {
        renames[oldEntities[i]] = newEntities[i];
      } else if (oldEntities[i] !== '' && newEntities[i] === '') {
        // Field was cleared → treat as removal so tile references are cleared too
        removed.add(oldEntities[i]);
      } else if (oldEntities[i] === '' && newEntities[i] !== '') {
        // Field was re-populated after being cleared: propagate to any tile with ''
        renames[''] = newEntities[i];
      }
    }
  } else if (newEntities.length < oldEntities.length) {
    // Shorter → find removed names
    const newSet = new Set(newEntities);
    for (const e of oldEntities) {
      if (e !== '' && !newSet.has(e)) {
        removed.add(e);
      }
    }
  }

  // Sync dynamic_entity_values keys across renames and removals
  let nextFixedValues = config.dynamic_entity_values
    ? { ...config.dynamic_entity_values }
    : undefined;
  if (nextFixedValues) {
    const updatedFixed: Record<string, FixedEntityEntry[]> = {};
    const validSet = new Set(newEntities.filter(Boolean));
    for (const [key, vals] of Object.entries(nextFixedValues)) {
      if (removed.has(key)) continue;
      const mappedKey = renames[key] !== undefined ? renames[key] : key;
      if (mappedKey && validSet.has(mappedKey)) {
        updatedFixed[mappedKey] = vals;
      }
    }
    nextFixedValues = Object.keys(updatedFixed).length > 0 ? updatedFixed : undefined;
  }

  const withFixed = (base: Config): Config => {
    const next = { ...base };
    if (nextFixedValues) {
      next.dynamic_entity_values = nextFixedValues;
    } else {
      delete next.dynamic_entity_values;
    }
    return next;
  };

  // No changes to propagate
  if (Object.keys(renames).length === 0 && removed.size === 0) {
    return withFixed({ ...config, dynamic_entities: newEntities });
  }

  const patchValue = (val: string): string => {
    if (renames[val] !== undefined) return renames[val];
    if (removed.has(val)) return '';
    return val;
  };

  const updatedPages = config.pages.map(page => ({
    ...page,
    tiles: page.tiles.map(tile => {
      let updated = { ...tile };

      // tile.dynamic_entity (toggle_entity, cycle_entity)
      if (typeof tile.dynamic_entity === 'string' && tile.dynamic_entity !== '') {
        updated.dynamic_entity = patchValue(tile.dynamic_entity);
      }
      if (typeof tile.long_dynamic_entity === 'string' && tile.long_dynamic_entity !== '') {
        updated.long_dynamic_entity = patchValue(tile.long_dynamic_entity);
      }

      // tile.dynamic_entry (move_page): single object or array of objects
      if (Array.isArray(tile.dynamic_entry)) {
        updated.dynamic_entry = tile.dynamic_entry.map((entry: any) =>
          entry &&
          typeof entry === 'object' &&
          typeof entry.dynamic_entity === 'string' &&
          entry.dynamic_entity !== ''
            ? { ...entry, dynamic_entity: patchValue(entry.dynamic_entity) }
            : entry
        );
      } else if (
        tile.dynamic_entry &&
        typeof tile.dynamic_entry === 'object' &&
        typeof tile.dynamic_entry.dynamic_entity === 'string' &&
        tile.dynamic_entry.dynamic_entity !== ''
      ) {
        updated.dynamic_entry = {
          ...tile.dynamic_entry,
          dynamic_entity: patchValue(tile.dynamic_entry.dynamic_entity),
        };
      }

      // tile.activation_var.dynamic_entity (common field, applies to all tile types)
      if (
        tile.activation_var &&
        typeof tile.activation_var === 'object' &&
        typeof tile.activation_var.dynamic_entity === 'string' &&
        tile.activation_var.dynamic_entity !== ''
      ) {
        updated.activation_var = {
          ...tile.activation_var,
          dynamic_entity: patchValue(tile.activation_var.dynamic_entity),
        };
      }

      // tile.entities[i].dynamic_entity (ha_action, title — entity list items)
      if (Array.isArray(tile.entities)) {
        const patchedEntities = tile.entities.map((entry: any) => {
          if (
            entry &&
            typeof entry === 'object' &&
            typeof entry.dynamic_entity === 'string' &&
            entry.dynamic_entity !== ''
          ) {
            return { ...entry, dynamic_entity: patchValue(entry.dynamic_entity) };
          }
          return entry;
        });
        // Only replace the array if something actually changed
        if (patchedEntities.some((e: any, i: number) => e !== tile.entities[i])) {
          updated.entities = patchedEntities;
        }
      }

      // tile.options[i].dynamic_entity (cycle_entity fixed dynamic entity options)
      if (Array.isArray(tile.options)) {
        const patchedOptions = tile.options.map((entry: any) => {
          if (
            entry &&
            typeof entry === 'object' &&
            typeof entry.dynamic_entity === 'string' &&
            entry.dynamic_entity !== ''
          ) {
            return { ...entry, dynamic_entity: patchValue(entry.dynamic_entity) };
          }
          return entry;
        });
        if (patchedOptions.some((o: any, i: number) => o !== tile.options[i])) {
          updated.options = patchedOptions;
        }
      }

      return updated;
    }),
  }));

  return withFixed({ ...config, dynamic_entities: newEntities, pages: updatedPages });
}

/**
 * Set or clear fixed Home Assistant entity value(s) for a declared dynamic entity.
 * Passing `null` switches the variable back to a runtime (unfixed) dynamic entity.
 */
export function updateDynamicEntityFixedValues(
  config: Config,
  varName: string,
  fixedValues: FixedEntityEntry[] | null
): Config {
  const name = varName.trim();
  if (!name) return config;

  const nextMap: Record<string, FixedEntityEntry[]> = { ...(config.dynamic_entity_values || {}) };
  if (fixedValues === null) {
    delete nextMap[name];
  } else {
    nextMap[name] = [...fixedValues];
  }

  const nextConfig: Config = { ...config };
  if (Object.keys(nextMap).length > 0) {
    nextConfig.dynamic_entity_values = nextMap;
  } else {
    delete nextConfig.dynamic_entity_values;
  }
  return nextConfig;
}

export const getTileNavigationTarget = (
  tile: { type: string; destination?: unknown; long_destination?: unknown }
): { destination: string; isLongPress: boolean } | null => {
  if (tile.type === 'move_page' && typeof tile.destination === 'string' && tile.destination) {
    return { destination: tile.destination, isLongPress: false };
  }
  if (tile.type === 'ha_action' && typeof tile.long_destination === 'string' && tile.long_destination) {
    return { destination: tile.long_destination, isLongPress: true };
  }
  return null;
};

export const getTileLabel = (tile: Tile): string => {
  if (typeof tile.title === 'string') return tile.title;
  if (typeof tile.label === 'string') return tile.label;
  if (typeof tile.presentation_name === 'string') return tile.presentation_name;
  if (typeof tile.destination === 'string') return `To: ${tile.destination}`;
  
  if (tile.type === 'ha_action') {
      if (tile.perform && Array.isArray(tile.perform) && tile.perform.length > 0) {
          const p = tile.perform[0];
          if (typeof p === 'string') return p;
          if (p && typeof p === 'object') return Object.keys(p)[0] || tile.type;
      }
      if (tile.location_perform && Array.isArray(tile.location_perform) && tile.location_perform.length > 0) {
          const p = tile.location_perform[0];
          if (typeof p === 'string') return p;
          if (p && typeof p === 'object') return Object.keys(p)[0] || tile.type;
      }
      
      if (tile.entities && Array.isArray(tile.entities) && tile.entities.length > 0) {
          const first = tile.entities[0];
          if (typeof first === 'string') return first;
          if (first && typeof first === 'object') {
              if (typeof first.entity === 'string') return first.entity;
              if (Array.isArray(first.entity) && typeof first.entity[0] === 'string') return first.entity[0];
              if (typeof first.dynamic_entity === 'string') return first.dynamic_entity;
          }
          return tile.type;
      }
  }
  return tile.type;
};
