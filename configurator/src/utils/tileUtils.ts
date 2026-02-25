import { Config, Tile } from '../types';

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

  // No changes to propagate
  if (Object.keys(renames).length === 0 && removed.size === 0) {
    return { ...config, dynamic_entities: newEntities };
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

      // tile.dynamic_entry.dynamic_entity (move_page)
      if (
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

      return updated;
    }),
  }));

  return { ...config, dynamic_entities: newEntities, pages: updatedPages };
}

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
