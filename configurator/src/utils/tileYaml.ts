import yaml from 'js-yaml';
import type { Page, Tile } from '../types';
import { unknownPageFields, unknownTileFields } from './yamlGenerator.ts';
import { convertParsedYamlToConfig } from './yamlParser.ts';

const VALID_PAGE_FLAGS = new Set(['BASE', 'TEMPORARY', 'FAST_REFRESH', 'OMIT_TIME_WIFI']);
const VALID_BACKGROUND_KEYS = new Set(['color', 'image', 'condition']);

const isMapping = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

function validateCondition(value: unknown): void {
  if (typeof value === 'string') return;
  if (Array.isArray(value)) {
    value.forEach(validateCondition);
    return;
  }
  if (!isMapping(value)) throw new Error('Conditions must be strings or mappings.');
  if ('operator' in value && typeof value.operator !== 'string') {
    throw new Error('A condition operator must be a string.');
  }
  for (const key of ['or', 'and']) {
    if (key in value) {
      if (!Array.isArray(value[key])) throw new Error(`Condition ${key} must be a list.`);
      value[key].forEach(validateCondition);
    }
  }
  if ('not' in value) validateCondition(value.not);
  if ('conditions' in value) validateCondition(value.conditions);
}

function rejectCycles(value: unknown, ancestors = new Set<object>()): void {
  if (!value || typeof value !== 'object') return;
  if (ancestors.has(value)) throw new Error('Recursive YAML aliases are not supported.');
  ancestors.add(value);
  Object.values(value).forEach(item => rejectCycles(item, ancestors));
  ancestors.delete(value);
}

function loadDedentedYaml(text: string): unknown {
  const lines = text.split('\n');
  const indents = lines.filter(line => line.trim()).map(line => line.match(/^ */)![0].length);
  const indent = indents.length ? Math.min(...indents) : 0;
  const normalized = lines.map(line => line.trim() ? line.slice(indent) : '').join('\n');

  try {
    return yaml.load(normalized);
  } catch (error) {
    if (error instanceof yaml.YAMLException && error.mark) {
      const offset = lines[error.mark.line]?.trim() ? indent : 0;
      throw new Error(`Line ${error.mark.line + 1}, column ${error.mark.column + offset + 1}: ${error.reason}`);
    }
    throw error;
  }
}

