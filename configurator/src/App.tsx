import { useState, useEffect } from 'react';

import { Sidebar } from './components/PropertiesSidebar';
import { NewPageDialog } from './components/NewPageDialog';
import { LeftSidebar } from './components/LeftSidebar';
import { MainContent } from './components/MainContent';
import { TopBar } from './components/TopBar';
import { HASettingsDialog } from './components/HASettingsDialog';
import { FileManagementDialog } from './components/FileManagementDialog';
import { SaveDeviceDialog } from './components/SaveDeviceDialog';
import { LoadDeviceDialog } from './components/LoadDeviceDialog';
import { ScreensFileDialog } from './components/ScreensFileDialog';

import { useSidebarResizing } from './hooks/useSidebarResizing';
import { useHaConnection } from './hooks/useHaConnection';
import { useTileConfig } from './hooks/useTileConfig';
import { useValidation } from './hooks/useValidation';
import { useFileOperations } from './hooks/useFileOperations';
import { getTileLabel } from './utils/tileUtils';
import { apiFetch } from './utils/api';

function App() {
  // Local UI State
  const [schema, setSchema] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'visual' | 'yaml' | 'output'>('visual');
  const [isPageDialogOpen, setIsPageDialogOpen] = useState(false);
  const [isHaSettingsOpen, setIsHaSettingsOpen] = useState(false);
  const [isDynamicEntitiesOpen, setIsDynamicEntitiesOpen] = useState(false);
  const [isAddTileOpen, setIsAddTileOpen] = useState(false);
  const [isPagesOpen, setIsPagesOpen] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  
  // File Management State
  const [isFileManagementOpen, setIsFileManagementOpen] = useState(false);
  const [isSaveDeviceOpen, setIsSaveDeviceOpen] = useState(false);
  const [isLoadDeviceOpen, setIsLoadDeviceOpen] = useState(false);
  const [isScreensFileOpen, setIsScreensFileOpen] = useState(false);
  const [screensFileMode, setScreensFileMode] = useState<'save' | 'load'>('save');
  const [sidebarKey, setSidebarKey] = useState(0);

  // Hooks
  const {
    leftSidebarWidth,
    rightSidebarWidth,
    setIsDraggingLeft,
    setIsDraggingRight
  } = useSidebarResizing();

  const {
    haUrl, setHaUrl,
    haToken, setHaToken,
    connectionType, setConnectionType,
    haEntities,
    haStatus,
    fetchHaEntities
  } = useHaConnection();

  const {
    config, setConfig,
    undo, redo, canUndo, canRedo,
    activePageId, setActivePageId,
    selectedTileId, setSelectedTileId,
    activePage, selectedTile,
    handleAddTile, handleDuplicateTile, handleUpdateTile, handleDeleteTile,
    handleDeletePage, handleUpdatePage, handleRenamePage, handleClearConfig,
    handleDragEnd
  } = useTileConfig();

  const {
    isValidating,
    validationStatus,
    isGenerating,
    generationOutput,
    handleGenerate
  } = useValidation(config);

  const checkLibStatus = (data?: any) => {
    if (data && typeof data.synced === 'boolean') {
      setUpdateAvailable(!data.synced);
      return;
    }
    apiFetch('/check_lib_status')
      .then(res => res.json())
      .then(data => {
        if (data && typeof data.synced === 'boolean') {
          setUpdateAvailable(!data.synced);
        }
      })
      .catch(err => console.error("Failed to check lib status", err));
  };

  const {
    fileInputRef,
    handleSaveYaml,
    handleDownloadYaml,
    handleLoadProject,
    handleExport,
    handleLoadFromHa,
    handleSaveDeviceConfig,
    handleLoadDeviceConfig
  } = useFileOperations(config, setConfig, setActivePageId, checkLibStatus, () => setSidebarKey(prev => prev + 1));

  useEffect(() => {
    apiFetch('/schema')
      .then(res => res.json())
      .then(data => setSchema(data))
      .catch(err => console.error("Failed to fetch schema", err));
      
    // Check for updates
    checkLibStatus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) {
          redo();
        } else {
          undo();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        redo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undo, redo]);

  const handleSidebarClick = () => {
    if (activeTab === 'output') {
      setActiveTab('visual');
    }
  };

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-slate-50">
      <TopBar 
        haStatus={haStatus}
        connectionType={connectionType}
        entityCount={haEntities.length}
        onOpenSettings={() => setIsHaSettingsOpen(true)}
        onRefreshHa={fetchHaEntities}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undo}
        onRedo={redo}
        onGenerate={() => handleGenerate(() => setActiveTab('output'))}
        onOpenFileManagement={() => setIsFileManagementOpen(true)}
        isGenerating={isGenerating}
        updateAvailable={updateAvailable}
      />

      <div className="flex flex-1 overflow-hidden">
        <LeftSidebar 
          key={sidebarKey}
          width={leftSidebarWidth}
          onSidebarClick={handleSidebarClick}
          isDynamicEntitiesOpen={isDynamicEntitiesOpen}
          setIsDynamicEntitiesOpen={setIsDynamicEntitiesOpen}
          config={config}
          setConfig={setConfig}
          isAddTileOpen={isAddTileOpen}
          setIsAddTileOpen={setIsAddTileOpen}
          schema={schema}
          handleAddTile={handleAddTile}
          handleDuplicateTile={handleDuplicateTile}
          isPagesOpen={isPagesOpen}
          setIsPagesOpen={setIsPagesOpen}
          activePageId={activePageId}
          setActivePageId={setActivePageId}
          handleDeletePage={handleDeletePage}
          selectedTileId={selectedTileId}
          setSelectedTileId={setSelectedTileId}
          handleDeleteTile={handleDeleteTile}
          getTileLabel={getTileLabel}
          setIsPageDialogOpen={setIsPageDialogOpen}
          fileInputRef={fileInputRef}
          handleLoadProject={handleLoadProject}
          handleClearConfig={handleClearConfig}
        />

      {/* Left Resizer */}
      <div
        className="w-1 bg-slate-200 hover:bg-blue-400 cursor-col-resize flex-shrink-0 transition-colors"
        onMouseDown={() => setIsDraggingLeft(true)}
      />

      <MainContent 
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isValidating={isValidating}
        validationStatus={validationStatus}
        isGenerating={isGenerating}
          activePage={activePage}
          config={config}
          selectedTileId={selectedTileId}
          setSelectedTileId={setSelectedTileId}
          handleDragEnd={handleDragEnd}
          handleDeleteTile={handleDeleteTile}
          activePageId={activePageId}
          generationOutput={generationOutput}
          onGenerate={() => handleGenerate(() => setActiveTab('output'))}
          onCopyYaml={handleExport}
      />

      {/* Right Resizer */}
      <div
        className="w-1 bg-slate-200 hover:bg-blue-400 cursor-col-resize flex-shrink-0 transition-colors"
        onMouseDown={() => setIsDraggingRight(true)}
      />

      {/* Right Sidebar - Properties */}
      <div 
        className="bg-white border-l flex-shrink-0 h-full"
        style={{ width: rightSidebarWidth }}
        onClick={handleSidebarClick}
      >
        <Sidebar 
          selectedTile={selectedTile} 
          onUpdate={handleUpdateTile} 
          onDelete={handleDeleteTile} 
          config={config}
          schema={schema}
          activePage={activePage}
          haEntities={haEntities}
          onUpdatePage={handleUpdatePage}
          onRenamePage={handleRenamePage}
        />
      </div>
      </div>
      
      <NewPageDialog 
        isOpen={isPageDialogOpen} 
        onClose={() => setIsPageDialogOpen(false)} 
        onAdd={(id) => {
            setConfig({...config, pages: [...config.pages, { id, tiles: [], rows: 2, cols: 3 }]});
            setActivePageId(id);
        }}
        existingIds={config.pages.map(p => p.id)}
      />

      <HASettingsDialog 
        isOpen={isHaSettingsOpen}
        onClose={() => setIsHaSettingsOpen(false)}
        connectionType={connectionType}
        setConnectionType={setConnectionType}
        haUrl={haUrl}
        setHaUrl={setHaUrl}
        haToken={haToken}
        setHaToken={setHaToken}
        onRefresh={fetchHaEntities}
        onCheckLibStatus={checkLibStatus}
      />

      <FileManagementDialog 
        isOpen={isFileManagementOpen}
        onClose={() => setIsFileManagementOpen(false)}
        onLoadLocal={() => fileInputRef.current?.click()}
        onDownloadLocal={handleDownloadYaml}
        onSaveScreen={() => {
          setScreensFileMode('save');
          setIsFileManagementOpen(false);
          setIsScreensFileOpen(true);
        }}
        onLoadScreen={() => {
          setScreensFileMode('load');
          setIsFileManagementOpen(false);
          setIsScreensFileOpen(true);
        }}
        onSaveDevice={() => {
          setIsFileManagementOpen(false);
          setIsSaveDeviceOpen(true);
        }}
        onLoadDevice={() => {
          setIsFileManagementOpen(false);
          setIsLoadDeviceOpen(true);
        }}
        connectionType={connectionType}
      />

      <SaveDeviceDialog 
        isOpen={isSaveDeviceOpen}
        onClose={() => setIsSaveDeviceOpen(false)}
        onBack={() => {
          setIsSaveDeviceOpen(false);
          setIsFileManagementOpen(true);
        }}
        onSave={handleSaveDeviceConfig}
      />
      
      <LoadDeviceDialog 
        isOpen={isLoadDeviceOpen}
        onClose={() => setIsLoadDeviceOpen(false)}
        onBack={() => {
          setIsLoadDeviceOpen(false);
          setIsFileManagementOpen(true);
        }}
        onLoad={handleLoadDeviceConfig}
      />
      
      <ScreensFileDialog 
        isOpen={isScreensFileOpen}
        onClose={() => setIsScreensFileOpen(false)}
        onBack={() => {
          setIsScreensFileOpen(false);
          setIsFileManagementOpen(true);
        }}
        config={config}
        setConfig={setConfig}
        onSave={handleSaveYaml}
        onLoad={() => handleLoadFromHa()}
        mode={screensFileMode}
      />
    </div>
  );
}

export default App;
