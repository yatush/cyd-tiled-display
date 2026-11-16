import { test } from 'node:test';
import assert from 'node:assert/strict';
import { duplicateTile } from '../src/utils/tileUtils.ts';

test('duplicates all settings independently into a free area that fits the span', () => {
  const tile = { id: 'original', type: 'function', x: 0, y: 0, x_span: 2, display: [{ text: 'Hello', optional: undefined }] };
  const page = { id: 'main', rows: 2, cols: 3, tiles: [tile, { id: 'other', type: 'function', x: 1, y: 1 }] };
  const copy = duplicateTile(tile, page);
  assert.deepEqual({ ...copy, id: tile.id, x: tile.x, y: tile.y }, tile);
  assert.notEqual(copy.id, tile.id);
  assert.deepEqual([copy.x, copy.y], [-1, -1]);
  copy.display[0].text = 'Changed';
  assert.equal(tile.display[0].text, 'Hello');

  page.tiles.pop();
  const placed = duplicateTile(tile, page);
  assert.deepEqual([placed.x, placed.y], [0, 1]);
});

test('does not place a spanning duplicate outside the grid or over a tile', () => {
  const tile = { id: 'original', type: 'function', x: 1, y: 0, x_span: 2 };
  const page = { id: 'main', rows: 1, cols: 3, tiles: [tile] };
  const copy = duplicateTile(tile, page);
  assert.deepEqual([copy.x, copy.y], [-1, -1]);
});