function validateTileMapping(type: string, props: Record<string, unknown>): void {
  rejectCycles(props);
  const unknown = unknownTileFields(props, type);
  if (unknown.length) throw new Error(`Unsupported field(s) for ${type}: ${unknown.join(', ')}`);
  for (const key of ['x', 'y', 'x_span', 'y_span']) {
    const value = props[key];
    if ((key === 'x' || key === 'y' || value !== undefined) &&
        (typeof value !== 'number' || !Number.isInteger(value) || value < (key.endsWith('_span') ? 1 : -1))) {
      throw new Error(`${key} must be ${key.endsWith('_span') ? 'a positive integer' : 'an integer of at least -1'}.`);
    }
  }
  for (const key of ['entities', 'display', 'display_assets', 'options']) {
    const value = props[key];
    if (value !== undefined && !Array.isArray(value)) {
      throw new Error(`${key} must be a list.`);
    }
  }
  if (Array.isArray(props.entities) &&
      props.entities.some(item => typeof item !== 'string' && !isMapping(item))) {
    throw new Error('Each entity must be a string or mapping.');
  }
  if (Array.isArray(props.display) && props.display.some(item =>
    typeof item !== 'string' && (!isMapping(item) || Object.keys(item).length !== 1 ||
      !isMapping(Object.values(item)[0])))) {
    throw new Error('Each display entry must be a script name or a single script mapping with parameters.');
  }
  for (const key of ['display_assets', 'options']) {
    const value = props[key];
    if (Array.isArray(value) && value.some(item => !isMapping(item))) {
      throw new Error(`Each ${key} entry must be a mapping.`);
    }
  }
  for (const key of ['dynamic_entity', 'destination', 'long_destination', 'long_dynamic_entity', 'presentation_name', 'display_page_if_no_entity']) {
    if (props[key] !== undefined && typeof props[key] !== 'string') {
      throw new Error(`${key} must be a string.`);
    }
  }
  for (const key of ['initially_chosen', 'reset_on_leave']) {
    if (props[key] !== undefined && typeof props[key] !== 'boolean') {
      throw new Error(`${key} must be a boolean.`);
    }
  }
  if (props.activation_var !== undefined && !isMapping(props.activation_var)) {
    throw new Error('activation_var must be a mapping.');
  }
  if (
    props.dynamic_entry !== undefined &&
    !isMapping(props.dynamic_entry) &&
    (!Array.isArray(props.dynamic_entry) || props.dynamic_entry.some(item => !isMapping(item)))
  ) {
    throw new Error('dynamic_entry must be a mapping or a list of mappings.');
  }
  if (props.dynamic_entry !== undefined) {
    const entries = Array.isArray(props.dynamic_entry) ? props.dynamic_entry : [props.dynamic_entry];
    const seenDynamicEntities = new Set<string>();
    for (const item of entries) {
      const de = item.dynamic_entity;
      if (typeof de === 'string' && de.trim() !== '') {
        if (seenDynamicEntities.has(de)) {
          throw new Error(`Duplicate dynamic_entity "${de}" in dynamic_entry list.`);
        }
        seenDynamicEntities.add(de);
      }
      if (Array.isArray(item.value)) {
        const seenValues = new Set<string>();
        for (const val of item.value) {
          if (typeof val === 'string' && val.trim() !== '') {
            if (seenValues.has(val)) {
              throw new Error(`Duplicate entity "${val}" in dynamic_entry value list.`);
            }
            seenValues.add(val);
          }
        }
      }
    }
  }
  for (const key of ['fill_color', 'border_color', 'border_width', 'border_radius']) {
    const value = props[key];
    if (value === undefined) continue;
    const scalarType = key.endsWith('color') ? 'string' : 'number';
    if (typeof value !== scalarType && (!Array.isArray(value) || value.some(item => !isMapping(item)))) {
      throw new Error(`${key} must be a ${scalarType} or a list of mappings.`);
    }
    const itemKey = scalarType === 'string' ? 'color' : 'value';
    if (Array.isArray(value) && value.some(item => typeof item[itemKey] !== scalarType)) {
      throw new Error(`Each ${key} entry must contain a ${scalarType} ${itemKey}.`);
    }
  }
  if (props.requires_fast_refresh !== undefined) validateCondition(props.requires_fast_refresh);
  if (Array.isArray(props.display_assets)) {
    for (const entry of props.display_assets) {
      if (!isMapping(entry)) continue;
      if (entry.condition !== undefined) validateCondition(entry.condition);
      for (const key of ['image', 'icon', 'icon_color', 'icon_size']) {
        if (entry[key] !== undefined && typeof entry[key] !== 'string') {
          throw new Error(`display_assets ${key} must be a string.`);
        }
      }
      if (entry.animation !== undefined) {
        if (!isMapping(entry.animation)) throw new Error('Animation must be a mapping.');
        if (entry.animation.steps !== undefined &&
            (!Array.isArray(entry.animation.steps) || entry.animation.steps.some(step => !isMapping(step)))) {
          throw new Error('Animation steps must be a list of mappings.');
        }
      }
    }
  }
}

export function parseTileYaml(text: string, id: string): Tile {
  let parsed = loadDedentedYaml(text);

  if (Array.isArray(parsed)) {
    if (parsed.length !== 1) throw new Error('Enter exactly one tile.');
    parsed = parsed[0];
  }
  if (!isMapping(parsed) || Object.keys(parsed).length !== 1) {
    throw new Error('Enter one tile as a mapping with its type as the key.');
  }
  const [type, props] = Object.entries(parsed)[0];
  if (!isMapping(props)) throw new Error('Tile properties must be a mapping.');
  validateTileMapping(type, props);

  const config = convertParsedYamlToConfig({
    screens: [{ id: 'editor', rows: 1, cols: 1, tiles: [{ [type]: props }] }]
  });
  return { ...config.pages[0].tiles[0], id };
}

export function validateTileBounds(
  tile: { x: number; y: number; x_span?: number; y_span?: number },
  rows: number,
  cols: number
): void {
  const tx = tile.x;
  const ty = tile.y;
  const txSpan = tile.x_span ?? 1;
  const tySpan = tile.y_span ?? 1;
  if ((tx < 0) !== (ty < 0) || (tx >= 0 && ty >= 0 && (tx + txSpan > cols || ty + tySpan > rows))) {
    throw new Error('Each tile position must be within the page grid (or -1, -1 for unplaced tiles).');
  }
}

