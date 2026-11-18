import React, { useState, useEffect, useRef } from 'react';
import { Trash2, Plus, Upload, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { ImageEntry, ScreenImageEntry } from '../types';
import { IconPicker, ColorPicker } from './Pickers';
import { ConditionBuilder } from './ConditionBuilder';

/** Derive an ESPHome image type from whether the PNG has an alpha channel. */
function detectImageType(base64: string): 'RGBA' | 'RGB565' {
  try {
    const raw = atob(base64.slice(0, 44));
    const colourType = raw.charCodeAt(25);
    return colourType === 6 || colourType === 4 ? 'RGBA' : 'RGB565';
  } catch {
    return 'RGB565';
  }
}

/** Cover-crop an image to exactly targetWidth × targetHeight (scale-to-fill + center-crop). */
function coverCropToPng(dataUrl: string, targetWidth: number, targetHeight: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.max(targetWidth / img.width, targetHeight / img.height);
      const scaledW = Math.round(img.width * scale);
      const scaledH = Math.round(img.height * scale);
      const offsetX = Math.round((scaledW - targetWidth) / 2);
      const offsetY = Math.round((scaledH - targetHeight) / 2);
      const canvas = document.createElement('canvas');
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('No 2d context')); return; }
      ctx.drawImage(img, -offsetX, -offsetY, scaledW, scaledH);
      resolve(canvas.toDataURL('image/png').split(',')[1]);
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}

/** Resize an image to fit within maxWidth × maxHeight, returning a PNG base64 string. */
function resizeImageToPng(dataUrl: string, maxWidth: number, maxHeight: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      const ratio = Math.min(maxWidth / width, maxHeight / height, 1);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('No 2d context')); return; }
      ctx.clearRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL('image/png').split(',')[1]);
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}

export function generateImageId(filename: string, existing: Record<string, ImageEntry>): string {
  const stem = filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_]/g, '_');
  const base = `img_${stem}`;
  if (!existing[base]) return base;
  let n = 1;
  while (existing[`${base}_${n}`]) n++;
  return `${base}_${n}`;
}

export function generateScreenImageId(filename: string, existing: Record<string, ScreenImageEntry>): string {
  const stem = filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_]/g, '_');
  const base = `bg_${stem}`;
  if (!existing[base]) return base;
  let n = 1;
  while (existing[`${base}_${n}`]) n++;
  return `${base}_${n}`;
}

