import { Trash2, Plus } from 'lucide-react';
import { Config, ImageEntry, Page, ScreenBgEntry, ScreenImageEntry } from '../types';
import { ConditionBuilder, ImageSelectInput } from './FormInputs';
import { ColorPicker } from './Pickers';

export const PagePropertiesPanel = ({
  activePage,
  config,
  colorList,
  screenImages,
  onUpdatePage,
  onRenamePage,
  setConfig,
}: {
  activePage: Page;
  config: Config;
  colorList: { id: string; value: string }[];
  screenImages?: Record<string, ScreenImageEntry>;
  onUpdatePage: (p: Page) => void;
  onRenamePage: (oldId: string, newId: string) => void;
  setConfig?: (config: Config) => void;
}) => {
  const bgEntries: ScreenBgEntry[] = activePage.background || [];
  const bgEnabled = bgEntries.length > 0;
  const updateBg = (entries: ScreenBgEntry[]) => {
    onUpdatePage({ ...activePage, background: entries.length > 0 ? entries : undefined });
  };

  return (
    <>
      <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-3 tracking-wider">Page Settings</label>
        <div className="mb-4">
          <label className="block text-xs text-slate-600 mb-1 font-medium">Page ID</label>
          <input
            type="text"
            value={activePage.id}
            onChange={e => onRenamePage(activePage.id, e.target.value)}
            className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
          />
        </div>

        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-3 tracking-wider">Grid Dimensions</label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Rows</label>
            <input
              type="number"
              value={activePage.rows}
              onChange={e => onUpdatePage({ ...activePage, rows: Math.max(1, parseInt(e.target.value) || 1) })}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Columns</label>
            <input
              type="number"
              value={activePage.cols}
              onChange={e => onUpdatePage({ ...activePage, cols: Math.max(1, parseInt(e.target.value) || 1) })}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
          </div>
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Page Flags</label>
        <div className="space-y-2">
          {['BASE', 'TEMPORARY', 'FAST_REFRESH', 'OMIT_TIME_WIFI'].map(flag => {
            const isChecked = activePage.flags?.includes(flag) || false;
            const isBase = flag === 'BASE';
            const isTemporaryFlag = flag === 'TEMPORARY';
            const isCurrentBase = activePage.flags?.includes('BASE');
            const isTemporary = activePage.flags?.includes('TEMPORARY');
            const isDisabled =
              (isBase && isCurrentBase) ||
              (isBase && isTemporary && !isChecked) ||
              (isTemporaryFlag && isCurrentBase && !isChecked);

            return (
              <div key={flag} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id={`flag-${flag}`}
                  checked={isChecked}
                  disabled={isDisabled}
                  onChange={e => {
                    if (isBase && e.target.checked) {
                      if (setConfig) {
                        const updatedPages = config.pages.map(p => ({
                          ...p,
                          flags:
                            p.id === activePage.id
                              ? [...(p.flags || []), 'BASE']
                              : p.flags?.filter(f => f !== 'BASE') || [],
                        }));
                        setConfig({ ...config, pages: updatedPages });
                      }
                    } else {
                      const newFlags = e.target.checked
                        ? [...(activePage.flags || []), flag]
                        : (activePage.flags || []).filter(f => f !== flag);
                      onUpdatePage({ ...activePage, flags: newFlags });
                    }
                  }}
                  className={`rounded ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                />
                <label htmlFor={`flag-${flag}`} className={`text-sm ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
                  {flag === 'OMIT_TIME_WIFI' ? 'Omit time & WiFi indicator' : flag}
                  {isBase && isCurrentBase && <span className="text-xs text-slate-500 ml-1">(cannot remove)</span>}
                  {isBase && isTemporary && !isChecked && <span className="text-xs text-slate-500 ml-1">(cannot use with TEMPORARY)</span>}
                  {isTemporaryFlag && isCurrentBase && !isChecked && <span className="text-xs text-slate-500 ml-1">(cannot use with BASE)</span>}
                </label>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Time Color</label>
        <div className="bg-slate-50 rounded-lg border border-slate-100 p-3">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="page-time-color-enable"
              checked={!!activePage.time_color}
              onChange={e => {
                if (e.target.checked) {
                  onUpdatePage({ ...activePage, time_color: 'dark_gray' });
                } else {
                  const { time_color: _tc, ...rest } = activePage as any;
                  onUpdatePage(rest as Page);
                }
              }}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="page-time-color-enable" className="text-xs font-medium text-slate-700 select-none cursor-pointer">
              Override time color
            </label>
          </div>
          {activePage.time_color && (
            <div className="pl-4 mt-3">
              <ColorPicker
                value={activePage.time_color}
                onChange={v => onUpdatePage({ ...activePage, time_color: v })}
                colors={colorList}
              />
            </div>
          )}
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Screen Background</label>
        <div className="bg-slate-50 rounded-lg border border-slate-100 p-3">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="page-bg-enable"
              checked={bgEnabled}
              onChange={e => updateBg(e.target.checked ? [{ color: 'black' }] : [])}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="page-bg-enable" className="text-xs font-medium text-slate-700 select-none cursor-pointer">
              Enable background
            </label>
          </div>

          {bgEnabled && (
            <div className="pl-4 mt-3 space-y-3">
              {bgEntries.map((entry, idx) => {
                const isImage = 'image' in entry;
                const hasCondition = 'condition' in entry;
                return (
                  <div key={idx} className="space-y-2 pb-2 border-b border-slate-200 last:border-b-0 last:pb-0">
                    <div className="flex items-center gap-2">
                      <select
                        value={isImage ? 'image' : 'color'}
                        onChange={e => {
                          const newEntries = bgEntries.map((en, i) => {
                            if (i !== idx) return en;
                            if (e.target.value === 'image') {
                              const { color: _c, ...rest } = en as any;
                              return { ...rest, image: '' };
                            }
                            const { image: _img, ...rest } = en as any;
                            return { ...rest, color: 'black' };
                          });
                          updateBg(newEntries);
                        }}
                        className="text-xs border rounded px-1.5 py-1 bg-white flex-shrink-0"
                      >
                        <option value="color">Color</option>
                        <option value="image">Image</option>
                      </select>
                      <div className="flex-1 min-w-0">
                        {isImage ? (
                          <ImageSelectInput
                            value={entry.image || ''}
                            onChange={v => updateBg(bgEntries.map((en, i) => (i === idx ? { ...en, image: v } : en)))}
                            images={(screenImages || {}) as Record<string, ImageEntry>}
                          />
                        ) : (
                          <ColorPicker
                            value={(entry as any).color || 'black'}
                            onChange={v => updateBg(bgEntries.map((en, i) => (i === idx ? { ...en, color: v } : en)))}
                            colors={colorList}
                          />
                        )}
                      </div>
                      <button
                        onClick={() => updateBg(bgEntries.filter((_, i) => i !== idx))}
                        className="text-red-400 hover:text-red-600 p-0.5 rounded shrink-0"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        id={`bg-cond-${idx}`}
                        checked={hasCondition}
                        onChange={ev => {
                          const newEntries = bgEntries.map((en, i) => {
                            if (i !== idx) return en;
                            const updated = { ...en };
                            if (ev.target.checked) {
                              (updated as any).condition = '';
                            } else {
                              delete (updated as any).condition;
                            }
                            return updated;
                          });
                          updateBg(newEntries);
                        }}
                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      <label htmlFor={`bg-cond-${idx}`} className="text-[10px] text-slate-500 select-none cursor-pointer">
                        Only if condition
                      </label>
                    </div>
                    {hasCondition && (
                      <ConditionBuilder
                        value={(entry as any).condition || ''}
                        onChange={v => updateBg(bgEntries.map((en, i) => (i === idx ? { ...en, condition: v } : en)))}
                      />
                    )}
                  </div>
                );
              })}
              <button
                onClick={() => updateBg([...bgEntries, { color: 'black' }])}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                <Plus size={12} /> Add background layer
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
};
