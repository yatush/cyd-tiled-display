import { Tile } from '../types';

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
