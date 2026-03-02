import { useState, useEffect, useRef } from 'react';
import { Trash2, Plus, Upload } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { HaEntity, ImageEntry } from '../types';

export const NumberInput = ({ label, value, onChange, min = 0 }: { label: string, value: number, onChange: (v: number) => void, min?: number }) => (
  <div className="mb-2">
    <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
    <input 
      type="number" 
      value={value || 0} 
      onChange={e => onChange(parseInt(e.target.value))}
      min={min}
      className="w-full border rounded p-1 text-sm"
    />
  </div>
);

export const TextInput = ({ label, value, onChange, haEntities }: { label: string, value: string, onChange: (v: string) => void, haEntities?: HaEntity[] }) => {
  const listId = `ha-entities-text-${Math.random().toString(36).substr(2, 9)}`;
  return (
  <div className="mb-2">
    <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
    <input 
      type="text" 
      value={value || ''} 
      onChange={e => onChange(e.target.value)}
      list={haEntities ? listId : undefined}
      className="w-full border rounded p-1 text-sm"
    />
    {haEntities && (
        <datalist id={listId}>
            {haEntities.map(e => (
                <option key={e.entity_id} value={e.entity_id}>
                    {e.friendly_name && e.friendly_name !== e.entity_id ? e.friendly_name : null}
                </option>
            ))}
        </datalist>
    )}
  </div>
  );
};

