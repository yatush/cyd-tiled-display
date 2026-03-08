import React, { useState, useEffect, useRef } from 'react';
import { Trash2, Plus, Upload, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { HaEntity, ImageEntry } from '../types';
import { IconPicker, ColorPicker } from './Pickers';

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
    <div className="border rounded p-2 bg-white mb-2 overflow-hidden">
        <div className="flex items-center gap-2 mb-2 min-w-0">
            <select 
                value={type} 
                onChange={e => handleTypeChange(e.target.value)}
                className="flex-shrink-0 border rounded p-1 text-xs font-bold bg-slate-100"
            >
                <option value="leaf">Condition</option>
                <option value="and">AND</option>
                <option value="or">OR</option>
                <option value="not">NOT</option>
            </select>
            {type === 'leaf' && (
                <div className="flex-1 min-w-0">
                    <select 
                        value={value as string} 
                        onChange={e => onChange(e.target.value)}
                        className="w-full min-w-0 border rounded p-1 text-xs"
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
// Custom thumbnail picker (upload is handled by ImageManagerPanel in the left sidebar).

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
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageIds = Object.keys(images || {});
  const isNone = value === 'none';
  const selected = !isNone && value && images?.[value] ? images[value] : null;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleToggle = () => {
    if (!open && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      setDropUp(spaceBelow < 280);
    }
    setOpen(o => !o);
  };

  return (
    <div className="relative" ref={containerRef}>
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}

      {/* Trigger button */}
      <button
        type="button"
        onClick={handleToggle}
        className="w-full flex items-center gap-2 border rounded p-1 bg-white hover:bg-slate-50 text-sm text-left min-w-0"
      >
        {isNone ? (
          <>
            <span className="flex-shrink-0 h-8 w-8 flex items-center justify-center rounded bg-slate-100 text-slate-400 text-xs font-mono">∅</span>
            <span className="truncate flex-1 text-slate-500 italic">none</span>
          </>
        ) : selected ? (
          <>
            <img
              src={`data:image/png;base64,${selected.data}`}
              alt={selected.filename}
              className="flex-shrink-0 h-8 w-8 object-contain rounded bg-slate-100"
            />
            <span className="truncate flex-1 text-slate-700" title={value}>{value}</span>
          </>
        ) : (
          <span className="flex-1 text-slate-400">— select image —</span>
        )}
        <svg className="flex-shrink-0 w-3 h-3 text-slate-400" viewBox="0 0 10 6" fill="none">
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className={`absolute z-50 bg-white border rounded shadow-lg p-2 w-56 max-h-64 overflow-y-auto ${dropUp ? 'bottom-full mb-1' : 'mt-1'}`}>
          {/* Always-available "none" option */}
          <button
            type="button"
            onClick={() => { onChange('none'); setOpen(false); }}
            className={`flex items-center gap-2 w-full px-2 py-1 rounded border mb-2 text-left hover:bg-blue-50 hover:border-blue-300 transition-colors ${value === 'none' ? 'border-blue-400 bg-blue-50' : 'border-slate-200'}`}
            title="none — no image (e.g. for animations that don't start from the first frame)"
          >
            <span className="h-8 w-8 flex items-center justify-center rounded bg-slate-100 text-slate-400 text-xs font-mono flex-shrink-0">∅</span>
            <span className="text-xs text-slate-500 italic">none</span>
          </button>
          {imageIds.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-2">No images uploaded yet</p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {imageIds.map(id => (
                <button
                  key={id}
                  type="button"
                  onClick={() => { onChange(id); setOpen(false); }}
                  className={`flex flex-col items-center gap-0.5 p-1 rounded border text-center hover:bg-blue-50 hover:border-blue-300 transition-colors ${value === id ? 'border-blue-400 bg-blue-50' : 'border-transparent'}`}
                  title={id}
                >
                  <img
                    src={`data:image/png;base64,${images[id].data}`}
                    alt={id}
                    className="h-12 w-12 object-contain rounded bg-slate-100"
                  />
                  <span className="text-[9px] text-slate-500 truncate w-full leading-tight">{id}</span>
                </button>
              ))}
            </div>
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
  onUpdateImage,
}: {
  images: Record<string, ImageEntry>;
  onAddImage: (id: string, entry: ImageEntry) => void;
  onDeleteImage: (id: string) => void;
  onUpdateImage?: (id: string, patch: Partial<ImageEntry>) => void;
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
        const scale = entry.scale ?? 100;
        // Filled portion of the slider track (scale range is 10–100 → map to 0–100%)
        const fillPct = ((scale - 10) / 90) * 100;
        const trackStyle = {
          background: `linear-gradient(to right, #3b82f6 ${fillPct}%, #e2e8f0 ${fillPct}%)`,
        };
        return (
          <div key={id} className="p-1.5 border rounded bg-white hover:bg-slate-50">
            <div className="flex items-center gap-2">
              <img
                src={`data:image/png;base64,${entry.data}`}
                alt={entry.filename}
                className="flex-shrink-0 w-8 h-8 object-contain border rounded bg-slate-100"
              />
              <div className="flex-1 min-w-0">
                <div className="text-[10px] font-bold text-blue-700 truncate">{id}</div>
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
            {/* Scale slider — how much of the tile the image fills (5 px padding always kept) */}
            <div className="mt-1.5 flex items-center gap-1.5 pl-0.5 pr-1" title="Image size: % of tile area (5 px padding always applied)">
              <input
                type="range"
                min={10}
                max={100}
                step={5}
                value={scale}
                onChange={e => onUpdateImage?.(id, { scale: Number(e.target.value) })}
                className="flex-1 h-1.5 rounded-full cursor-pointer"
                style={trackStyle}
              />
              <span className="text-[9px] font-bold text-slate-500 w-7 text-right flex-shrink-0">{scale}%</span>
            </div>
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
// Unified list of images, each with an optional condition and optional animation.
// All entries whose condition is true are rendered, in order (first = bottom layer, last = top layer).
// An entry without a condition is always drawn.

// Fractional position grid for animation from/to selection.
// Positions are encoded as [x, y] where x and y are fractions of 1 in 0.05 steps.
// Top-left is [0, 0], bottom-right is [1, 1].

const FRAC_STEPS = 21; // 0.00 to 1.00 in 0.05 increments
const FRAC_STEP = 0.05;

type AnimPos = [number, number]; // [x, y]

const DEFAULT_ANIM_POS: AnimPos = [0.5, 0.5];

function fracSnap(v: number): number {
  return Math.round(Math.round(v / FRAC_STEP) * FRAC_STEP * 100) / 100;
}

/** Interactive fractional position picker: 21×21 grid (0.00–1.00 in 0.05 steps).
 *  Click a cell to move the indicator. Selected value shown below. */
const FractionalPositionPicker = ({
  value,
  onChange,
  label,
  ghostPoint,
}: { value: AnimPos; onChange: (v: AnimPos) => void; label: string; ghostPoint?: AnimPos }) => {
  const [x, y] = value;
  const CELL = 5; // px per cell (~50% of original)
  const SIZE = CELL * (FRAC_STEPS - 1); // total canvas size

  return (
    <div className="select-none">
      <label className="block text-[10px] text-slate-500 uppercase mb-1">{label}</label>
      {/* Grid area — tabIndex makes it focusable for keyboard control */}
      <div
        tabIndex={0}
        className="relative border border-slate-300 rounded bg-white cursor-crosshair outline-none focus:ring-2 focus:ring-blue-400"
        style={{ width: SIZE + 1, height: SIZE + 1 }}
        onClick={e => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - rect.left;
          const py = e.clientY - rect.top;
          // Snap to nearest 0.05 grid line (cell center) rather than raw pixel position
          const nx = fracSnap(Math.max(0, Math.min(1, px / SIZE)));
          const ny = fracSnap(Math.max(0, Math.min(1, py / SIZE)));
          onChange([nx, ny]);
        }}
        onKeyDown={e => {
          const ARROW_KEYS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
          if (!ARROW_KEYS.includes(e.key)) return;
          e.preventDefault();
          const [cx, cy] = value;
          if (e.key === 'ArrowLeft')  onChange([fracSnap(Math.max(0, cx - FRAC_STEP)), cy]);
          if (e.key === 'ArrowRight') onChange([fracSnap(Math.min(1, cx + FRAC_STEP)), cy]);
          if (e.key === 'ArrowUp')    onChange([cx, fracSnap(Math.max(0, cy - FRAC_STEP))]);
          if (e.key === 'ArrowDown')  onChange([cx, fracSnap(Math.min(1, cy + FRAC_STEP))]);
        }}
      >
        {/* Grid lines */}
        {Array.from({ length: FRAC_STEPS }).map((_, i) => {
          const pct = (i / (FRAC_STEPS - 1)) * 100;
          const isMajor = i % 2 === 0; // every 0.10
          return (
            <React.Fragment key={i}>
              <div
                className="absolute top-0 bottom-0 pointer-events-none"
                style={{ left: `${pct}%`, width: 1, background: isMajor ? '#cbd5e1' : '#f1f5f9' }}
              />
              <div
                className="absolute left-0 right-0 pointer-events-none"
                style={{ top: `${pct}%`, height: 1, background: isMajor ? '#cbd5e1' : '#f1f5f9' }}
              />
            </React.Fragment>
          );
        })}
        {/* Ghost point: previous step's "to" position */}
        {ghostPoint && (
          <div
            className="absolute pointer-events-none"
            style={{
              left: `${ghostPoint[0] * 100}%`,
              top: `${ghostPoint[1] * 100}%`,
              transform: 'translate(-50%, -50%)',
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: '#94a3b8',
              border: '1.5px solid #64748b',
            }}
          />
        )}
        {/* Selected point indicator — use % to align exactly with the % grid lines */}
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${x * 100}%`,
            top: `${y * 100}%`,
            transform: 'translate(-50%, -50%)',
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: '#3b82f6',
            border: '1.5px solid #1d4ed8',
            boxShadow: '0 0 0 1.5px #bfdbfe',
          }}
        />
      </div>
      {/* Value readout */}
      <div className="mt-1 text-[10px] text-slate-600 font-mono text-center">
        ({x.toFixed(2)}, {y.toFixed(2)})
      </div>
    </div>
  );
};

// Animation step: from/to positions + duration + optional per-step image or icon override.
// from/to are [x, y] fractions (0.0–1.0 in 0.05 steps), top-left=[0,0] bottom-right=[1,1].
type AnimStep = { from: AnimPos; to: AnimPos; duration: number; image?: string; icon?: string; icon_color?: string; icon_size?: string; };
// Animation config: either flat single-step or multi-step with 'steps' array.
type AnimConfig = { from: AnimPos; to: AnimPos; duration: number }
               | { steps: AnimStep[] };

/** Normalize a from/to position value from [x,y] array form to AnimPos. */
function normalizePos(pos: any): AnimPos {
  if (Array.isArray(pos) && pos.length === 2 && typeof pos[0] === 'number') {
    return [fracSnap(pos[0]), fracSnap(pos[1])];
  }
  return DEFAULT_ANIM_POS;
}

function toSteps(anim: AnimConfig): AnimStep[] {
  if ('steps' in anim && Array.isArray(anim.steps)) {
    return anim.steps.map(s => ({ ...s, from: normalizePos(s.from), to: normalizePos(s.to) }));
  }
  const { from, to, duration } = anim as any;
  return [{ from: normalizePos(from ?? DEFAULT_ANIM_POS), to: normalizePos(to ?? DEFAULT_ANIM_POS), duration: duration ?? 3 }];
}
function fromSteps(steps: AnimStep[]): AnimConfig {
  if (steps.length === 1) {
    const { from, to, duration, image, icon, icon_color, icon_size } = steps[0];
    const r: any = { from, to, duration };
    if (image !== undefined) r.image = image;
    if (icon !== undefined) { r.icon = icon; r.icon_color = icon_color; r.icon_size = icon_size; }
    return r;
  }
  return { steps };
}

type ImageRow = {
  // Exactly one of image or icon should be set
  image?: string;
  icon?: string;
  icon_color?: string;
  icon_size?: string;
  condition?: any;
  animation?: AnimConfig;
};

export const ImagesListInput = ({
  value,
  onChange,
  images,
}: {
  value: ImageRow[];
  onChange: (v: ImageRow[]) => void;
  images: Record<string, ImageEntry>;
}) => {
  const rows: ImageRow[] = Array.isArray(value) ? value : [];

  // Fetch icons, colors, fonts for icon entries
  const [iconList, setIconList] = useState<{value: string, label: string}[]>([]);
  const [colorList, setColorList] = useState<{id: string, value: string}[]>([]);
  const [fontList, setFontList] = useState<string[]>([]);

  useEffect(() => {
    apiFetch('/scripts').then(async res => {
      if (res.ok) {
        const data = await res.json();
        if (data.icons) setIconList(data.icons);
        if (data.colors) setColorList(data.colors);
        if (data.fonts) setFontList(data.fonts);
      }
    }).catch(() => {});
  }, []);

  const updateRow = (idx: number, patch: Partial<typeof rows[0]>) => {
    onChange(rows.map((r, i) => i === idx ? { ...r, ...patch } : r));
  };

  const removeRow = (idx: number) => onChange(rows.filter((_, i) => i !== idx));

  const toggleCondition = (idx: number, checked: boolean) => {
    if (checked) {
      updateRow(idx, { condition: '' });
    } else {
      const { condition: _c, ...rest } = rows[idx];
      onChange(rows.map((r, i) => i === idx ? rest : r));
    }
  };

  const toggleAnimation = (idx: number, checked: boolean) => {
    if (checked) {
      updateRow(idx, { animation: { from: DEFAULT_ANIM_POS, to: DEFAULT_ANIM_POS, duration: 3 } });
    } else {
      const { animation: _a, ...rest } = rows[idx];
      onChange(rows.map((r, i) => i === idx ? rest : r));
    }
  };

  // Render one animation step's controls.
  // Each step independently chooses Image or Icon mode via its own toggle (shown in multi-step).
  const renderStep = (step: AnimStep, si: number, steps: AnimStep[], updateSteps: (s: AnimStep[]) => void) => {
    const updateStep = (patch: Partial<AnimStep>) =>
      updateSteps(steps.map((s, i) => i === si ? { ...s, ...patch } : s));
    const isMulti = steps.length > 1;
    const isIconStep = step.icon !== undefined;

    const switchStepToImage = () => {
      const { icon: _i, icon_color: _c, icon_size: _s, ...rest } = step as any;
      updateSteps(steps.map((s, i) => i === si ? rest : s));
    };
    const switchStepToIcon = () => {
      const { image: _img, ...rest } = step as any;
      updateSteps(steps.map((s, i) => i === si ? { ...rest, icon: '', icon_color: 'white', icon_size: 'big' } : s));
    };

    return (
      <div key={si} className={isMulti ? "border border-slate-100 rounded p-2 space-y-1.5" : "space-y-1.5"}>
        {isMulti && (
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-blue-500 uppercase font-semibold">Step {si + 1}</span>
            <div className="flex items-center gap-1">
              {/* Per-step Image/Icon toggle — only for steps 1+ (step 0 inherits from the row toggle) */}
              {si > 0 && (
                <div className="flex rounded border border-slate-200 overflow-hidden text-[9px]">
                  <button
                    type="button"
                    onClick={switchStepToImage}
                    className={`px-1.5 py-0.5 ${!isIconStep ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use image for this step"
                  >Image</button>
                  <button
                    type="button"
                    onClick={switchStepToIcon}
                    className={`px-1.5 py-0.5 ${isIconStep ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use icon for this step"
                  >Icon</button>
                </div>
              )}
              <button
                type="button"
                onClick={() => updateSteps(steps.filter((_, i) => i !== si))}
                className="text-red-400 hover:text-red-600 p-0.5 rounded"
                title="Remove step"
              ><Trash2 size={12} /></button>
            </div>
          </div>
        )}
        <div className="flex gap-4 items-start flex-wrap">
          <FractionalPositionPicker
            value={normalizePos(step.from ?? DEFAULT_ANIM_POS)}
            onChange={v => updateStep({ from: v })}
            label="From"
            ghostPoint={si > 0 ? normalizePos(steps[si - 1].to ?? DEFAULT_ANIM_POS) : undefined}
          />
          <div className="flex items-center self-center pt-4 text-slate-400 text-lg">→</div>
          <FractionalPositionPicker
            value={normalizePos(step.to ?? DEFAULT_ANIM_POS)}
            onChange={v => updateStep({ to: v })}
            label="To"
          />
        </div>
        <div>
          <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Duration (seconds)</label>
          <input
            type="number" min={0.5} step={0.5} value={step.duration}
            onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v) && v > 0) updateStep({ duration: v }); }}
            className="w-full border rounded p-1 text-xs"
          />
        </div>
        {/* Per-step image override (steps 1+ only) */}
        {!isIconStep && si > 0 && (
          <div>
            <div className="flex items-center gap-1 mb-0.5">
              <label className="block text-[10px] text-slate-500 uppercase">Image</label>
              <span className="text-[9px] text-slate-400">(overrides row image)</span>
              {step.image && (
                <button
                  type="button"
                  onClick={() => { const { image: _i, ...rest } = step as any; updateSteps(steps.map((s, i) => i === si ? rest : s)); }}
                  className="ml-auto text-slate-400 hover:text-slate-600 p-0.5 rounded"
                  title="Clear — inherit row image"
                ><X size={10} /></button>
              )}
            </div>
            <ImageSelectInput
              value={step.image ?? ''}
              onChange={v => updateStep({ image: v })}
              images={images}
            />
          </div>
        )}
        {/* Per-step icon UI */}
        {isIconStep && (
          <div className="space-y-1">
            <label className="block text-[10px] text-slate-500 uppercase">Icon</label>
            <IconPicker
              value={step.icon ?? ''}
              onChange={v => updateStep({ icon: v })}
              icons={iconList}
            />
            <div className="flex gap-2">
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Color</label>
                <ColorPicker
                  value={step.icon_color ?? 'white'}
                  onChange={v => updateStep({ icon_color: v })}
                  colors={colorList}
                />
              </div>
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Size</label>
                <select
                  value={step.icon_size ?? 'big'}
                  onChange={e => updateStep({ icon_size: e.target.value })}
                  className="w-full border rounded p-1 text-xs bg-white"
                >
                  {fontList.length === 0 && <option value="big">big</option>}
                  {fontList.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}

      </div>
    );
  };

  return (
    <div className="space-y-2">
      {rows.map((row, idx) => {
        const hasCondition = 'condition' in row;
        const hasAnimation = !!row.animation;
        const isIconRow = row.icon !== undefined;

        const switchToImage = () => {
          const { icon: _i, icon_color: _c, icon_size: _s, ...rest } = row as any;
          onChange(rows.map((r, i) => i === idx ? { ...rest, image: '' } : r));
        };
        const switchToIcon = () => {
          const { image: _m, ...rest } = row as any;
          onChange(rows.map((r, i) => i === idx ? { ...rest, icon: '', icon_color: 'white', icon_size: 'big' } : r));
        };

        return (
          <div key={idx} className="border rounded p-2 bg-white">
            {/* Row header: label + Image/Icon toggle + remove */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-slate-500 uppercase font-medium">Layer {idx + 1}</span>
              <div className="flex items-center gap-1">
                {/* Image / Icon toggle */}
                <div className="flex rounded border border-slate-200 overflow-hidden text-[9px]">
                  <button
                    type="button"
                    onClick={switchToImage}
                    className={`px-1.5 py-0.5 ${!isIconRow ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use image"
                  >Image</button>
                  <button
                    type="button"
                    onClick={switchToIcon}
                    className={`px-1.5 py-0.5 ${isIconRow ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use icon"
                  >Icon</button>
                </div>
                <button
                  type="button"
                  onClick={() => removeRow(idx)}
                  className="text-red-400 hover:text-red-600 p-0.5 rounded"
                  title="Remove"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            {/* Image selector */}
            {!isIconRow && (
              <div className="mb-2">
                <ImageSelectInput
                  value={row.image ?? ''}
                  onChange={v => updateRow(idx, { image: v })}
                  images={images}
                />
              </div>
            )}

            {/* Icon selector */}
            {isIconRow && (
              <div className="mb-2 space-y-1">
                <label className="block text-[10px] text-slate-500 uppercase">Icon</label>
                <IconPicker
                  value={row.icon ?? ''}
                  onChange={v => updateRow(idx, { icon: v })}
                  icons={iconList}
                />
                <div className="flex gap-2">
                  <div className="flex-1 min-w-0">
                    <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Color</label>
                    <ColorPicker
                      value={row.icon_color ?? 'white'}
                      onChange={v => updateRow(idx, { icon_color: v })}
                      colors={colorList}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Size</label>
                    <select
                      value={row.icon_size ?? 'big'}
                      onChange={e => updateRow(idx, { icon_size: e.target.value })}
                      className="w-full border rounded p-1 text-xs bg-white"
                    >
                      {fontList.length === 0 && <option value="big">big</option>}
                      {fontList.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* Condition */}
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

            {/* Animation */}
            <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer select-none mt-2">
              <input
                type="checkbox"
                checked={hasAnimation}
                onChange={e => toggleAnimation(idx, e.target.checked)}
                className="rounded border-slate-300"
              />
              Animate
            </label>
            {hasAnimation && (() => {
              const steps = toSteps(row.animation!);
              const updateSteps = (newSteps: AnimStep[]) =>
                updateRow(idx, { animation: newSteps.length ? fromSteps(newSteps) : undefined });
              return (
                <div className="mt-1 pl-2 border-l-2 border-blue-100 space-y-2">
                  {steps.map((step, si) => renderStep(step, si, steps, updateSteps))}
                  <button
                    type="button"
                    onClick={() => {
                      // For icon rows: materialize entry-level icon into any un-configured steps,
                      // and default the new step to icon mode as well.
                      const iconDefaults = isIconRow
                        ? { icon: row.icon ?? '', icon_color: row.icon_color ?? 'white', icon_size: row.icon_size ?? 'big' }
                        : {};
                      const normalizedSteps = isIconRow
                        ? steps.map(s =>
                            s.icon === undefined
                              ? { ...s, ...iconDefaults }
                              : s
                          )
                        : steps;
                      updateSteps([...normalizedSteps, { from: DEFAULT_ANIM_POS, to: DEFAULT_ANIM_POS, duration: 3, ...iconDefaults }]);
                    }}
                    className="w-full text-xs text-purple-500 border border-dashed border-purple-200 rounded py-0.5 hover:bg-purple-50 flex items-center justify-center gap-1"
                  ><Plus size={10} /> Add step</button>
                </div>
              );
            })()}
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, { image: '' }])}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1 hover:bg-blue-50 flex items-center justify-center gap-1"
      >
        <Plus size={12} /> Add Image / Icon
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
