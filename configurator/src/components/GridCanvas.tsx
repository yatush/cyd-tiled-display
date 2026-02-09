import { useState, useEffect } from 'react';
import { DndContext, MouseSensor, TouchSensor, useSensor, useSensors, DragEndEvent } from '@dnd-kit/core';
import { DroppableCell } from './DroppableCell';
import { DraggableTile } from './DraggableTile';
import { Page, Tile } from '../types';

export const GridCanvas = ({ page, onSelectTile, selectedTileId, onDragEnd, onDeleteTile, rows, cols, dynamicEntities }: { 
  page: Page, 
  onSelectTile: (t: Tile) => void, 
  selectedTileId: string | null,
  onDragEnd: (event: DragEndEvent) => void,
  onDeleteTile: (id: string) => void,
  rows: number,
  cols: number,
  dynamicEntities?: string[]
}) => {
  const sensors = useSensors(
    useSensor(MouseSensor, {
      activationConstraint: {
        distance: 5,
      },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 250,
        tolerance: 5,
      },
    })
  );

  const [cellActiveIndices, setCellActiveIndices] = useState<{[key: string]: number}>({});

  // Sync active index with selected tile
  useEffect(() => {
    if (selectedTileId) {
      const selectedTile = page.tiles.find(t => t.id === selectedTileId);
      if (selectedTile) {
        setCellActiveIndices(prev => {
            const next = { ...prev };
            let hasChanges = false;

            // Iterate over all cells to find where this tile is present
            for (let i = 0; i < rows * cols; i++) {
                const x = i % cols;
                const y = Math.floor(i / cols);
                
                // Check if the selected tile covers this cell
                const t_x_span = selectedTile.x_span || 1;
                const t_y_span = selectedTile.y_span || 1;
                const covers = x >= selectedTile.x && x < selectedTile.x + t_x_span &&
                               y >= selectedTile.y && y < selectedTile.y + t_y_span;
                
                if (covers) {
                    // Calculate covering tiles for this cell to find the index
                    const coveringTiles = page.tiles.filter(t => {
                        const txs = t.x_span || 1;
                        const tys = t.y_span || 1;
                        return x >= t.x && x < t.x + txs &&
                               y >= t.y && y < t.y + tys;
                    });
                    
                    const newIndex = coveringTiles.findIndex(t => t.id === selectedTileId);
                    const cellKey = `${x},${y}`;
                    
                    if (newIndex !== -1 && next[cellKey] !== newIndex) {
                        next[cellKey] = newIndex;
                        hasChanges = true;
                    }
                }
            }
            return hasChanges ? next : prev;
        });
      }
    }
  }, [selectedTileId, page.tiles, rows, cols]);
  
  const unplacedTiles = page.tiles.filter(t => t.x < 0 || t.y < 0);

  return (
    <DndContext onDragEnd={onDragEnd} sensors={sensors}>
      <div className="flex flex-col items-center gap-6">
        <div className="relative bg-white shadow-lg rounded-lg overflow-hidden" style={{ width: '480px', height: '320px' }}>
          <div 
            className="absolute inset-0 grid gap-1 p-1 bg-slate-200"
            style={{
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`
            }}
          >
            {Array.from({ length: cols * rows }).map((_, i) => {
              const x = i % cols;
              const y = Math.floor(i / cols);
              
              // Tiles that physically start in this cell (for rendering)
              const startingTiles = page.tiles.filter(t => t.x === x && t.y === y);
              
              // Tiles that cover this cell (for interaction/selection)
              const coveringTiles = page.tiles.filter(t => {
                  const t_x_span = t.x_span || 1;
                  const t_y_span = t.y_span || 1;
                  return x >= t.x && x < t.x + t_x_span &&
                         y >= t.y && y < t.y + t_y_span;
              });
              
              const cellKey = `${x},${y}`;
              const activeIndex = cellActiveIndices[cellKey] || 0;
              const validIndex = coveringTiles.length > 0 ? activeIndex % coveringTiles.length : 0;
              const activeTile = coveringTiles[validIndex];
              
              return (
                <DroppableCell key={i} x={x} y={y}>
                  {startingTiles.map(tile => (
                    <DraggableTile 
                      key={tile.id}
                      tile={tile} 
                      isSelected={selectedTileId === tile.id} 
                      onClick={() => onSelectTile(tile)} 
                      onDelete={() => onDeleteTile(tile.id)}
                      zIndex={activeTile && activeTile.id === tile.id ? 60 : undefined}
                      dynamicEntities={dynamicEntities}
                    />
                  ))}
                  {coveringTiles.length > 1 && (
                      <div className="absolute bottom-1 left-1 right-1 flex justify-between items-center bg-white/90 rounded px-1 z-[110] text-[10px] font-bold shadow-sm border border-slate-300">
                          <button 
                              onPointerDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                  e.stopPropagation();
                                  const nextIndex = (validIndex - 1 + coveringTiles.length) % coveringTiles.length;
                                  setCellActiveIndices(prev => ({
                                      ...prev,
                                      [cellKey]: nextIndex
                                  }));
                                  onSelectTile(coveringTiles[nextIndex]);
                              }}
                              className="hover:text-blue-600 p-0.5 cursor-pointer"
                          >
                              &lt;
                          </button>
                          <span className="text-slate-600">{validIndex + 1}/{coveringTiles.length}</span>
                          <button 
                              onPointerDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                  e.stopPropagation();
                                  const nextIndex = (validIndex + 1) % coveringTiles.length;
                                  setCellActiveIndices(prev => ({
                                      ...prev,
                                      [cellKey]: nextIndex
                                  }));
                                  onSelectTile(coveringTiles[nextIndex]);
                              }}
                              className="hover:text-blue-600 p-0.5 cursor-pointer"
                          >
                              &gt;
                          </button>
                      </div>
                  )}
                </DroppableCell>
              );
            })}
          </div>
        </div>

        {unplacedTiles.length > 0 && (
          <div className="w-full max-w-[480px] p-4 bg-slate-50 border-2 border-dashed border-slate-300 rounded-xl">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Unplaced Tiles (Staging)</h4>
              <span className="text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-full font-bold">{unplacedTiles.length}</span>
            </div>
            <div className="flex flex-wrap gap-3">
              {unplacedTiles.map(tile => (
                <div key={tile.id} className="w-[70px] h-[70px] relative shadow-sm rounded overflow-hidden bg-white">
                  <DraggableTile 
                    tile={tile} 
                    isSelected={selectedTileId === tile.id} 
                    onClick={() => onSelectTile(tile)} 
                    onDelete={() => onDeleteTile(tile.id)}
                    dynamicEntities={dynamicEntities}
                  />
                </div>
              ))}
            </div>
            <p className="mt-3 text-[10px] text-slate-400 italic text-center">Drag these onto the grid to place them</p>
          </div>
        )}
      </div>
    </DndContext>
  );
};
