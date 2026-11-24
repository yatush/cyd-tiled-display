import { useState } from 'react';
import { Trash2, Plus, Bluetooth, Settings2, AlertTriangle, Radar } from 'lucide-react';
import { BleFanConfig, FixedEntityEntry, HaEntity, TuyaBleCandidate } from '../types';
import {
  computeBleResourcePlan,
  deriveDefaultBleEntityIds,
  findCandidateForEntity,
  getOtherBleFanHosts,
  normalizeEntityId,
  toggleBleFanForEntity,
  upsertBleFan,
} from '../utils/bleFanUtils';

export interface BleFanProps {
  bleFans?: BleFanConfig[];
  tuyaBleCandidates?: TuyaBleCandidate[];
  bleFanHosts?: Record<string, string[]>;
  currentDevicePath?: string;
  onUpdateBleFans?: (next: BleFanConfig[]) => void;
}

export const BleFanToggle = ({
  entityId,
  bleFans = [],
  tuyaBleCandidates = [],
  bleFanHosts = {},
  currentDevicePath,
  onUpdateBleFans,
}: {
  entityId: string;
} & BleFanProps) => {
  const [showDetails, setShowDetails] = useState(false);
  if (!onUpdateBleFans) return null;

  const norm = normalizeEntityId(entityId);
  if (!norm) return null;

  const candidate = findCandidateForEntity(norm, tuyaBleCandidates);
  const configuredIdx = bleFans.findIndex(
    f =>
      normalizeEntityId(f.fan_entity_id) === norm ||
      (f.light_entity_id && normalizeEntityId(f.light_entity_id) === norm)
  );
  const configured = configuredIdx >= 0 ? bleFans[configuredIdx] : undefined;
  const isFanEntity = norm.startsWith('fan.');
  const hasAnyBleContext = bleFans.length > 0 || tuyaBleCandidates.length > 0;

  if (!candidate && !configured && !(isFanEntity && hasAnyBleContext)) {
    return null;
  }

  const updateConfigured = (patch: Partial<BleFanConfig>) => {
    if (configuredIdx < 0) return;
    const copy = [...bleFans];
    copy[configuredIdx] = { ...copy[configuredIdx], ...patch };
    onUpdateBleFans(copy);
  };

  const isChecked = Boolean(configured);
  const missingCreds = isChecked && (!configured?.device_id?.trim() || !configured?.local_key?.trim());
  const companionLight = configured?.light_entity_id || candidate?.light_entity_id || '';
  const companionFan = configured?.fan_entity_id || candidate?.fan_entity_id || '';
  const effectiveDeviceId = configured?.device_id || candidate?.device_id || '';
  const otherHosts = getOtherBleFanHosts(effectiveDeviceId, bleFanHosts, currentDevicePath);

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

      {otherHosts.length > 0 && (
        <div className="mt-1 px-1.5 py-1 rounded bg-amber-50 border border-amber-200 text-[10px] text-amber-800 flex items-start gap-1">
          <AlertTriangle size={11} className="text-amber-600 flex-shrink-0 mt-0.5" />
          <span>
            Already hosted via BLE by <strong>{otherHosts.join(', ')}</strong>. Tuya fans only accept 1 BLE connection at a time — consider controlling via Home Assistant instead.
          </span>
        </div>
      )}

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
              onChange={e => updateConfigured({ device_id: e.target.value })}
              placeholder="Device ID"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.local_key}
              onChange={e => updateConfigured({ local_key: e.target.value })}
              placeholder="Local Key"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.product_id || ''}
              onChange={e => updateConfigured({ product_id: e.target.value })}
              placeholder="Product ID (optional)"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
            <input
              type="text"
              value={configured.mac_address || ''}
              onChange={e => updateConfigured({ mac_address: e.target.value })}
              placeholder="BLE MAC (auto-discover)"
              className="border rounded px-1 py-0.5 text-[10px] bg-white"
            />
          </div>
          <input
            type="text"
            value={configured.light_entity_id || ''}
            onChange={e => updateConfigured({ light_entity_id: e.target.value })}
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
  bleFanHosts,
  currentDevicePath,
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
              bleFanHosts={bleFanHosts}
              currentDevicePath={currentDevicePath}
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
  bleFanHosts,
  currentDevicePath,
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
                          bleFanHosts={bleFanHosts}
                          currentDevicePath={currentDevicePath}
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
  bleFanHosts,
  currentDevicePath,
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
                      bleFanHosts={bleFanHosts}
                      currentDevicePath={currentDevicePath}
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

