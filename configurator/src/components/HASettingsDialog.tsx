import React, { useState, useEffect } from 'react';
import { X, Server, Globe, Database, ShieldCheck, RefreshCw } from 'lucide-react';
import { ConnectionType } from '../hooks/useHaConnection';
import { isAddon, apiFetch } from '../utils/api';

interface HASettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  connectionType: ConnectionType;
  setConnectionType: (type: ConnectionType) => void;
  haUrl: string;
  setHaUrl: (url: string) => void;
  haToken: string;
  setHaToken: (token: string) => void;
  onRefresh: () => void;
}

export const HASettingsDialog: React.FC<HASettingsDialogProps> = ({
  isOpen,
  onClose,
  connectionType,
  setConnectionType,
  haUrl,
  setHaUrl,
  haToken,
  setHaToken,
  onRefresh
}) => {
  const [localType, setLocalType] = useState<ConnectionType>(connectionType);
  const [localUrl, setLocalUrl] = useState(haUrl);
  const [localToken, setLocalToken] = useState(haToken);

  // Reset local state when dialog opens
  useEffect(() => {
    if (isOpen) {
      setLocalType(connectionType);
      setLocalUrl(haUrl);
      setLocalToken(haToken);
    }
  }, [isOpen, connectionType, haUrl, haToken]);

  if (!isOpen) return null;

  const handleApply = () => {
    setConnectionType(localType);
    setHaUrl(localUrl);
    setHaToken(localToken);
    onRefresh();
    onClose();
  };

  const handleUpdateLib = async () => {
    if (!confirm("This will overwrite your /config/esphome/lib folder with the latest version. The old version will be backed up to /config/esphome/lib_old. Continue?")) return;
    
    try {
        const res = await apiFetch('/update_lib', { method: 'POST' });
        if (res.ok) {
            alert("Library files updated successfully!");
        } else {
            const err = await res.json();
            alert("Failed to update library: " + err.error);
        }
    } catch (e) {
        alert("Error updating library: " + e);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b bg-slate-50">
          <div className="flex items-center gap-2">
            <Server className="text-blue-600" size={20} />
            <h2 className="font-bold text-slate-800">HA Connection Settings</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="space-y-3">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Connection Mode</label>
            <div className="grid grid-cols-1 gap-2">
              {isAddon && (
                <button
                  onClick={() => setLocalType('local')}
                  className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                    localType === 'local' 
                      ? 'border-blue-600 bg-blue-50 text-blue-700' 
                      : 'border-slate-100 hover:border-slate-200 text-slate-600'
                  }`}
                >
                  <ShieldCheck size={20} />
                  <div className="text-left">
                    <div className="font-bold text-sm">Local Home Assistant</div>
                    <div className="text-[10px] opacity-70">Use Supervisor API (Add-on mode)</div>
                  </div>
                </button>
              )}

              <button
                onClick={() => setLocalType('remote')}
                className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                  localType === 'remote' 
                    ? 'border-blue-600 bg-blue-50 text-blue-700' 
                    : 'border-slate-100 hover:border-slate-200 text-slate-600'
                }`}
              >
                <Globe size={20} />
                <div className="text-left">
                  <div className="font-bold text-sm">Remote Home Assistant</div>
                  <div className="text-[10px] opacity-70">Connect via URL and Long-Lived Token</div>
                </div>
              </button>

              <button
                onClick={() => setLocalType('mock')}
                className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                  localType === 'mock' 
                    ? 'border-blue-600 bg-blue-50 text-blue-700' 
                    : 'border-slate-100 hover:border-slate-200 text-slate-600'
                }`}
              >
                <Database size={20} />
                <div className="text-left">
                  <div className="font-bold text-sm">Mock Data Mode</div>
                  <div className="text-[10px] opacity-70">Use sample entities for testing</div>
                </div>
              </button>
            </div>
          </div>

          {localType === 'remote' && (
            <div className="space-y-4 p-4 bg-slate-50 rounded-lg border border-slate-100 animate-in slide-in-from-top-2 duration-200">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">HA URL</label>
                <input 
                  type="text" 
                  value={localUrl} 
                  onChange={e => setLocalUrl(e.target.value)}
                  placeholder="http://homeassistant.local:8123"
                  className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1.5">Long-Lived Token</label>
                <input 
                  type="password" 
                  value={localToken} 
                  onChange={e => setLocalToken(e.target.value)}
                  placeholder="Paste your token here..."
                  className="w-full border-2 border-slate-200 rounded-lg p-2 text-sm focus:border-blue-500 outline-none transition-colors"
                />
              </div>
            </div>
          )}

          {isAddon && (
            <div className="pt-4 border-t border-slate-100">
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 block">Maintenance</label>
                <button 
                    onClick={handleUpdateLib}
                    className="w-full flex items-center justify-center gap-2 bg-amber-50 text-amber-800 border border-amber-200 p-3 rounded-lg text-sm font-bold hover:bg-amber-100 transition-colors"
                >
                    <RefreshCw size={16} /> Update HA Esphome files
                </button>
                <p className="text-[10px] text-slate-400 mt-1 text-center">
                    Updates the shared library files in /config/esphome/lib
                </p>
            </div>
          )}
        </div>

        <div className="p-4 border-t bg-slate-50 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Close
          </button>
          <button
            onClick={handleApply}
            className="px-4 py-2 text-sm font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-sm transition-all"
          >
            Apply & Refresh
          </button>
        </div>
      </div>
    </div>
  );
};
