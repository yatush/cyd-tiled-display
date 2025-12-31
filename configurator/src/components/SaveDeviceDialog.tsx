import React, { useState } from 'react';
import { X, Save, Monitor, ArrowLeft } from 'lucide-react';

interface SaveDeviceDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  onSave: (deviceName: string, friendlyName: string, screenType: string, fileName: string) => void;
}

export const SaveDeviceDialog: React.FC<SaveDeviceDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  onSave
}) => {
  const [deviceName, setDeviceName] = useState('');
  const [friendlyName, setFriendlyName] = useState('');
  const [screenType, setScreenType] = useState('2432s028');
  const [fileName, setFileName] = useState('');

  if (!isOpen) return null;

  const handleSave = () => {
    if (!deviceName || !friendlyName || !fileName) {
      alert('Please fill in all fields');
      return;
    }
    onSave(deviceName, friendlyName, screenType, fileName);
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
            <input 
              type="text" 
              value={fileName} 
              onChange={e => setFileName(e.target.value)}
              placeholder="e.g. living_room.yaml"
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors font-mono"
            />
            <p className="text-[10px] text-slate-400 mt-1">The filename to save in /config/esphome</p>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">Friendly Name</label>
            <input 
              type="text" 
              value={friendlyName} 
              onChange={e => setFriendlyName(e.target.value)}
              placeholder="e.g. Living Room Display"
              className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
            />
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
