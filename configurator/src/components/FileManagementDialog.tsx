import React from 'react';
import { X, Upload, Download, FileText, Monitor, FolderOpen, Zap, Settings, Save, Check, UploadCloud } from 'lucide-react';
import { isAddon } from '../utils/api';
import { FileContext, getDisplayFileName } from '../utils/fileContext';

interface FileManagementDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadLocal: () => void;
  onDownloadLocal: () => void;
  onSaveScreen: () => void;
  onLoadScreen: () => void;
  onSaveDevice: () => void;
  onLoadDevice: () => void;
  onInstallDevice: () => void;
  onHwOverrides: () => void;
  fileContext?: FileContext | null;
  isDirty?: boolean;
  onQuickSave?: () => void;
  onBatchUpdate?: () => void;
}

export const FileManagementDialog: React.FC<FileManagementDialogProps> = ({
  isOpen,
  onClose,
  onLoadLocal,
  onDownloadLocal,
  onSaveScreen,
  onLoadScreen,
  onSaveDevice,
  onLoadDevice,
  onInstallDevice,
  onHwOverrides,
  fileContext,
  isDirty,
  onQuickSave,
  onBatchUpdate,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[200] backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b bg-slate-50">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <FolderOpen className="text-blue-600" size={20} />
            File Management
          </h2>
          <button 
            onClick={onClose}
            className="p-1 hover:bg-slate-200 rounded-full transition-colors text-slate-500"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Active File Context Quick Save */}
          {fileContext && onQuickSave && (
            <div className={`p-3 rounded-lg border flex items-center justify-between gap-3 ${
              isDirty ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="min-w-0">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Current {fileContext.kind === 'device' ? 'Device' : fileContext.kind === 'screen' ? 'Screen' : 'Local'} File
                </div>
                <div className="text-xs font-mono font-bold text-slate-800 truncate" title={fileContext.path}>
                  {getDisplayFileName(fileContext.path)}
                </div>
                <div className="text-[11px] text-slate-500">
                  {isDirty ? 'Unsaved changes' : 'Up to date'}
                </div>
              </div>
              <button
                onClick={() => { onQuickSave(); onClose(); }}
                disabled={!isDirty}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold transition-colors flex-shrink-0 ${
                  isDirty
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-emerald-100 text-emerald-700 cursor-default'
                }`}
              >
                {isDirty ? <Save size={14} /> : <Check size={14} />}
                {isDirty ? 'Save' : 'Saved'}
              </button>
            </div>
          )}

          {/* Local Section */}
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Local Files</h3>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => { onDownloadLocal(); onClose(); }}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-lg border-2 border-slate-100 hover:border-blue-500 hover:bg-blue-50 text-slate-600 hover:text-blue-700 transition-all group"
              >
                <Download size={24} className="text-slate-400 group-hover:text-blue-600 transition-colors" />
                <span className="font-bold text-sm">Download YAML</span>
              </button>
              <button
                onClick={() => { onLoadLocal(); onClose(); }}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-lg border-2 border-slate-100 hover:border-blue-500 hover:bg-blue-50 text-slate-600 hover:text-blue-700 transition-all group"
              >
                <Upload size={24} className="text-slate-400 group-hover:text-blue-600 transition-colors" />
                <span className="font-bold text-sm">Load YAML</span>
              </button>
            </div>
          </div>

          {/* HA Server Section */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">HA Server Files</h3>
            </div>
            
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <button 
                  onClick={() => { onSaveScreen(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <FileText size={16} className="text-slate-500 group-hover:text-blue-600" />
                  </div>
                  <span className="font-bold text-xs">Save Screen As...</span>
                </button>
                <button 
                  onClick={() => { onLoadScreen(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <FolderOpen size={16} className="text-slate-500 group-hover:text-blue-600" />
                  </div>
                  <span className="font-bold text-xs">Load Screen</span>
                </button>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <button 
                  onClick={() => { onSaveDevice(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <Monitor size={16} className="text-slate-500 group-hover:text-indigo-600" />
                  </div>
                  <span className="font-bold text-xs">Save Device As...</span>
                </button>
                <button 
                  onClick={() => { onLoadDevice(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <Upload size={16} className="text-slate-500 group-hover:text-indigo-600" />
                  </div>
                  <span className="font-bold text-xs">Load Device</span>
                </button>
                <button 
                  onClick={() => { onInstallDevice(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-green-400 hover:bg-green-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <Zap size={16} className="text-slate-500 group-hover:text-green-600" />
                  </div>
                  <span className="font-bold text-xs">Install</span>
                </button>
              </div>

              {isAddon && onBatchUpdate && (
                <button
                  onClick={() => { onBatchUpdate(); onClose(); }}
                  className="w-full flex items-center gap-2.5 p-3 rounded-lg border border-indigo-200 bg-indigo-50/60 hover:bg-indigo-50 hover:border-indigo-400 text-indigo-800 transition-all group text-left"
                >
                  <div className="p-1.5 bg-white rounded shadow-sm">
                    <UploadCloud size={16} className="text-indigo-600" />
                  </div>
                  <div>
                    <div className="font-bold text-xs">Update All Online CYD Devices (OTA)</div>
                    <div className="text-[10px] text-indigo-600/80">Compile &amp; OTA-flash all online CYD configs on drive</div>
                  </div>
                </button>
              )}
            </div>
          </div>

          {/* Hardware Overrides */}
          {isAddon && (
            <div>
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Hardware</h3>
              <button
                onClick={() => { onHwOverrides(); onClose(); }}
                className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-amber-400 hover:bg-amber-50 text-slate-700 transition-all group text-left"
              >
                <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                  <Settings size={16} className="text-slate-500 group-hover:text-amber-600" />
                </div>
                <div>
                  <div className="font-bold text-xs">Hardware Overrides</div>
                  <div className="text-[10px] text-slate-400">Customize touchscreen, backlight, etc.</div>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