export const ImageSelectInput = ({
  label,
  value,
  onChange,
  images,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  images: Record<string, ImageEntry>;
}) => {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageIds = Object.keys(images || {});
  const isNone = value === 'none';
  const selected = !isNone && value && images?.[value] ? images[value] : null;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleToggle = () => {
    if (!open && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      setDropUp(spaceBelow < 280);
    }
    setOpen(o => !o);
  };

  return (
    <div className="relative" ref={containerRef}>
      {label && <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>}

      <button
        type="button"
        onClick={handleToggle}
        className="w-full flex items-center gap-2 border rounded p-1 bg-white hover:bg-slate-50 text-sm text-left min-w-0"
      >
        {isNone ? (
          <>
            <span className="flex-shrink-0 h-8 w-8 flex items-center justify-center rounded bg-slate-100 text-slate-400 text-xs font-mono">∅</span>
            <span className="truncate flex-1 text-slate-500 italic">none</span>
          </>
        ) : selected ? (
          <>
            <img
              src={`data:image/png;base64,${selected.data}`}
              alt={selected.filename}
              className="flex-shrink-0 h-8 w-8 object-contain rounded bg-slate-100"
            />
            <span className="truncate flex-1 text-slate-700" title={value}>{value}</span>
          </>
        ) : (
          <span className="flex-1 text-slate-400">— select image —</span>
        )}
        <svg className="flex-shrink-0 w-3 h-3 text-slate-400" viewBox="0 0 10 6" fill="none">
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div className={`absolute z-50 bg-white border rounded shadow-lg p-2 w-56 max-h-64 overflow-y-auto ${dropUp ? 'bottom-full mb-1' : 'mt-1'}`}>
          <button
            type="button"
            onClick={() => { onChange('none'); setOpen(false); }}
            className={`flex items-center gap-2 w-full px-2 py-1 rounded border mb-2 text-left hover:bg-blue-50 hover:border-blue-300 transition-colors ${value === 'none' ? 'border-blue-400 bg-blue-50' : 'border-slate-200'}`}
            title="none — no image (e.g. for animations that don't start from the first frame)"
          >
            <span className="h-8 w-8 flex items-center justify-center rounded bg-slate-100 text-slate-400 text-xs font-mono flex-shrink-0">∅</span>
            <span className="text-xs text-slate-500 italic">none</span>
          </button>
          {imageIds.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-2">No images uploaded yet</p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {imageIds.map(id => (
                <button
                  key={id}
                  type="button"
                  onClick={() => { onChange(id); setOpen(false); }}
                  className={`flex flex-col items-center gap-0.5 p-1 rounded border text-center hover:bg-blue-50 hover:border-blue-300 transition-colors ${value === id ? 'border-blue-400 bg-blue-50' : 'border-transparent'}`}
                  title={id}
                >
                  <img
                    src={`data:image/png;base64,${images[id].data}`}
                    alt={id}
                    className="h-12 w-12 object-contain rounded bg-slate-100"
                  />
                  <span className="text-[9px] text-slate-500 truncate w-full leading-tight">{id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const ImageManagerPanel = ({
  images,
  onAddImage,
  onDeleteImage,
  onUpdateImage,
}: {
  images: Record<string, ImageEntry>;
  onAddImage: (id: string, entry: ImageEntry) => void;
  onDeleteImage: (id: string) => void;
  onUpdateImage?: (id: string, patch: Partial<ImageEntry>) => void;
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageIds = Object.keys(images || {});

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      if (!file.name.match(/\.(png|jpg|jpeg|gif|bmp)$/i)) return;
      const reader = new FileReader();
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string;
        const originalBase64 = dataUrl.split(',')[1];
        const imgType = file.name.toLowerCase().endsWith('.png') ? detectImageType(originalBase64) : 'RGB565';
        if (Object.keys(images || {}).some(id => images[id].filename === file.name)) return;
        resizeImageToPng(dataUrl, 400, 300).then(base64 => {
          const newId = generateImageId(file.name, images || {});
          onAddImage(newId, { data: base64, filename: file.name, type: imgType });
        }).catch(() => {
          const newId = generateImageId(file.name, images || {});
          onAddImage(newId, { data: originalBase64, filename: file.name, type: imgType });
        });
      };
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  return (
    <div className="space-y-1.5">
      {imageIds.length === 0 && (
        <div className="text-[10px] text-slate-400 italic px-1 py-1">No images yet</div>
      )}
      {imageIds.map(id => {
        const entry = images[id];
        const scale = entry.scale ?? 100;
        const fillPct = ((scale - 10) / 90) * 100;
        const trackStyle = {
          background: `linear-gradient(to right, #3b82f6 ${fillPct}%, #e2e8f0 ${fillPct}%)`,
        };
        return (
          <div key={id} className="p-1.5 border rounded bg-white hover:bg-slate-50">
            <div className="flex items-center gap-2">
              <img
                src={`data:image/png;base64,${entry.data}`}
                alt={entry.filename}
                className="flex-shrink-0 w-8 h-8 object-contain border rounded bg-slate-100"
              />
              <div className="flex-1 min-w-0">
                <div className="text-[10px] font-bold text-blue-700 truncate">{id}</div>
                <div className="text-[9px] text-slate-400">{entry.type || 'RGB565'}</div>
              </div>
              <button
                type="button"
                onClick={() => onDeleteImage(id)}
                className="flex-shrink-0 text-red-400 hover:text-red-600 p-1 rounded hover:bg-red-50"
                title={`Delete ${id}`}
              >
                <Trash2 size={12} />
              </button>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 pl-0.5 pr-1" title="Image size: % of tile area (5 px padding always applied)">
              <input
                type="range"
                min={10}
                max={100}
                step={5}
                value={scale}
                onChange={e => onUpdateImage?.(id, { scale: Number(e.target.value) })}
                className="flex-1 h-1.5 rounded-full cursor-pointer"
                style={trackStyle}
              />
              <span className="text-[9px] font-bold text-slate-500 w-7 text-right flex-shrink-0">{scale}%</span>
            </div>
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1.5 hover:bg-blue-50 flex items-center justify-center gap-1 mt-1"
      >
        <Upload size={12} /> Upload Image
      </button>
      <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
    </div>
  );
};

export const ScreenImageManagerPanel = ({
  images,
  onAddImage,
  onDeleteImage,
}: {
  images: Record<string, ScreenImageEntry>;
  onAddImage: (id: string, entry: ScreenImageEntry) => void;
  onDeleteImage: (id: string) => void;
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageIds = Object.keys(images || {});

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      if (!file.name.match(/\.(png|jpg|jpeg|gif|bmp)$/i)) return;
      const reader = new FileReader();
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string;
        const originalBase64 = dataUrl.split(',')[1];
        const imgType = file.name.toLowerCase().endsWith('.png') ? detectImageType(originalBase64) : 'RGB565';
        if (Object.keys(images || {}).some(id => images[id].filename === file.name)) return;
        coverCropToPng(dataUrl, 480, 320).then(base64 => {
          const newId = generateScreenImageId(file.name, images || {});
          onAddImage(newId, { data: base64, filename: file.name, type: imgType });
        }).catch(() => {
          const newId = generateScreenImageId(file.name, images || {});
          onAddImage(newId, { data: originalBase64, filename: file.name, type: imgType });
        });
      };
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  return (
    <div className="space-y-1.5">
      {imageIds.length === 0 && (
        <div className="text-[10px] text-slate-400 italic px-1 py-1">No screen background images yet</div>
      )}
      {imageIds.map(id => {
        const entry = images[id];
        return (
          <div key={id} className="p-1.5 border rounded bg-white hover:bg-slate-50">
            <div className="flex items-center gap-2">
              <img
                src={`data:image/png;base64,${entry.data}`}
                alt={entry.filename}
                className="flex-shrink-0 w-12 h-8 object-contain border rounded bg-slate-100"
              />
              <div className="flex-1 min-w-0">
                <div className="text-[10px] font-bold text-blue-700 truncate">{id}</div>
                <div className="text-[9px] text-slate-400">{entry.type || 'RGB565'} · screen bg</div>
              </div>
              <button
                type="button"
                onClick={() => onDeleteImage(id)}
                className="flex-shrink-0 text-red-400 hover:text-red-600 p-1 rounded hover:bg-red-50"
                title={`Delete ${id}`}
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1.5 hover:bg-blue-50 flex items-center justify-center gap-1 mt-1"
      >
        <Upload size={12} /> Upload Screen Image
      </button>
      <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
    </div>
  );
};

const FRAC_STEPS = 21;
const FRAC_STEP = 0.05;
type AnimPos = [number, number];
const DEFAULT_ANIM_POS: AnimPos = [0.5, 0.5];

function fracSnap(v: number): number {
  return Math.round(Math.round(v / FRAC_STEP) * FRAC_STEP * 100) / 100;
}

const FractionalPositionPicker = ({
  value,
  onChange,
  label,
  ghostPoint,
}: { value: AnimPos; onChange: (v: AnimPos) => void; label: string; ghostPoint?: AnimPos }) => {
  const [x, y] = value;
  const CELL = 5;
  const SIZE = CELL * (FRAC_STEPS - 1);

  return (
    <div className="select-none">
      <label className="block text-[10px] text-slate-500 uppercase mb-1">{label}</label>
      <div
        tabIndex={0}
        className="relative border border-slate-300 rounded bg-white cursor-crosshair outline-none focus:ring-2 focus:ring-blue-400"
        style={{ width: SIZE + 1, height: SIZE + 1 }}
        onClick={e => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - rect.left;
          const py = e.clientY - rect.top;
          const nx = fracSnap(Math.max(0, Math.min(1, px / SIZE)));
          const ny = fracSnap(Math.max(0, Math.min(1, py / SIZE)));
          onChange([nx, ny]);
        }}
        onKeyDown={e => {
          const ARROW_KEYS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
          if (!ARROW_KEYS.includes(e.key)) return;
          e.preventDefault();
          const [cx, cy] = value;
          if (e.key === 'ArrowLeft') onChange([fracSnap(Math.max(0, cx - FRAC_STEP)), cy]);
          if (e.key === 'ArrowRight') onChange([fracSnap(Math.min(1, cx + FRAC_STEP)), cy]);
          if (e.key === 'ArrowUp') onChange([cx, fracSnap(Math.max(0, cy - FRAC_STEP))]);
          if (e.key === 'ArrowDown') onChange([cx, fracSnap(Math.min(1, cy + FRAC_STEP))]);
        }}
      >
        {Array.from({ length: FRAC_STEPS }).map((_, i) => {
          const pct = (i / (FRAC_STEPS - 1)) * 100;
          const isMajor = i % 2 === 0;
          return (
            <React.Fragment key={i}>
              <div
                className="absolute top-0 bottom-0 pointer-events-none"
                style={{ left: `${pct}%`, width: 1, background: isMajor ? '#cbd5e1' : '#f1f5f9' }}
              />
              <div
                className="absolute left-0 right-0 pointer-events-none"
                style={{ top: `${pct}%`, height: 1, background: isMajor ? '#cbd5e1' : '#f1f5f9' }}
              />
            </React.Fragment>
          );
        })}
        {ghostPoint && (
          <div
            className="absolute pointer-events-none"
            style={{
              left: `${ghostPoint[0] * 100}%`,
              top: `${ghostPoint[1] * 100}%`,
              transform: 'translate(-50%, -50%)',
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: '#94a3b8',
              border: '1.5px solid #64748b',
            }}
          />
        )}
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${x * 100}%`,
            top: `${y * 100}%`,
            transform: 'translate(-50%, -50%)',
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: '#3b82f6',
            border: '1.5px solid #1d4ed8',
            boxShadow: '0 0 0 1.5px #bfdbfe',
          }}
        />
      </div>
      <div className="mt-1 text-[10px] text-slate-600 font-mono text-center">
        ({x.toFixed(2)}, {y.toFixed(2)})
      </div>
    </div>
  );
};

type AnimStep = { from: AnimPos; to: AnimPos; duration: number; image?: string; icon?: string; icon_color?: string; icon_size?: string; };
type AnimConfig = { from: AnimPos; to: AnimPos; duration: number } | { steps: AnimStep[] };

function normalizePos(pos: any): AnimPos {
  if (Array.isArray(pos) && pos.length === 2 && typeof pos[0] === 'number') {
    return [fracSnap(pos[0]), fracSnap(pos[1])];
  }
  return DEFAULT_ANIM_POS;
}

function toSteps(anim: AnimConfig): AnimStep[] {
  if ('steps' in anim && Array.isArray(anim.steps)) {
    return anim.steps.map(s => ({ ...s, from: normalizePos(s.from), to: normalizePos(s.to) }));
  }
  const { from, to, duration } = anim as any;
  return [{ from: normalizePos(from ?? DEFAULT_ANIM_POS), to: normalizePos(to ?? DEFAULT_ANIM_POS), duration: duration ?? 3 }];
}

function fromSteps(steps: AnimStep[]): AnimConfig {
  if (steps.length === 1) {
    const { from, to, duration, image, icon, icon_color, icon_size } = steps[0];
    const r: any = { from, to, duration };
    if (image !== undefined) r.image = image;
    if (icon !== undefined) { r.icon = icon; r.icon_color = icon_color; r.icon_size = icon_size; }
    return r;
  }
  return { steps };
}

type ImageRow = {
  image?: string;
  icon?: string;
  icon_color?: string;
  icon_size?: string;
  condition?: any;
  animation?: AnimConfig;
};

export const ImagesListInput = ({
  value,
  onChange,
  images,
}: {
  value: ImageRow[];
  onChange: (v: ImageRow[]) => void;
  images: Record<string, ImageEntry>;
}) => {
  const rows: ImageRow[] = Array.isArray(value) ? value : [];
  const [iconList, setIconList] = useState<{ value: string; label: string }[]>([]);
  const [colorList, setColorList] = useState<{ id: string; value: string }[]>([]);
  const [fontList, setFontList] = useState<string[]>([]);

  useEffect(() => {
    apiFetch('/scripts').then(async res => {
      if (res.ok) {
        const data = await res.json();
        if (data.icons) setIconList(data.icons);
        if (data.colors) setColorList(data.colors);
        if (data.fonts) setFontList(data.fonts);
      }
    }).catch(() => {});
  }, []);

  const updateRow = (idx: number, patch: Partial<typeof rows[0]>) => {
    onChange(rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const removeRow = (idx: number) => onChange(rows.filter((_, i) => i !== idx));

  const toggleCondition = (idx: number, checked: boolean) => {
    if (checked) {
      updateRow(idx, { condition: '' });
    } else {
      const { condition: _c, ...rest } = rows[idx];
      onChange(rows.map((r, i) => (i === idx ? rest : r)));
    }
  };

  const toggleAnimation = (idx: number, checked: boolean) => {
    if (checked) {
      updateRow(idx, { animation: { from: DEFAULT_ANIM_POS, to: DEFAULT_ANIM_POS, duration: 3 } });
    } else {
      const { animation: _a, ...rest } = rows[idx];
      onChange(rows.map((r, i) => (i === idx ? rest : r)));
    }
  };

  const renderStep = (step: AnimStep, si: number, steps: AnimStep[], updateSteps: (s: AnimStep[]) => void) => {
    const updateStep = (patch: Partial<AnimStep>) =>
      updateSteps(steps.map((s, i) => (i === si ? { ...s, ...patch } : s)));
    const isMulti = steps.length > 1;
    const isIconStep = step.icon !== undefined;

    const switchStepToImage = () => {
      const { icon: _i, icon_color: _c, icon_size: _s, ...rest } = step as any;
      updateSteps(steps.map((s, i) => (i === si ? rest : s)));
    };
    const switchStepToIcon = () => {
      const { image: _img, ...rest } = step as any;
      updateSteps(steps.map((s, i) => (i === si ? { ...rest, icon: '', icon_color: 'white', icon_size: 'big' } : s)));
    };

    return (
      <div key={si} className={isMulti ? 'border border-slate-100 rounded p-2 space-y-1.5' : 'space-y-1.5'}>
        {isMulti && (
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-blue-500 uppercase font-semibold">Step {si + 1}</span>
            <div className="flex items-center gap-1">
              {si > 0 && (
                <div className="flex rounded border border-slate-200 overflow-hidden text-[9px]">
                  <button
                    type="button"
                    onClick={switchStepToImage}
                    className={`px-1.5 py-0.5 ${!isIconStep ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use image for this step"
                  >Image</button>
                  <button
                    type="button"
                    onClick={switchStepToIcon}
                    className={`px-1.5 py-0.5 ${isIconStep ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use icon for this step"
                  >Icon</button>
                </div>
              )}
              <button
                type="button"
                onClick={() => updateSteps(steps.filter((_, i) => i !== si))}
                className="text-red-400 hover:text-red-600 p-0.5 rounded"
                title="Remove step"
              ><Trash2 size={12} /></button>
            </div>
          </div>
        )}
        <div className="flex gap-4 items-start flex-wrap">
          <FractionalPositionPicker
            value={normalizePos(step.from ?? DEFAULT_ANIM_POS)}
            onChange={v => updateStep({ from: v })}
            label="From"
            ghostPoint={si > 0 ? normalizePos(steps[si - 1].to ?? DEFAULT_ANIM_POS) : undefined}
          />
          <div className="flex items-center self-center pt-4 text-slate-400 text-lg">→</div>
          <FractionalPositionPicker
            value={normalizePos(step.to ?? DEFAULT_ANIM_POS)}
            onChange={v => updateStep({ to: v })}
            label="To"
          />
        </div>
        <div>
          <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Duration (seconds)</label>
          <input
            type="number" min={0.5} step={0.5} value={step.duration}
            onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v) && v > 0) updateStep({ duration: v }); }}
            className="w-full border rounded p-1 text-xs"
          />
        </div>
        {!isIconStep && si > 0 && (
          <div>
            <div className="flex items-center gap-1 mb-0.5">
              <label className="block text-[10px] text-slate-500 uppercase">Image</label>
              <span className="text-[9px] text-slate-400">(overrides row image)</span>
              {step.image && (
                <button
                  type="button"
                  onClick={() => { const { image: _i, ...rest } = step as any; updateSteps(steps.map((s, i) => (i === si ? rest : s))); }}
                  className="ml-auto text-slate-400 hover:text-slate-600 p-0.5 rounded"
                  title="Clear — inherit row image"
                ><X size={10} /></button>
              )}
            </div>
            <ImageSelectInput
              value={step.image ?? ''}
              onChange={v => updateStep({ image: v })}
              images={images}
            />
          </div>
        )}
        {isIconStep && (
          <div className="space-y-1">
            <label className="block text-[10px] text-slate-500 uppercase">Icon</label>
            <IconPicker
              value={step.icon ?? ''}
              onChange={v => updateStep({ icon: v })}
              icons={iconList}
            />
            <div className="flex gap-2">
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Color</label>
                <ColorPicker
                  value={step.icon_color ?? 'white'}
                  onChange={v => updateStep({ icon_color: v })}
                  colors={colorList}
                />
              </div>
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Size</label>
                <select
                  value={step.icon_size ?? 'big'}
                  onChange={e => updateStep({ icon_size: e.target.value })}
                  className="w-full border rounded p-1 text-xs bg-white"
                >
                  {fontList.length === 0 && <option value="big">big</option>}
                  {fontList.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2">
      {rows.map((row, idx) => {
        const hasCondition = 'condition' in row;
        const hasAnimation = !!row.animation;
        const isIconRow = row.icon !== undefined;

        const switchToImage = () => {
          const { icon: _i, icon_color: _c, icon_size: _s, ...rest } = row as any;
          onChange(rows.map((r, i) => (i === idx ? { ...rest, image: '' } : r)));
        };
        const switchToIcon = () => {
          const { image: _m, ...rest } = row as any;
          onChange(rows.map((r, i) => (i === idx ? { ...rest, icon: '', icon_color: 'white', icon_size: 'big' } : r)));
        };

        return (
          <div key={idx} className="border rounded p-2 bg-white">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-slate-500 uppercase font-medium">Layer {idx + 1}</span>
              <div className="flex items-center gap-1">
                <div className="flex rounded border border-slate-200 overflow-hidden text-[9px]">
                  <button
                    type="button"
                    onClick={switchToImage}
                    className={`px-1.5 py-0.5 ${!isIconRow ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use image"
                  >Image</button>
                  <button
                    type="button"
                    onClick={switchToIcon}
                    className={`px-1.5 py-0.5 ${isIconRow ? 'bg-blue-500 text-white font-bold' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                    title="Use icon"
                  >Icon</button>
                </div>
                <button
                  type="button"
                  onClick={() => removeRow(idx)}
                  className="text-red-400 hover:text-red-600 p-0.5 rounded"
                  title="Remove"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            {!isIconRow && (
              <div className="mb-2">
                <ImageSelectInput
                  value={row.image ?? ''}
                  onChange={v => updateRow(idx, { image: v })}
                  images={images}
                />
              </div>
            )}

            {isIconRow && (
              <div className="mb-2 space-y-1">
                <label className="block text-[10px] text-slate-500 uppercase">Icon</label>
                <IconPicker
                  value={row.icon ?? ''}
                  onChange={v => updateRow(idx, { icon: v })}
                  icons={iconList}
                />
                <div className="flex gap-2">
                  <div className="flex-1 min-w-0">
                    <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Color</label>
                    <ColorPicker
                      value={row.icon_color ?? 'white'}
                      onChange={v => updateRow(idx, { icon_color: v })}
                      colors={colorList}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <label className="block text-[10px] text-slate-500 uppercase mb-0.5">Size</label>
                    <select
                      value={row.icon_size ?? 'big'}
                      onChange={e => updateRow(idx, { icon_size: e.target.value })}
                      className="w-full border rounded p-1 text-xs bg-white"
                    >
                      {fontList.length === 0 && <option value="big">big</option>}
                      {fontList.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            )}

            <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer select-none mt-1">
              <input
                type="checkbox"
                checked={hasCondition}
                onChange={e => toggleCondition(idx, e.target.checked)}
                className="rounded border-slate-300"
              />
              Conditional
            </label>
            {hasCondition && (
              <div className="mt-1">
                <ConditionBuilder value={row.condition} onChange={v => updateRow(idx, { condition: v })} />
              </div>
            )}

            <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer select-none mt-2">
              <input
                type="checkbox"
                checked={hasAnimation}
                onChange={e => toggleAnimation(idx, e.target.checked)}
                className="rounded border-slate-300"
              />
              Animate
            </label>
            {hasAnimation && (() => {
              const steps = toSteps(row.animation!);
              const updateSteps = (newSteps: AnimStep[]) =>
                updateRow(idx, { animation: newSteps.length ? fromSteps(newSteps) : undefined });
              return (
                <div className="mt-1 pl-2 border-l-2 border-blue-100 space-y-2">
                  {steps.map((step, si) => renderStep(step, si, steps, updateSteps))}
                  <button
                    type="button"
                    onClick={() => {
                      const iconDefaults = isIconRow
                        ? { icon: row.icon ?? '', icon_color: row.icon_color ?? 'white', icon_size: row.icon_size ?? 'big' }
                        : {};
                      const normalizedSteps = isIconRow
                        ? steps.map(s => (s.icon === undefined ? { ...s, ...iconDefaults } : s))
                        : steps;
                      updateSteps([...normalizedSteps, { from: DEFAULT_ANIM_POS, to: DEFAULT_ANIM_POS, duration: 3, ...iconDefaults }]);
                    }}
                    className="w-full text-xs text-purple-500 border border-dashed border-purple-200 rounded py-0.5 hover:bg-purple-50 flex items-center justify-center gap-1"
                  ><Plus size={10} /> Add step</button>
                </div>
              );
            })()}
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, { image: '' }])}
        className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded py-1 hover:bg-blue-50 flex items-center justify-center gap-1"
      >
        <Plus size={12} /> Add Image / Icon
      </button>
    </div>
  );
};
