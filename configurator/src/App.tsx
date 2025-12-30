import { useState, useEffect } from 'react';

import { Sidebar } from './components/PropertiesSidebar';
import { NewPageDialog } from './components/NewPageDialog';
import { LeftSidebar } from './components/LeftSidebar';
import { MainContent } from './components/MainContent';
import { TopBar } from './components/TopBar';
import { HASettingsDialog } from './components/HASettingsDialog';

import { useSidebarResizing } from './hooks/useSidebarResizing';
import { useHaConnection } from './hooks/useHaConnection';
import { useTileConfig } from './hooks/useTileConfig';
import { useValidation } from './hooks/useValidation';
import { useFileOperations } from './hooks/useFileOperations';
import { getTileLabel } from './utils/tileUtils';
import { apiFetch, isAddon } from './utils/api';

function App() {
  // Hooks
  const {
    leftSidebarWidth,
    rightSidebarWidth,
    setIsDraggingLeft
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
    handleAddTile, handleUpdateTile, handleDeleteTile,
    handleDeletePage, handleUpdatePage, handleClearConfig,
    handleDragEnd
  } = useTileConfig();

  const {
    isValidating,
    validationStatus,
    isGenerating,
    generationOutput,
    handleGenerate
  } = useValidation(config);

  const {
    fileInputRef,
    handleSaveYaml,
    handleLoadProject,
    handleExport,
    handleLoadFromHa
  } = useFileOperations(config, setConfig, setActivePageId);

  // Local UI State
  const [schema, setSchema] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'visual' | 'yaml' | 'output'>('visual');
  const [isPageDialogOpen, setIsPageDialogOpen] = useState(false);
  const [isHaSettingsOpen, setIsHaSettingsOpen] = useState(false);
  const [isDynamicEntitiesOpen, setIsDynamicEntitiesOpen] = useState(false);
  const [isAddTileOpen, setIsAddTileOpen] = useState(false);
  const [isPagesOpen, setIsPagesOpen] = useState(false);

  useEffect(() => {
    if (isAddon) {
      handleLoadFromHa('monitor_config/tiles.yaml');
    }
  }, [handleLoadFromHa]);

  useEffect(() => {
    apiFetch('/schema')
      .then(res => res.json())
      .then(data => setSchema(data))
      .catch(err => console.error("Failed to fetch schema", err));
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
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undo}
        onRedo={redo}
        onGenerate={() => handleGenerate(() => setActiveTab('output'))}
        isGenerating={isGenerating}
      />

      <div className="flex flex-1 overflow-hidden">
        <LeftSidebar 
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
          handleSaveYaml={handleSaveYaml}
          fileInputRef={fileInputRef}
          handleLoadProject={handleLoadProject}
          handleExport={handleExport}
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
          onUpdateConfig={setConfig}
          onLoadFromHa={handleLoadFromHa}
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
      />
    </div>
  );
}

export default App;