export const BleFansManagerPanel = ({
  bleFans = [],
  tuyaBleCandidates = [],
  bleFanHosts = {},
  currentDevicePath,
  hasBleProxy = false,
  onUpdateBleFans,
  onOpenFindBleFans,
}: {
  bleFans?: BleFanConfig[];
  tuyaBleCandidates?: TuyaBleCandidate[];
  bleFanHosts?: Record<string, string[]>;
  currentDevicePath?: string;
  hasBleProxy?: boolean;
  onUpdateBleFans: (next: BleFanConfig[]) => void;
  onOpenFindBleFans?: () => void;
}) => {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const resourcePlan = computeBleResourcePlan(bleFans.length, hasBleProxy);

  const availableCandidates = tuyaBleCandidates.filter(
    c =>
      !bleFans.some(
        f =>
          (c.device_id && f.device_id === c.device_id) ||
          (c.fan_entity_id && normalizeEntityId(f.fan_entity_id) === normalizeEntityId(c.fan_entity_id))
      )
  );

  const handleAddCandidate = (deviceId: string) => {
    const cand = availableCandidates.find(c => c.device_id === deviceId);
    if (!cand) return;
    const fanName = cand.name || cand.fan_entity_id || cand.device_id;
    const defaults = deriveDefaultBleEntityIds(fanName, currentDevicePath);
    const next = upsertBleFan(bleFans, {
      name: fanName,
      device_id: cand.device_id,
      local_key: cand.local_key,
      product_id: cand.product_id || '',
      mac_address: cand.mac_address || '',
      uuid: cand.uuid || '',
      fan_entity_id: cand.fan_entity_id || defaults.fan_entity_id,
      light_entity_id: cand.light_entity_id || defaults.light_entity_id,
      expose_to_ha: true,
    });
    onUpdateBleFans(next);
  };

  const handleAddManual = () => {
    const defaultName = `BLE Fan ${bleFans.length + 1}`;
    const defaults = deriveDefaultBleEntityIds(defaultName, currentDevicePath);
    const next: BleFanConfig[] = [
      ...bleFans,
      {
        name: defaultName,
        device_id: '',
        local_key: '',
        product_id: '',
        fan_entity_id: defaults.fan_entity_id,
        light_entity_id: defaults.light_entity_id,
        expose_to_ha: true,
      },
    ];
    onUpdateBleFans(next);
    setExpandedIdx(next.length - 1);
  };

  const updateAt = (idx: number, patch: Partial<BleFanConfig>) => {
    const copy = [...bleFans];
    const prev = copy[idx];
    const nextPatch: Partial<BleFanConfig> = { ...patch };

    if (patch.name !== undefined) {
      const prevDefaults = deriveDefaultBleEntityIds(prev.name, currentDevicePath);
      const nextDefaults = deriveDefaultBleEntityIds(patch.name, currentDevicePath);
      if (
        patch.fan_entity_id === undefined &&
        (!prev.fan_entity_id?.trim() || prev.fan_entity_id.trim() === prevDefaults.fan_entity_id)
      ) {
        nextPatch.fan_entity_id = nextDefaults.fan_entity_id;
      }
      if (
        patch.light_entity_id === undefined &&
        (!prev.light_entity_id?.trim() || prev.light_entity_id.trim() === prevDefaults.light_entity_id)
      ) {
        nextPatch.light_entity_id = nextDefaults.light_entity_id;
      }
    }

    copy[idx] = { ...prev, ...nextPatch };
    onUpdateBleFans(copy);
  };

  const removeAt = (idx: number) => {
    onUpdateBleFans(bleFans.filter((_, i) => i !== idx));
    setExpandedIdx(prev => (prev === null || prev === idx ? null : prev > idx ? prev - 1 : prev));
  };

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-slate-500 leading-snug">
        Host Tuya BLE fans on this CYD and expose them to Home Assistant — no tile required.
      </p>

      {onOpenFindBleFans && (
        <button
          type="button"
          onClick={onOpenFindBleFans}
          className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-semibold bg-sky-600 text-white hover:bg-sky-700 shadow-sm transition-colors"
        >
          <Radar size={13} />
          <span>Find &amp; Pair BLE Fans</span>
        </button>
      )}

      {bleFans.length > 0 && (
        <div
          className={`rounded border p-2 text-[10px] space-y-1 ${
            resourcePlan.displayBufferSize === '15%'
              ? 'bg-amber-50/80 border-amber-200 text-amber-900'
              : 'bg-sky-50/80 border-sky-200 text-sky-900'
          }`}
        >
          <div className="flex items-center justify-between font-semibold">
            <span>BLE Connections</span>
            <span>
              {resourcePlan.fanSlots} fan{resourcePlan.fanSlots > 1 ? 's' : ''}
              {resourcePlan.proxySlots > 0 ? ' + 1 proxy' : ''} ({resourcePlan.totalConnections} total)
            </span>
          </div>
          <div className="opacity-85 leading-snug">
            {resourcePlan.persistent ? (
              <span>
                All {bleFans.length} fan{bleFans.length > 1 ? 's' : ''} stay persistently connected simultaneously (instant control &amp; live RSSI).
              </span>
            ) : (
              <span>
                {resourcePlan.fanSlots} simultaneous slots shared across {bleFans.length} fans (on-demand switch, {resourcePlan.idleDisconnectS}s idle disconnect).
              </span>
            )}
          </div>
          <div className="flex items-center justify-between pt-1 border-t border-current/15">
            <span className="font-semibold">3.5&quot; Display Buffer</span>
            <span className="font-mono font-bold">{resourcePlan.displayBufferSize}</span>
          </div>
          <div className="opacity-80 leading-snug">
            {resourcePlan.displayBufferSize === '15%'
              ? 'Extra-compact 15% buffer (~23 KB) to keep safe RAM headroom for 3 simultaneous BLE connections + HA API.'
              : 'Compact 20% buffer (~31 KB, matching BLE Proxy) to keep safe RAM headroom alongside Wi-Fi + HA API.'}
          </div>
        </div>
      )}

      {bleFans.length > 0 && (
        <div className="space-y-1.5">
          {bleFans.map((fan, idx) => {
            const missingCreds = !fan.device_id?.trim() || !fan.local_key?.trim();
            const isExpanded = expandedIdx === idx || missingCreds;
            const otherHosts = getOtherBleFanHosts(fan.device_id, bleFanHosts, currentDevicePath);
            return (
              <div key={idx} className="border border-blue-200 rounded p-2 bg-white space-y-1.5 shadow-sm">
                <div className="flex items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Bluetooth size={12} className="text-blue-600 flex-shrink-0" />
                    <span className="text-xs font-semibold text-slate-700 truncate">
                      {fan.name || fan.fan_entity_id || 'Unnamed BLE Fan'}
                    </span>
                  </div>
                  <div className="flex items-center gap-0.5 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => setExpandedIdx(isExpanded && !missingCreds ? null : idx)}
                      className={`p-1 rounded hover:bg-blue-50 ${missingCreds ? 'text-amber-600' : 'text-slate-500'}`}
                      title="Edit BLE fan settings"
                    >
                      <Settings2 size={12} />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeAt(idx)}
                      className="p-1 rounded text-red-500 hover:bg-red-50"
                      title="Remove BLE fan"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                {otherHosts.length > 0 && (
                  <div className="px-1.5 py-1 rounded bg-amber-50 border border-amber-200 text-[10px] text-amber-800 flex items-start gap-1">
                    <AlertTriangle size={11} className="text-amber-600 flex-shrink-0 mt-0.5" />
                    <span>
                      Already hosted via BLE by <strong>{otherHosts.join(', ')}</strong>. Tuya fans only accept 1 BLE connection at a time.
                    </span>
                  </div>
                )}

                {(fan.fan_entity_id || fan.light_entity_id) && (
                  <div className="flex flex-wrap gap-1">
                    {fan.fan_entity_id && (
                      <span className="text-[9px] px-1 py-0.5 rounded bg-slate-100 text-slate-600 truncate max-w-full">
                        {fan.fan_entity_id}
                      </span>
                    )}
                    {fan.light_entity_id && (
                      <span className="text-[9px] px-1 py-0.5 rounded bg-blue-50 text-blue-700 truncate max-w-full">
                        {fan.light_entity_id}
                      </span>
                    )}
                  </div>
                )}

                {isExpanded && (
                  <div className="pt-1.5 border-t border-slate-100 space-y-1">
                    <input
                      type="text"
                      value={fan.name}
                      onChange={e => updateAt(idx, { name: e.target.value })}
                      placeholder="Room / Fan Name (e.g. Office)"
                      className="w-full border rounded px-1.5 py-1 text-[11px]"
                    />
                    <div className="grid grid-cols-2 gap-1">
                      <input
                        type="text"
                        value={fan.device_id}
                        onChange={e => updateAt(idx, { device_id: e.target.value })}
                        placeholder="Device ID *"
                        className="border rounded px-1.5 py-1 text-[10px]"
                      />
                      <input
                        type="text"
                        value={fan.local_key}
                        onChange={e => updateAt(idx, { local_key: e.target.value })}
                        placeholder="Local Key *"
                        className="border rounded px-1.5 py-1 text-[10px]"
                      />
                      <input
                        type="text"
                        value={fan.product_id || ''}
                        onChange={e => updateAt(idx, { product_id: e.target.value })}
                        placeholder="Product ID (optional)"
                        className="border rounded px-1.5 py-1 text-[10px]"
                      />
                      <input
                        type="text"
                        value={fan.mac_address || ''}
                        onChange={e => updateAt(idx, { mac_address: e.target.value })}
                        placeholder="BLE MAC (auto)"
                        className="border rounded px-1.5 py-1 text-[10px]"
                      />
                    </div>
                    <div className="pt-0.5 space-y-1">
                      <div className="text-[9px] text-slate-500">
                        Entity IDs (auto-filled — available in tile dropdowns with <span className="font-semibold text-blue-600">[BLE]</span>):
                      </div>
                      <input
                        type="text"
                        value={fan.fan_entity_id || ''}
                        onChange={e => updateAt(idx, { fan_entity_id: e.target.value })}
                        placeholder="fan.office_fan"
                        className="w-full border rounded px-1.5 py-1 text-[10px] font-mono"
                      />
                      <input
                        type="text"
                        value={fan.light_entity_id || ''}
                        onChange={e => updateAt(idx, { light_entity_id: e.target.value })}
                        placeholder="light.office_light"
                        className="w-full border rounded px-1.5 py-1 text-[10px] font-mono"
                      />
                    </div>
                    <label className="flex items-center gap-1.5 text-[10px] text-slate-600 cursor-pointer pt-0.5">
                      <input
                        type="checkbox"
                        checked={fan.expose_to_ha !== false}
                        onChange={e => updateAt(idx, { expose_to_ha: e.target.checked })}
                        className="rounded border-slate-300 text-blue-600"
                      />
                      <span>Expose fan, light &amp; timer to Home Assistant</span>
                    </label>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {availableCandidates.length > 0 && (
        <select
          value=""
          onChange={e => {
            if (e.target.value) handleAddCandidate(e.target.value);
          }}
          className="w-full border border-blue-200 rounded p-1.5 text-xs bg-white text-blue-700 font-medium"
        >
          <option value="">+ Import saved / discovered BLE fan...</option>
          {availableCandidates.map(c => {
            const hosts = getOtherBleFanHosts(c.device_id, bleFanHosts, currentDevicePath);
            const suffix = hosts.length > 0 ? ` [⚠ on ${hosts.join(', ')}]` : '';
            return (
              <option key={c.device_id} value={c.device_id}>
                {c.name} ({c.fan_entity_id || c.device_id}){suffix}
              </option>
            );
          })}
        </select>
      )}

      <button
        type="button"
        onClick={handleAddManual}
        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
      >
        <Plus size={12} /> Add Manual BLE Fan
      </button>
    </div>
  );
};
