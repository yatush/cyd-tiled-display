import { useState, useEffect, KeyboardEvent } from 'react';
import { Trash2, Copy, Layout, Settings2, Plus } from 'lucide-react';
import { Tile, Config, Page, HaEntity, ImageEntry, ScreenBgEntry, ScreenImageEntry } from '../types';
import { 
  TextInput, 
  Checkbox, 
  ScriptInput, 
  ArrayInput, 
  ObjectInput, 
  ObjectArrayInput, 
  EntityArrayInput, 
  EntityListInput,
  ConditionBuilder,
  ImagesListInput,
  ImageSelectInput
} from './FormInputs';
import { DisplayListInput } from './DisplayListInput';
import { ColorPicker } from './Pickers';
import { apiFetch } from '../utils/api';
import { generateTileYaml, generatePageYaml } from '../utils/yamlGenerator';
import { parseTileYaml, parsePageYaml } from '../utils/tileYaml';
import { getTileDynamicEntities } from '../utils/yamlParser';

type YamlDraft = { text: string; initialText: string; baseSnapshot: string };

const handleYamlKeyDown = (
  event: KeyboardEvent<HTMLTextAreaElement>,
  text: string,
  onChangeText: (nextText: string) => void
) => {
  if ((event.key !== 'Enter' && event.key !== 'Tab') || event.ctrlKey || event.metaKey || event.altKey) return;
  const input = event.currentTarget;
  const start = input.selectionStart;
  const end = input.selectionEnd;
  if (event.shiftKey && (event.key !== 'Tab' || start === end)) return;
  if (event.key === 'Tab' && start !== end) {
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const lastSelected = text[end - 1] === '\n' ? end - 1 : end;
    const lineEnd = text.indexOf('\n', lastSelected);
    const blockEnd = lineEnd === -1 ? text.length : lineEnd;
    const block = text.slice(lineStart, blockEnd).split('\n')
      .map(line => event.shiftKey ? line.replace(/^ {1,2}/, '') : `  ${line}`).join('\n');
    event.preventDefault();
    onChangeText(text.slice(0, lineStart) + block + text.slice(blockEnd));
    requestAnimationFrame(() => {
      input.selectionStart = lineStart;
      input.selectionEnd = lineStart + block.length;
    });
    return;
  }
  let insertion = '  ';
  if (event.key === 'Enter') {
    const line = text.slice(text.lastIndexOf('\n', start - 1) + 1, start);
    const spaces = line.match(/^ */)?.[0] ?? '';
    const extra = /:\s*$/.test(line) ? (/^\s*-\s+/.test(line) ? '    ' : '  ') : '';
    insertion = `\n${spaces}${extra}`;
  }
  event.preventDefault();
  onChangeText(text.slice(0, start) + insertion + text.slice(end));
  requestAnimationFrame(() => {
    input.selectionStart = input.selectionEnd = start + insertion.length;
  });
};

