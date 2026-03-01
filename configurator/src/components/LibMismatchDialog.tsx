import React from 'react';
import { AlertTriangle, Settings, X } from 'lucide-react';

interface LibMismatchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onGoToSettings: () => void;
  details: string[];
}

export const LibMismatchDialog: React.FC<LibMismatchDialogProps> = ({
  isOpen,
  onClose,
  onGoToSettings,
  details,
}) => {
  if (!isOpen) return null;

  const handleGoToSettings = () => {
    onClose();
    onGoToSettings();
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[250] p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b bg-amber-50">
          <div className="flex items-center gap-2">
            <AlertTriangle className="text-amber-500" size={20} />
            <h2 className="font-bold text-slate-800">Library Files Out of Sync</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-amber-100 rounded-full transition-colors"
          >
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <p className="text-sm text-slate-600">
            The shared ESPHome library files in your HA config directory do not match the
            current add-on version. It is recommended to update them before compiling
            your devices.
          </p>

          {details.length > 0 && (
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                Mismatched files
              </p>
              <div className="p-3 bg-slate-100 rounded-lg border border-slate-200 max-h-48 overflow-y-auto">
                {details.map((line, i) => (
                  <div
                    key={i}
                    className={
                      line.startsWith('  -')
                        ? 'pl-2 text-red-600 text-[11px] font-mono'
                        : 'font-bold text-slate-700 text-[11px] font-mono mt-1.5 first:mt-0'
                    }
                  >
                    {line}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t bg-slate-50 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Dismiss
          </button>
          <button
            onClick={handleGoToSettings}
            className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-amber-500 text-white rounded-lg hover:bg-amber-600 shadow-sm transition-all"
          >
            <Settings size={15} />
            Go to Settings
          </button>
        </div>
      </div>
    </div>
  );
};
