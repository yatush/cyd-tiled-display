import yaml from 'js-yaml';
import type { Tile } from '../types';
import { unknownTileFields } from './yamlGenerator.ts';
import { convertParsedYamlToConfig } from './yamlParser.ts';

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

export function parseTileYaml(text: string, id: string): Tile {
  const lines = text.split('\n');
  const indents = lines.filter(line => line.trim()).map(line => line.match(/^ */)![0].length);
  const indent = indents.length ? Math.min(...indents) : 0;
  const normalized = lines.map(line => line.trim() ? line.slice(indent) : '').join('\n');

  let parsed: unknown;
  try {
    parsed = yaml.load(normalized);
  } catch (error) {
    if (error instanceof yaml.YAMLException && error.mark) {
      const offset = lines[error.mark.line]?.trim() ? indent : 0;
      throw new Error(`Line ${error.mark.line + 1}, column ${error.mark.column + offset + 1}: ${error.reason}`);
    }
    throw error;
  }

  if (Array.isArray(parsed)) {
    if (parsed.length !== 1) throw new Error('Enter exactly one tile.');
    parsed = parsed[0];
  }
  if (!isMapping(parsed) || Object.keys(parsed).length !== 1) {
    throw new Error('Enter one tile as a mapping with its type as the key.');
  }
  const [type, props] = Object.entries(parsed)[0];
  if (!isMapping(props)) throw new Error('Tile properties must be a mapping.');
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
    for (const key of ['activation_var', 'dynamic_entry']) {
      if (props[key] !== undefined && !isMapping(props[key])) {
        throw new Error(`${key} must be a mapping.`);
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

  const config = convertParsedYamlToConfig({
    screens: [{ id: 'editor', rows: 1, cols: 1, tiles: [{ [type]: props }] }]
  });
  return { ...config.pages[0].tiles[0], id };
}
