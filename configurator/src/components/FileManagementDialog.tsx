import React from 'react';
import { X, Upload, Download, FileText, Monitor, FolderOpen } from 'lucide-react';
import { ConnectionType } from '../hooks/useHaConnection';
import { isAddon } from '../utils/api';

interface FileManagementDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadLocal: () => void;
  onDownloadLocal: () => void;
  onSaveScreen: () => void;
  onLoadScreen: () => void;
  onSaveDevice: () => void;
  onLoadDevice: () => void;
  connectionType: ConnectionType;
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
  connectionType
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
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

        <div className="p-6 space-y-6">
          {/* Local Section */}
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Local Files</h3>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => { onLoadLocal(); onClose(); }}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-lg border-2 border-slate-100 hover:border-blue-500 hover:bg-blue-50 text-slate-600 hover:text-blue-700 transition-all group"
              >
                <Upload size={24} className="text-slate-400 group-hover:text-blue-600 transition-colors" />
                <span className="font-bold text-sm">Load YAML</span>
              </button>
              <button
                onClick={() => { onDownloadLocal(); onClose(); }}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-lg border-2 border-slate-100 hover:border-blue-500 hover:bg-blue-50 text-slate-600 hover:text-blue-700 transition-all group"
              >
                <Download size={24} className="text-slate-400 group-hover:text-blue-600 transition-colors" />
                <span className="font-bold text-sm">Download YAML</span>
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
                  <span className="font-bold text-xs">Save Screen</span>
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

              <div className="grid grid-cols-2 gap-3">
                <button 
                  onClick={() => { onSaveDevice(); onClose(); }}
                  className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50 text-slate-700 transition-all group text-left"
                >
                  <div className="p-1.5 bg-slate-100 rounded group-hover:bg-white group-hover:shadow-sm transition-all">
                    <Monitor size={16} className="text-slate-500 group-hover:text-indigo-600" />
                  </div>
                  <span className="font-bold text-xs">Save Device</span>
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
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
