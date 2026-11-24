import { useState } from 'react';
import { Trash2, Plus, Bluetooth, Settings2 } from 'lucide-react';
import { BleFanConfig, FixedEntityEntry, HaEntity, TuyaBleCandidate } from '../types';
import {
  findCandidateForEntity,
  findConfiguredBleFan,
  normalizeEntityId,
  toggleBleFanForEntity,
  upsertBleFan,
} from '../utils/bleFanUtils';

export interface BleFanProps {
  bleFans?: BleFanConfig[];
  tuyaBleCandidates?: TuyaBleCandidate[];
  onUpdateBleFans?: (next: BleFanConfig[]) => void;
}

export const BleFanToggle = ({
  entityId,
  bleFans = [],
  tuyaBleCandidates = [],
  onUpdateBleFans,
}: {
  entityId: string;
} & BleFanProps) => {
  const [showDetails, setShowDetails] = useState(false);
  if (!onUpdateBleFans) return null;

  const norm = normalizeEntityId(entityId);
  if (!norm) return null;

  const candidate = findCandidateForEntity(norm, tuyaBleCandidates);
  const configured = findConfiguredBleFan(norm, bleFans);
  const isFanEntity = norm.startsWith('fan.');

  if (!candidate && !configured && !isFanEntity) {
    return null;
  }

  const isChecked = Boolean(configured);
  const missingCreds = isChecked && (!configured?.device_id?.trim() || !configured?.local_key?.trim());
  const companionLight = configured?.light_entity_id || candidate?.light_entity_id || '';
  const companionFan = configured?.fan_entity_id || candidate?.fan_entity_id || '';

  return (
    <div className="mt-1 px-1.5 py-1 rounded bg-blue-50/70 border border-blue-100 text-[11px]">
      <div className="flex items-center justify-between gap-1.5">
        <label className="flex items-center gap-1.5 cursor-pointer select-none text-blue-800 font-medium">
          <input
            type="checkbox"
            checked={isChecked}
            onChange={e => {
              const next = toggleBleFanForEntity(bleFans, norm, e.target.checked, candidate);
              onUpdateBleFans(next);
              if (e.target.checked && !candidate) {
                setShowDetails(true);
              }
            }}
            className="rounded border-blue-300 text-blue-600 focus:ring-blue-500"
          />
          <Bluetooth size={11} className="text-blue-600 flex-shrink-0" />
          <span>Control via BLE</span>
        </label>
        <div className="flex items-center gap-1">
          {companionLight && companionFan && (
            <span
              className="text-[10px] px-1 py-0.2 rounded bg-blue-100 text-blue-700"
              title={`Routes both ${companionFan} and ${companionLight} over BLE`}
            >
              fan + light
            </span>
          )}
          {isChecked && (
            <button
              type="button"
              onClick={() => setShowDetails(s => !s)}
              className={`p-0.5 rounded hover:bg-blue-100 ${missingCreds ? 'text-amber-600' : 'text-blue-600'}`}
              title="Edit BLE credentials"
            >
              <Settings2 size={12} />
            </button>
          )}
        </div>
      </div>

      {isChecked && (showDetails || missingCreds) && configured && (
        <div className="mt-1.5 pt-1.5 border-t border-blue-100 space-y-1">
          {missingCreds && (
            <div className="text-[10px] text-amber-700 font-medium">
              Enter Tuya device_id &amp; local_key (auto-filled when tuya_local is present in HA).
            </div>
          )}
          <div className="grid grid-cols-2 gap-1">
            <input
              type="text"
              value={configured.device_id}
              onChange={e => onUpdateBleFans(upsertBleFan(bleFans, { ...configured, device_id: e.target.value }))}
              placeholder="Device ID"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.local_key}
              onChange={e => onUpdateBleFans(upsertBleFan(bleFans, { ...configured, local_key: e.target.value }))}
              placeholder="Local Key"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.product_id || ''}
              onChange={e => onUpdateBleFans(upsertBleFan(bleFans, { ...configured, product_id: e.target.value }))}
              placeholder="Product ID (optional)"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.mac_address || ''}
              onChange={e => onUpdateBleFans(upsertBleFan(bleFans, { ...configured, mac_address: e.target.value }))}
              placeholder="BLE MAC (auto-discover)"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
          </div>
          <input
            type="text"
            value={configured.light_entity_id || ''}
            onChange={e => onUpdateBleFans(upsertBleFan(bleFans, { ...configured, light_entity_id: e.target.value }))}
            placeholder="Companion light entity (e.g. light.office_fan_light)"
            className="w-full border rounded px-1 py-0.5 text-[10px] bg-white"
          />
        </div>
      )}
    </div>
  );
};

