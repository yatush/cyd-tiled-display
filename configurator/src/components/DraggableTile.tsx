import { useDraggable } from '@dnd-kit/core';
import { Trash2 } from 'lucide-react';
import { Tile } from '../types';

export const DraggableTile = ({ tile, isSelected, onClick, onDelete, zIndex }: { 
  tile: Tile, 
  isSelected: boolean, 
  onClick: () => void, 
  onDelete: () => void,
  zIndex?: number 
}) => {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: tile.id,
  });
  
  const x_span = tile.x_span || 1;
  const y_span = tile.y_span || 1;

  const style: React.CSSProperties = {
    ...(transform ? {
      transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
    } : {}),
    width: `calc(${x_span} * (100% + 4px) + ${(x_span - 1) * 4}px)`,
    height: `calc(${y_span} * (100% + 4px) + ${(y_span - 1) * 4}px)`,
    top: '-2px',
    left: '-2px',
    zIndex: isSelected ? 100 : (zIndex ?? (x_span > 1 || y_span > 1 ? 50 : 10)),
  };

  return (
    <div 
      ref={setNodeRef} 
      style={style} 
      {...listeners} 
      {...attributes}
      className={`absolute border-2 border-solid rounded flex items-center justify-center group
        ${isSelected ? 'bg-blue-100 border-blue-600 ring-2 ring-blue-400' : 'bg-blue-50 border-blue-500'}
        cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow
      `}
      onClick={() => {
        // Prevent drag click from triggering selection immediately if we want to separate them, 
        // but usually onClick fires after drag end if no drag happened.
        onClick();
      }}
    >
      <button 
        className="absolute top-1 right-1 p-1 bg-white rounded-full shadow opacity-0 group-hover:opacity-100 hover:bg-red-50 text-red-500 transition-opacity z-10"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        title="Delete Tile"
      >
        <Trash2 size={12} />
      </button>
      <div className="text-center p-1 overflow-hidden w-full pointer-events-none">
        <div className="font-bold text-[10px] uppercase text-blue-700 truncate">{tile.type.replace('_', ' ')}</div>
        {tile.display && (
          <div className="text-[9px] text-slate-600 truncate mt-1" title={(() => {
            const items = Array.isArray(tile.display) ? tile.display : [tile.display];
            return items.map(d => typeof d === 'string' ? d : Object.keys(d)[0]).join(', ');
          })()}>
            {(() => {
               const items = Array.isArray(tile.display) ? tile.display : [tile.display];
               if (items.length === 0) return null;
               const first = items[0];
               
               if (typeof first === 'string') return first;
               
               const key = Object.keys(first)[0];
               if (key === 'tile_icon' && first[key]?.icon) {
                   let iconVal = first[key].icon;
                   // Handle potential double quoting from YAML load
                   if (typeof iconVal === 'string' && iconVal.startsWith('"') && iconVal.endsWith('"')) {
                       iconVal = iconVal.slice(1, -1);
                   }

                   let displayChar = iconVal;
                   if (iconVal.startsWith('\\U')) {
                       try {
                           displayChar = String.fromCodePoint(parseInt(iconVal.substring(2), 16));
                       } catch (e) {}
                   }
                   return <span style={{ fontFamily: '"Material Symbols Outlined"', fontSize: '24px', lineHeight: 1 }}>{displayChar}</span>;
               }
               return key;
            })()}
          </div>
        )}
        {(tile as any).entity && (
          <div className="text-[9px] text-slate-500 truncate mt-0.5">{(tile as any).entity}</div>
        )}
      </div>
    </div>
  );
};