export const Sidebar = ({ selectedTile, onUpdate, onDelete, onDuplicate, config, schema, activePage, setActivePageId, onUpdatePage, onRenamePage, haEntities, setConfig, screenImages }: {
  selectedTile: Tile | null, 
  onUpdate: (t: Tile, discoverDynamicEntities?: boolean) => void,
  onDelete: () => void,
  onDuplicate: (id: string) => void,
  config: Config,
  schema: any,
  activePage: Page,
  setActivePageId?: (id: string) => void,
  onUpdatePage: (p: Page) => void,
  onRenamePage: (oldId: string, newId: string) => void,
  haEntities: HaEntity[],
  setConfig?: (config: Config) => void,
  screenImages?: Record<string, ScreenImageEntry>
}) => {
  const [activeTab, setActiveTab] = useState<'tile' | 'page'>('page');
  const [tileEditor, setTileEditor] = useState<'form' | 'yaml'>('form');
  const [yamlDrafts, setYamlDrafts] = useState<Record<string, YamlDraft>>({});
  const [yamlError, setYamlError] = useState('');
  const [pageEditor, setPageEditor] = useState<'form' | 'yaml'>('form');
  const [pageYamlDrafts, setPageYamlDrafts] = useState<Record<string, YamlDraft>>({});
  const [pageYamlError, setPageYamlError] = useState('');

  const dynamicEntities = config.dynamic_entities || [];
  const tileSchema = selectedTile ? schema?.types?.find((t: any) => t.type === selectedTile.type) : null;
  const images = config.images || {};
  const tileIds = new Set(config.pages.flatMap(page => page.tiles.map(tile => tile.id)));
  const orphanDrafts = Object.entries(yamlDrafts).filter(([id]) => !tileIds.has(id));
  const pageIds = new Set(config.pages.map(page => page.id));
  const orphanPageDrafts = Object.entries(pageYamlDrafts).filter(([id]) => !pageIds.has(id));

  const [colorList, setColorList] = useState<{id: string, value: string}[]>([]);

  // Switch to tile tab when a tile is selected
  useEffect(() => {
    if (selectedTile) {
      setActiveTab('tile');
    }
    setYamlError('');
  }, [selectedTile?.id]);

  useEffect(() => {
    setPageYamlError('');
  }, [activePage.id]);

  useEffect(() => {
    if (Object.keys(yamlDrafts).length === 0 && Object.keys(pageYamlDrafts).length === 0) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [yamlDrafts, pageYamlDrafts]);

  useEffect(() => {
    apiFetch('/scripts').then(async res => {
      if (res.ok) {
        const data = await res.json();
        if (data.colors) setColorList(data.colors);
      }
    }).catch(() => {});
  }, []);

  const draft = selectedTile ? yamlDrafts[selectedTile.id] : undefined;
  const yamlText = selectedTile && tileEditor === 'yaml' ? draft?.text ?? generateTileYaml(selectedTile) : '';
  const updateYamlText = (text: string) => {
    if (!selectedTile) return;
    const initialText = draft?.initialText ?? generateTileYaml(selectedTile);
    setYamlDrafts(current => {
      const next = { ...current };
      if (text === initialText) delete next[selectedTile.id];
      else next[selectedTile.id] = {
        text,
        initialText,
        baseSnapshot: draft?.baseSnapshot ?? JSON.stringify(selectedTile)
      };
      return next;
    });
    setYamlError('');
  };
  const discardYamlDraft = () => {
    if (!selectedTile) return;
    setYamlDrafts(current => {
      const next = { ...current };
      delete next[selectedTile.id];
      return next;
    });
    setYamlError('');
  };
  const applyYamlDraft = () => {
    if (!selectedTile) return;
    if (draft && draft.baseSnapshot !== JSON.stringify(selectedTile)) {
      setYamlError('The tile changed since this draft was started. Cancel the draft and reopen YAML to edit the current tile.');
      return;
    }
    try {
      const tile = parseTileYaml(yamlText, selectedTile.id);
      if (tile.x >= activePage.cols || tile.y >= activePage.rows) {
        throw new Error('The tile position must be within the current page grid.');
      }
      onUpdate(tile, true);
      discardYamlDraft();
      setTileEditor('form');
    } catch (error) {
      setYamlError(error instanceof Error ? error.message : String(error));
    }
  };

  const pageDraft = pageYamlDrafts[activePage.id];
  const pageYamlText = pageEditor === 'yaml' ? pageDraft?.text ?? generatePageYaml(activePage) : '';
  const updatePageYamlText = (text: string) => {
    const initialText = pageDraft?.initialText ?? generatePageYaml(activePage);
    setPageYamlDrafts(current => {
      const next = { ...current };
      if (text === initialText) delete next[activePage.id];
      else next[activePage.id] = {
        text,
        initialText,
        baseSnapshot: pageDraft?.baseSnapshot ?? JSON.stringify(activePage)
      };
      return next;
    });
    setPageYamlError('');
  };
  const discardPageYamlDraft = () => {
    setPageYamlDrafts(current => {
      const next = { ...current };
      delete next[activePage.id];
      return next;
    });
    setPageYamlError('');
  };
  const applyPageYamlDraft = () => {
    if (pageDraft && pageDraft.baseSnapshot !== JSON.stringify(activePage)) {
      setPageYamlError('The page changed since this draft was started. Cancel the draft and reopen YAML to edit the current page.');
      return;
    }
    try {
      const existingPageIds = config.pages.filter(p => p.id !== activePage.id).map(p => p.id);
      const parsedPage = parsePageYaml(pageYamlText, activePage, existingPageIds);
      const otherHasBase = config.pages.some(p => p.id !== activePage.id && p.flags?.includes('BASE'));
      if (config.pages.length > 1 && activePage.flags?.includes('BASE') && !parsedPage.flags?.includes('BASE') && !otherHasBase) {
        throw new Error('Cannot remove BASE flag from the only BASE page. Set BASE on another page instead.');
      }

      if (setConfig) {
        let pages = config.pages.map(p => {
          if (p.id === activePage.id) return parsedPage;
          if (parsedPage.flags?.includes('BASE') && p.flags?.includes('BASE')) {
            return { ...p, flags: p.flags.filter(f => f !== 'BASE') };
          }
          return p;
        });
        if (parsedPage.id !== activePage.id) {
          pages = pages.map(p => ({
            ...p,
            tiles: p.tiles.map(t => ({
              ...t,
              ...(t.destination === activePage.id ? { destination: parsedPage.id } : {}),
              ...(t.long_destination === activePage.id ? { long_destination: parsedPage.id } : {}),
              ...(t.display_page_if_no_entity === activePage.id ? { display_page_if_no_entity: parsedPage.id } : {}),
            }))
          }));
        }
        const existingDynamic = config.dynamic_entities || [];
        const discovered = Array.from(new Set(parsedPage.tiles.flatMap(t => getTileDynamicEntities(t))));
        const nextDynamic = [...existingDynamic];
        for (const dyn of discovered) {
          if (!nextDynamic.includes(dyn)) nextDynamic.push(dyn);
        }
        setConfig({
          ...config,
          pages,
          ...(nextDynamic.length > existingDynamic.length ? { dynamic_entities: nextDynamic } : {})
        });
        if (parsedPage.id !== activePage.id) {
          setActivePageId?.(parsedPage.id);
        }
      } else {
        if (parsedPage.id !== activePage.id) {
          onUpdatePage({ ...parsedPage, id: activePage.id });
          onRenamePage(activePage.id, parsedPage.id);
          setActivePageId?.(parsedPage.id);
        } else {
          onUpdatePage(parsedPage);
        }
      }

      discardPageYamlDraft();
      setPageEditor('form');
    } catch (error) {
      setPageYamlError(error instanceof Error ? error.message : String(error));
    }
  };

  const renderPageProperties = () => (
    <div className="space-y-5 pb-20">
      <div className="flex justify-between items-start border-b pb-3">
        <div>
          <h2 className="font-bold text-base text-slate-800">Edit Page</h2>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">{activePage.id}</div>
        </div>
      </div>

      <div className="flex gap-2" aria-label="Page editor mode">
        <button
          type="button"
          onClick={() => setPageEditor('form')}
          className={`px-3 py-1 rounded text-sm ${pageEditor === 'form' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
        >Form</button>
        <button
          type="button"
          onClick={() => setPageEditor('yaml')}
          className={`px-3 py-1 rounded text-sm ${pageEditor === 'yaml' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
        >YAML{pageDraft ? ' *' : ''}</button>
      </div>

      {pageEditor === 'yaml' ? (
        <div className="space-y-2">
          <label htmlFor="page-yaml" className="block text-xs font-medium text-slate-700">Page YAML</label>
          <p className="text-xs text-slate-500">Edit this screen and its tiles as YAML. Common leading indentation is removed; relative indentation must be valid. Comments and formatting are not saved.</p>
          <textarea
            id="page-yaml"
            spellCheck={false}
            value={pageYamlText}
            onChange={event => updatePageYamlText(event.target.value)}
            onKeyDown={event => handleYamlKeyDown(event, pageYamlText, updatePageYamlText)}
            className="w-full min-h-[380px] border-2 border-slate-200 rounded-lg p-2 text-xs font-mono focus:border-blue-500 outline-none"
          />
          {pageYamlError && <p role="alert" className="text-xs text-red-600 whitespace-pre-wrap">{pageYamlError}</p>}
          <div className="flex gap-2">
            <button type="button" onClick={applyPageYamlDraft} className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm">Apply</button>
            <button type="button" onClick={() => { discardPageYamlDraft(); setPageEditor('form'); }} className="px-3 py-1.5 rounded bg-slate-100 text-slate-700 text-sm">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {pageDraft && <p className="text-xs text-amber-700">A YAML draft is pending. Return to YAML to apply or cancel it.</p>}
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
              onChange={e => onUpdatePage({...activePage, rows: Math.max(1, parseInt(e.target.value) || 1)})}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Columns</label>
            <input 
              type="number" 
              value={activePage.cols} 
              onChange={e => onUpdatePage({...activePage, cols: Math.max(1, parseInt(e.target.value) || 1)})}
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
            
            // Cannot uncheck BASE if it's the current base screen
            // Cannot check BASE if page is TEMPORARY
            // Cannot check TEMPORARY if page is BASE
            const isDisabled = (isBase && isCurrentBase) || (isBase && isTemporary && !isChecked) || (isTemporaryFlag && isCurrentBase && !isChecked);
            
            return (
              <div key={flag} className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  id={`flag-${flag}`}
                  checked={isChecked}
                  disabled={isDisabled}
                  onChange={(e) => {
                    if (isBase && e.target.checked) {
                      // When setting BASE on this page, remove it from all others
                      if (setConfig) {
                        const updatedPages = config.pages.map(p => ({
                          ...p,
                          flags: p.id === activePage.id 
                            ? [...(p.flags || []), 'BASE'] 
                            : (p.flags?.filter(f => f !== 'BASE') || [])
                        }));
                        setConfig({...config, pages: updatedPages});
                      }
                    } else {
                      // For other flags, just add/remove normally
                      const newFlags = e.target.checked 
                        ? [...(activePage.flags || []), flag]
                        : (activePage.flags || []).filter(f => f !== flag);
                      onUpdatePage({...activePage, flags: newFlags});
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

      {/* Time Color */}
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

      {/* Screen Background */}
      <div>
        <label className="block text-[10px] font-bold text-slate-500 uppercase mb-2 tracking-wider">Screen Background</label>
        <div className="bg-slate-50 rounded-lg border border-slate-100 p-3">
          {(() => {
            const bgEntries: ScreenBgEntry[] = activePage.background || [];
            const bgEnabled = bgEntries.length > 0;

            const updateBg = (entries: ScreenBgEntry[]) => {
              onUpdatePage({ ...activePage, background: entries.length > 0 ? entries : undefined });
            };

            return (
              <>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="page-bg-enable"
                    checked={bgEnabled}
                    onChange={e => {
                      if (e.target.checked) {
                        updateBg([{ color: 'black' }]);
                      } else {
                        updateBg([]);
                      }
                    }}
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
                          {/* Type + delete row */}
                          <div className="flex items-center gap-2">
                            <select
                              value={isImage ? 'image' : 'color'}
                              onChange={e => {
                                const newEntries = bgEntries.map((en, i) => {
                                  if (i !== idx) return en;
                                  if (e.target.value === 'image') {
                                    const { color: _c, ...rest } = en as any;
                                    return { ...rest, image: '' };
                                  } else {
                                    const { image: _img, ...rest } = en as any;
                                    return { ...rest, color: 'black' };
                                  }
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
                                  onChange={v => {
                                    const newEntries = bgEntries.map((en, i) => i === idx ? { ...en, image: v } : en);
                                    updateBg(newEntries);
                                  }}
                                  images={(screenImages || {}) as Record<string, ImageEntry>}
                                />
                              ) : (
                                <ColorPicker
                                  value={(entry as any).color || 'black'}
                                  onChange={v => {
                                    const newEntries = bgEntries.map((en, i) => i === idx ? { ...en, color: v } : en);
                                    updateBg(newEntries);
                                  }}
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

                          {/* Only if condition */}
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
                              onChange={v => {
                                const newEntries = bgEntries.map((en, i) => i === idx ? { ...en, condition: v } : en);
                                updateBg(newEntries);
                              }}
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
              </>
            );
          })()}
        </div>
      </div>
    </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex border-b bg-slate-50">
        <button
          onClick={() => setActiveTab('page')}
          className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'page' 
              ? 'bg-white text-blue-600 border-b-2 border-blue-600' 
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          <Layout size={16} />
          Page
        </button>
        <button
          onClick={() => setActiveTab('tile')}
          disabled={!selectedTile}
          className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'tile' 
              ? 'bg-white text-blue-600 border-b-2 border-blue-600' 
              : 'text-slate-400 hover:text-slate-600 disabled:opacity-30'
          }`}
        >
          <Settings2 size={16} />
          Tile
        </button>
      </div>

      {(orphanDrafts.length > 0 || orphanPageDrafts.length > 0) && (
        <div className="p-3 bg-amber-50 text-xs text-amber-800 space-y-2">
          {orphanDrafts.length > 0 && (
            <>
              <p>These YAML drafts belong to tiles no longer in the project. Copy or discard them before leaving.</p>
              {orphanDrafts.map(([id, orphan]) => (
                <details key={`tile-${id}`}>
                  <summary className="cursor-pointer">Draft for removed tile {id}</summary>
                  <textarea aria-label={`Draft for removed tile ${id}`} readOnly value={orphan.text} className="w-full min-h-[100px] mt-1 p-1 font-mono border rounded bg-white" />
                  <button type="button" className="underline" onClick={() => {
                    if (!confirm('Discard this YAML draft?')) return;
                    setYamlDrafts(current => {
                      const next = { ...current };
                      delete next[id];
                      return next;
                    });
                  }}>Discard draft</button>
                </details>
              ))}
            </>
          )}
          {orphanPageDrafts.length > 0 && (
            <>
              <p>These YAML drafts belong to pages no longer in the project. Copy or discard them before leaving.</p>
              {orphanPageDrafts.map(([id, orphan]) => (
                <details key={`page-${id}`}>
                  <summary className="cursor-pointer">Draft for removed page {id}</summary>
                  <textarea aria-label={`Draft for removed page ${id}`} readOnly value={orphan.text} className="w-full min-h-[100px] mt-1 p-1 font-mono border rounded bg-white" />
                  <button type="button" className="underline" onClick={() => {
                    if (!confirm('Discard this YAML draft?')) return;
                    setPageYamlDrafts(current => {
                      const next = { ...current };
                      delete next[id];
                      return next;
                    });
                  }}>Discard draft</button>
                </details>
              ))}
            </>
          )}
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'page' ? (
          renderPageProperties()
        ) : selectedTile ? (
          <div className="space-y-5 pb-20">
            {/* Header */}
            <div className="flex justify-between items-start border-b pb-3">
              <div>
                <h2 className="font-bold text-base text-slate-800">Edit Tile</h2>
                <div className="text-[10px] font-mono text-slate-400 mt-0.5">{selectedTile.type}</div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => onDuplicate(selectedTile.id)} className="text-blue-600 hover:bg-blue-50 p-1.5 rounded-lg transition-colors" title="Duplicate Tile" aria-label="Duplicate Tile">
                  <Copy size={18} />
                </button>
                <button onClick={() => onDelete()} className="text-red-500 hover:bg-red-50 p-1.5 rounded-lg transition-colors" title="Delete Tile">
                  <Trash2 size={18} />
                </button>
              </div>
            </div>

            <div className="flex gap-2" aria-label="Tile editor mode">
              <button
                type="button"
                onClick={() => setTileEditor('form')}
                className={`px-3 py-1 rounded text-sm ${tileEditor === 'form' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
              >Form</button>
              <button
                type="button"
                onClick={() => setTileEditor('yaml')}
                className={`px-3 py-1 rounded text-sm ${tileEditor === 'yaml' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
              >YAML{draft ? ' *' : ''}</button>
            </div>
            {tileEditor === 'yaml' ? (
              <div className="space-y-2">
                <label htmlFor="tile-yaml" className="block text-xs font-medium text-slate-700">Tile YAML</label>
                <p className="text-xs text-slate-500">Paste one tile. Common leading indentation is removed; relative indentation must be valid. Comments and formatting are not saved.</p>
                <textarea
                  id="tile-yaml"
                  spellCheck={false}
                  value={yamlText}
                  onChange={event => updateYamlText(event.target.value)}
                  onKeyDown={event => handleYamlKeyDown(event, yamlText, updateYamlText)}
                  className="w-full min-h-[300px] border-2 border-slate-200 rounded-lg p-2 text-xs font-mono focus:border-blue-500 outline-none"
                />
                {yamlError && <p role="alert" className="text-xs text-red-600 whitespace-pre-wrap">{yamlError}</p>}
                <div className="flex gap-2">
                  <button type="button" onClick={applyYamlDraft} className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm">Apply</button>
                  <button type="button" onClick={() => { discardYamlDraft(); setTileEditor('form'); }} className="px-3 py-1.5 rounded bg-slate-100 text-slate-700 text-sm">Cancel</button>
                </div>
              </div>
            ) : (
            <>
            {draft && <p className="text-xs text-amber-700">A YAML draft is pending. Return to YAML to apply or cancel it.</p>}
            {/* Position & Size */}
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-widest">Position & Size</label>
              <div className="bg-slate-50 rounded-lg border border-slate-100 p-3 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {schema?.common?.filter((f: any) => f.name === 'x' || f.name === 'y').map((field: any) => (
                    <div key={field.name}>
                      <label className="block text-xs text-slate-500 mb-1 font-medium">{field.label}</label>
                      <input
                        type="number"
                        value={selectedTile[field.name]}
                        onChange={e => onUpdate({...selectedTile, [field.name]: parseInt(e.target.value)})}
                        className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors bg-white"
                      />
                    </div>
                  ))}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="enable_span"
                      checked={selectedTile.x_span !== undefined || selectedTile.y_span !== undefined}
                      onChange={e => {
                        if (!e.target.checked) {
                          const { x_span, y_span, ...rest } = selectedTile;
                          onUpdate(rest);
                        } else {
                          onUpdate({...selectedTile, x_span: 1, y_span: 1});
                        }
                      }}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <label htmlFor="enable_span" className="text-xs font-medium text-slate-700 select-none cursor-pointer">Span Multiple Cells</label>
                  </div>
                  {(selectedTile.x_span !== undefined || selectedTile.y_span !== undefined) && (
                    <div className="grid grid-cols-2 gap-3 pl-6 mt-2">
                      <div>
                        <label className="block text-xs text-slate-500 mb-1 font-medium">X Span</label>
                        <input
                          type="number"
                          value={selectedTile.x_span || 1}
                          onChange={e => onUpdate({...selectedTile, x_span: Math.max(1, parseInt(e.target.value) || 1)})}
                          min={1}
                          className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-500 mb-1 font-medium">Y Span</label>
                        <input
                          type="number"
                          value={selectedTile.y_span || 1}
                          onChange={e => onUpdate({...selectedTile, y_span: Math.max(1, parseInt(e.target.value) || 1)})}
                          min={1}
                          className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors bg-white"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Display */}
            {selectedTile.type !== 'blind_position' && schema?.common?.some((f: any) => f.type === 'display_list') && (() => {
              const field = schema.common.find((f: any) => f.type === 'display_list');
              const imagesField = schema?.common?.find((f: any) => f.type === 'assets_list');
              const hasImages = Array.isArray(selectedTile.display_assets) && selectedTile.display_assets.length > 0;
              const hasDisplayScripts = Array.isArray(selectedTile[field.name]) && selectedTile[field.name].length > 0;
              const imagesEnabled = imagesField && selectedTile[imagesField.name] !== undefined;
              return (
                <div key="display-section">
                  <label className="block text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-widest">Display</label>
                  <div className="bg-slate-50 rounded-lg border border-slate-100 p-3 space-y-3">
                    {hasImages && hasDisplayScripts && (
                      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-1">
                        ⚠ Display scripts are ignored when Display Assets are set.
                      </div>
                    )}
                    <DisplayListInput
                      value={Array.isArray(selectedTile[field.name]) ? selectedTile[field.name] : (selectedTile[field.name] ? [selectedTile[field.name]] : [])}
                      onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                      tileType={selectedTile.type}
                    />
                    {imagesField && (
                      <div className="border-t pt-3">
                        <div className="flex items-center gap-2 mb-2">
                          <input
                            type="checkbox"
                            checked={!!imagesEnabled}
                            onChange={e => {
                              if (e.target.checked) {
                                onUpdate({...selectedTile, [imagesField.name]: []});
                              } else {
                                const newTile = {...selectedTile};
                                delete newTile[imagesField.name];
                                onUpdate(newTile);
                              }
                            }}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                          />
                          <label
                            className="text-xs font-medium text-slate-600 select-none cursor-pointer"
                            onClick={() => {
                              if (!imagesEnabled) onUpdate({...selectedTile, [imagesField.name]: []});
                              else { const t = {...selectedTile}; delete t[imagesField.name]; onUpdate(t); }
                            }}
                          >{imagesField.label}</label>
                        </div>
                        {imagesEnabled && hasDisplayScripts && (
                          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-1 mb-2">
                            ⚠ Cannot have both Images and Display Scripts. Remove the display scripts first.
                          </div>
                        )}
                        {imagesEnabled && (
                          <ImagesListInput
                            value={selectedTile[imagesField.name] || []}
                            onChange={v => onUpdate({...selectedTile, [imagesField.name]: v})}
                            images={images}
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Appearance */}
            {schema?.common?.some((f: any) => f.type === 'boolean' || f.type === 'color' || f.type === 'color_list' || f.type === 'int_list') && (
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-widest">Appearance</label>
                <div className="bg-slate-50 rounded-lg border border-slate-100 p-3 space-y-3">
                  {schema.common.filter((f: any) => f.type === 'boolean' || f.type === 'color' || f.type === 'color_list' || f.type === 'int_list').map((field: any) => {
                    if (field.type === 'boolean') {
                      return (
                        <Checkbox
                          key={field.name}
                          label={field.label}
                          checked={selectedTile[field.name] || false}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                        />
                      );
                    }
                    if (field.type === 'color') {
                      const isEnabled = selectedTile[field.name] !== undefined;
                      return (
                        <div key={field.name}>
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={isEnabled}
                              onChange={e => {
                                if (e.target.checked) {
                                  onUpdate({...selectedTile, [field.name]: 'dark_dark_gray'});
                                } else {
                                  const newTile = {...selectedTile};
                                  delete newTile[field.name];
                                  onUpdate(newTile);
                                }
                              }}
                              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                            />
                            <label
                              className="text-xs font-medium text-slate-700 select-none cursor-pointer"
                              onClick={() => {
                                if (!isEnabled) onUpdate({...selectedTile, [field.name]: 'dark_dark_gray'});
                                else { const t = {...selectedTile}; delete t[field.name]; onUpdate(t); }
                              }}
                            >{field.label}</label>
                          </div>
                          {isEnabled && (
                            <div className="pl-6 mt-1">
                              <ColorPicker
                                value={selectedTile[field.name]}
                                onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                                colors={colorList}
                              />
                            </div>
                          )}
                        </div>
                      );
                    }
                    if (field.type === 'color_list') {
                      const isEnabled = selectedTile[field.name] !== undefined;
                      const entries: {color: string, condition?: any}[] = isEnabled
                        ? (Array.isArray(selectedTile[field.name])
                            ? selectedTile[field.name]
                            : [{color: selectedTile[field.name] || 'dark_dark_gray'}])
                        : [];
                      return (
                        <div key={field.name}>
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={isEnabled}
                              onChange={e => {
                                if (e.target.checked) {
                                  onUpdate({...selectedTile, [field.name]: [{color: 'dark_dark_gray'}]});
                                } else {
                                  const newTile = {...selectedTile};
                                  delete newTile[field.name];
                                  onUpdate(newTile);
                                }
                              }}
                              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                            />
                            <label
                              className="text-xs font-medium text-slate-700 select-none cursor-pointer"
                              onClick={() => {
                                if (!isEnabled) onUpdate({...selectedTile, [field.name]: [{color: 'dark_dark_gray'}]});
                                else { const t = {...selectedTile}; delete t[field.name]; onUpdate(t); }
                              }}
                            >{field.label}</label>
                          </div>
                          {isEnabled && (
                            <div className="pl-6 mt-2 space-y-2">
                              {entries.map((entry, idx) => {
                                const hasCondition = 'condition' in entry;
                                return (
                                <div key={idx} className="space-y-1">
                                  <div className="flex items-center gap-1">
                                    <div className="flex-1">
                                      <ColorPicker
                                        value={entry.color}
                                        onChange={v => {
                                          const newEntries = entries.map((e, i) => i === idx ? {...e, color: v} : e);
                                          onUpdate({...selectedTile, [field.name]: newEntries});
                                        }}
                                        colors={colorList}
                                      />
                                    </div>
                                    {idx > 0 && (
                                      <button
                                        onClick={() => {
                                          const newEntries = entries.filter((_, i) => i !== idx);
                                          onUpdate({...selectedTile, [field.name]: newEntries});
                                        }}
                                        className="text-red-400 hover:text-red-600 p-0.5 rounded shrink-0"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <input
                                      type="checkbox"
                                      id={`fill-cond-${field.name}-${idx}`}
                                      checked={hasCondition}
                                      onChange={ev => {
                                        const newEntries = entries.map((e, i) => {
                                          if (i !== idx) return e;
                                          const updated = {...e};
                                          if (ev.target.checked) {
                                            updated.condition = '';
                                          } else {
                                            delete updated.condition;
                                          }
                                          return updated;
                                        });
                                        onUpdate({...selectedTile, [field.name]: newEntries});
                                      }}
                                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                    />
                                    <label
                                      htmlFor={`fill-cond-${field.name}-${idx}`}
                                      className="text-[10px] text-slate-500 select-none cursor-pointer"
                                    >Only if condition</label>
                                  </div>
                                  {hasCondition && (
                                    <ConditionBuilder
                                      value={entry.condition || ''}
                                      onChange={v => {
                                        const newEntries = entries.map((e, i) => i === idx ? {...e, condition: v} : e);
                                        onUpdate({...selectedTile, [field.name]: newEntries});
                                      }}
                                    />
                                  )}
                                </div>
                                );
                              })}
                              <button
                                onClick={() => {
                                  const newEntries = [...entries, {color: 'dark_dark_gray', condition: ''}];
                                  onUpdate({...selectedTile, [field.name]: newEntries});
                                }}
                                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                              >
                                <Plus size={12} /> Add conditional color
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    }
                    if (field.type === 'int_list') {
                      const isEnabled = selectedTile[field.name] !== undefined;
                      const entries: {value: number, condition?: any}[] = isEnabled
                        ? (Array.isArray(selectedTile[field.name])
                            ? selectedTile[field.name]
                            : [{value: selectedTile[field.name] ?? 1}])
                        : [];
                      return (
                        <div key={field.name}>
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={isEnabled}
                              onChange={e => {
                                if (e.target.checked) {
                                  onUpdate({...selectedTile, [field.name]: [{value: 1}]});
                                } else {
                                  const newTile = {...selectedTile};
                                  delete newTile[field.name];
                                  onUpdate(newTile);
                                }
                              }}
                              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                            />
                            <label
                              className="text-xs font-medium text-slate-700 select-none cursor-pointer"
                              onClick={() => {
                                if (!isEnabled) onUpdate({...selectedTile, [field.name]: [{value: 1}]});
                                else { const t = {...selectedTile}; delete t[field.name]; onUpdate(t); }
                              }}
                            >{field.label}</label>
                          </div>
                          {isEnabled && (
                            <div className="pl-6 mt-2 space-y-2">
                              {entries.map((entry, idx) => {
                                const hasCondition = 'condition' in entry;
                                return (
                                <div key={idx} className="space-y-1">
                                  <div className="flex items-center gap-1">
                                    <input
                                      type="number"
                                      min={0}
                                      value={entry.value}
                                      onChange={e => {
                                        const newEntries = entries.map((en, i) => i === idx ? {...en, value: parseInt(e.target.value) || 0} : en);
                                        onUpdate({...selectedTile, [field.name]: newEntries});
                                      }}
                                      className="w-20 text-xs border border-slate-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                    {idx > 0 && (
                                      <button
                                        onClick={() => {
                                          const newEntries = entries.filter((_, i) => i !== idx);
                                          onUpdate({...selectedTile, [field.name]: newEntries});
                                        }}
                                        className="text-red-400 hover:text-red-600 p-0.5 rounded shrink-0"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <input
                                      type="checkbox"
                                      id={`int-cond-${field.name}-${idx}`}
                                      checked={hasCondition}
                                      onChange={ev => {
                                        const newEntries = entries.map((e, i) => {
                                          if (i !== idx) return e;
                                          const updated = {...e};
                                          if (ev.target.checked) {
                                            (updated as any).condition = '';
                                          } else {
                                            delete (updated as any).condition;
                                          }
                                          return updated;
                                        });
                                        onUpdate({...selectedTile, [field.name]: newEntries});
                                      }}
                                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                    />
                                    <label
                                      htmlFor={`int-cond-${field.name}-${idx}`}
                                      className="text-[10px] text-slate-500 select-none cursor-pointer"
                                    >Only if condition</label>
                                  </div>
                                  {hasCondition && (
                                    <ConditionBuilder
                                      value={(entry as any).condition || ''}
                                      onChange={v => {
                                        const newEntries = entries.map((e, i) => i === idx ? {...e, condition: v} : e);
                                        onUpdate({...selectedTile, [field.name]: newEntries});
                                      }}
                                    />
                                  )}
                                </div>
                                );
                              })}
                              <button
                                onClick={() => {
                                  const newEntries = [...entries, {value: 1, condition: ''}];
                                  onUpdate({...selectedTile, [field.name]: newEntries});
                                }}
                                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                              >
                                <Plus size={12} /> Add conditional value
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>
              </div>
            )}

            {/* Behavior */}
            {schema?.common?.some((f: any) => f.type === 'condition_logic' || (f.type === 'object' && f.optional)) && (
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-widest">Behavior</label>
                <div className="bg-slate-50 rounded-lg border border-slate-100 p-3 space-y-3">
                  {schema.common.filter((f: any) => (f.type === 'condition_logic' || (f.type === 'object' && f.optional)) && !(selectedTile.type === 'blind_position' && f.name === 'requires_fast_refresh')).map((field: any) => {
                    const isEnabled = selectedTile[field.name] !== undefined;
                    const toggle = (enabled: boolean) => {
                      if (enabled) {
                        onUpdate({...selectedTile, [field.name]: field.type === 'object' ? {} : ''});
                      } else {
                        const newTile = {...selectedTile};
                        delete newTile[field.name];
                        onUpdate(newTile);
                      }
                    };
                    return (
                      <div key={field.name}>
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={isEnabled}
                            onChange={e => toggle(e.target.checked)}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                          />
                          <label
                            className="text-xs font-medium text-slate-700 select-none cursor-pointer"
                            onClick={() => toggle(!isEnabled)}
                          >{field.label}</label>
                        </div>
                        {isEnabled && field.type === 'condition_logic' && (
                          <div className="pl-6 mt-2">
                            <ConditionBuilder
                              value={selectedTile[field.name] || ''}
                              onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                            />
                          </div>
                        )}
                        {isEnabled && field.type === 'object' && (
                          <div className="pl-6 mt-2">
                            <ObjectInput
                              label=""
                              value={selectedTile[field.name] || {}}
                              fields={field.objectFields}
                              onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                              dynamicEntities={dynamicEntities}
                              haEntities={haEntities}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Specific Properties */}
            {tileSchema?.fields?.length > 0 && (
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-widest">{tileSchema.label} Properties</label>
                {selectedTile.type === 'ha_action' && (
                  <p className="text-xs text-slate-500 mb-2">A long-press action or destination enables two-second holds. Short actions then run on release instead of touch.</p>
                )}
                <div className="bg-slate-50 rounded-lg border border-slate-100 p-3 space-y-3">
                  {tileSchema.fields.map((field: any) => {
                    if (field.type === 'string' || field.type === 'ha_entity') {
                      return (
                        <TextInput
                          key={field.name}
                          label={field.label}
                          value={selectedTile[field.name] || ''}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          haEntities={field.type === 'ha_entity' ? haEntities : undefined}
                        />
                      );
                    }
                    if (field.type === 'ha_entity_list') {
                      return (
                        <EntityListInput
                          key={field.name}
                          label={field.label}
                          values={selectedTile[field.name] || []}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          haEntities={haEntities}
                        />
                      );
                    }
                    if (field.type === 'boolean') {
                      return (
                        <Checkbox
                          key={field.name}
                          label={field.label}
                          checked={selectedTile[field.name] || false}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                        />
                      );
                    }
                    if (field.type === 'script') {
                      return (
                        <ScriptInput
                          key={field.name}
                          label={field.label}
                          value={selectedTile[field.name] || ''}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          type={field.scriptType}
                        />
                      );
                    }
                    if (field.type === 'script_list') {
                      return (
                        <ArrayInput
                          key={field.name}
                          label={field.label}
                          values={selectedTile[field.name] || []}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          suggestionType={field.scriptType}
                        />
                      );
                    }
                    if (field.type === 'entity_list') {
                      return (
                        <EntityArrayInput
                          key={field.name}
                          label={field.label}
                          values={selectedTile[field.name] || []}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          dynamicEntities={dynamicEntities}
                          haEntities={haEntities}
                        />
                      );
                    }
                    if (field.type === 'object') {
                      if (field.optional) {
                        const isEnabled = selectedTile[field.name] !== undefined;
                        return (
                          <div key={field.name} className="border rounded-lg p-2 bg-white">
                            <div className="flex items-center gap-2 mb-2">
                              <input
                                type="checkbox"
                                checked={isEnabled}
                                onChange={e => {
                                  if (e.target.checked) {
                                    onUpdate({...selectedTile, [field.name]: {}});
                                  } else {
                                    const newTile = {...selectedTile};
                                    delete newTile[field.name];
                                    onUpdate(newTile);
                                  }
                                }}
                                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                              />
                              <label className="text-xs font-medium text-slate-600 select-none cursor-pointer" onClick={() => {
                                if (!isEnabled) onUpdate({...selectedTile, [field.name]: {}});
                                else { const newTile = {...selectedTile}; delete newTile[field.name]; onUpdate(newTile); }
                              }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                              <div className="pl-2">
                                <ObjectInput
                                  label=""
                                  value={selectedTile[field.name] || {}}
                                  fields={field.objectFields}
                                  onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                                  dynamicEntities={dynamicEntities}
                                  haEntities={haEntities}
                                />
                              </div>
                            )}
                          </div>
                        );
                      }
                      return (
                        <ObjectInput
                          key={field.name}
                          label={field.label}
                          value={selectedTile[field.name] || {}}
                          fields={field.objectFields}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          dynamicEntities={dynamicEntities}
                          haEntities={haEntities}
                        />
                      );
                    }
                    if (field.type === 'object_list') {
                      return (
                        <ObjectArrayInput
                          key={field.name}
                          label={field.label}
                          values={selectedTile[field.name] || []}
                          fields={field.objectFields}
                          onChange={v => onUpdate({...selectedTile, [field.name]: v})}
                          haEntities={haEntities}
                        />
                      );
                    }
                    if (field.type === 'page_select') {
                      if (field.optional) {
                        const isEnabled = selectedTile[field.name] !== undefined;
                        return (
                          <div key={field.name}>
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={isEnabled}
                                onChange={e => {
                                  if (e.target.checked) {
                                    onUpdate({...selectedTile, [field.name]: config.pages[0].id});
                                  } else {
                                    const newTile = {...selectedTile};
                                    delete newTile[field.name];
                                    onUpdate(newTile);
                                  }
                                }}
                                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                              />
                              <label className="text-xs font-medium text-slate-700 select-none cursor-pointer" onClick={() => {
                                if (!isEnabled) onUpdate({...selectedTile, [field.name]: config.pages[0].id});
                                else { const newTile = {...selectedTile}; delete newTile[field.name]; onUpdate(newTile); }
                              }}>{field.label}</label>
                            </div>
                            {isEnabled && (
                              <div className="pl-6 mt-1">
                                <select
                                  value={selectedTile[field.name] || ''}
                                  onChange={e => onUpdate({...selectedTile, [field.name]: e.target.value})}
                                  className="w-full border rounded p-1 text-sm bg-white"
                                >
                                  <option value="">Select page...</option>
                                  {config.pages.map(p => <option key={p.id} value={p.id}>{p.id}</option>)}
                                </select>
                              </div>
                            )}
                          </div>
                        );
                      }
                      return (
                        <div key={field.name} className="mb-1">
                          <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                          <select
                            value={selectedTile[field.name] || ''}
                            onChange={e => onUpdate({...selectedTile, [field.name]: e.target.value})}
                            className="w-full border rounded p-1 text-sm bg-white"
                          >
                            <option value="">Select page...</option>
                            {config.pages.map(p => <option key={p.id} value={p.id}>{p.id}</option>)}
                          </select>
                        </div>
                      );
                    }
                    if (field.type === 'dynamic_entity_select') {
                      return (
                        <div key={field.name} className="mb-1">
                          <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                          <select
                            value={selectedTile[field.name] || ''}
                            onChange={e => {
                              const updated: Tile = {...selectedTile, [field.name]: e.target.value};
                              if (field.optional && !e.target.value) delete updated[field.name];
                              onUpdate(updated);
                            }}
                            className="w-full border rounded p-1 text-sm bg-white"
                          >
                            <option value="">Select variable...</option>
                            {dynamicEntities.map(d => <option key={d} value={d}>{d}</option>)}
                          </select>
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>
              </div>
            )}
            </>
            )}
          </div>
        ) : null}
  </div>
</div>
  );
};
