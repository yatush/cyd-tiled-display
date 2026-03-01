import { useState, useEffect, useRef } from 'react';
import { RefreshCw } from 'lucide-react';

import { Sidebar } from './components/PropertiesSidebar';
import { NewPageDialog } from './components/NewPageDialog';
import { LeftSidebar } from './components/LeftSidebar';
import { MainContent } from './components/MainContent';
import { TopBar } from './components/TopBar';
import { HASettingsDialog } from './components/HASettingsDialog';
import { FileManagementDialog } from './components/FileManagementDialog';
import { LibMismatchDialog } from './components/LibMismatchDialog';
import { SaveDeviceDialog } from './components/SaveDeviceDialog';
import { LoadDeviceDialog } from './components/LoadDeviceDialog';
import { InstallDialog } from './components/InstallDialog';
import { ScreensFileDialog } from './components/ScreensFileDialog';
import { EmulatorDialog } from './components/EmulatorDialog';

import { useSidebarResizing } from './hooks/useSidebarResizing';
import { useHaConnection } from './hooks/useHaConnection';
import { useTileConfig } from './hooks/useTileConfig';
import { useValidation } from './hooks/useValidation';
import { useFileOperations } from './hooks/useFileOperations';
import { getTileLabel } from './utils/tileUtils';
import { apiFetch, generateNewSessionId } from './utils/api';