export function parsePageYaml(text: string, currentPage: Page, existingPageIds: string[] = []): Page {
  let parsed = loadDedentedYaml(text);

  if (isMapping(parsed) && Object.keys(parsed).length === 1 && 'screens' in parsed && Array.isArray(parsed.screens)) {
    parsed = parsed.screens;
  }
  if (Array.isArray(parsed)) {
    if (parsed.length !== 1) throw new Error('Enter exactly one page.');
    parsed = parsed[0];
  }
  if (!isMapping(parsed)) {
    throw new Error('Enter one page as a mapping.');
  }

  rejectCycles(parsed);
  const unknown = unknownPageFields(parsed);
  if (unknown.length) {
    throw new Error(`Unsupported field(s) for page: ${unknown.join(', ')}`);
  }

  if (typeof parsed.id !== 'string' || !parsed.id.trim()) {
    throw new Error('Page id must be a non-empty string.');
  }
  if (parsed.id !== currentPage.id && existingPageIds.includes(parsed.id)) {
    throw new Error(`Page ID "${parsed.id}" already exists.`);
  }

  for (const key of ['rows', 'cols'] as const) {
    const val = parsed[key];
    if (val !== undefined && (typeof val !== 'number' || !Number.isInteger(val) || val < 1)) {
      throw new Error(`${key} must be a positive integer.`);
    }
  }
  const rows = (parsed.rows as number | undefined) ?? currentPage.rows ?? 2;
  const cols = (parsed.cols as number | undefined) ?? currentPage.cols ?? 3;

  if (parsed.flags !== undefined) {
    if (!Array.isArray(parsed.flags) || parsed.flags.some(f => typeof f !== 'string')) {
      throw new Error('flags must be a list of flag strings.');
    }
    for (const flag of parsed.flags) {
      if (!VALID_PAGE_FLAGS.has(flag)) {
        throw new Error(`Invalid page flag "${flag}". Valid flags: ${Array.from(VALID_PAGE_FLAGS).join(', ')}.`);
      }
    }
    if (parsed.flags.includes('BASE') && parsed.flags.includes('TEMPORARY')) {
      throw new Error('A page cannot have both BASE and TEMPORARY flags.');
    }
  }

  if (parsed.time_color !== undefined && (typeof parsed.time_color !== 'string' || !parsed.time_color.trim())) {
    throw new Error('time_color must be a non-empty string.');
  }

  if (parsed.background !== undefined) {
    if (!Array.isArray(parsed.background) || parsed.background.some(item => !isMapping(item))) {
      throw new Error('background must be a list of mappings.');
    }
    for (const entry of parsed.background) {
      const extraBgKeys = Object.keys(entry).filter(k => !VALID_BACKGROUND_KEYS.has(k));
      if (extraBgKeys.length) {
        throw new Error(`Unsupported background field(s): ${extraBgKeys.join(', ')}.`);
      }
      const hasColor = 'color' in entry;
      const hasImage = 'image' in entry;
      if (hasColor && hasImage) {
        throw new Error('A background entry cannot have both color and image.');
      }
      if (!hasColor && !hasImage) {
        throw new Error('Each background entry must specify either color or image.');
      }
      if (hasColor && (typeof entry.color !== 'string' || !entry.color.trim())) {
        throw new Error('background color must be a non-empty string.');
      }
      if (hasImage && (typeof entry.image !== 'string' || !entry.image.trim())) {
        throw new Error('background image must be a non-empty string.');
      }
      if (entry.condition !== undefined) {
        validateCondition(entry.condition);
      }
    }
  }

  if (parsed.tiles !== undefined && !Array.isArray(parsed.tiles)) {
    throw new Error('tiles must be a list.');
  }
  const rawTiles = (parsed.tiles as unknown[] | undefined) ?? [];
  for (const item of rawTiles) {
    if (!isMapping(item) || Object.keys(item).length !== 1) {
      throw new Error('Each tile entry must be a mapping with its type as the key.');
    }
    const [tileType, tileProps] = Object.entries(item)[0];
    if (!isMapping(tileProps)) {
      throw new Error('Tile properties must be a mapping.');
    }
    validateTileMapping(tileType, tileProps);
    validateTileBounds(
      {
        x: tileProps.x as number,
        y: tileProps.y as number,
        x_span: tileProps.x_span as number | undefined,
        y_span: tileProps.y_span as number | undefined,
      },
      rows,
      cols
    );
  }

  const convertedPage = convertParsedYamlToConfig({
    screens: [{ ...parsed, rows, cols, tiles: rawTiles }]
  }).pages[0];

  return {
    ...convertedPage,
    tiles: convertedPage.tiles.map((tile, idx) => ({
      ...tile,
      id: currentPage.tiles[idx]?.id ?? tile.id,
    })),
  };
}
