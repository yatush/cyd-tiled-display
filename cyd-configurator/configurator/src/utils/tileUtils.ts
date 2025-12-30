import { Tile } from '../types';

export const getTileLabel = (tile: Tile) => {
  if (tile.title) return tile.title;
  if (tile.label) return tile.label;
  if (tile.presentation_name) return tile.presentation_name;
  if (tile.destination) return `To: ${tile.destination}`;
  if (tile.type === 'ha_action' && tile.entities && tile.entities.length > 0) {
      const first = tile.entities[0];
      return typeof first === 'string' ? first : (first.entity || first.dynamic_entity || tile.type);
  }
  return tile.type;
};
