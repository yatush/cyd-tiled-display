import React, { useState } from 'react';
import { X, Save, Monitor, ArrowLeft, RefreshCw, FolderOpen } from 'lucide-react';
import { FileExplorer } from './FileExplorer';
import { apiFetch } from '../utils/api';

interface SaveDeviceDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  onSave: (deviceName: string, friendlyName: string, screenType: string, fileName: string, encryptionKey: string) => void;
}

export const SaveDeviceDialog: React.FC<SaveDeviceDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  onSave
}) => {
  const [deviceName, setDeviceName] = useState('');
  const [screenType, setScreenType] = useState('2432s028');
  const [fileName, setFileName] = useState('');
  const [encryptionKey, setEncryptionKey] = useState('');
  const [showExplorer, setShowExplorer] = useState(false);

  const generateKey = () => {
    const randomValues = new Uint8Array(32);
    window.crypto.getRandomValues(randomValues);
    let binaryString = "";
    for (let i = 0; i < randomValues.length; i++) {
        binaryString += String.fromCharCode(randomValues[i]);
    }
    setEncryptionKey(btoa(binaryString));
  };

  React.useEffect(() => {
    if (isOpen && !encryptionKey) {
        generateKey();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const checkFileAndGetInfo = async (path: string): Promise<{ key: string | null, deviceName: string | null, screenType: string | null }> => {
      try {
          const res = await apiFetch(`/load?path=${encodeURIComponent(path)}`);
          if (res.ok) {
              const data = await res.json();
              let detectedScreenType = null;
              const deviceBase = data?.packages?.device_base;
              if (typeof deviceBase === 'string') {
                  if (deviceBase.includes('2432s028')) detectedScreenType = '2432s028';
                  else if (deviceBase.includes('3248s035')) detectedScreenType = '3248s035';
              }
              
              return {
                  key: data?.api?.encryption?.key || null,
                  deviceName: data?.substitutions?.device_name || null,
                  screenType: detectedScreenType
              };
          }
      } catch (e) {
          console.error("Error checking file", e);
      }
      return { key: null, deviceName: null, screenType: null };
  };

  const handleSave = async () => {
    if (!deviceName || !fileName || !encryptionKey) {
      alert('Please fill in all fields');
      return;
    }

    // Check for existing file and key mismatch
    const info = await checkFileAndGetInfo(fileName);
    if (info.key && info.key !== encryptionKey) {
        alert(`Cannot overwrite file "${fileName}" because the Encryption Key does not match.\n\nExisting key: ${info.key}\nCurrent key: ${encryptionKey}\n\nPlease restore the original key (by re-selecting the file) or choose a different filename.`);
        return;
    }

    // Use deviceName as friendlyName
    onSave(deviceName, deviceName, screenType, fileName, encryptionKey);
    onClose();
  };

  const handleDeviceNameChange = (val: string) => {
      const clean = val.toLowerCase().replace(/[^a-z0-9_]/g, '_');
      setDeviceName(clean);
      if (!fileName || fileName === `${deviceName}.yaml`) {
          setFileName(`${clean}.yaml`);
      }
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
            <h2 className="font-bold text-slate-800">Save Device Configuration</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">Device Name (ID)</label>
            <input 
              type="text" 
              value={deviceName} 
              onChange={e => handleDeviceNameChange(e.target.value)}
              placeholder="e.g. living_room_display"
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors font-mono"
            />
            <p className="text-[10px] text-slate-400 mt-1">Used for esphome ID. Lowercase, no spaces.</p>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">File Name</label>
            <div className="flex gap-2">
                <input 
                type="text" 
                value={fileName} 
                onChange={e => setFileName(e.target.value)}
                placeholder="e.g. living_room.yaml"
                className="flex-1 border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors font-mono"
                />
                <button 
                    onClick={() => setShowExplorer(!showExplorer)}
                    className={`p-2 rounded-lg border-2 transition-colors ${
                    showExplorer ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                    title="Browse files"
                >
                    <FolderOpen size={20} />
                </button>
            </div>
            
            {showExplorer && (
              <div className="mt-2 h-48 border rounded-lg overflow-hidden bg-white">
                <FileExplorer 
                  currentPath={fileName.includes('/') ? fileName.split('/').slice(0, -1).join('/') : ''}
                  selectedPath={fileName}
                  onSelect={async (path) => {
                    setFileName(path);
                    setShowExplorer(false);
                    const info = await checkFileAndGetInfo(path);
                    if (info.key) {
                        setEncryptionKey(info.key);
                    }
                    if (info.deviceName) {
                        setDeviceName(info.deviceName);
                    }
                    if (info.screenType) {
                        setScreenType(info.screenType);
                    }
                  }} 
                />
              </div>
            )}
            <p className="text-[10px] text-slate-400 mt-1">The filename to save in /config/esphome</p>
          </div>

          <div>
            <div className="flex justify-between items-center mb-1.5">
                <label className="block text-[10px] font-bold text-slate-500 uppercase">Encryption Key</label>
                <button onClick={generateKey} className="text-[10px] text-blue-600 hover:text-blue-800 flex items-center gap-1">
                    <RefreshCw size={10} /> Regenerate
                </button>
            </div>
            <input 
              type="text" 
              value={encryptionKey} 
              onChange={e => setEncryptionKey(e.target.value)}
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors font-mono text-xs"
            />
            <p className="text-[10px] text-slate-400 mt-1">32-byte base64-encoded key for API encryption</p>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">Screen Type</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setScreenType('2432s028')}
                className={`p-3 rounded-lg border-2 text-left transition-all ${
                  screenType === '2432s028' 
                    ? 'border-blue-600 bg-blue-50 text-blue-700' 
                    : 'border-slate-100 hover:border-slate-200 text-slate-600'
                }`}
              >
                <div className="font-bold text-sm">2.8" Display</div>
                <div className="text-[10px] opacity-70">2432s028 (Resistive)</div>
              </button>
              <button
                onClick={() => setScreenType('3248s035')}
                className={`p-3 rounded-lg border-2 text-left transition-all ${
                  screenType === '3248s035' 
                    ? 'border-blue-600 bg-blue-50 text-blue-700' 
                    : 'border-slate-100 hover:border-slate-200 text-slate-600'
                }`}
              >
                <div className="font-bold text-sm">3.5" Display</div>
                <div className="text-[10px] opacity-70">3248s035 (Capacitive)</div>
              </button>
            </div>
          </div>
        </div>

        <div className="p-4 border-t bg-slate-50 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 text-sm font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-sm transition-all flex items-center gap-2"
          >
            <Save size={16} /> Save Configuration
          </button>
        </div>
      </div>
    </div>
  );
};