export const ScriptInput = ({ label, value, onChange, type }: { label: string, value: string | Record<string, any>, onChange: (v: string | Record<string, any>) => void, type: 'display' | 'action' }) => {
  const [options, setOptions] = useState<string[]>([]);
  const [scriptPool, setScriptPool] = useState<any[]>([]);
  
  const fetchOptions = async () => {
    try {
      const res = await apiFetch('/scripts');
      if (res.ok) {
        const data = await res.json();
        const scripts = data.scripts || [];
        setScriptPool(scripts);
        setOptions(scripts.map((s: any) => s.id).filter((id: string) => !id.startsWith('_')).sort());
      }
    } catch (e) {
      console.error("Failed to fetch scripts", e);
    }
  };

  useEffect(() => {
    fetchOptions();
  }, [type]);

   const scriptId = typeof value === 'string' ? value : (value && typeof value === 'object' ? Object.keys(value)[0] : '');
   const params = (value && typeof value === 'object' && scriptId) ? value[scriptId] : {};
   const scriptDef = scriptPool.find(s => s.id === scriptId);
   const hasParams = scriptDef && scriptDef.params && scriptDef.params.length > 0;

  return (
    <div className="mb-2 p-2 border rounded bg-slate-50">
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <select 
        value={scriptId || ''} 
        onChange={e => {
             const newId = e.target.value;
             onChange(newId);
        }}
        onFocus={fetchOptions}
        className="w-full border rounded p-1 text-sm bg-white"
      >
        <option value="">Select script...</option>
        {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
      </select>
      
      {hasParams && (
        <div className="pl-2 space-y-2 mt-2 border-l-2 border-slate-200">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Parameters</div>
            {scriptDef.params.map((p: any) => (
                <div key={p.name}>
                    <label className="block text-xs font-medium text-slate-600 mb-0.5 pointer-events-none truncate">{p.name} <span className="text-[10px] text-slate-400 font-normal">({p.type})</span></label>
                    <input 
                        type="text"
                        value={params[p.name] || ''}
                        onChange={e => {
                            const newVal = e.target.value;
                            const currentParams = {...params};
                            if (newVal) currentParams[p.name] = newVal;
                            else delete currentParams[p.name];
                            
                            onChange({ [scriptId]: currentParams });
                        }}
                        className="w-full border rounded p-1 text-xs focus:border-blue-500 outline-none"
                        placeholder={`Value for ${p.name}`}
                    />
                </div>
            ))}
        </div>
      )}
    </div>
  );
};

export const Checkbox = ({ label, checked, onChange }: { label: string, checked: boolean, onChange: (v: boolean) => void }) => (
  <div className="mb-2 flex items-center gap-2">
    <input 
      type="checkbox" 
      checked={checked || false} 
      onChange={e => onChange(e.target.checked)}
      className="rounded border-slate-300"
    />
    <label className="text-sm text-slate-700">{label}</label>
  </div>
);

export const ArrayInput = ({ label, values, onChange, suggestionType, allowedValues }: { 
  label: string, 
  values: any[], 
  onChange: (v: any[]) => void, 
  suggestionType?: 'display' | 'action',
  allowedValues?: string[]
}) => {
  const [options, setOptions] = useState<string[]>([]);
  const [scriptPool, setScriptPool] = useState<any[]>([]);

  const fetchOptions = async () => {
    if (allowedValues) {
        setOptions(allowedValues);
        return;
    }
    if (!suggestionType) return;
    try {
      const res = await apiFetch('/scripts');
      if (res.ok) {
        const data = await res.json();
        const scripts = data.scripts || [];
        setScriptPool(scripts);
        setOptions(scripts.map((s: any) => s.id).filter((id: string) => !id.startsWith('_')).sort());
      }
    } catch (e) {
      console.error("Failed to fetch scripts", e);
    }
  };

  useEffect(() => {
    fetchOptions();
  }, [suggestionType, allowedValues]);

  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);

  return (
    <div className="mb-2">
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}
      <div className="space-y-2">
        {safeValues.map((v, i) => {
            const scriptId = typeof v === 'string' ? v : (v && typeof v === 'object' ? Object.keys(v)[0] : '');
            const params = (v && typeof v === 'object' && scriptId) ? v[scriptId] : {};
            const scriptDef = scriptPool.find(s => s.id === scriptId);
            const hasParams = scriptDef && scriptDef.params && scriptDef.params.length > 0;
            
            return (
          <div key={i} className="border p-2 rounded bg-slate-50 relative group">
            <div className="flex gap-1 mb-1">
            {suggestionType || allowedValues ? (
                <select
                  value={scriptId}
                  onChange={e => {
                    const newId = e.target.value;
                    const newValues = [...safeValues];
                    // Reset to string when changing script
                    newValues[i] = newId;
                    onChange(newValues);
                  }}
                  onFocus={fetchOptions}
                  className="flex-1 border rounded p-1 text-sm bg-white"
                >
                    <option value="">Select...</option>
                    {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
            ) : (
                <input 
                  type="text" 
                  value={typeof v === 'string' ? v : JSON.stringify(v)} 
                  onChange={e => {
                    const newValues = [...safeValues];
                    newValues[i] = e.target.value;
                    onChange(newValues);
                  }}
                  className="flex-1 border rounded p-1 text-sm"
                />
            )}
            <button 
              onClick={() => onChange(safeValues.filter((_, idx) => idx !== i))}
              className="text-red-500 hover:bg-red-50 p-1 rounded"
            >
              <Trash2 size={14} />
            </button>
            </div>
            
            {hasParams && (
                <div className="pl-2 space-y-2 mt-2 border-l-2 border-slate-200">
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Parameters</div>
                    {scriptDef.params.map((p: any) => (
                        <div key={p.name}>
                            <label className="block text-xs font-medium text-slate-600 mb-0.5 pointer-events-none truncate" title={`${p.name} (${p.type})`}>{p.name}</label>
                            <input 
                                type="text"
                                value={params[p.name] || ''}
                                onChange={e => {
                                    const newVal = e.target.value;
                                    const newValues = [...safeValues];
                                    const currentParams = {...params};
                                    if (newVal) currentParams[p.name] = newVal;
                                    else delete currentParams[p.name];
                                    
                                    // Switch to object format
                                    newValues[i] = { [scriptId]: currentParams };
                                    onChange(newValues);
                                }}
                                className="w-full border rounded p-1 text-xs focus:border-blue-500 outline-none"
                                placeholder={`Value for ${p.name}`}
                            />
                        </div>
                    ))}
                </div>
            )}
          </div>
        );
        })}
        <button 
          onClick={() => onChange([...safeValues, ''])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Item
        </button>
      </div>
    </div>
  );
};

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

export const ConditionBuilder = ({ value, onChange, scriptOptions: propScriptOptions }: { value: any, onChange: (v: any) => void, globals?: string[], scriptOptions?: string[] }) => {
  const [options, setOptions] = useState<string[]>(propScriptOptions || []);

  useEffect(() => {
    if (propScriptOptions) {
        setOptions(propScriptOptions);
        return;
    }

    apiFetch('/scripts').then(res => res.json()).then(data => {
        const all = (data.scripts || []).map((s: any) => s.id).filter((id: string) => !id.startsWith('_')).sort();
        if (!propScriptOptions) setOptions(all);
    }).catch(e => console.error(e));
  }, [propScriptOptions]);

  const type = typeof value === 'string' ? 'leaf' : 
               value?.operator === 'AND' ? 'and' : 
               value?.operator === 'OR' ? 'or' : 
               value?.operator === 'NOT' ? 'not' : 
               value?.and ? 'and' : 
               value?.or ? 'or' : 
               value?.not ? 'not' : 
               Array.isArray(value) ? 'or' : 'leaf'; // Default array to OR

  const handleTypeChange = (newType: string) => {
      if (newType === 'leaf') onChange('');
      else if (newType === 'and') onChange({ operator: 'AND', conditions: [] });
      else if (newType === 'or') onChange({ operator: 'OR', conditions: [] });
      else if (newType === 'not') onChange({ operator: 'NOT', conditions: '' });
  };

  // Normalize value for rendering
  const conditions = value?.conditions ?? (value?.and || value?.or || value?.not || (Array.isArray(value) ? value : []));

  return (
    <div className="border rounded p-2 bg-white mb-2">
        <div className="flex items-center gap-2 mb-2">
            <select 
                value={type} 
                onChange={e => handleTypeChange(e.target.value)}
                className="border rounded p-1 text-xs font-bold bg-slate-100"
            >
                <option value="leaf">Condition</option>
                <option value="and">AND</option>
                <option value="or">OR</option>
                <option value="not">NOT</option>
            </select>
            {type === 'leaf' && (
                <div className="flex-1 flex gap-1">
                    <select 
                        value={value as string} 
                        onChange={e => onChange(e.target.value)}
                        className="flex-1 border rounded p-1 text-xs"
                    >
                        <option value="">Select script...</option>
                        {options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                </div>
            )}
        </div>
        
        {type === 'and' && (
            <div className="pl-4 border-l-2 border-blue-200 space-y-2">
                {(Array.isArray(conditions) ? conditions : []).map((item: any, idx: number) => (
                    <div key={idx} className="flex gap-2 items-start">
                        <div className="flex-1">
                            <ConditionBuilder 
                                value={item} 
                                scriptOptions={options}
                                onChange={newItem => {
                                    const newConditions = [...(Array.isArray(conditions) ? conditions : [])];
                                    newConditions[idx] = newItem;
                                    onChange({ operator: 'AND', conditions: newConditions });
                                }} 
                            />
                        </div>
                        <button onClick={() => {
                            const newConditions = (Array.isArray(conditions) ? conditions : []).filter((_: any, i: number) => i !== idx);
                            onChange({ operator: 'AND', conditions: newConditions });
                        }} className="text-red-500 p-1"><Trash2 size={14}/></button>
                    </div>
                ))}
                <button onClick={() => onChange({ operator: 'AND', conditions: [...(Array.isArray(conditions) ? conditions : []), ''] })} className="text-xs text-blue-600 flex items-center gap-1">
                    <Plus size={12} /> Add Condition
                </button>
            </div>
        )}

        {type === 'or' && (
            <div className="pl-4 border-l-2 border-orange-200 space-y-2">
                {(Array.isArray(conditions) ? conditions : []).map((item: any, idx: number) => (
                    <div key={idx} className="flex gap-2 items-start">
                        <div className="flex-1">
                            <ConditionBuilder 
                                value={item} 
                                scriptOptions={options}
                                onChange={newItem => {
                                    const newConditions = [...(Array.isArray(conditions) ? conditions : [])];
                                    newConditions[idx] = newItem;
                                    onChange({ operator: 'OR', conditions: newConditions });
                                }} 
                            />
                        </div>
                        <button onClick={() => {
                            const newConditions = (Array.isArray(conditions) ? conditions : []).filter((_: any, i: number) => i !== idx);
                            onChange({ operator: 'OR', conditions: newConditions });
                        }} className="text-red-500 p-1"><Trash2 size={14}/></button>
                    </div>
                ))}
                <button onClick={() => onChange({ operator: 'OR', conditions: [...(Array.isArray(conditions) ? conditions : []), ''] })} className="text-xs text-blue-600 flex items-center gap-1">
                    <Plus size={12} /> Add Condition
                </button>
            </div>
        )}

        {type === 'not' && (
            <div className="pl-4 border-l-2 border-red-200">
                <ConditionBuilder 
                    value={conditions} 
                    scriptOptions={options}
                    onChange={newItem => onChange({ operator: 'NOT', conditions: newItem })} 
                />
            </div>
        )}
    </div>
  );
};

export const ObjectInput = ({ label, value, fields, onChange, dynamicEntities, haEntities }: { 
  label: string, 
  value: any, 
  fields: { key: string, label: string, type?: string }[],
  onChange: (v: any) => void,
  dynamicEntities?: string[],
  haEntities?: HaEntity[]
}) => {
  const listId = `ha-entities-obj-${Math.random().toString(36).substr(2, 9)}`;
  return (
  <div className="mb-4">
    {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}
    <div className="border rounded p-2 bg-slate-50">
      <div className="grid gap-2">
        {fields.map(field => (
          <div key={field.key}>
            <label className="block text-[10px] text-slate-500 uppercase">{field.label}</label>
            {field.type === 'dynamic_entity_select' && dynamicEntities ? (
                <select 
                  value={value?.[field.key] || ''} 
                  onChange={e => {
                    const newValue = { ...value, [field.key]: e.target.value };
                    onChange(newValue);
                  }}
                  className="w-full border rounded p-1 text-xs bg-white"
                >
                    <option value="">Select variable...</option>
                    {dynamicEntities.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
            ) : field.type === 'ha_entity' && haEntities ? (
                <div className="relative">
                    <input 
                        type="text" 
                        value={value?.[field.key] || ''} 
                        onChange={e => {
                            const newValue = { ...value, [field.key]: e.target.value };
                            onChange(newValue);
                        }}
                        list={listId}
                        className="w-full border rounded p-1 text-xs"
                    />
                    <datalist id={listId}>
                        {haEntities.map(e => (
                            <option key={e.entity_id} value={e.entity_id}>
                                {e.friendly_name && e.friendly_name !== e.entity_id ? e.friendly_name : null}
                            </option>
                        ))}
                    </datalist>
                </div>
            ) : field.type === 'ha_entity_list' ? (
                <EntityListInput 
                    label="" 
                    values={value?.[field.key] || []} 
                    onChange={v => {
                        const newValue = { ...value, [field.key]: v };
                        onChange(newValue);
                    }}
                    haEntities={haEntities}
                />
            ) : field.type === 'string_list' ? (
                <ArrayInput 
                    label="" 
                    values={value?.[field.key] || []} 
                    onChange={v => {
                        const newValue = { ...value, [field.key]: v };
                        onChange(newValue);
                    }}
                />
            ) : field.type === 'condition_logic' ? (
                <ConditionBuilder 
                    value={value?.[field.key] || ''} 
                    onChange={v => {
                        const newValue = { ...value, [field.key]: v };
                        onChange(newValue);
                    }}
                />
            ) : (
                <input 
                  type="text" 
                  value={value?.[field.key] || ''} 
                  onChange={e => {
                    const newValue = { ...value, [field.key]: e.target.value };
                    onChange(newValue);
                  }}
                  className="w-full border rounded p-1 text-xs"
                />
            )}
          </div>
        ))}
      </div>
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
      {safeValues.map((item, i) => {
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
                        // Switch to dynamic: keep sensor, remove entity, add dynamic_entity
                        const { entity, ...rest } = item;
                        newValues[i] = { ...rest, dynamic_entity: '' };
                    } else {
                        // Switch to static: keep sensor, remove dynamic_entity, add entity
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
                  list={listId}
                  className="w-full border rounded p-1 text-xs"
                />
            </div>
          </div>
        </div>
      )})}
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

// ============================================================
// Image helpers
// ============================================================

/** Derive an ESPHome image type from whether the PNG has an alpha channel. */
function detectImageType(base64: string): 'RGBA' | 'RGB565' {
  // PNG with RGBA has colour type 6. Bytes 24-25 of the raw data map to
  // base64 characters at positions 32-33 of the base64 string.
  // Colour type byte is at offset 25 in the PNG file (IHDR chunk).
  try {
    const raw = atob(base64.slice(0, 44)); // first 33 bytes is enough
    const colourType = raw.charCodeAt(25);
    return colourType === 6 || colourType === 4 ? 'RGBA' : 'RGB565';
  } catch {
    return 'RGB565';
  }
}

/** Generate a unique image ID from a filename, avoiding collisions with existing keys. */
/** Resize an image to fit within maxWidth × maxHeight, returning a PNG base64 string. */
function resizeImageToPng(dataUrl: string, maxWidth: number, maxHeight: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      // Only downscale, never upscale
      const ratio = Math.min(maxWidth / width, maxHeight / height, 1);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('No 2d context')); return; }
      ctx.clearRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL('image/png').split(',')[1]);
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}

export function generateImageId(filename: string, existing: Record<string, ImageEntry>): string {
  const stem = filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_]/g, '_');
  const base = `img_${stem}`;
  if (!existing[base]) return base;
  let n = 1;
  while (existing[`${base}_${n}`]) n++;
  return `${base}_${n}`;
}

