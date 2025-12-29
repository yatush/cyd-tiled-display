import React from 'react';
import { ChevronDown, ChevronRight, Server, ShieldCheck, ShieldAlert, Loader2, Box, LayoutGrid, FileText, Trash2, Save, Upload, Download } from 'lucide-react';
import { Config, Tile } from '../types';
import { DynamicEntitiesEditor } from './FormInputs';

interface LeftSidebarProps {
  width: number;
  onSidebarClick: () => void;
  haStatus: string;
  haUrl: string;
  setHaUrl: (url: string) => void;
  haToken: string;
  setHaToken: (token: string) => void;
  useMockData: boolean;
  setUseMockData: (use: boolean) => void;
  isHaSettingsOpen: boolean;
  setIsHaSettingsOpen: (open: boolean) => void;
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
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleLoadProject: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleExport: () => void;
  handleClearConfig: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  width,
  onSidebarClick,
  haStatus,
  haUrl,
  setHaUrl,
  haToken,
  setHaToken,
  useMockData,
  setUseMockData,
  isHaSettingsOpen,
  setIsHaSettingsOpen,
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
  fileInputRef,
  handleLoadProject,
  handleExport,
  handleClearConfig
}) => {
  return (
    <div 
      className="bg-white border-r flex flex-col flex-shrink-0"
      style={{ width }}
      onClick={onSidebarClick}
    >
      <div className="p-4 border-b">
        <h1 className="font-bold text-xl text-blue-600">CYD Config</h1>
      </div>
      
      <div className="p-4 flex-1 overflow-y-auto">
        {/* HA Connection */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div 
              className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setIsHaSettingsOpen(!isHaSettingsOpen)}
          >
              <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                  {isHaSettingsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Server size={14} /> HA Connection
              </h3>
              <div className="flex items-center gap-1">
                  {haStatus === 'connected' && <ShieldCheck size={14} className="text-green-500" />}
                  {haStatus === 'mock' && <div className="text-[10px] font-bold text-amber-600 bg-amber-100 px-1 rounded">MOCK</div>}
                  {haStatus === 'error' && <ShieldAlert size={14} className="text-red-500" />}
                  {haStatus === 'idle' && <Loader2 size={14} className="text-slate-400 animate-spin" />}
              </div>
          </div>
          
          {isHaSettingsOpen && (
              <div className="p-3 pt-0 space-y-2 border-t border-slate-100 mt-2">
                  <div className="pt-2">
                      <label className="block text-[10px] font-medium text-slate-500 uppercase mb-1">HA URL</label>
                      <input 
                          type="text" 
                          value={haUrl} 
                          onChange={e => setHaUrl(e.target.value)}
                          placeholder="http://homeassistant.local:8123"
                          className="w-full border rounded p-1 text-xs"
                      />
                  </div>
                  <div>
                      <label className="block text-[10px] font-medium text-slate-500 uppercase mb-1">Long-Lived Token</label>
                      <input 
                          type="password" 
                          value={haToken} 
                          onChange={e => setHaToken(e.target.value)}
                          placeholder="Paste token here..."
                          className="w-full border rounded p-1 text-xs"
                      />
                  </div>
                  <div className="flex items-center gap-2 pt-1">
                      <input 
                          type="checkbox" 
                          id="use-mock"
                          checked={useMockData} 
                          onChange={e => setUseMockData(e.target.checked)}
                          className="rounded border-slate-300"
                      />
                      <label htmlFor="use-mock" className="text-[10px] font-medium text-slate-600 uppercase cursor-pointer">Use Mock Data</label>
                  </div>
              </div>
          )}
        </div>

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
                              className="p-2 text-[10px] font-medium bg-white hover:bg-blue-50 border rounded text-left truncate transition-colors"
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

      <div className="p-4 border-t bg-slate-50 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <button 
              onClick={handleSaveYaml}
              className="flex items-center justify-center gap-2 bg-white border text-slate-700 p-2 rounded hover:bg-slate-50 text-xs"
              title="Save Project YAML"
          >
              <Save size={14} /> Save YAML
          </button>
          <button 
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center justify-center gap-2 bg-white border text-slate-700 p-2 rounded hover:bg-slate-50 text-xs"
              title="Load Project YAML"
          >
              <Upload size={14} /> Load YAML
          </button>
          <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleLoadProject} 
              className="hidden" 
              accept=".yaml,.yml"
          />
        </div>
        <button 
          onClick={handleExport}
          className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white p-2 rounded hover:bg-slate-800"
        >
          <Download size={16} /> Copy YAML
        </button>
        <button 
          onClick={handleClearConfig}
          className="w-full flex items-center justify-center gap-2 text-red-500 p-2 rounded hover:bg-red-50 border border-red-200"
        >
          <Trash2 size={16} /> Clear All
        </button>
      </div>
    </div>
  );
};