export const EntityListInput = ({
  label,
  values,
  onChange,
  haEntities,
  bleFans,
  tuyaBleCandidates,
  onUpdateBleFans,
}: {
  label: string,
  values: string[],
  onChange: (v: string[]) => void,
  haEntities?: HaEntity[]
} & BleFanProps) => {
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);
  const listId = `ha-entities-list-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="mb-2">
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}
      <div className="space-y-1">
        {safeValues.map((v, i) => (
          <div key={i}>
            <div className="flex gap-1">
              <input
                type="text"
                value={v}
                onChange={e => {
                  const newValues = [...safeValues];
                  newValues[i] = e.target.value;
                  onChange(newValues);
                }}
                list={listId}
                className="flex-1 border rounded p-1 text-sm"
              />
              <button
                onClick={() => onChange(safeValues.filter((_, idx) => idx !== i))}
                className="text-red-500 hover:bg-red-50 p-1 rounded"
              >
                <Trash2 size={14} />
              </button>
            </div>
            <BleFanToggle
              entityId={v}
              bleFans={bleFans}
              tuyaBleCandidates={tuyaBleCandidates}
              onUpdateBleFans={onUpdateBleFans}
            />
          </div>
        ))}
        <datalist id={listId}>
          {haEntities?.map(e => (
            <option key={e.entity_id} value={e.entity_id}>
              {e.friendly_name && e.friendly_name !== e.entity_id ? e.friendly_name : null}
            </option>
          ))}
        </datalist>
        <button
          onClick={() => onChange([...safeValues, ''])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Entity
        </button>
      </div>
    </div>
  );
};

export const DynamicEntitiesEditor = ({
  entities,
  fixedValues = {},
  onChange,
  onFixedChange,
  haEntities,
  bleFans,
  tuyaBleCandidates,
  onUpdateBleFans,
}: {
  entities: string[];
  fixedValues?: Record<string, FixedEntityEntry[]>;
  onChange: (v: string[]) => void;
  onFixedChange?: (varName: string, values: FixedEntityEntry[] | null) => void;
  haEntities?: HaEntity[];
} & BleFanProps) => {
  const safeEntities = Array.isArray(entities) ? entities : (entities ? [entities] : []);
  const listId = `ha-dyn-fixed-${Math.random().toString(36).substr(2, 9)}`;

  const getEntryParts = (entry: FixedEntityEntry): { entity: string; label: string } => {
    if (typeof entry === 'string') return { entity: entry, label: '' };
    return { entity: entry?.entity || '', label: entry?.label || '' };
  };

  const makeEntry = (entity: string, label: string): FixedEntityEntry => {
    return label.trim() ? { entity, label } : entity;
  };

  return (
    <div className="mb-2">
      <div className="space-y-2">
        {safeEntities.map((v, i) => {
          const trimmedName = v.trim();
          const isFixed = Boolean(trimmedName && Object.prototype.hasOwnProperty.call(fixedValues, trimmedName));
          const boundEntities: FixedEntityEntry[] = isFixed ? (fixedValues[trimmedName] || ['']) : [];
          const displayBound: FixedEntityEntry[] = boundEntities.length > 0 ? boundEntities : [''];

          return (
            <div key={i} className="border rounded p-2 bg-white space-y-1.5 shadow-sm">
              <div className="flex gap-1 items-center">
                <input
                  type="text"
                  value={v}
                  onChange={e => {
                    const newValues = [...safeEntities];
                    newValues[i] = e.target.value;
                    onChange(newValues);
                  }}
                  className="flex-1 min-w-0 border rounded p-1 text-xs font-medium"
                  placeholder="Variable Name"
                />
                <button
                  onClick={() => onChange(safeEntities.filter((_, idx) => idx !== i))}
                  className="text-red-500 hover:bg-red-50 p-1 rounded flex-shrink-0"
                  title="Delete Variable"
                >
                  <Trash2 size={13} />
                </button>
              </div>

              {onFixedChange && trimmedName !== '' && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">Mode</span>
                  <div className="inline-flex rounded border overflow-hidden text-[10px] font-semibold">
                    <button
                      type="button"
                      onClick={() => isFixed && onFixedChange(trimmedName, null)}
                      className={`px-2 py-0.5 transition-colors ${!isFixed ? 'bg-blue-600 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'}`}
                      title="Set dynamically at runtime by navigation or selector tiles"
                    >
                      Runtime
                    </button>
                    <button
                      type="button"
                      onClick={() => !isFixed && onFixedChange(trimmedName, [''])}
                      className={`px-2 py-0.5 border-l transition-colors ${isFixed ? 'bg-purple-600 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'}`}
                      title="Bind to fixed Home Assistant entity ID(s) in this file"
                    >
                      Fixed
                    </button>
                  </div>
                </div>
              )}

              {onFixedChange && isFixed && (
                <div className="pt-1 border-t border-slate-100 space-y-1.5">
                  <label className="block text-[10px] text-slate-500 uppercase">Fixed Entity ID(s)</label>
                  {displayBound.map((entry, entIdx) => {
                    const { entity: entVal, label: lblVal } = getEntryParts(entry);
                    return (
                      <div key={entIdx} className="space-y-1">
                        <div className="flex gap-1 items-center">
                          <input
                            type="text"
                            value={entVal}
                            onChange={e => {
                              const next = [...displayBound];
                              next[entIdx] = makeEntry(e.target.value, lblVal);
                              onFixedChange(trimmedName, next);
                            }}
                            list={haEntities ? listId : undefined}
                            placeholder="e.g. light.living_room"
                            className="flex-1 min-w-0 border rounded p-1 text-xs"
                          />
                          {displayBound.length > 1 && (
                            <button
                              type="button"
                              onClick={() => onFixedChange(trimmedName, displayBound.filter((_, idx) => idx !== entIdx))}
                              className="text-red-500 hover:bg-red-50 p-0.5 rounded flex-shrink-0"
                              title="Remove Entity"
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                        <input
                          type="text"
                          value={lblVal}
                          onChange={e => {
                            const next = [...displayBound];
                            next[entIdx] = makeEntry(entVal, e.target.value);
                            onFixedChange(trimmedName, next);
                          }}
                          placeholder="Label (optional, for cycle_entity)"
                          className="w-full border rounded p-1 text-[11px] text-slate-700 bg-slate-50"
                        />
                        <BleFanToggle
                          entityId={entVal}
                          bleFans={bleFans}
                          tuyaBleCandidates={tuyaBleCandidates}
                          onUpdateBleFans={onUpdateBleFans}
                        />
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => onFixedChange(trimmedName, [...displayBound, ''])}
                    className="text-[10px] text-purple-600 hover:underline flex items-center gap-0.5"
                  >
                    <Plus size={11} /> Add Entity
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {haEntities && (
          <datalist id={listId}>
            {haEntities.map(e => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.friendly_name && e.friendly_name !== e.entity_id ? e.friendly_name : null}
              </option>
            ))}
          </datalist>
        )}
        <button
          onClick={() => onChange([...safeEntities, ''])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Variable
        </button>
      </div>
    </div>
  );
};

export const EntityArrayInput = ({
  label,
  values,
  onChange,
  dynamicEntities,
  haEntities,
  bleFans,
  tuyaBleCandidates,
  onUpdateBleFans,
}: {
  label: string,
  values: any[],
  onChange: (v: any[]) => void,
  dynamicEntities: string[],
  haEntities?: HaEntity[]
} & BleFanProps) => {
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);
  const listId = `ha-entities-arr-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="mb-4">
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <div className="space-y-2">
        {safeValues.map((rawItem, i) => {
          const item = typeof rawItem === 'string' ? { entity: rawItem } : rawItem;
          const isDynamic = 'dynamic_entity' in item;
          const type = isDynamic ? 'dynamic' : 'static';

          return (
            <div key={i} className="border rounded p-2 bg-slate-50 relative">
              <button
                onClick={() => onChange(safeValues.filter((_, idx) => idx !== i))}
                className="absolute top-1 right-1 text-red-500 hover:bg-red-100 p-1 rounded"
              >
                <Trash2 size={12} />
              </button>

              <div className="mb-2">
                <label className="block text-[10px] text-slate-500 uppercase">Type</label>
                <select
                  value={type}
                  onChange={e => {
                    const newType = e.target.value;
                    const newValues = [...safeValues];
                    if (newType === 'dynamic') {
                      const { entity, ...rest } = item;
                      newValues[i] = { ...rest, dynamic_entity: '' };
                    } else {
                      const { dynamic_entity, ...rest } = item;
                      newValues[i] = { ...rest, entity: '' };
                    }
                    onChange(newValues);
                  }}
                  className="w-full border rounded p-1 text-xs bg-white"
                >
                  <option value="static">Static Entity</option>
                  <option value="dynamic">Dynamic Entity</option>
                </select>
              </div>

              <div className="grid gap-2">
                {type === 'dynamic' ? (
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase">Dynamic Entity (Var Name)</label>
                    <select
                      value={item.dynamic_entity || ''}
                      onChange={e => {
                        const newValues = [...safeValues];
                        newValues[i] = { ...item, dynamic_entity: e.target.value };
                        onChange(newValues);
                      }}
                      className="w-full border rounded p-1 text-xs bg-white"
                    >
                      <option value="">Select variable...</option>
                      {dynamicEntities.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                ) : (
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase">Entity ID</label>
                    <input
                      type="text"
                      value={item.entity || ''}
                      onChange={e => {
                        const newValues = [...safeValues];
                        newValues[i] = { ...item, entity: e.target.value };
                        onChange(newValues);
                      }}
                      list={listId}
                      className="w-full border rounded p-1 text-xs"
                    />
                    <BleFanToggle
                      entityId={item.entity || ''}
                      bleFans={bleFans}
                      tuyaBleCandidates={tuyaBleCandidates}
                      onUpdateBleFans={onUpdateBleFans}
                    />
                  </div>
                )}

                <div>
                  <label className="block text-[10px] text-slate-500 uppercase">Sensor (Optional)</label>
                  <input
                    type="text"
                    value={item.sensor || ''}
                    onChange={e => {
                      const newValues = [...safeValues];
                      newValues[i] = { ...item, sensor: e.target.value };
                      onChange(newValues);
                    }}
                    className="w-full border rounded p-1 text-xs"
                  />
                </div>
              </div>
            </div>
          );
        })}
        <button
          onClick={() => onChange([...safeValues, { entity: '' }])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Entity
        </button>
      </div>
      {haEntities && (
        <datalist id={listId}>
          {haEntities.map(e => (
            <option key={e.entity_id} value={e.entity_id}>
              {e.friendly_name || e.entity_id}
            </option>
          ))}
        </datalist>
      )}
    </div>
  );
};
