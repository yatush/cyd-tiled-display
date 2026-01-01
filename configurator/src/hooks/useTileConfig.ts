import { useState, useEffect, useMemo, useCallback } from 'react';
import { Config, Tile, Page } from '../types';

const DEFAULT_CONFIG: Config = {
  project_path: 'tiles.yaml',
  pages: [
    { id: 'main_page', tiles: [], rows: 2, cols: 3 }
  ]
};

export function useTileConfig() {
  const [config, setConfigState] = useState<Config>(() => {
    const saved = localStorage.getItem('tile_config');
    if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.rows && parsed.cols && parsed.pages) {
            parsed.pages = (parsed.pages || []).map((p: any) => ({
                ...p,
                rows: p.rows || parsed.rows,
                cols: p.cols || parsed.cols
            }));
            delete parsed.rows;
            delete parsed.cols;
        }
        return parsed;
    }
    return DEFAULT_CONFIG;
  });

  const [history, setHistory] = useState<Config[]>([]);
  const [future, setFuture] = useState<Config[]>([]);

  const setConfig = useCallback((newConfig: Config | ((prev: Config) => Config), saveToHistory = true) => {
    setConfigState(prev => {
      const next = typeof newConfig === 'function' ? newConfig(prev) : newConfig;
      if (saveToHistory) {
        setHistory(h => [...h, prev].slice(-50)); // Keep last 50 states
        setFuture([]);
      }
      return next;
    });
  }, []);

  const undo = useCallback(() => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setHistory(h => h.slice(0, -1));
    setFuture(f => [config, ...f]);
    setConfigState(prev);
  }, [history, config]);

  const redo = useCallback(() => {
    if (future.length === 0) return;
    const next = future[0];
    setFuture(f => f.slice(1));
    setHistory(h => [...h, config]);
    setConfigState(next);
  }, [future, config]);

  const [activePageId, setActivePageId] = useState<string>('main_page');
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem('tile_config', JSON.stringify(config));
  }, [config]);

  // Ensure activePageId is valid
  useEffect(() => {
    if (config.pages && config.pages.length > 0) {
        const exists = config.pages.find(p => p.id === activePageId);
        if (!exists) {
            setActivePageId(config.pages[0].id);
        }
    }
  }, [config.pages, activePageId]);

  const activePage = useMemo(() => {
    if (!config.pages || config.pages.length === 0) {
        return { id: 'default', tiles: [], rows: 2, cols: 3 };
    }
    return config.pages.find(p => p.id === activePageId) || config.pages[0];
  }, [config.pages, activePageId]);

  const selectedTile = useMemo(() => 
    activePage.tiles.find(t => t.id === selectedTileId) || null,
    [activePage.tiles, selectedTileId]
  );

  const handleAddTile = (type: string) => {
    let x = 0, y = 0;
    let found = false;
    for(let r=0; r<activePage.rows; r++) {
      for(let c=0; c<activePage.cols; c++) {
        if (!activePage.tiles.find(t => t.x === c && t.y === r)) {
          x = c; y = r;
          found = true;
          break;
        }
      }
      if(found) break;
    }

    if (!found) {
      x = -1;
      y = -1;
    }

    const newTile: Tile = {
      id: Math.random().toString(36).substr(2, 9),
      type,
      x,
      y,
      ...(type === 'move_page' ? { destination: 'home' } : {}),
      ...(type === 'toggle_entity' ? { dynamic_entity: 'light', entity: 'light.example' } : {}),
      ...(type === 'cycle_entity' ? { dynamic_entity: 'scene', options: [] } : {}),
    } as Tile;

    const updatedPage = {
      ...activePage,
      tiles: [...activePage.tiles, newTile]
    };

    setConfig({
      ...config,
      pages: config.pages.map(p => p.id === activePage.id ? updatedPage : p)
    });
    setSelectedTileId(newTile.id);
  };

  const handleUpdateTile = (updatedTile: Tile) => {
    const updatedPage = {
      ...activePage,
      tiles: activePage.tiles.map(t => t.id === updatedTile.id ? updatedTile : t)
    };
    setConfig({
      ...config,
      pages: config.pages.map(p => p.id === activePage.id ? updatedPage : p)
    });
  };

  const handleDeleteTile = (id?: string) => {
    const targetId = id || selectedTileId;
    if (!targetId) return;
    const updatedPage = {
      ...activePage,
      tiles: activePage.tiles.filter(t => t.id !== targetId)
    };
    setConfig({
      ...config,
      pages: config.pages.map(p => p.id === activePage.id ? updatedPage : p)
    });
    if (selectedTileId === targetId) {
      setSelectedTileId(null);
    }
  };

  const handleDeletePage = (pageId: string) => {
    if (config.pages.length <= 1) {
      alert("Cannot delete the last page.");
      return;
    }
    if (confirm(`Are you sure you want to delete page "${pageId}"?`)) {
      const newPages = config.pages.filter(p => p.id !== pageId);
      setConfig({ ...config, pages: newPages });
      if (activePageId === pageId) {
        setActivePageId(newPages[0].id);
      }
    }
  };

  const handleUpdatePage = (updatedPage: Page) => {
    setConfig({
      ...config,
      pages: config.pages.map(p => p.id === updatedPage.id ? updatedPage : p)
    });
  };

  const handleRenamePage = (oldId: string, newId: string) => {
    if (oldId === newId) return;
    if (!newId.trim()) {
        alert("Page ID cannot be empty");
        return;
    }
    if (config.pages.some(p => p.id === newId)) {
        alert(`Page ID "${newId}" already exists`);
        return;
    }

    // 1. Update the page ID
    const newPages = config.pages.map(p => 
        p.id === oldId ? { ...p, id: newId } : p
    );

    // 2. Update references in all tiles across all pages
    const updatedPagesWithRefs = newPages.map(page => ({
        ...page,
        tiles: page.tiles.map(tile => {
            let updatedTile = { ...tile };
            
            // Update move_page destination
            if (tile.type === 'move_page' && tile.destination === oldId) {
                updatedTile.destination = newId;
            }
            
            // Update ha_action display_page_if_no_entity
            if (tile.type === 'ha_action' && tile.display_page_if_no_entity === oldId) {
                updatedTile.display_page_if_no_entity = newId;
            }
            
            return updatedTile;
        })
    }));

    setConfig({ ...config, pages: updatedPagesWithRefs });
    
    // Update active page ID if we renamed the active page
    if (activePageId === oldId) {
        setActivePageId(newId);
    }
  };

  const handleClearConfig = () => {
    if (confirm("Are you sure you want to clear the entire configuration? This cannot be undone.")) {
      setConfig(DEFAULT_CONFIG);
      setActivePageId('main_page');
      setSelectedTileId(null);
      localStorage.removeItem('tile_config');
    }
  };

  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    
    if (over && active.id !== over.id) {
      const overData = over.data.current as { x: number, y: number } | undefined;
      
      if (overData) {
        const { x, y } = overData;
        const draggedTile = activePage.tiles.find(t => t.id === active.id);
        
        if (!draggedTile) return;

        let newTiles = [...activePage.tiles];
        newTiles = newTiles.map(t => {
          if (t.id === draggedTile.id) return { ...t, x, y };
          return t;
        });

        const updatedPage = { ...activePage, tiles: newTiles };
        setConfig({
          ...config,
          pages: config.pages.map(p => p.id === activePage.id ? updatedPage : p)
        });
      }
    }
  };

  return {
    config,
    setConfig,
    undo,
    redo,
    canUndo: history.length > 0,
    canRedo: future.length > 0,
    activePageId,
    setActivePageId,
    selectedTileId,
    setSelectedTileId,
    activePage,
    selectedTile,
    handleAddTile,
    handleUpdateTile,
    handleDeleteTile,
    handleDeletePage,
    handleUpdatePage,
    handleRenamePage,
    handleClearConfig,
    handleDragEnd
  };
}
