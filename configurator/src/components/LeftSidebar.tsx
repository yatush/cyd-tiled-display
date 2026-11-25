import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Box, LayoutGrid, FileText, Trash2, ImageIcon, Copy, Home, Bluetooth, AlertTriangle, Radio } from 'lucide-react';
import { Config, Tile, ImageEntry, ScreenImageEntry, HaEntity, BleFanConfig, EspNowFanLink, HeadlessHubConfig, TuyaBleCandidate } from '../types';
import { DynamicEntitiesEditor, ImageManagerPanel, ScreenImageManagerPanel, BleFansManagerPanel } from './FormInputs';
import { applyDynamicEntityListChange, updateDynamicEntityFixedValues } from '../utils/tileUtils';
import { configHasBleProxy, deriveDefaultBleEntityIds } from '../utils/bleFanUtils';

interface LeftSidebarProps {
  width: number;
  onSidebarClick: () => void;
  isImagesOpen: boolean;
  setIsImagesOpen: (open: boolean) => void;
  onAddImage: (id: string, entry: ImageEntry) => void;
  onDeleteImage: (id: string) => void;
  onUpdateImage: (id: string, patch: Partial<ImageEntry>) => void;
  isScreenImagesOpen: boolean;
  setIsScreenImagesOpen: (open: boolean) => void;
  onAddScreenImage: (id: string, entry: ScreenImageEntry) => void;
  onDeleteScreenImage: (id: string) => void;
  isDynamicEntitiesOpen: boolean;
  setIsDynamicEntitiesOpen: (open: boolean) => void;
  config: Config;
  setConfig: (config: Config | ((prev: Config) => Config)) => void;
  isAddTileOpen: boolean;
  setIsAddTileOpen: (open: boolean) => void;
  schema: any;
  handleAddTile: (type: string, initialProps?: Partial<Tile>) => void;
  handleDuplicateTile: (id: string) => void;
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
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleLoadProject: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleClearConfig: () => void;
  haEntities?: HaEntity[];
  tuyaBleCandidates?: TuyaBleCandidate[];
  bleFanHosts?: Record<string, string[]>;
  bleHubs?: HeadlessHubConfig[];
  currentDevicePath?: string;
  onOpenFindBleFans?: () => void;
  onOpenHeadlessHubs?: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  width,
  onSidebarClick,
  isImagesOpen,
  setIsImagesOpen,
  onAddImage,
  onDeleteImage,
  onUpdateImage,
  isScreenImagesOpen,
  setIsScreenImagesOpen,
  onAddScreenImage,
  onDeleteScreenImage,
  isDynamicEntitiesOpen,
  setIsDynamicEntitiesOpen,
  config,
  setConfig,
  isAddTileOpen,
  setIsAddTileOpen,
  schema,
  handleDuplicateTile,
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
  fileInputRef,
  handleLoadProject,
  handleClearConfig,
  haEntities,
  tuyaBleCandidates,
  bleFanHosts,
  bleHubs = [],
  currentDevicePath,
  onOpenFindBleFans,
  onOpenHeadlessHubs,
}) => {
  const [expandedPages, setExpandedPages] = useState<Set<string>>(new Set([activePageId]));
  const [isBleFansOpen, setIsBleFansOpen] = useState(false);

  const handleUpdateBleFans = (next: BleFanConfig[]) => setConfig(prev => {
    const updated: Config = { ...prev };
    if (next.length > 0) updated.ble_fans = next;
    else delete updated.ble_fans;
    return updated;
  });

  const handleToggleEspNowFan = (link: EspNowFanLink) => setConfig(prev => {
    const existing = prev.espnow_fans || [];
    const key = link.fan_entity_id || link.light_entity_id || link.name;
    const found = existing.some(f => (f.fan_entity_id || f.light_entity_id || f.name) === key);
    const next = found
      ? existing.filter(f => (f.fan_entity_id || f.light_entity_id || f.name) !== key)
      : [...existing, link];
    const updated: Config = { ...prev };
    if (next.length > 0) updated.espnow_fans = next;
    else delete updated.espnow_fans;
    return updated;
  });

  useEffect(() => {
    setExpandedPages(prev => {
      const next = new Set(prev);
      next.add(activePageId);
      return next;
    });
  }, [activePageId]);

  const togglePageExpansion = (pageId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedPages(prev => {
      const next = new Set(prev);
      if (next.has(pageId)) {
        next.delete(pageId);
      } else {
        next.add(pageId);
      }
      return next;
    });
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
        {/* Images */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div
            className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
            onClick={() => setIsImagesOpen(!isImagesOpen)}
          >
            <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
              {isImagesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <ImageIcon size={14} /> Images
            </h3>
            <span className="text-[10px] font-bold text-slate-400 bg-slate-200 px-1.5 rounded-full">
              {Object.keys(config.images || {}).length}
            </span>
          </div>
          {isImagesOpen && (
            <div className="p-3 pt-0 border-t border-slate-100 mt-2">
              <div className="pt-2">
                <ImageManagerPanel
                  images={config.images || {}}
                  onAddImage={onAddImage}
                  onDeleteImage={onDeleteImage}
                  onUpdateImage={onUpdateImage}
                />
              </div>
            </div>
          )}
        </div>

        {/* Screen Background Images */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div
            className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
            onClick={() => setIsScreenImagesOpen(!isScreenImagesOpen)}
          >
            <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
              {isScreenImagesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <ImageIcon size={14} /> Screen Backgrounds
            </h3>
            <span className="text-[10px] font-bold text-slate-400 bg-slate-200 px-1.5 rounded-full">
              {Object.keys(config.screen_images || {}).length}
            </span>
          </div>
          {isScreenImagesOpen && (
            <div className="p-3 pt-0 border-t border-slate-100 mt-2">
              <div className="pt-2">
                <ScreenImageManagerPanel
                  images={config.screen_images || {}}
                  onAddImage={onAddScreenImage}
                  onDeleteImage={onDeleteScreenImage}
                />
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
                          fixedValues={config.dynamic_entity_values}
                          onChange={v => setConfig(prev => applyDynamicEntityListChange(prev, v))} 
                          onFixedChange={(varName, vals) => setConfig(prev => updateDynamicEntityFixedValues(prev, varName, vals))}
                          haEntities={haEntities}
                          bleFans={config.ble_fans || []}
                          tuyaBleCandidates={tuyaBleCandidates}
                          bleFanHosts={bleFanHosts}
                          currentDevicePath={currentDevicePath}
                          onUpdateBleFans={handleUpdateBleFans}
                      />
                  </div>
              </div>
          )}
        </div>

        {/* BLE Fans (Device-level, no tile required) */}
        <div className="mb-6 bg-slate-50 border rounded-lg overflow-hidden">
          <div 
              className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setIsBleFansOpen(!isBleFansOpen)}
          >
              <h3 className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                  {isBleFansOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Bluetooth size={14} className="text-blue-600" /> BLE Fans
              </h3>
              <span className={`text-[10px] font-bold px-1.5 rounded-full ${(config.ble_fans || []).length > 0 ? 'bg-blue-100 text-blue-700' : 'text-slate-400 bg-slate-200'}`}>
                  {(config.ble_fans || []).length}
              </span>
          </div>
          
          {isBleFansOpen && (
              <div className="p-3 pt-0 border-t border-slate-100 mt-2 space-y-3">
                  {onOpenHeadlessHubs && (
                    <div className="pt-2">
                      <button
                        onClick={onOpenHeadlessHubs}
                        className="w-full flex items-center justify-between px-2.5 py-2 text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-100 transition-colors"
                      >
                        <span className="flex items-center gap-1.5">
                          <Radio size={13} /> Headless BLE Hubs (ESP-NOW)
                        </span>
                        <span className="text-[10px] font-bold bg-indigo-200/80 text-indigo-800 px-1.5 py-0.5 rounded-full">
                          {bleHubs.length}
                        </span>
                      </button>
                    </div>
                  )}

                  {(bleHubs.some(h => (h.fans || []).length > 0) || (tuyaBleCandidates || []).length > 0) && (
                    <div className="bg-white border border-slate-200 rounded-md p-2 space-y-1.5">
                      <div className="text-[10px] font-bold uppercase text-indigo-600 flex items-center gap-1">
                        <Radio size={11} /> ESP-NOW Remote Fans (No BLE on CYD)
                      </div>
                      <p className="text-[10px] text-slate-500">
                        Hub-hosted fans used by tiles auto-link on save. You can also pre-link any fan below:
                      </p>
                      <div className="space-y-1 max-h-36 overflow-y-auto">
                        {(tuyaBleCandidates || []).map(c => {
                          const defaults = deriveDefaultBleEntityIds(c.name || c.device_id);
                          const fanId = c.fan_entity_id || defaults.fan_entity_id;
                          const lightId = c.light_entity_id || defaults.light_entity_id;
                          const linked = (config.espnow_fans || []).some(
                            f => f.fan_entity_id === fanId
                          );
                          const hubOwner = bleHubs.find(h =>
                            (h.fans || []).some(hf => hf.device_id === c.device_id)
                          );
                          return (
                            <label
                              key={`espnow-${c.device_id}`}
                              className="flex items-center justify-between text-[11px] px-1.5 py-1 rounded hover:bg-slate-50 cursor-pointer"
                            >
                              <span className="flex items-center gap-1.5 truncate">
                                <input
                                  type="checkbox"
                                  checked={linked}
                                  onChange={() =>
                                    handleToggleEspNowFan({
                                      name: c.name,
                                      fan_entity_id: fanId,
                                      light_entity_id: lightId || undefined,
                                    })
                                  }
                                  className="rounded text-indigo-600"
                                />
                                <span className="truncate font-medium text-slate-700">{c.name}</span>
                              </span>
                              {hubOwner && (
                                <span className="text-[9px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full shrink-0 ml-1">
                                  {hubOwner.name}
                                </span>
                              )}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="pt-1">
                      <BleFansManagerPanel
                          bleFans={config.ble_fans || []}
                          tuyaBleCandidates={tuyaBleCandidates}
                          bleFanHosts={bleFanHosts}
                          currentDevicePath={currentDevicePath}
                          hasBleProxy={configHasBleProxy(config)}
                          onUpdateBleFans={handleUpdateBleFans}
                          onOpenFindBleFans={onOpenFindBleFans}
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
                      <button
                          onClick={() => handleAddTile('function', {
                              display: ['tile_ble_proxy'],
                              on_press: 'action_toggle_ble_proxy'
                          })}
                          className="p-2 h-10 flex items-center justify-center gap-1.5 text-xs font-bold bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded text-center transition-colors shadow-sm"
                      >
                          <Bluetooth size={14} /> BLE Proxy
                      </button>
                  </div>
                  {configHasBleProxy(config) && (
                    <div className="mt-2 p-2 rounded bg-amber-50 border border-amber-200 text-[11px] text-amber-800 flex items-start gap-1.5">
                      <AlertTriangle size={13} className="text-amber-600 flex-shrink-0 mt-0.5" />
                      <span>
                        BLE Proxy runs continuous scanning and reduces the display buffer, which may make the screen less responsive
                        {(config.ble_fans?.length || 0) > 0 ? ' (especially when combined with BLE fans)' : ''}.
                      </span>
                    </div>
                  )}
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
                                  <div className="flex items-center gap-1 overflow-hidden">
                                      <button 
                                        onClick={(e) => togglePageExpansion(p.id, e)}
                                        className="p-0.5 hover:bg-black/10 rounded text-slate-500"
                                      >
                                        {expandedPages.has(p.id) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                                      </button>
                                      <span className="text-xs truncate font-medium">{p.id}</span>
                                      {p.flags?.includes('BASE') && (
                                          <span title="Base Screen" aria-label="Base Screen" className="flex-shrink-0">
                                            <Home size={12} className="text-amber-500" aria-hidden="true" />
                                          </span>
                                      )}
                                  </div>
                                  {config.pages.length > 1 && !p.flags?.includes('BASE') && (
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

                              {expandedPages.has(p.id) && (
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
                                              <div className="flex items-center gap-1">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleDuplicateTile(tile.id);
                                                    }}
                                                    className="text-slate-300 hover:text-blue-500"
                                                    title="Duplicate Tile"
                                                >
                                                    <Copy size={12} />
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleDeleteTile(tile.id);
                                                    }}
                                                    className="text-slate-300 hover:text-red-500"
                                                    title="Delete Tile"
                                                >
                                                    <Trash2 size={12} />
                                                </button>
                                              </div>
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

      <div className="p-4 border-t bg-slate-50">
        <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleLoadProject} 
            className="hidden" 
            accept=".yaml,.yml"
        />
        
        <div className="grid grid-cols-1 gap-2">
          <button 
            onClick={handleClearConfig}
            className="flex items-center justify-center gap-2 text-red-500 p-2 rounded hover:bg-red-50 border border-red-200 text-[10px] font-bold"
          >
            <Trash2 size={14} /> Clear All
          </button>
        </div>
      </div>
    </div>
  );
};