// ---- ImageSelectInput -------------------------------------------------------
// Simple select-only dropdown (upload is handled by ImageManagerPanel in the left sidebar).

export const ImageSelectInput = ({
  label,
  value,
  onChange,
  images,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  images: Record<string, ImageEntry>;
}) => {
  const imageIds = Object.keys(images || {});
  const selected = value && images?.[value] ? images[value] : null;

  return (
    <div className="mb-2">
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}
      <div className="min-w-0 overflow-hidden">
        <select
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          className="w-full border rounded p-1 text-sm bg-white"
        >
          <option value="">— select image —</option>
          {imageIds.map(id => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
      </div>
      {selected && (
        <div className="mt-1 flex items-center gap-2">
          <img
            src={`data:image/png;base64,${selected.data}`}
            alt={selected.filename}
            className="flex-shrink-0 max-h-10 max-w-[50px] object-contain border rounded bg-slate-100"
          />
          <span className="text-[10px] text-slate-500 truncate flex-1" title={selected.filename}>
            {selected.filename}
          </span>
          {value && (
            <button
              type="button"
              title="Clear"
              onClick={() => onChange('')}
              className="flex-shrink-0 text-red-500 hover:bg-red-50 p-0.5 rounded"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// ---- ImageManagerPanel -------------------------------------------------------
// Manages the global images store: upload, list, delete.
// Rendered in the LeftSidebar — images uploaded here are available to all tiles.

export const ImageManagerPanel = ({
  images,
  onAddImage,
  onDeleteImage,
}: {
  images: Record<string, ImageEntry>;
  onAddImage: (id: string, entry: ImageEntry) => void;
  onDeleteImage: (id: string) => void;
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageIds = Object.keys(images || {});

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      if (!file.name.match(/\.(png|jpg|jpeg|gif|bmp)$/i)) return;
      const reader = new FileReader();
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string;
        const originalBase64 = dataUrl.split(',')[1];
        const imgType = file.name.toLowerCase().endsWith('.png') ? detectImageType(originalBase64) : 'RGB565';
        // Skip if same filename already uploaded
        if (Object.keys(images || {}).some(id => images[id].filename === file.name)) return;
        // Resize to a storage-friendly max; PIL resizes to tile dims at generation time
        resizeImageToPng(dataUrl, 400, 300).then(base64 => {
          const newId = generateImageId(file.name, images || {});
          onAddImage(newId, { data: base64, filename: file.name, type: imgType });
        }).catch(() => {
          const newId = generateImageId(file.name, images || {});
          onAddImage(newId, { data: originalBase64, filename: file.name, type: imgType });
        });
      };
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  return (
    <div className="space-y-1.5">
      {imageIds.length === 0 && (
        <div className="text-[10px] text-slate-400 italic px-1 py-1">No images yet</div>
      )}
      {imageIds.map(id => {
        const entry = images[id];
        return (
          <div key={id} className="flex items-center gap-2 p-1.5 border rounded bg-white hover:bg-slate-50">
            <img
              src={`data:image/png;base64,${entry.data}`}
              alt={entry.filename}
              className="flex-shrink-0 w-10 h-10 object-contain border rounded bg-slate-100"
            />
            <div className="flex-1 min-w-0">
              <div className="text-[10px] font-bold text-blue-700 truncate">{id}</div>
              <div className="text-[9px] text-slate-500 truncate" title={entry.filename}>{entry.filename}</div>
              <div className="text-[9px] text-slate-400">{entry.type || 'RGB565'}</div>
            </div>
            <button
              type="button"
              onClick={() => onDeleteImage(id)}
              className="flex-shrink-0 text-red-400 hover:text-red-600 p-1 rounded hover:bg-red-50"
              title={`Delete ${id}`}
            >
              <Trash2 size={12} />
            </button>
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1.5 hover:bg-blue-50 flex items-center justify-center gap-1 mt-1"
      >
        <Upload size={12} /> Upload Image
      </button>
      <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
    </div>
  );
};

// ---- ImagesListInput --------------------------------------------------------
// Unified list of images, each with an optional condition.
// Value: Array<{ image: string; condition?: any }>
// Entries are evaluated in order; first matching condition wins.
// An entry without a condition is an unconditional fallback.

export const ImagesListInput = ({
  value,
  onChange,
  images,
}: {
  value: Array<{ image: string; condition?: any }>;
  onChange: (v: Array<{ image: string; condition?: any }>) => void;
  images: Record<string, ImageEntry>;
}) => {
  const rows = Array.isArray(value) ? value : [];

  const updateRow = (idx: number, patch: Partial<{ image: string; condition?: any }>) => {
    onChange(rows.map((r, i) => i === idx ? { ...r, ...patch } : r));
  };

  const removeRow = (idx: number) => onChange(rows.filter((_, i) => i !== idx));

  const toggleCondition = (idx: number, checked: boolean) => {
    if (checked) {
      updateRow(idx, { condition: '' });
    } else {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { condition: _c, ...rest } = rows[idx];
      onChange(rows.map((r, i) => i === idx ? rest : r));
    }
  };

  return (
    <div className="space-y-2">
      {rows.map((row, idx) => {
        const hasCondition = 'condition' in row;
        return (
          <div key={idx} className="border rounded p-2 bg-white">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-slate-500 uppercase font-medium">Image {idx + 1}</span>
              <button
                type="button"
                onClick={() => removeRow(idx)}
                className="text-red-400 hover:text-red-600 p-0.5 rounded"
                title="Remove"
              >
                <Trash2 size={12} />
              </button>
            </div>
            <ImageSelectInput
              value={row.image}
              onChange={v => updateRow(idx, { image: v })}
              images={images}
            />
            <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer select-none mt-1">
              <input
                type="checkbox"
                checked={hasCondition}
                onChange={e => toggleCondition(idx, e.target.checked)}
                className="rounded border-slate-300"
              />
              Conditional
            </label>
            {hasCondition && (
              <div className="mt-1">
                <ConditionBuilder value={row.condition} onChange={v => updateRow(idx, { condition: v })} />
              </div>
            )}
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, { image: '' }])}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1 hover:bg-blue-50 flex items-center justify-center gap-1"
      >
        <Plus size={12} /> Add Image
      </button>
    </div>
  );
};

export const ObjectArrayInput = ({ label, values, fields, onChange, haEntities }: { 
  label: string, 
  values: any[], 
  fields: { key: string, label: string, type?: string }[],
  onChange: (v: any[]) => void,
  haEntities?: HaEntity[]
}) => {
  const listId = `ha-entities-obj-arr-${Math.random().toString(36).substr(2, 9)}`;
  // Check if one of the fields is 'entity'
  const hasEntityField = fields.some(f => f.key === 'entity');
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);

  return (
  <div className="mb-4">
    <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
    <div className="space-y-2">
      {safeValues.map((item, i) => {
        const isAllOption = hasEntityField && item.entity === '*';

        return (
        <div key={i} className="border rounded p-2 bg-slate-50 relative">
          <button 
            onClick={() => onChange(safeValues.filter((_, idx) => idx !== i))}
            className="absolute top-1 right-1 text-red-500 hover:bg-red-100 p-1 rounded"
          >
            <Trash2 size={12} />
          </button>

          {hasEntityField && (
             <div className="mb-2 flex items-center gap-2">
                <input 
                    type="checkbox"
                    checked={isAllOption}
                    onChange={e => {
                        const newValues = [...safeValues];
                        if (e.target.checked) {
                            newValues[i] = { ...item, entity: '*' };
                        } else {
                            newValues[i] = { ...item, entity: '' };
                        }
                        onChange(newValues);
                    }}
                    className="rounded border-slate-300"
                />
                <label className="text-[10px] text-slate-500 uppercase">Use 'All' Option</label>
             </div>
          )}

          <div className="grid gap-2">
            {fields.map(field => {
              if (isAllOption && field.key === 'entity') return null;

              return (
              <div key={field.key}>
                <label className="block text-[10px] text-slate-500 uppercase">{field.label}</label>
                {field.type === 'ha_entity_list' ? (
                  <EntityListInput 
                    label="" 
                    values={item[field.key] || []} 
                    onChange={v => {
                      const newValues = [...safeValues];
                      newValues[i] = { ...item, [field.key]: v };
                      onChange(newValues);
                    }}
                    haEntities={haEntities}
                  />
                ) : (
                  <input 
                    type="text" 
                    value={item[field.key] || ''} 
                    onChange={e => {
                      const newValues = [...safeValues];
                      newValues[i] = { ...item, [field.key]: e.target.value };
                      onChange(newValues);
                    }}
                    list={field.type === 'ha_entity' ? listId : undefined}
                    className="w-full border rounded p-1 text-xs"
                  />
                )}
              </div>
            )})}
          </div>
        </div>
      )})}
      <button 
        onClick={() => onChange([...safeValues, {}])}
        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
      >
        <Plus size={12} /> Add Item
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
