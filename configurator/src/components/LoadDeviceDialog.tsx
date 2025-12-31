import React, { useState } from 'react';
import { Monitor, X, Upload, ArrowLeft } from 'lucide-react';
import { FileExplorer } from './FileExplorer';

interface LoadDeviceDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  onLoad: (path: string) => void;
}

export const LoadDeviceDialog: React.FC<LoadDeviceDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  onLoad
}) => {
  const [selectedFile, setSelectedFile] = useState('');

  if (!isOpen) return null;

  const handleLoad = () => {
    if (!selectedFile) return;
    onLoad(selectedFile);
    onClose();
  };

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
            <Monitor className="text-blue-600" size={20} />
            <h2 className="font-bold text-slate-800">Load Device Configuration</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-4 h-64">
            <FileExplorer 
                onSelect={(path) => setSelectedFile(path)}
                selectedPath={selectedFile}
                allowCreateFolder={false}
                filter={(item) => !item.is_dir && (item.name.endsWith('.yaml') || item.name.endsWith('.yml'))}
            />
        </div>

        <div className="p-4 border-t bg-slate-50 flex justify-end gap-2">
            <button 
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200 rounded transition-colors"
            >
                Cancel
            </button>
            <button 
                onClick={handleLoad}
                disabled={!selectedFile}
                className="px-4 py-2 text-xs font-bold bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
                <Upload size={14} /> Load Configuration
            </button>
        </div>
      </div>
    </div>
  );
};
