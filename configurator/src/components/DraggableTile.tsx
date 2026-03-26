import { useDraggable } from '@dnd-kit/core';
import { Trash2, ArrowRightCircle } from 'lucide-react';
import { Tile, ImageEntry } from '../types';

// Resolves a fill_color value (named id or Color(r,g,b)) to a CSS color string.
function resolveFillColor(val: string, colorList: {id: string, value: string}[]): string | null {
  if (!val) return null;
  const found = colorList.find(c => c.id === val);
  if (found) {
    const v = found.value;
    if (v.startsWith('#')) return v;
    const rgbMatch = v.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (rgbMatch) return `rgb(${rgbMatch[1]},${rgbMatch[2]},${rgbMatch[3]})`;
    return v;
  }
  const colorFn = val.match(/^Color\((\d+),\s*(\d+),\s*(\d+)\)$/);
  if (colorFn) return `rgb(${colorFn[1]},${colorFn[2]},${colorFn[3]})`;
  return null;
}

// Returns true if the CSS color is perceptually dark (luminance < 0.35).
function isColorDark(css: string): boolean {
  let r = 0, g = 0, b = 0;
  const hex = css.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    r = parseInt(hex[1].slice(0, 2), 16);
    g = parseInt(hex[1].slice(2, 4), 16);
    b = parseInt(hex[1].slice(4, 6), 16);
  } else {
    const rgb = css.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (rgb) { r = +rgb[1]; g = +rgb[2]; b = +rgb[3]; }
  }
  // sRGB relative luminance
  const lum = (c: number) => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
  const L = 0.2126 * lum(r) + 0.7152 * lum(g) + 0.0722 * lum(b);
  return L < 0.35;
}

