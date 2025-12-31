import React, { useState } from 'react';
import { X, FolderOpen, Save, Upload, FileText, ArrowLeft } from 'lucide-react';
import { Config } from '../types';
import { FileExplorer } from './FileExplorer';

interface ScreensFileDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  config: Config;
  setConfig: (config: Config) => void;
  onSave: () => void;
  onLoad: () => void;
}

export const ScreensFileDialog: React.FC<ScreensFileDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  config,
  setConfig,
  onSave,
  onLoad
}) => {
  const [showExplorer, setShowExplorer] = useState(false);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b bg-slate-50">
          <div className="flex items-center gap-2">
            {onBack && (
              <button onClick={onBack} className="p-1 hover:bg-slate-200 rounded-full transition-colors mr-1">
                <ArrowLeft size={20} className="text-slate-500" />
              </button>
            )}
            <FileText className="text-blue-600" size={20} />
            <h2 className="font-bold text-slate-800">Manage Screens File</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
            <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">File Path</label>
                <div className="flex gap-2">
                <input 
                    type="text" 
                    value={config.project_path || 'monitor_config/tiles.yaml'} 
                    onChange={e => setConfig({...config, project_path: e.target.value})}
                    placeholder="monitor_config/tiles.yaml"
                    className="flex-1 border border-slate-200 rounded p-1.5 text-xs font-mono focus:border-blue-500 outline-none transition-colors bg-white"
                />
                <button 
                    onClick={() => setShowExplorer(!showExplorer)}
                    className={`p-1.5 rounded border transition-colors ${
                    showExplorer ? 'bg-blue-600 text-white border-blue-700' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                    title="Browse files"
                >
                    <FolderOpen size={16} />
                </button>
                </div>
            </div>

            {showExplorer && (
              <div className="h-48 border rounded overflow-hidden bg-white">
                <FileExplorer 
                  currentPath={config.project_path?.split('/').slice(0, -1).join('/')}
                  selectedPath={config.project_path}
                  onSelect={(path) => {
                    setConfig({...config, project_path: path});
                  }} 
                  onSelectDir={(dirPath) => {
                    const currentFile = config.project_path?.split('/').pop() || 'tiles.yaml';
                    const newPath = dirPath ? `${dirPath}/${currentFile}` : currentFile;
                    setConfig({...config, project_path: newPath});
                  }}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 pt-2">
              <button 
                onClick={() => { onSave(); onClose(); }}
                className="flex items-center justify-center gap-2 bg-blue-600 text-white border border-blue-700 p-3 rounded-lg text-sm font-bold hover:bg-blue-700 transition-colors shadow-sm"
              >
                <Save size={16} /> Save to HA
              </button>
              <button 
                onClick={() => { onLoad(); onClose(); }}
                className="flex items-center justify-center gap-2 bg-white text-slate-700 border border-slate-200 p-3 rounded-lg text-sm font-bold hover:bg-slate-50 transition-colors shadow-sm"
              >
                <Upload size={16} /> Load from HA
              </button>
            </div>
        </div>
      </div>
    </div>
  );
};
