import { useState, useEffect } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { IconPicker, ColorPicker } from './Pickers';
import { apiFetch } from '../utils/api';

export const DisplayListInput = ({ value, onChange, tileType }: { value: any[], onChange: (v: any[]) => void, tileType?: string }) => {
  const [availableScripts, setAvailableScripts] = useState<{id: string, params: {name: string, type: string}[]}[]>([]);
  const [colors, setColors] = useState<{id: string, value: string}[]>([]);
  const [fonts, setFonts] = useState<string[]>([]);
  const [icons, setIcons] = useState<{value: string, label: string}[]>([]);

  const safeValue = Array.isArray(value) ? value : (value ? [value] : []);

  const fetchScripts = async () => {
    try {
      const res = await apiFetch('/scripts');
      if (res.ok) {
        const data = await res.json();
        setAvailableScripts((data.scripts || []).filter((s: any) => !s.id.startsWith('_')).sort((a: any, b: any) => a.id.localeCompare(b.id)));
        if (data.colors) setColors(data.colors);
        if (data.fonts) setFonts(data.fonts);
        if (data.icons) setIcons(data.icons);
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchScripts();
  }, []);

  return (
    <div className="mb-4">
      <label className="block text-xs font-medium text-slate-600 mb-1">Display Scripts</label>
      <div className="space-y-2">
        {safeValue.map((item, i) => {
          const scriptId = typeof item === 'string' ? item : Object.keys(item)[0];
          const params = typeof item === 'string' ? {} : item[scriptId];
          const scriptDef = availableScripts.find(s => s.id === scriptId);
          
          return (
            <div key={i} className="border rounded p-2 bg-slate-50 relative">
               <button 
                onClick={() => onChange(safeValue.filter((_, idx) => idx !== i))}
                className="absolute top-1 right-1 text-red-500 hover:bg-red-100 p-1 rounded"
              >
                <Trash2 size={12} />
              </button>
              
              <div className="mb-2">
                <label className="block text-[10px] text-slate-500 uppercase">Script</label>
                <select 
                  value={scriptId}
                  onChange={e => {
                    const newId = e.target.value;
                    // Reset params when script changes
                    const newValues = [...safeValue];
                    newValues[i] = newId; 
                    onChange(newValues);
                  }}
                  onFocus={fetchScripts}
                  className="w-full border rounded p-1 text-sm bg-white"
                >
                  <option value="">Select script...</option>
                  {availableScripts.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
                </select>
              </div>

              {scriptDef && scriptDef.params && scriptDef.params.length > 0 && (
                <div className="pl-2 border-l-2 border-slate-200 space-y-1">
                  {scriptDef.params.map(p => {
                    // Generic rule: if a display function gets a name:string, it should not appear in the UI
                    if (p.name === 'name' && p.type === 'string') {
                        return null;
                    }

                    // For toggle_entity, is_on is passed dynamically, so hide it from static config
                    if (tileType === 'toggle_entity' && p.name === 'is_on') {
                        return null;
                    }

                    let options: {value: string, label?: string}[] = [];
                    
                    if (p.name === 'icon') {
                        return (
                            <div key={p.name}>
                                <label className="block text-[10px] text-slate-500 uppercase">{p.name} <span className="text-slate-300">({p.type})</span></label>
                                <IconPicker 
                                    value={params[p.name] || ''}
                                    onChange={v => {
                                        const newParams = { ...params, [p.name]: v };
                                        const newValues = [...value];
                                        newValues[i] = { [scriptId]: newParams };
                                        onChange(newValues);
                                    }}
                                    icons={icons}
                                    onFocus={fetchScripts}
                                />
                            </div>
                        );
                    }

                    if (p.name === 'color' || p.type.includes('Color')) {
                        return (
                            <div key={p.name}>
                                <label className="block text-[10px] text-slate-500 uppercase">{p.name} <span className="text-slate-300">({p.type})</span></label>
                                <ColorPicker 
                                    value={params[p.name] || ''}
                                    onChange={v => {
                                        const newParams = { ...params, [p.name]: v };
                                        const newValues = [...safeValue];
                                        newValues[i] = { [scriptId]: newParams };
                                        onChange(newValues);
                                    }}
                                    colors={colors}
                                    onFocus={fetchScripts}
                                />
                            </div>
                        );
                    }

                    if (p.name === 'size') {
                        options = fonts.map(f => ({ value: f }));
                    }

                    if (options.length > 0) {
                        // Ensure value matches one of the options, or show it as custom if not found (but for size we expect it to be in the list)
                        // If the value is wrapped in id(), strip it for comparison if needed, but we already strip it in parser.
                        // However, if the value is "id(text_small)" and options has "text_small", the select won't match.
                        // The parser should have handled this, but let's be safe.
                        let currentValue = params[p.name] || '';
                        if (currentValue.startsWith('id(') && currentValue.endsWith(')')) {
                            currentValue = currentValue.substring(3, currentValue.length - 1);
                        }

                        return (
                            <div key={p.name}>
                                <label className="block text-[10px] text-slate-500 uppercase">{p.name} <span className="text-slate-300">({p.type})</span></label>
                                <select
                                    value={currentValue}
                                    onChange={e => {
                                        const newParams = { ...params, [p.name]: e.target.value };
                                        const newValues = [...safeValue];
                                        newValues[i] = { [scriptId]: newParams };
                                        onChange(newValues);
                                    }}
                                    onFocus={fetchScripts}
                                    className="w-full border rounded p-1 text-xs bg-white"
                                >
                                    <option value="">Select {p.name}...</option>
                                    {options.map((o, idx) => <option key={idx} value={o.value}>{o.label || o.value}</option>)}
                                </select>
                            </div>
                        );
                    }

                    return (
                    <div key={p.name}>
                      <label className="block text-[10px] text-slate-500 uppercase">{p.name} <span className="text-slate-300">({p.type})</span></label>
                      <input 
                        type="text"
                        value={params[p.name] || ''}
                        onChange={e => {
                          const newParams = { ...params, [p.name]: e.target.value };
                          const newValues = [...safeValue];
                          newValues[i] = { [scriptId]: newParams };
                          onChange(newValues);
                        }}
                        className="w-full border rounded p-1 text-xs"
                      />
                    </div>
                  )})}
                </div>
              )}
            </div>
          );
        })}
        <button 
          onClick={() => onChange([...safeValue, ''])}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          <Plus size={12} /> Add Script
        </button>
      </div>
    </div>
  );
};
