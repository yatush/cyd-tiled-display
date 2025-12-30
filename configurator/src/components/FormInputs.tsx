import { useState, useEffect } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { apiFetch } from '../utils/api';

export const TextInput = ({ label, value, onChange, haEntities }: { label: string, value: string, onChange: (v: string) => void, haEntities?: string[] }) => (
  <div className="mb-2">
    <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
    <input 
      type="text" 
      value={value || ''} 
      onChange={e => onChange(e.target.value)}
      list={haEntities ? "ha-entities" : undefined}
      className="w-full border rounded p-1 text-sm"
    />
    {haEntities && (
        <datalist id="ha-entities">
            {haEntities.map(e => <option key={e} value={e} />)}
        </datalist>
    )}
  </div>
);

export const ScriptInput = ({ label, value, onChange, type }: { label: string, value: string, onChange: (v: string) => void, type: 'display' | 'action' }) => {
  const [options, setOptions] = useState<string[]>([]);
  
  const fetchOptions = async () => {
    try {
      const res = await apiFetch('/scripts');
      if (res.ok) {
        const data = await res.json();
        setOptions(type === 'display' ? data.display.map((d:any) => d.id) : data.action);
      }
    } catch (e) {
      console.error("Failed to fetch scripts", e);
    }
  };

  useEffect(() => {
    fetchOptions();
  }, [type]);

  return (
    <div className="mb-2">
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <select 
        value={value || ''} 
        onChange={e => onChange(e.target.value)}
        onFocus={fetchOptions}
        className="w-full border rounded p-1 text-sm bg-white"
      >
        <option value="">Select script...</option>
        {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
      </select>
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
  values: string[], 
  onChange: (v: string[]) => void, 
  suggestionType?: 'display' | 'action',
  allowedValues?: string[]
}) => {
  const [options, setOptions] = useState<string[]>([]);

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
        setOptions(suggestionType === 'display' ? data.display.map((d:any) => d.id) : data.action);
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
      <div className="space-y-1">
        {safeValues.map((v, i) => (
          <div key={i} className="flex gap-1">
            {suggestionType || allowedValues ? (
                <select
                  value={v}
                  onChange={e => {
                    const newValues = [...safeValues];
                    newValues[i] = e.target.value;
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
                  value={v} 
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
        ))}
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
  haEntities?: string[]
}) => {
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);

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
              list="ha-entities"
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
        <button 
          onClick={() => onChange([...safeValues, ''])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Entity
        </button>
      </div>
      {haEntities && (
        <datalist id="ha-entities">
            {haEntities.map(e => <option key={e} value={e} />)}
        </datalist>
      )}
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

    fetch('/api/scripts').then(res => res.json()).then(data => {
        const all = [...(data.display || []).map((d:any) => d.id), ...(data.action || [])];
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
  haEntities?: string[]
}) => (
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
                        list="ha-entities"
                        className="w-full border rounded p-1 text-xs"
                    />
                    <datalist id="ha-entities">
                        {haEntities.map(e => <option key={e} value={e} />)}
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
  haEntities?: string[]
}) => {
  const safeValues = Array.isArray(values) ? values : (values ? [values] : []);

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
                  list="ha-entities"
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
                  list="ha-entities"
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
        <datalist id="ha-entities">
            {haEntities.map(e => <option key={e} value={e} />)}
        </datalist>
    )}
  </div>
  );
};

export const ObjectArrayInput = ({ label, values, fields, onChange, haEntities }: { 
  label: string, 
  values: any[], 
  fields: { key: string, label: string, type?: string }[],
  onChange: (v: any[]) => void,
  haEntities?: string[]
}) => {
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
                    list={field.type === 'ha_entity' ? "ha-entities" : undefined}
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
        <datalist id="ha-entities">
            {haEntities.map(e => <option key={e} value={e} />)}
        </datalist>
    )}
  </div>
);
};
