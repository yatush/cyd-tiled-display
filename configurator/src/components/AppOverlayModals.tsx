import React from 'react';
import { RefreshCw } from 'lucide-react';

interface AppOverlayModalsProps {
  isSaveAndUpdateConfirmOpen: boolean;
  fileContextPath?: string | null;
  isSavingBeforeUpdate: boolean;
  onCancelSaveAndUpdate: () => void;
  onConfirmSaveAndUpdate: () => void;

  isEmulatorDevicePickerOpen: boolean;
  onCancelEmulatorPicker: () => void;
  onSelectEmulatorDevice: (device: '2432s028' | '3248s035') => void;

  usbCompileActive: boolean;
  otaInstallActive: boolean;
  isInstallDeviceOpen: boolean;
  onOpenInstallDialog: () => void;

  batchUpdateActive: boolean;
  batchUpdateLabel?: string;
  isBatchUpdateOpen: boolean;
  onOpenBatchUpdateDialog: () => void;
}

export const AppOverlayModals: React.FC<AppOverlayModalsProps> = ({
  isSaveAndUpdateConfirmOpen,
  fileContextPath,
  isSavingBeforeUpdate,
  onCancelSaveAndUpdate,
  onConfirmSaveAndUpdate,
  isEmulatorDevicePickerOpen,
  onCancelEmulatorPicker,
  onSelectEmulatorDevice,
  usbCompileActive,
  otaInstallActive,
  isInstallDeviceOpen,
  onOpenInstallDialog,
  batchUpdateActive,
  batchUpdateLabel,
  isBatchUpdateOpen,
  onOpenBatchUpdateDialog,
}) => {
  return (
    <>
      {/* Save-before-update confirmation popup when active device file has unsaved changes */}
      {isSaveAndUpdateConfirmOpen && fileContextPath && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-[260] p-4 backdrop-blur-sm"
          onClick={() => !isSavingBeforeUpdate && onCancelSaveAndUpdate()}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            <div className="px-5 py-4 border-b bg-amber-50">
              <h3 className="font-bold text-slate-800 text-base">Save Changes Before Updating?</h3>
            </div>
            <div className="p-5 space-y-2 text-sm text-slate-600">
              <p>
                You have unsaved changes to{' '}
                <span className="font-mono font-bold text-slate-800">{fileContextPath}</span>.
              </p>
              <p className="text-xs text-slate-500">
                The file will be saved first, then the OTA update will start for this device.
              </p>
            </div>
            <div className="px-5 py-3 border-t bg-slate-50 flex justify-end gap-2">
              <button
                onClick={onCancelSaveAndUpdate}
                disabled={isSavingBeforeUpdate}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onConfirmSaveAndUpdate}
                disabled={isSavingBeforeUpdate}
                className="px-4 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSavingBeforeUpdate && <RefreshCw size={13} className="animate-spin" />}
                {isSavingBeforeUpdate ? 'Saving...' : 'Save & Update Device'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Device picker dialog shown before starting the emulator */}
      {isEmulatorDevicePickerOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-gray-800 border border-gray-600 rounded-lg p-6 shadow-xl w-80">
            <h2 className="text-lg font-semibold text-white mb-2">Select Device</h2>
            <p className="text-sm text-gray-400 mb-5">Choose which device to emulate:</p>
            <div className="flex flex-col gap-3">
              <button
                className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium transition-colors"
                onClick={() => onSelectEmulatorDevice('2432s028')}
              >
                CYD 2.8&quot; — 320×240
              </button>
              <button
                className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium transition-colors"
                onClick={() => onSelectEmulatorDevice('3248s035')}
              >
                CYD 3.5&quot; — 480×320
              </button>
              <button
                className="w-full px-4 py-3 bg-gray-600 hover:bg-gray-500 text-white rounded-md text-sm font-medium transition-colors"
                onClick={onCancelEmulatorPicker}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating USB Compile indicator */}
      {usbCompileActive && !isInstallDeviceOpen && (
        <button
          onClick={onOpenInstallDialog}
          className="fixed bottom-4 right-4 z-[100] flex items-center gap-2 px-4 py-2.5 bg-purple-600 text-white rounded-full shadow-lg hover:bg-purple-700 transition-all animate-pulse"
        >
          <RefreshCw size={14} className="animate-spin" />
          <span className="text-sm font-bold">USB Compiling...</span>
        </button>
      )}

      {/* Floating OTA Install indicator */}
      {otaInstallActive && !isInstallDeviceOpen && (
        <button
          onClick={onOpenInstallDialog}
          className="fixed bottom-4 right-4 z-[100] flex items-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-full shadow-lg hover:bg-green-700 transition-all animate-pulse"
        >
          <RefreshCw size={14} className="animate-spin" />
          <span className="text-sm font-bold">OTA Installing...</span>
        </button>
      )}

      {/* Floating Batch OTA Update indicator */}
      {batchUpdateActive && !isBatchUpdateOpen && (
        <button
          onClick={onOpenBatchUpdateDialog}
          className="fixed bottom-4 right-4 z-[100] flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-full shadow-lg hover:bg-indigo-700 transition-all animate-pulse"
        >
          <RefreshCw size={14} className="animate-spin" />
          <span className="text-sm font-bold">{batchUpdateLabel || 'Updating Devices...'}</span>
        </button>
      )}
    </>
  );
};
