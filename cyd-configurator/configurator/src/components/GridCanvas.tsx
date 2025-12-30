import { useState, useEffect } from 'react';
import { DndContext, MouseSensor, TouchSensor, useSensor, useSensors, DragEndEvent } from '@dnd-kit/core';
import { DroppableCell } from './DroppableCell';
import { DraggableTile } from './DraggableTile';
import { Page, Tile } from '../types';

export const GridCanvas = ({ page, onSelectTile, selectedTileId, onDragEnd, onDeleteTile, rows, cols }: { 
  page: Page, 
  onSelectTile: (t: Tile) => void, 
  selectedTileId: string | null,
  onDragEnd: (event: DragEndEvent) => void,
  onDeleteTile: (id: string) => void,
  rows: number,
  cols: number
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
      if (selectedTile && selectedTile.x >= 0 && selectedTile.y >= 0) {
        const cellKey = `${selectedTile.x},${selectedTile.y}`;
        const cellTiles = page.tiles.filter(t => t.x === selectedTile.x && t.y === selectedTile.y);
        const index = cellTiles.findIndex(t => t.id === selectedTileId);
        if (index !== -1) {
          setCellActiveIndices(prev => ({
            ...prev,
            [cellKey]: index
          }));
        }
      }
    }
  }, [selectedTileId, page.tiles]);
  
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
              const tiles = page.tiles.filter(t => t.x === x && t.y === y);
              
              const cellKey = `${x},${y}`;
              const activeIndex = cellActiveIndices[cellKey] || 0;
              const validIndex = tiles.length > 0 ? activeIndex % tiles.length : 0;
              const activeTile = tiles[validIndex];
              
              return (
                <DroppableCell key={i} x={x} y={y}>
                  {activeTile && (
                    <DraggableTile 
                      tile={activeTile} 
                      isSelected={selectedTileId === activeTile.id} 
                      onClick={() => onSelectTile(activeTile)} 
                      onDelete={() => onDeleteTile(activeTile.id)}
                    />
                  )}
                  {tiles.length > 1 && (
                      <div className="absolute bottom-1 left-1 right-1 flex justify-between items-center bg-white/90 rounded px-1 z-20 text-[10px] font-bold shadow-sm border border-slate-300">
                          <button 
                              onPointerDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                  e.stopPropagation();
                                  const nextIndex = (validIndex - 1 + tiles.length) % tiles.length;
                                  setCellActiveIndices(prev => ({
                                      ...prev,
                                      [cellKey]: nextIndex
                                  }));
                                  onSelectTile(tiles[nextIndex]);
                              }}
                              className="hover:text-blue-600 p-0.5 cursor-pointer"
                          >
                              &lt;
                          </button>
                          <span className="text-slate-600">{validIndex + 1}/{tiles.length}</span>
                          <button 
                              onPointerDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                  e.stopPropagation();
                                  const nextIndex = (validIndex + 1) % tiles.length;
                                  setCellActiveIndices(prev => ({
                                      ...prev,
                                      [cellKey]: nextIndex
                                  }));
                                  onSelectTile(tiles[nextIndex]);
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
