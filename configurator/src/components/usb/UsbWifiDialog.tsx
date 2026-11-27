import React from 'react';
import { Eye, EyeOff, RefreshCw, Wifi } from 'lucide-react';

interface UsbWifiDialogProps {
  isOpen: boolean;
  wifiSsid: string;
  wifiPassword: string;
  wifiShowPassword: boolean;
  wifiSaving: boolean;
  onSsidChange: (val: string) => void;
  onPasswordChange: (val: string) => void;
  onToggleShowPassword: () => void;
  onCancel: () => void;
  onSave: () => void;
}

export const UsbWifiDialog: React.FC<UsbWifiDialogProps> = ({
  isOpen,
  wifiSsid,
  wifiPassword,
  wifiShowPassword,
  wifiSaving,
  onSsidChange,
  onPasswordChange,
  onToggleShowPassword,
  onCancel,
  onSave,
}) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[300] p-4 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-sm overflow-hidden animate-in fade-in zoom-in duration-200"
        onClick={e => e.stopPropagation()}
      >
        <div className="p-4 border-b bg-blue-50">
          <div className="flex items-center gap-2">
            <Wifi className="text-blue-600" size={20} />
            <h3 className="font-bold text-slate-800">WiFi Configuration</h3>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Enter your WiFi credentials. The device needs WiFi to connect to Home Assistant.
          </p>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">
              WiFi Network (SSID)
            </label>
            <input
              type="text"
              value={wifiSsid}
              onChange={e => onSsidChange(e.target.value)}
              placeholder="Your WiFi network name"
              className="w-full px-3 py-2 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-400 focus:outline-none transition-colors"
              autoFocus
              onKeyDown={e => {
                if (e.key === 'Enter') document.getElementById('wifi-password-input')?.focus();
              }}
            />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">
              Password
            </label>
            <div className="relative">
              <input
                id="wifi-password-input"
                type={wifiShowPassword ? 'text' : 'password'}
                value={wifiPassword}
                onChange={e => onPasswordChange(e.target.value)}
                placeholder="WiFi password"
                className="w-full px-3 py-2 pr-10 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-400 focus:outline-none transition-colors"
                onKeyDown={e => {
                  if (e.key === 'Enter' && wifiSsid.trim() && wifiPassword.trim()) onSave();
                }}
              />
              <button
                type="button"
                onClick={onToggleShowPassword}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600"
              >
                {wifiShowPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
        </div>
        <div className="p-4 border-t bg-slate-50 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={!wifiSsid.trim() || !wifiPassword.trim() || wifiSaving}
            className="px-4 py-1.5 text-sm font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {wifiSaving ? <RefreshCw size={14} className="animate-spin" /> : <Wifi size={14} />}
            {wifiSaving ? 'Saving...' : 'Save & Continue'}
          </button>
        </div>
      </div>
    </div>
  );
};
