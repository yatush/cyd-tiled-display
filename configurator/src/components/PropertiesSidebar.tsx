import { useState, useEffect } from 'react';
import { Trash2, Layout, Settings2 } from 'lucide-react';
import { Tile, Config, Page, HaEntity } from '../types';
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
  haEntities: HaEntity[]
}) => {
  const [activeTab, setActiveTab] = useState<'tile' | 'page'>('page');

  const dynamicEntities = config.dynamic_entities || [];
  const tileSchema = selectedTile ? schema?.types?.find((t: any) => t.type === selectedTile.type) : null;

  // Switch to tile tab when a tile is selected
  useEffect(() => {
    if (selectedTile) {
      setActiveTab('tile');
    }
  }, [selectedTile?.id]);

  const renderPageProperties = () => (
    <div className="space-y-6">
      <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-3 tracking-wider">Grid Dimensions</label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Rows</label>
            <input 
              type="number" 
              value={activePage.rows} 
              onChange={e => onUpdatePage({...activePage, rows: Math.max(1, parseInt(e.target.value) || 1)})}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Columns</label>
            <input 
              type="number" 
              value={activePage.cols} 
              onChange={e => onUpdatePage({...activePage, cols: Math.max(1, parseInt(e.target.value) || 1)})}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
          </div>
        </div>
      </div>
      
      <div>
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Page Flags</label>
        <ArrayInput 
          label="Flags" 
          values={activePage.flags || []} 
          onChange={v => onUpdatePage({...activePage, flags: v})} 
          allowedValues={['BASE', 'TEMPORARY', 'FAST_REFRESH']}
        />
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex border-b bg-slate-50">
        <button
          onClick={() => setActiveTab('page')}
          className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'page' 
              ? 'bg-white text-blue-600 border-b-2 border-blue-600' 
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          <Layout size={16} />
          Page
        </button>
        <button
          onClick={() => setActiveTab('tile')}
          disabled={!selectedTile}
          className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'tile' 
              ? 'bg-white text-blue-600 border-b-2 border-blue-600' 
              : 'text-slate-400 hover:text-slate-600 disabled:opacity-30'
          }`}
        >
          <Settings2 size={16} />
          Tile
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'page' ? (
          renderPageProperties()
        ) : selectedTile ? (
          <div className="space-y-4 pb-20">
            <div className="flex justify-between items-center border-b pb-2">
              <h2 className="font-bold text-lg text-slate-800">Edit Tile</h2>
              <button onClick={() => onDelete()} className="text-red-500 hover:bg-red-50 p-1.5 rounded-lg transition-colors" title="Delete Tile">
                <Trash2 size={18} />
              </button>
            </div>
            
            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Common</label>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="col-span-2">
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Type</label>
                  <div className="p-2 bg-slate-100 rounded-lg text-xs font-mono text-slate-600 border border-slate-200">{selectedTile.type}</div>
                </div>
                <div className="flex gap-3 col-span-2">
                  {schema?.common?.filter((f: any) => f.name === 'x' || f.name === 'y').map((field: any) => (
                    <div key={field.name} className="flex-1">
                      <label className="block text-xs text-slate-600 mb-1 font-medium">{field.label}</label>
                      <input 
                        type="number" 
                        value={selectedTile[field.name]} 
                        onChange={e => onUpdate({...selectedTile, [field.name]: parseInt(e.target.value)})}
                        className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
                      />
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="space-y-4">
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
      </div>
    ) : null}
  </div>
</div>
  );
};
