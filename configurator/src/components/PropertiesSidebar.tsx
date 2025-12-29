import { Trash2 } from 'lucide-react';
import { Tile, Config, Page } from '../types';
import { 
  TextInput, 
  Checkbox, 
  ScriptInput, 
  ArrayInput, 
  ObjectInput, 
  ObjectArrayInput, 
  EntityArrayInput, 
  EntityListInput,
  ConditionBuilder
} from './FormInputs';
import { DisplayListInput } from './DisplayListInput';

export const Sidebar = ({ selectedTile, onUpdate, onDelete, config, schema, activePage, onUpdatePage, haEntities }: { 
  selectedTile: Tile | null, 
  onUpdate: (t: Tile) => void, 
  onDelete: () => void,
  config: Config,
  schema: any,
  activePage: Page,
  onUpdatePage: (p: Page) => void,
  haEntities: string[]
}) => {
  if (!selectedTile) {
    return (
      <div className="p-4 space-y-4">
        <div className="border-b pb-2">
          <h2 className="font-bold text-lg">Page Properties</h2>
          <div className="text-xs text-slate-500">{activePage.id}</div>
        </div>
        
        <div>
          <label className="block text-xs font-medium text-slate-500 uppercase mb-2">Flags</label>
          <ArrayInput 
            label="Page Flags" 
            values={activePage.flags || []} 
            onChange={v => onUpdatePage({...activePage, flags: v})} 
            allowedValues={['BASE', 'TEMPORARY', 'FAST_REFRESH']}
          />
        </div>
      </div>
    );
  }

  const dynamicEntities = config.dynamic_entities || [];
  const tileSchema = schema?.types?.find((t: any) => t.type === selectedTile.type);
  
  return (
    <div className="p-4 space-y-4 pb-20">
      <div className="flex justify-between items-center border-b pb-2">
        <h2 className="font-bold text-lg">Edit Tile</h2>
        <button onClick={() => onDelete()} className="text-red-500 hover:bg-red-50 p-1 rounded" title="Delete Tile">
          <Trash2 size={16} />
        </button>
      </div>
      
      <div>
        <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Common</label>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <div>
            <label className="block text-xs text-slate-600">Type</label>
            <div className="p-1 bg-slate-100 rounded text-sm font-mono">{selectedTile.type}</div>
          </div>
          <div className="flex gap-2">
            {schema?.common?.filter((f: any) => f.name === 'x' || f.name === 'y').map((field: any) => (
              <div key={field.name} className="flex-1">
                <label className="block text-xs text-slate-600">{field.label}</label>
                <input 
                  type="number" 
                  value={selectedTile[field.name]} 
                  onChange={e => onUpdate({...selectedTile, [field.name]: parseInt(e.target.value)})}
                  className="w-full border rounded p-1 text-sm"
                />
              </div>
            ))}
          </div>
        </div>
        
        {schema?.common?.filter((f: any) => f.name !== 'x' && f.name !== 'y').map((field: any) => {
           if (field.type === 'display_list') {
             return (
                <DisplayListInput 
                  key={field.name}
                  value={Array.isArray(selectedTile[field.name]) ? selectedTile[field.name] : (selectedTile[field.name] ? [selectedTile[field.name]] : [])} 
                  onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                  tileType={selectedTile.type}
                />
             );
           }
           if (field.type === 'boolean') {
             return (
                <Checkbox 
                  key={field.name}
                  label={field.label} 
                  checked={selectedTile[field.name] || false} 
                  onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                />
             );
           }
           if (field.type === 'condition_logic') {
                if (field.optional) {
                    const isEnabled = selectedTile[field.name] !== undefined;
                    return (
                        <div key={field.name} className="mb-4 border rounded p-2 bg-slate-50">
                            <div className="flex items-center gap-2 mb-2">
                                <input 
                                    type="checkbox" 
                                    checked={isEnabled} 
                                    onChange={e => {
                                        if (e.target.checked) {
                                            onUpdate({...selectedTile, [field.name]: ''});
                                        } else {
                                            const newTile = {...selectedTile};
                                            delete newTile[field.name];
                                            onUpdate(newTile);
                                        }
                                    }}
                                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                />
                                <label className="text-xs font-medium text-slate-600 uppercase select-none cursor-pointer" onClick={() => {
                                    if (!isEnabled) onUpdate({...selectedTile, [field.name]: ''});
                                    else {
                                        const newTile = {...selectedTile};
                                        delete newTile[field.name];
                                        onUpdate(newTile);
                                    }
                                }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                                <div className="pl-2">
                                    <ConditionBuilder 
                                        value={selectedTile[field.name] || ''} 
                                        onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                                    />
                                </div>
                            )}
                        </div>
                    );
                }
                return (
                    <div key={field.name} className="mb-4">
                        <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                        <ConditionBuilder 
                            value={selectedTile[field.name] || ''} 
                            onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                        />
                    </div>
                );
           }
           if (field.type === 'object') {
                if (field.optional) {
                    const isEnabled = selectedTile[field.name] !== undefined;
                    return (
                        <div key={field.name} className="mb-4 border rounded p-2 bg-slate-50">
                            <div className="flex items-center gap-2 mb-2">
                                <input 
                                    type="checkbox" 
                                    checked={isEnabled} 
                                    onChange={e => {
                                        if (e.target.checked) {
                                            onUpdate({...selectedTile, [field.name]: {}});
                                        } else {
                                            const newTile = {...selectedTile};
                                            delete newTile[field.name];
                                            onUpdate(newTile);
                                        }
                                    }}
                                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                />
                                <label className="text-xs font-medium text-slate-600 uppercase select-none cursor-pointer" onClick={() => {
                                    if (!isEnabled) onUpdate({...selectedTile, [field.name]: {}});
                                    else {
                                        const newTile = {...selectedTile};
                                        delete newTile[field.name];
                                        onUpdate(newTile);
                                    }
                                }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                                <div className="pl-2">
                                    <ObjectInput 
                                        label="" 
                                        value={selectedTile[field.name] || {}} 
                                        fields={field.objectFields}
                                        onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                                        dynamicEntities={dynamicEntities}
                                        haEntities={haEntities}
                                    />
                                </div>
                            )}
                        </div>
                    );
                }
                return (
                    <ObjectInput 
                      key={field.name}
                      label={field.label} 
                      value={selectedTile[field.name] || {}} 
                      fields={field.objectFields}
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      dynamicEntities={dynamicEntities}
                      haEntities={haEntities}
                    />
                );
           }
           return null;
        })}
      </div>

      <div className="border-t pt-4">
        <label className="block text-xs font-medium text-slate-500 uppercase mb-2">Specific Properties</label>
        
        {tileSchema?.fields?.map((field: any) => {
            if (field.type === 'string' || field.type === 'ha_entity') {
                return (
                    <TextInput 
                      key={field.name}
                      label={field.label} 
                      value={selectedTile[field.name] || ''} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      haEntities={field.type === 'ha_entity' ? haEntities : undefined}
                    />
                );
            }
            if (field.type === 'ha_entity_list') {
                return (
                    <EntityListInput 
                      key={field.name}
                      label={field.label} 
                      values={selectedTile[field.name] || []} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      haEntities={haEntities}
                    />
                );
            }
            if (field.type === 'boolean') {
                return (
                    <Checkbox 
                      key={field.name}
                      label={field.label} 
                      checked={selectedTile[field.name] || false} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                    />
                );
            }
            if (field.type === 'script') {
                return (
                    <ScriptInput 
                      key={field.name}
                      label={field.label} 
                      value={selectedTile[field.name] || ''} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      type={field.scriptType}
                    />
                );
            }
            if (field.type === 'script_list') {
                return (
                    <ArrayInput 
                      key={field.name}
                      label={field.label} 
                      values={selectedTile[field.name] || []} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      suggestionType={field.scriptType}
                    />
                );
            }
            if (field.type === 'entity_list') {
                return (
                    <EntityArrayInput 
                      key={field.name}
                      label={field.label} 
                      values={selectedTile[field.name] || []} 
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      dynamicEntities={dynamicEntities}
                      haEntities={haEntities}
                    />
                );
            }
            if (field.type === 'object') {
                if (field.optional) {
                    const isEnabled = selectedTile[field.name] !== undefined;
                    return (
                        <div key={field.name} className="mb-4 border rounded p-2 bg-slate-50">
                            <div className="flex items-center gap-2 mb-2">
                                <input 
                                    type="checkbox" 
                                    checked={isEnabled} 
                                    onChange={e => {
                                        if (e.target.checked) {
                                            onUpdate({...selectedTile, [field.name]: {}});
                                        } else {
                                            const newTile = {...selectedTile};
                                            delete newTile[field.name];
                                            onUpdate(newTile);
                                        }
                                    }}
                                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                />
                                <label className="text-xs font-medium text-slate-600 uppercase select-none cursor-pointer" onClick={() => {
                                    if (!isEnabled) onUpdate({...selectedTile, [field.name]: {}});
                                    else {
                                        const newTile = {...selectedTile};
                                        delete newTile[field.name];
                                        onUpdate(newTile);
                                    }
                                }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                                <div className="pl-2">
                                    <ObjectInput 
                                        label="" 
                                        value={selectedTile[field.name] || {}} 
                                        fields={field.objectFields}
                                        onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                                        dynamicEntities={dynamicEntities}
                                        haEntities={haEntities}
                                    />
                                </div>
                            )}
                        </div>
                    );
                }
                return (
                    <ObjectInput 
                      key={field.name}
                      label={field.label} 
                      value={selectedTile[field.name] || {}} 
                      fields={field.objectFields}
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      dynamicEntities={dynamicEntities}
                      haEntities={haEntities}
                    />
                );
            }
            if (field.type === 'object_list') {
                return (
                    <ObjectArrayInput 
                      key={field.name}
                      label={field.label} 
                      values={selectedTile[field.name] || []} 
                      fields={field.objectFields}
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})} 
                      haEntities={haEntities}
                    />
                );
            }
            if (field.type === 'page_select') {
                if (field.optional) {
                    const isEnabled = selectedTile[field.name] !== undefined;
                    return (
                        <div key={field.name} className="mb-4 border rounded p-2 bg-slate-50">
                            <div className="flex items-center gap-2 mb-2">
                                <input 
                                    type="checkbox" 
                                    checked={isEnabled} 
                                    onChange={e => {
                                        if (e.target.checked) {
                                            onUpdate({...selectedTile, [field.name]: config.pages[0].id});
                                        } else {
                                            const newTile = {...selectedTile};
                                            delete newTile[field.name];
                                            onUpdate(newTile);
                                        }
                                    }}
                                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                />
                                <label className="text-xs font-medium text-slate-600 uppercase select-none cursor-pointer" onClick={() => {
                                    if (!isEnabled) onUpdate({...selectedTile, [field.name]: config.pages[0].id});
                                    else {
                                        const newTile = {...selectedTile};
                                        delete newTile[field.name];
                                        onUpdate(newTile);
                                    }
                                }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                                <div className="pl-2">
                                    <select 
                                        value={selectedTile[field.name] || ''} 
                                        onChange={e => onUpdate({...selectedTile, [field.name]: e.target.value})} 
                                        className="w-full border rounded p-1 text-sm bg-white"
                                    >
                                        <option value="">Select page...</option>
                                        {config.pages.map(p => <option key={p.id} value={p.id}>{p.id}</option>)}
                                    </select>
                                </div>
                            )}
                        </div>
                    );
                }
                return (
                    <div key={field.name} className="mb-2">
                        <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                        <select 
                          value={selectedTile[field.name] || ''} 
                          onChange={e => onUpdate({...selectedTile, [field.name]: e.target.value})} 
                          className="w-full border rounded p-1 text-sm bg-white"
                        >
                            <option value="">Select page...</option>
                            {config.pages.map(p => <option key={p.id} value={p.id}>{p.id}</option>)}
                        </select>
                    </div>
                );
            }
            if (field.type === 'dynamic_entity_select') {
                return (
                    <div key={field.name} className="mb-2">
                        <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                        <select 
                          value={selectedTile[field.name] || ''} 
                          onChange={e => onUpdate({...selectedTile, [field.name]: e.target.value})} 
                          className="w-full border rounded p-1 text-sm bg-white"
                        >
                            <option value="">Select variable...</option>
                            {dynamicEntities.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                    </div>
                );
            }
            return null;
        })}
      </div>
    </div>
  );
};