import { generateYaml } from './utils/yamlGenerator';

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
  const [isMismatchDialogOpen, setIsMismatchDialogOpen] = useState(false);
  const [libMismatchDetails, setLibMismatchDetails] = useState<string[]>([]);
  const hasShownMismatchRef = useRef(false);
  
  // File Management State
  const [isFileManagementOpen, setIsFileManagementOpen] = useState(false);
  const [isSaveDeviceOpen, setIsSaveDeviceOpen] = useState(false);
  const [isLoadDeviceOpen, setIsLoadDeviceOpen] = useState(false);
  const [isInstallDeviceOpen, setIsInstallDeviceOpen] = useState(false);
  const [isScreensFileOpen, setIsScreensFileOpen] = useState(false);
  const [screensFileMode, setScreensFileMode] = useState<'save' | 'load'>('save');
  const [isEmulatorOpen, setIsEmulatorOpen] = useState(false);
  const [sidebarKey, setSidebarKey] = useState(0);
  const [usbCompileActive, setUsbCompileActive] = useState(false);

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

  const handleLibStatusData = (data: any, fromInitialLoad = false) => {
    if (data && typeof data.synced === 'boolean') {
      setUpdateAvailable(!data.synced);
      if (data.details && Array.isArray(data.details)) {
        setLibMismatchDetails(data.details);
      }
      if (fromInitialLoad && !data.synced && !hasShownMismatchRef.current) {
        hasShownMismatchRef.current = true;
        setIsMismatchDialogOpen(true);
      }
    }
  };

  const checkLibStatus = (data?: any) => {
    if (data && typeof data.synced === 'boolean') {
      handleLibStatusData(data);
      return;
    }
    apiFetch('/check_lib_status')
      .then(res => res.json())
      .then(data => handleLibStatusData(data, true))
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

  // Emulator State
  const [emulatorStatus, setEmulatorStatus] = useState<'stopped' | 'running' | 'starting' | 'error'>('stopped');
  const [websockifyPort, setWebsockifyPort] = useState<number | null>(null);
  const emulatorKeepAliveRef = useRef<AbortController | null>(null);
  const currentEmulatorSessionIdRef = useRef<string | null>(null);

  const checkEmulatorStatus = async () => {
    try {
      const res = await apiFetch('/emulator/status', {}, currentEmulatorSessionIdRef.current || undefined);
      const data = await res.json();
      setEmulatorStatus(data.status);
      if (data.websockify_port) {
        setWebsockifyPort(data.websockify_port);
      }
    } catch (e) {
      // console.error("Failed to check emulator status", e);
    }
  };

  useEffect(() => {
    checkEmulatorStatus();
    const interval = setInterval(checkEmulatorStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Sync keep-alive connection with status
    if (emulatorStatus === 'running' && !emulatorKeepAliveRef.current) {
      const controller = new AbortController();
      emulatorKeepAliveRef.current = controller;
      
      (async () => {
        try {
          const res = await apiFetch('/emulator/start', { 
            method: 'POST', 
            signal: controller.signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ check_only: true })
          }, currentEmulatorSessionIdRef.current || undefined);
          const reader = res.body?.getReader();
          if (reader) {
            while (true) {
              const { done } = await reader.read();
              if (done) break;
            }
          }
        } catch (e) {
          // Ignore abort errors
        } finally {
          emulatorKeepAliveRef.current = null;
        }
      })();
    } else if (emulatorStatus === 'stopped' && emulatorKeepAliveRef.current) {
      emulatorKeepAliveRef.current.abort();
      emulatorKeepAliveRef.current = null;
    }
  }, [emulatorStatus]);

  const handleStartEmulator = async () => {
    setIsEmulatorOpen(true);
    
    if (emulatorKeepAliveRef.current) {
        emulatorKeepAliveRef.current.abort();
    }
    
    const controller = new AbortController();
    emulatorKeepAliveRef.current = controller;

    // Generate a new session ID for this emulator start
    const newSessionId = generateNewSessionId();
    currentEmulatorSessionIdRef.current = newSessionId;

    setEmulatorStatus('running');
    
    try {
      const yamlConfig = generateYaml(config);
      const res = await apiFetch('/emulator/start', { 
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: yamlConfig })
      }, newSessionId);  // Pass new session ID
      
      // Check for session limit error
      if (res.status === 429) {
        const errorData = await res.json();
        alert(errorData.message || 'Too many emulators are currently running. Please try again later.');
        setEmulatorStatus('stopped');
        setIsEmulatorOpen(false);
        emulatorKeepAliveRef.current = null;
        return;
      }
      
      // Check for other errors
      if (!res.ok) {
        const errorData = await res.json();
        alert(errorData.message || 'Failed to start emulator');
        setEmulatorStatus('error');
        setIsEmulatorOpen(false);
        emulatorKeepAliveRef.current = null;
        return;
      }
      
      const reader = res.body?.getReader();
      if (reader) {
        const decoder = new TextDecoder();
        const { value } = await reader.read();
        const text = decoder.decode(value);
        try {
          // Parse the first line which contains the status and ports
          const firstLine = text.split('\n')[0];
          const data = JSON.parse(firstLine);
          if (data.websockify_port) {
            setWebsockifyPort(data.websockify_port);
          }
        } catch (e) {
          console.error("Failed to parse emulator start response", e);
        }
        
        // Continue reading to keep connection alive
        while (true) {
          const { done } = await reader.read();
          if (done) break;
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setEmulatorStatus('error');
        emulatorKeepAliveRef.current = null;
        console.error(e);
      }
    }
  };

  const handleStopEmulator = async () => {
    setIsEmulatorOpen(false);
    setEmulatorStatus('stopped');
    
    if (emulatorKeepAliveRef.current) {
      emulatorKeepAliveRef.current.abort();
      emulatorKeepAliveRef.current = null;
    }

    try {
      await apiFetch('/emulator/stop', { method: 'POST' }, currentEmulatorSessionIdRef.current || undefined);
    } catch (e) {
      console.error("Failed to stop emulator", e);
    }
    
    currentEmulatorSessionIdRef.current = null;
  };

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
        emulatorStatus={emulatorStatus}
        onStartEmulator={handleStartEmulator}
        onStopEmulator={handleStopEmulator}
        onOpenEmulator={() => setIsEmulatorOpen(true)}
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
          onNavigateToPage={setActivePageId}
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
          setConfig={setConfig}
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
        onInstallDevice={() => {
          setIsFileManagementOpen(false);
          setIsInstallDeviceOpen(true);
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

      <InstallDialog 
        isOpen={isInstallDeviceOpen}
        onClose={() => setIsInstallDeviceOpen(false)}
        onBack={() => {
          setIsInstallDeviceOpen(false);
          setIsFileManagementOpen(true);
        }}
        onSaveAndInstall={async (deviceName, friendlyName, screenType, fileName, encryptionKey, otaPassword, ipAddress) => {
          // forceWrite=true: USB compile must save the file to the server even in standalone/cloud mode
          const saved = await handleSaveDeviceConfig(deviceName, friendlyName, screenType, fileName, encryptionKey, otaPassword, ipAddress, true, true);
          if (!saved) {
            throw new Error('Failed to save device configuration');
          }
        }}
        stayMounted={usbCompileActive}
        onCompileActiveChange={setUsbCompileActive}
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

      <EmulatorDialog 
        isOpen={isEmulatorOpen} 
        onClose={() => setIsEmulatorOpen(false)}
        websockifyPort={websockifyPort}
        emulatorSessionId={currentEmulatorSessionIdRef.current}
      />

      <LibMismatchDialog
        isOpen={isMismatchDialogOpen}
        onClose={() => setIsMismatchDialogOpen(false)}
        onGoToSettings={() => setIsHaSettingsOpen(true)}
        details={libMismatchDetails}
      />

      {/* Floating USB Compile indicator — shown when dialog is closed but compile is running */}
      {usbCompileActive && !isInstallDeviceOpen && (
        <button
          onClick={() => setIsInstallDeviceOpen(true)}
          className="fixed bottom-4 right-4 z-[100] flex items-center gap-2 px-4 py-2.5 bg-purple-600 text-white rounded-full shadow-lg hover:bg-purple-700 transition-all animate-pulse"
        >
          <RefreshCw size={14} className="animate-spin" />
          <span className="text-sm font-bold">USB Compiling...</span>
        </button>
      )}
    </div>
  );
}

export default App;
