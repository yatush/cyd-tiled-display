import { test } from 'node:test';
import assert from 'node:assert/strict';
import { iconCodeToChar } from '../src/utils/iconUtils.ts';
import { getTileNavigationTarget } from '../src/utils/tileUtils.ts';
import { validateTileBounds } from '../src/utils/tileYaml.ts';

test('iconCodeToChar decodes bare, legacy-quoted, and plain icon strings', () => {
  assert.equal(iconCodeToChar('\\U0000e286'), '\ue286');
  assert.equal(iconCodeToChar('"\\U0000ec0e"'), '\uec0e');
  assert.equal(iconCodeToChar('\ue8b8'), '\ue8b8');
  assert.equal(iconCodeToChar(''), '');
  assert.equal(iconCodeToChar(null), '');
  assert.equal(iconCodeToChar(undefined), '');
});

test('validateTileBounds checks span overflow and unplaced coordinate parity', () => {
  // Valid single-cell and spanning tiles
  assert.doesNotThrow(() => validateTileBounds({ x: 0, y: 0 }, 4, 3));
  assert.doesNotThrow(() => validateTileBounds({ x: 1, y: 2, x_span: 2, y_span: 2 }, 4, 3));
  assert.doesNotThrow(() => validateTileBounds({ x: -1, y: -1 }, 4, 3));

  // Partial negative coordinates must be rejected
  assert.throws(() => validateTileBounds({ x: -1, y: 0 }, 4, 3), /within the page grid/);
  assert.throws(() => validateTileBounds({ x: 0, y: -1 }, 4, 3), /within the page grid/);

  // Span overflow beyond grid edges must be rejected
  assert.throws(() => validateTileBounds({ x: 2, y: 0, x_span: 2 }, 4, 3), /within the page grid/);
  assert.throws(() => validateTileBounds({ x: 0, y: 3, y_span: 2 }, 4, 3), /within the page grid/);
});

test('getTileNavigationTarget returns destination for move_page and ha_action long_destination', () => {
  assert.deepEqual(
    getTileNavigationTarget({ type: 'move_page', destination: 'pref' }),
    { destination: 'pref', isLongPress: false }
  );
  assert.deepEqual(
    getTileNavigationTarget({ type: 'ha_action', long_destination: 'blinds_page' }),
    { destination: 'blinds_page', isLongPress: true }
  );
  assert.equal(getTileNavigationTarget({ type: 'ha_action' }), null);
  assert.equal(getTileNavigationTarget({ type: 'move_page', destination: '' }), null);
  assert.equal(getTileNavigationTarget({ type: 'ha_action', long_destination: '' }), null);
  assert.equal(getTileNavigationTarget({ type: 'toggle_entity', destination: 'pref' }), null);
});
