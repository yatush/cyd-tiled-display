import { Trash2, Plus } from 'lucide-react';
import { HaEntity } from '../types';

export const EntityListInput = ({ label, values, onChange, haEntities }: {
  label: string,
  values: string[],
  onChange: (v: string[]) => void,
  haEntities?: HaEntity[]
}) => {
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);
  const listId = `ha-entities-list-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="mb-2">
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}
      <div className="space-y-1">
        {safeValues.map((v, i) => (
          <div key={i} className="flex gap-1">
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

export const DynamicEntitiesEditor = ({ entities, onChange }: { entities: string[], onChange: (v: string[]) => void }) => {
  const safeEntities = Array.isArray(entities) ? entities : (entities ? [entities] : []);

  return (
    <div className="mb-2">
      <div className="space-y-1">
        {safeEntities.map((v, i) => (
          <div key={i} className="flex gap-1">
            <input
              type="text"
              value={v}
              onChange={e => {
                const newValues = [...safeEntities];
                newValues[i] = e.target.value;
                onChange(newValues);
              }}
              className="flex-1 border rounded p-1 text-sm"
              placeholder="Variable Name"
            />
            <button
              onClick={() => onChange(safeEntities.filter((_, idx) => idx !== i))}
              className="text-red-500 hover:bg-red-50 p-1 rounded"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
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

export const EntityArrayInput = ({ label, values, onChange, dynamicEntities, haEntities }: {
  label: string,
  values: any[],
  onChange: (v: any[]) => void,
  dynamicEntities: string[],
  haEntities?: HaEntity[]
}) => {
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
