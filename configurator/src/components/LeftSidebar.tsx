import { useState } from 'react';
import { ChevronDown, ChevronRight, Box, LayoutGrid, FileText, Trash2, Save, Upload, Download, FolderOpen, RefreshCw } from 'lucide-react';
import { Config, Tile } from '../types';
import { DynamicEntitiesEditor } from './FormInputs';
import { isAddon, apiFetch } from '../utils/api';
import { FileExplorer } from './FileExplorer';

interface LeftSidebarProps {
  width: number;
  onSidebarClick: () => void;
  isDynamicEntitiesOpen: boolean;
  setIsDynamicEntitiesOpen: (open: boolean) => void;
  config: Config;
  setConfig: (config: Config) => void;
  isAddTileOpen: boolean;
  setIsAddTileOpen: (open: boolean) => void;
  schema: any;
  handleAddTile: (type: string) => void;
  isPagesOpen: boolean;
  setIsPagesOpen: (open: boolean) => void;
  activePageId: string;
  setActivePageId: (id: string) => void;
  handleDeletePage: (id: string) => void;
  selectedTileId: string | null;
  setSelectedTileId: (id: string | null) => void;
  handleDeleteTile: (id: string) => void;
  getTileLabel: (tile: Tile) => string;
  setIsPageDialogOpen: (open: boolean) => void;
  handleSaveYaml: () => void;
  handleLoadFromHa: (path?: string) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleLoadProject: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleExport: () => void;
  handleClearConfig: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  width,
  onSidebarClick,
  isDynamicEntitiesOpen,
  setIsDynamicEntitiesOpen,
  config,
  setConfig,
  isAddTileOpen,
  setIsAddTileOpen,
  schema,
  handleAddTile,
  isPagesOpen,
  setIsPagesOpen,
  activePageId,
  setActivePageId,
  handleDeletePage,
  selectedTileId,
  setSelectedTileId,
  handleDeleteTile,
  getTileLabel,
  setIsPageDialogOpen,
  handleSaveYaml,
  handleLoadFromHa,
  fileInputRef,
  handleLoadProject,
  handleExport,
  handleClearConfig
}) => {
  const [showExplorer, setShowExplorer] = useState(false);

  const handleUpdateLib = async () => {
    if (!confirm("This will overwrite your /config/esphome/lib folder with the latest version. The old version will be backed up to /config/esphome/lib_old. Continue?")) return;
    
    try {
        const res = await apiFetch('/update_lib', { method: 'POST' });
        if (res.ok) {
            alert("Library files updated successfully!");
        } else {
            const err = await res.json();
            alert("Failed to update library: " + err.error);
        }
    } catch (e) {
        alert("Error updating library: " + e);
    }
  };

  return (
    <div 
      className="bg-white border-r flex flex-col flex-shrink-0"
      style={{ width }}
      onClick={onSidebarClick}
    >
      <div className="p-4 border-b bg-slate-50">
        <h1 className="font-bold text-xl text-blue-600 flex items-center gap-2">
          <LayoutGrid size={24} />
          CYD Config
        </h1>
      </div>
      
      <div className="p-4 flex-1 overflow-y-auto">
        {/* Dynamic Entities */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div 
              className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setIsDynamicEntitiesOpen(!isDynamicEntitiesOpen)}
          >
              <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                  {isDynamicEntitiesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Box size={14} /> Dynamic Entities
              </h3>
              <span className="text-[10px] font-bold text-slate-400 bg-slate-200 px-1.5 rounded-full">
                  {(config.dynamic_entities || []).length}
              </span>
          </div>
          
          {isDynamicEntitiesOpen && (
              <div className="p-3 pt-0 border-t border-slate-100 mt-2">
                  <div className="pt-2">
                      <DynamicEntitiesEditor 
                          entities={config.dynamic_entities || []} 
                          onChange={v => setConfig({...config, dynamic_entities: v})} 
                      />
                  </div>
              </div>
          )}
        </div>

        {/* Add Tile */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div 
              className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setIsAddTileOpen(!isAddTileOpen)}
          >
              <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                  {isAddTileOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <LayoutGrid size={14} /> Add Tile
              </h3>
          </div>
          
          {isAddTileOpen && (
              <div className="p-3 pt-0 border-t border-slate-100 mt-2">
                  <div className="pt-2 grid grid-cols-2 gap-2">
                      {schema?.types?.map((t: any) => (
                          <button
                              key={t.type}
                              onClick={() => handleAddTile(t.type)}
                              className="p-2 h-10 flex items-center justify-center text-xs font-bold bg-white hover:bg-blue-50 border rounded text-center transition-colors shadow-sm"
                          >
                              {t.label}
                          </button>
                      ))}
                  </div>
              </div>
          )}
        </div>

        {/* Pages */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div 
              className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setIsPagesOpen(!isPagesOpen)}
          >
              <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                  {isPagesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <FileText size={14} /> Pages
              </h3>
              <span className="text-[10px] font-bold text-slate-400 bg-slate-200 px-1.5 rounded-full">
                  {config.pages.length}
              </span>
          </div>
          
          {isPagesOpen && (
              <div className="p-3 pt-0 border-t border-slate-100 mt-2">
                  <div className="pt-2 space-y-1">
                      {config.pages.map(p => (
                          <div key={p.id}>
                              <div 
                                  className={`flex items-center justify-between p-2 rounded cursor-pointer mb-1 ${activePageId === p.id ? 'bg-blue-100 text-blue-700' : 'hover:bg-slate-100'}`}
                                  onClick={() => setActivePageId(p.id)}
                              >
                                  <span className="text-xs truncate font-medium">{p.id}</span>
                                  {config.pages.length > 1 && (
                                      <button
                                          onClick={(e) => {
                                              e.stopPropagation();
                                              handleDeletePage(p.id);
                                          }}
                                          className="text-slate-400 hover:text-red-500 p-1"
                                          title="Delete Page"
                                      >
                                          <Trash2 size={14} />
                                      </button>
                                  )}
                              </div>

                              {activePageId === p.id && (
                                  <div className="ml-4 mb-2 space-y-1">
                                      {p.tiles.map(tile => (
                                          <div 
                                              key={tile.id}
                                              className={`flex items-center justify-between p-1.5 rounded text-[10px] cursor-pointer ${selectedTileId === tile.id ? 'bg-blue-50 text-blue-600 border border-blue-200' : 'text-slate-600 hover:bg-slate-50'}`}
                                              onClick={() => setSelectedTileId(tile.id)}
                                          >
                                              <div className="flex items-center gap-2 truncate">
                                                  <div className={`w-1.5 h-1.5 rounded-full ${tile.x === -1 ? 'bg-amber-400' : 'bg-blue-400'}`} />
                                                  <span className="truncate font-medium">{getTileLabel(tile)}</span>
                                              </div>
                                              <button
                                                  onClick={(e) => {
                                                      e.stopPropagation();
                                                      handleDeleteTile(tile.id);
                                                  }}
                                                  className="text-slate-300 hover:text-red-500"
                                              >
                                                  <Trash2 size={12} />
                                              </button>
                                          </div>
                                      ))}
                                      {p.tiles.length === 0 && (
                                          <div className="text-[10px] text-slate-400 italic p-1">No tiles on this page</div>
                                      )}
                                  </div>
                              )}
                          </div>
                      ))}
                      <button 
                          onClick={() => setIsPageDialogOpen(true)}
                          className="w-full mt-2 p-2 text-[10px] font-medium border border-dashed rounded text-slate-500 hover:text-blue-600 hover:bg-white transition-colors"
                      >
                          + New Page
                      </button>
                  </div>
              </div>
          )}
        </div>
      </div>

      <div className="p-4 border-t bg-slate-50 space-y-4">
        {isAddon && (
          <div className="space-y-2">
            <label className="block text-[10px] font-bold text-blue-600 uppercase tracking-wider">HA File Management</label>
            <div className="flex gap-2">
              <input 
                type="text" 
                value={config.project_path || 'monitor_config/tiles.yaml'} 
                onChange={e => setConfig({...config, project_path: e.target.value})}
                placeholder="monitor_config/tiles.yaml"
                className="flex-1 border border-slate-200 rounded p-1.5 text-[10px] font-mono focus:border-blue-500 outline-none transition-colors bg-white"
              />
              <button 
                onClick={() => setShowExplorer(!showExplorer)}
                className={`p-1.5 rounded border transition-colors ${
                  showExplorer ? 'bg-blue-600 text-white border-blue-700' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
                title="Browse files"
              >
                <FolderOpen size={14} />
              </button>
            </div>

            {showExplorer && (
              <div className="h-48 border rounded overflow-hidden bg-white">
                <FileExplorer 
                  currentPath={config.project_path?.split('/').slice(0, -1).join('/')}
                  selectedPath={config.project_path}
                  onSelect={(path) => {
                    setConfig({...config, project_path: path});
                  }} 
                  onSelectDir={(dirPath) => {
                    const currentFile = config.project_path?.split('/').pop() || 'tiles.yaml';
                    const newPath = dirPath ? `${dirPath}/${currentFile}` : currentFile;
                    setConfig({...config, project_path: newPath});
                  }}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <button 
                onClick={handleSaveYaml}
                className="flex items-center justify-center gap-2 bg-blue-600 text-white border border-blue-700 p-2 rounded text-xs font-bold hover:bg-blue-700 transition-colors shadow-sm"
                title="Save screens configuration to Home Assistant"
              >
                <Save size={14} /> Save Screens to HA
              </button>
              <button 
                onClick={() => handleLoadFromHa()}
                className="flex items-center justify-center gap-2 bg-white text-slate-700 border border-slate-200 p-2 rounded text-xs font-bold hover:bg-slate-50 transition-colors shadow-sm"
                title="Load screens configuration from Home Assistant"
              >
                <Upload size={14} /> Load Screens from HA
              </button>
            </div>
          </div>
        )}

        <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleLoadProject} 
            className="hidden" 
            accept=".yaml,.yml"
        />
        
        <div className="grid grid-cols-2 gap-2">
          <button 
            onClick={handleExport}
            className="flex items-center justify-center gap-2 bg-slate-900 text-white p-2 rounded hover:bg-slate-800 text-[10px]"
          >
            <Download size={14} /> Copy YAML
          </button>
          <button 
            onClick={handleClearConfig}
            className="flex items-center justify-center gap-2 text-red-500 p-2 rounded hover:bg-red-50 border border-red-200 text-[10px]"
          >
            <Trash2 size={14} /> Clear All
          </button>
        </div>

        {isAddon && (
            <button 
                onClick={handleUpdateLib}
                className="w-full flex items-center justify-center gap-2 bg-amber-100 text-amber-800 border border-amber-200 p-2 rounded text-[10px] font-bold hover:bg-amber-200 transition-colors"
            >
                <RefreshCw size={14} /> Update HA Esphome files
            </button>
        )}
      </div>
    </div>
  );
};
