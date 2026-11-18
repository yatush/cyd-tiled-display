import { useState, useEffect } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { apiFetch } from '../utils/api';

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
               Array.isArray(value) ? 'or' : 'leaf';

  const handleTypeChange = (newType: string) => {
    if (newType === 'leaf') onChange('');
    else if (newType === 'and') onChange({ operator: 'AND', conditions: [] });
    else if (newType === 'or') onChange({ operator: 'OR', conditions: [] });
    else if (newType === 'not') onChange({ operator: 'NOT', conditions: '' });
  };

  const conditions = value?.conditions ?? (value?.and || value?.or || value?.not || (Array.isArray(value) ? value : []));

  const renderGroup = (op: 'AND' | 'OR', borderColor: string) => (
    <div className={`pl-4 border-l-2 ${borderColor} space-y-2`}>
      {(Array.isArray(conditions) ? conditions : []).map((item: any, idx: number) => (
        <div key={idx} className="flex gap-2 items-start">
          <div className="flex-1">
            <ConditionBuilder
              value={item}
              scriptOptions={options}
              onChange={newItem => {
                const newConditions = [...(Array.isArray(conditions) ? conditions : [])];
                newConditions[idx] = newItem;
                onChange({ operator: op, conditions: newConditions });
              }}
            />
          </div>
          <button
            onClick={() => {
              const newConditions = (Array.isArray(conditions) ? conditions : []).filter((_: any, i: number) => i !== idx);
              onChange({ operator: op, conditions: newConditions });
            }}
            className="text-red-500 p-1"
          ><Trash2 size={14} /></button>
        </div>
      ))}
      <button
        onClick={() => onChange({ operator: op, conditions: [...(Array.isArray(conditions) ? conditions : []), ''] })}
        className="text-xs text-blue-600 flex items-center gap-1"
      >
        <Plus size={12} /> Add Condition
      </button>
    </div>
  );

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

      {type === 'and' && renderGroup('AND', 'border-blue-200')}
      {type === 'or' && renderGroup('OR', 'border-orange-200')}
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
