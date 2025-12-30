import { LayoutGrid, FileText, Terminal, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { GridCanvas } from './GridCanvas';
import { YamlPreview } from './YamlPreview';
import { Config, Page } from '../types';
import { DragEndEvent } from '@dnd-kit/core';

interface MainContentProps {
  activeTab: 'visual' | 'yaml' | 'output';
  setActiveTab: (tab: 'visual' | 'yaml' | 'output') => void;
  isValidating: boolean;
  validationStatus: { success: boolean; error?: string } | null;
  isGenerating: boolean;
  activePage: Page;
  config: Config;
  selectedTileId: string | null;
  setSelectedTileId: (id: string | null) => void;
  handleDragEnd: (event: DragEndEvent) => void;
  handleDeleteTile: (id: string) => void;
  activePageId: string;
  generationOutput: { success?: boolean; cpp?: string[]; error?: string; type?: string } | null;
}

export const MainContent: React.FC<MainContentProps> = ({
  activeTab,
  setActiveTab,
  isValidating,
  validationStatus,
  isGenerating,
  activePage,
  config,
  selectedTileId,
  setSelectedTileId,
  handleDragEnd,
  handleDeleteTile,
  activePageId,
  generationOutput
}) => {
  return (
    <div className="flex-1 bg-slate-100 flex flex-col relative min-w-0">
      <div className="bg-white border-b px-4 flex items-center justify-between h-12 flex-shrink-0">
          <div className="flex gap-4 h-full">
              <button 
                  className={`px-2 text-sm font-medium border-b-2 flex items-center gap-2 h-full ${activeTab === 'visual' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                  onClick={() => setActiveTab('visual')}
              >
                  <LayoutGrid size={16} /> Visual Editor
              </button>
              <button 
                  className={`px-2 text-sm font-medium border-b-2 flex items-center gap-2 h-full ${activeTab === 'yaml' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                  onClick={() => setActiveTab('yaml')}
              >
                  <FileText size={16} /> YAML Preview
              </button>
              <button 
                  className={`px-2 text-sm font-medium border-b-2 flex items-center gap-2 h-full ${activeTab === 'output' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                  onClick={() => setActiveTab('output')}
              >
                  <Terminal size={16} /> Output
              </button>
          </div>

          <div className="flex items-center gap-4">
              {isValidating && (
                  <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold uppercase tracking-wider">
                      <Loader2 size={12} className="animate-spin" />
                      Validating...
                  </div>
              )}
              {validationStatus && (
                  <div 
                      className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-colors ${
                          validationStatus.success 
                              ? 'bg-green-100 text-green-700 border border-green-200' 
                              : 'bg-red-100 text-red-700 border border-red-200 cursor-help'
                      }`}
                      title={validationStatus.error}
                      onClick={() => !validationStatus.success && setActiveTab('output')}
                  >
                      {validationStatus.success ? (
                          <><CheckCircle2 size={12} /> Valid</>
                      ) : (
                          <><AlertCircle size={12} /> Invalid</>
                      )}
                  </div>
              )}
          </div>
      </div>

      <div className="flex-1 overflow-hidden relative flex flex-col">
          {activeTab === 'visual' ? (
              <>
                  {validationStatus && !validationStatus.success && (
                      <div 
                          className="absolute top-10 left-0 right-0 z-50 bg-red-50 border-b border-red-200 px-4 py-2 flex items-center gap-2 text-red-700 text-xs cursor-pointer hover:bg-red-100 transition-colors shadow-sm"
                          onClick={() => setActiveTab('output')}
                      >
                          <AlertCircle size={14} className="flex-shrink-0" />
                          <span className="font-bold uppercase tracking-tight">Configuration Error:</span>
                          <span className="font-medium">{validationStatus.error}</span>
                          <span className="ml-auto text-[10px] font-bold uppercase opacity-40">Click for full output</span>
                      </div>
                  )}

                  <div className="flex-1 flex items-center justify-center p-8 overflow-auto">
                      <GridCanvas 
                      page={activePage} 
                      onSelectTile={(t) => setSelectedTileId(selectedTileId === t.id ? null : t.id)}
                      selectedTileId={selectedTileId}
                      onDragEnd={handleDragEnd}
                      onDeleteTile={handleDeleteTile}
                      rows={activePage.rows}
                      cols={activePage.cols}
                      />
                  </div>
              </>
          ) : activeTab === 'yaml' ? (
              <YamlPreview config={config} activePageId={activePageId} selectedTileId={selectedTileId} />
          ) : (
              <div className="flex-1 p-6 overflow-auto bg-slate-900 text-slate-100 font-mono text-sm">
                  {!generationOutput && !isGenerating && (
                      <div className="h-full flex flex-col items-center justify-center text-slate-500">
                          <Terminal size={48} className="mb-4 opacity-20" />
                          <p>Click "Generate" to validate and generate C++ code.</p>
                      </div>
                  )}
                  
                  {isGenerating && (
                      <div className="flex items-center gap-3 text-blue-400">
                          <Loader2 size={18} className="animate-spin" />
                          <span>Running Python generation script...</span>
                      </div>
                  )}

                  {generationOutput && (
                      <div className="space-y-4">
                          {generationOutput.error ? (
                              <div className="p-4 bg-red-900/30 border border-red-500/50 rounded-lg text-red-200">
                                  <div className="flex items-center gap-2 mb-2 font-bold">
                                      <AlertCircle size={18} />
                                      <span>{generationOutput.type === 'validation_error' ? 'Validation Error' : 'Error'}</span>
                                  </div>
                                  <pre className="whitespace-pre-wrap">{generationOutput.error}</pre>
                              </div>
                          ) : (
                              <div className="p-4 bg-green-900/30 border border-green-500/50 rounded-lg text-green-200">
                                  <div className="flex items-center gap-2 mb-2 font-bold">
                                      <CheckCircle2 size={18} />
                                      <span>Success</span>
                                  </div>
                                  <p className="mb-4">Successfully generated {generationOutput.cpp?.length} initialization blocks.</p>
                                  
                                  <div className="space-y-4">
                                      {generationOutput.cpp?.map((block, i) => (
                                          <div key={i} className="space-y-1">
                                              <div className="text-xs text-slate-400 uppercase tracking-wider">Block {i + 1}</div>
                                              <pre className="p-3 bg-black/40 rounded border border-white/10 whitespace-pre-wrap break-all">
                                                  {block}
                                              </pre>
                                          </div>
                                      ))}
                                  </div>
                              </div>
                          )}
                      </div>
                  )}
              </div>
          )}
      </div>
    </div>
  );
};