export const DraggableTile = ({ tile, isSelected, onClick, onDelete, zIndex, dynamicEntities = [], onNavigateToPage, images = {}, colorList = [] }: { 
  tile: Tile, 
  isSelected: boolean, 
  onClick: () => void, 
  onDelete: () => void,
  zIndex?: number,
  dynamicEntities?: string[],
  onNavigateToPage?: (pageId: string) => void,
  images?: Record<string, ImageEntry>,
  colorList?: {id: string, value: string}[]
}) => {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: tile.id,
  });
  
  const x_span = tile.x_span || 1;
  const y_span = tile.y_span || 1;

  const fillColorRaw = (tile as any).fill_color as string | undefined;
  const fillCss = fillColorRaw ? resolveFillColor(fillColorRaw, colorList) : null;
  const darkFill = fillCss ? isColorDark(fillCss) : false;

  const style: React.CSSProperties = {
    ...(transform ? {
      transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
    } : {}),
    width: `calc(${x_span} * (100% + 4px) + ${(x_span - 1) * 4}px)`,
    height: `calc(${y_span} * (100% + 4px) + ${(y_span - 1) * 4}px)`,
    top: '-2px',
    left: '-2px',
    zIndex: isSelected ? 100 : (zIndex ?? (x_span > 1 || y_span > 1 ? 50 : 10)),
    ...(fillCss ? { backgroundColor: fillCss } : {}),
  };

  const entityItems = (() => {
    const t = tile as any;
    const results: { name: string; sensor?: string }[] = [];

    // Helper: given any value, ensure we get a string or null
    const asString = (val: any): string | null => {
        if (typeof val === 'string') return val;
        if (typeof val === 'number' || typeof val === 'boolean') return String(val);
        if (Array.isArray(val)) {
            for (const item of val) {
                const s = asString(item);
                if (s) return s;
            }
        }
        return null;
    };

    // Extract entity info from an entities array item (object like {entity: "x", sensor: "y"} or {dynamic_entity: "var"})
    const fromEntityObj = (obj: any): { name: string; sensor?: string } | null => {
        if (!obj || typeof obj !== 'object') return null;
        if (obj.dynamic_entity && typeof obj.dynamic_entity === 'string') return { name: obj.dynamic_entity, sensor: asString(obj.sensor) || undefined };
        if (obj.entity) {
            const e = asString(obj.entity);
            if (e) return { name: e, sensor: asString(obj.sensor) || undefined };
        }
        return null;
    };

    // 1. Check tile.entities (ha_action, title tiles) - array of entity objects
    if (t.entities && Array.isArray(t.entities) && t.entities.length > 0) {
        for (const item of t.entities) {
            if (typeof item === 'string') { results.push({ name: item }); continue; }
            const info = fromEntityObj(item);
            if (info) results.push(info);
        }
    }

    // 2. Check tile.entity (toggle_entity) - could be string or array of strings
    if (t.entity) {
        if (Array.isArray(t.entity)) {
            for (const e of t.entity) { const s = asString(e); if (s) results.push({ name: s }); }
        } else {
            const e = asString(t.entity);
            if (e) results.push({ name: e, sensor: asString(t.sensor) || undefined });
        }
    }

    // 3. Check tile.dynamic_entity (toggle_entity, cycle_entity)
    if (t.dynamic_entity && typeof t.dynamic_entity === 'string') {
        results.push({ name: t.dynamic_entity, sensor: asString(t.sensor) || undefined });
    }

    // Deduplicate by name
    const seen = new Set<string>();
    return results.filter(r => { if (seen.has(r.name)) return false; seen.add(r.name); return true; });
  })();

  const globalSensor = typeof (tile as any).sensor === 'string' ? (tile as any).sensor : null;

  return (
    <div 
      ref={setNodeRef}  
      style={style} 
      {...listeners} 
      {...attributes}
      className={`absolute border-2 border-solid rounded flex items-center justify-center group overflow-hidden
        ${fillCss
          ? isSelected
            ? 'border-blue-600 ring-2 ring-blue-400'
            : 'border-blue-500'
          : isSelected
            ? 'bg-blue-100 border-blue-600 ring-2 ring-blue-400'
            : 'bg-blue-50 border-blue-500'
        }
        cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow
      `}
      onClick={() => {
        // Prevent drag click from triggering selection immediately if we want to separate them, 
        // but usually onClick fires after drag end if no drag happened.
        onClick();
      }}
    >
      <button 
        className="absolute top-0.5 right-0.5 p-1 bg-white rounded-full shadow opacity-0 group-hover:opacity-100 hover:bg-red-50 text-red-500 transition-opacity z-20"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        title="Delete Tile"
      >
        <Trash2 size={12} />
      </button>
      {/* ── Background image/icon layer (behind all content) ──────────── */}
      {(() => {
        const tileAny = tile as any;
        if (!Array.isArray(tileAny.display_assets) || tileAny.display_assets.length === 0) return null;
        const firstEntry = tileAny.display_assets[0];
        // Icon entry
        if (firstEntry?.icon) {
          let iconVal = firstEntry.icon;
          if (typeof iconVal === 'string' && iconVal.startsWith('"') && iconVal.endsWith('"')) iconVal = iconVal.slice(1, -1);
          let displayChar = iconVal;
          if (typeof iconVal === 'string' && iconVal.startsWith('\\U')) {
            try { displayChar = String.fromCodePoint(parseInt(iconVal.substring(2), 16)); } catch (e) {}
          }
          return (
            <div className="absolute pointer-events-none" style={{ inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 0 }}>
              <span style={{ fontFamily: '"Material Symbols Outlined"', fontSize: '28px', lineHeight: 1, opacity: 0.85 }}>{displayChar}</span>
            </div>
          );
        }
        // Image entry
        const firstImgId = firstEntry?.image;
        const entry = firstImgId ? images[firstImgId] : null;
        if (!entry) return null;
        const scale = entry.scale ?? 100;
        return (
          <div
            className="absolute pointer-events-none"
            style={{ inset: '5px',
                     display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 0 }}
          >
            <img
              src={`data:image/png;base64,${entry.data}`}
              alt={entry.filename}
              className="object-contain"
              style={{ maxWidth: `${scale}%`, maxHeight: `${scale}%` }}
            />
          </div>
        );
      })()}
      {(() => {
        const tileAny = tile as any;
        // ── Images/icons: show type badge on top, content is already rendered behind
        if (Array.isArray(tileAny.display_assets) && tileAny.display_assets.length > 0) {
          const firstEntry = tileAny.display_assets[0];
          const firstImgId = firstEntry?.image;
          const entry = firstImgId ? images[firstImgId] : null;
          return (
            <>
              {!entry && firstImgId && !firstEntry?.icon && (
                <div className={`absolute inset-0 flex items-center justify-center text-[9px] z-10 ${darkFill ? 'text-slate-300' : 'text-slate-400'}`}>{firstImgId}</div>
              )}
              <div className="absolute top-0.5 left-0 right-0 text-center pointer-events-none px-1 z-10">
                <span className={`text-[9px] font-bold rounded px-0.5 truncate inline-block max-w-full ${darkFill ? 'text-white bg-black/40' : 'text-blue-700 bg-white/70'}`}>
                  {tile.type.replace(/_/g, ' ')}
                </span>
              </div>
            </>
          );
        }
        // ── Display scripts ────────────────────────────────────────────────
        return (
          <div className="text-center p-1 overflow-hidden w-full pointer-events-none">
            <div className={`font-bold text-[10px] uppercase truncate ${darkFill ? 'text-white' : 'text-blue-700'}`}>{tile.type.replace('_', ' ')}</div>
            {tileAny.display && (() => {
              const items = Array.isArray(tileAny.display) ? tileAny.display : [tileAny.display];
              if (items.length === 0) return null;
              const first = items[0];
              const title = items.map((d: any) => typeof d === 'string' ? d : Object.keys(d)[0]).join(', ');
              return (
                <div className={`text-[9px] truncate mt-1 ${darkFill ? 'text-slate-300' : 'text-slate-600'}`} title={title}>
                  {(() => {
                    if (typeof first === 'string') return first;
                    const key = Object.keys(first)[0];
                    if (key === 'tile_icon' && first[key]?.icon) {
                      let iconVal = first[key].icon;
                      if (typeof iconVal === 'string' && iconVal.startsWith('"') && iconVal.endsWith('"')) iconVal = iconVal.slice(1, -1);
                      let displayChar = iconVal;
                      if (iconVal.startsWith('\\U')) {
                        try { displayChar = String.fromCodePoint(parseInt(iconVal.substring(2), 16)); } catch (e) {}
                      }
                      return <span style={{ fontFamily: '"Material Symbols Outlined"', fontSize: '24px', lineHeight: 1 }}>{displayChar}</span>;
                    }
                    if (key === 'tile_text' && first[key]?.text) {
                      let textVal = first[key].text;
                      if (typeof textVal === 'string' && textVal.startsWith('"') && textVal.endsWith('"')) textVal = textVal.slice(1, -1);
                      return <span className="truncate text-xs font-medium">{textVal}</span>;
                    }
                    return key;
                  })()}
                </div>
              );
            })()}
          </div>
        );
      })()}
      {tile.type === 'move_page' && tile.destination && (
        <div
          className="absolute top-0.5 left-0.5 max-w-[calc(100%-8px)] flex items-center gap-0.5 border border-green-400 rounded px-1 py-0.5 bg-green-50/90 cursor-pointer hover:bg-green-100 transition-colors z-10"
          title={`Go to page: ${tile.destination}`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onNavigateToPage?.(tile.destination);
          }}
        >
          <ArrowRightCircle size={10} className="text-green-600 flex-shrink-0" />
          <span className="text-[8px] leading-tight text-green-700 font-semibold truncate">
            {tile.destination}
          </span>
        </div>
      )}
      {(entityItems.length > 0 || (globalSensor && entityItems.every(e => !e.sensor))) && (
        <div className="absolute bottom-0.5 left-0.5 pointer-events-none max-w-[calc(100%-8px)] flex flex-col items-start gap-0.5 border border-blue-300 rounded px-1 py-0.5 bg-white/70 z-10">
          {entityItems.map((ei, idx) => {
            const dynamic = dynamicEntities?.includes(ei.name);
            return (
              <div key={idx} className="flex flex-col items-start max-w-full">
                <span className={`text-[8px] leading-tight truncate max-w-full px-0.5 rounded inline-block ${dynamic ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-600'}`} title={dynamic ? "Dynamic Entity" : "Static Entity"}>
                  {ei.name}
                </span>
                {ei.sensor && (
                  <span className="text-[7px] leading-tight text-slate-400 truncate max-w-full" title="Sensor">
                    {ei.sensor}
                  </span>
                )}
              </div>
            );
          })}
          {globalSensor && entityItems.every(e => !e.sensor) && (
            <span className="text-[7px] leading-tight text-slate-400 truncate max-w-full" title="Sensor">
              {globalSensor}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
