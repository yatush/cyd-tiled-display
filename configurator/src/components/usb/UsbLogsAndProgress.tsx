import React from 'react';
import { ChevronDown, ChevronUp, RefreshCw, Usb } from 'lucide-react';
import { UsbStatus } from './usbInstallHelpers';

interface UsbLogsAndProgressProps {
  status: UsbStatus;
  statusMessage: string;
  flashProgress: number;
  logs: string[];
  logsExpanded: boolean;
  logsEndRef: React.RefObject<HTMLDivElement>;
  onToggleLogs: () => void;
}

export const UsbLogsAndProgress: React.FC<UsbLogsAndProgressProps> = ({
  status,
  statusMessage,
  flashProgress,
  logs,
  logsExpanded,
  logsEndRef,
  onToggleLogs,
}) => {
  return (
    <div className="p-4 flex-1 overflow-hidden flex flex-col min-h-0">
      {/* Status Banner */}
      <div
        className={`p-3 rounded-lg mb-3 flex items-center gap-2 flex-shrink-0 ${
          status === 'saving'
            ? 'bg-amber-50 text-amber-700'
            : status === 'compiling' || status === 'compiled' || status === 'downloading'
            ? 'bg-blue-50 text-blue-700'
            : status === 'flashing'
            ? 'bg-purple-50 text-purple-700'
            : status === 'success'
            ? 'bg-green-50 text-green-700'
            : 'bg-red-50 text-red-700'
        }`}
      >
        {(status === 'saving' ||
          status === 'compiling' ||
          status === 'compiled' ||
          status === 'downloading') && (
          <>
            <RefreshCw size={16} className="animate-spin flex-shrink-0" />
            <div>
              <div className="font-bold text-sm">
                {status === 'saving'
                  ? 'Saving configuration...'
                  : status === 'downloading'
                  ? 'Downloading firmware...'
                  : 'Compiling firmware...'}
              </div>
              <div className="text-[10px] opacity-70">
                {status === 'compiling'
                  ? 'This may take a few minutes. You can close this dialog — compilation continues in the background.'
                  : status === 'saving'
                  ? 'Preparing device config.'
                  : status === 'downloading'
                  ? 'Fetching compiled firmware from server.'
                  : 'Preparing flash...'}
              </div>
            </div>
          </>
        )}
        {status === 'flashing' && (
          <>
            <Usb size={16} className="animate-pulse flex-shrink-0" />
            <div className="flex-1">
              <div className="font-bold text-sm">Flashing via USB... {flashProgress}%</div>
              <div className="w-full bg-purple-200 rounded-full h-1.5 mt-1">
                <div
                  className="bg-purple-600 h-1.5 rounded-full transition-all"
                  style={{ width: `${flashProgress}%` }}
                />
              </div>
            </div>
          </>
        )}
        {status === 'success' && (
          <div>
            <div className="font-bold text-sm">Flash Complete!</div>
            <div className="text-[10px] opacity-70">{statusMessage}</div>
          </div>
        )}
        {status === 'error' && (
          <div>
            <div className="font-bold text-sm">Failed</div>
            <div className="text-[10px] opacity-70">{statusMessage}</div>
          </div>
        )}
      </div>

      {/* Logs */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        <button
          onClick={onToggleLogs}
          className="flex items-center justify-between text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 hover:text-slate-700 flex-shrink-0"
        >
          <span>Logs ({logs.length} lines)</span>
          {logsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
        {logsExpanded && (
          <div className="flex-1 h-0 bg-slate-900 rounded-lg p-3 overflow-y-auto font-mono text-[11px] text-slate-300 leading-relaxed">
            {logs.map((line, i) => (
              <div
                key={i}
                className={`whitespace-pre-wrap break-all ${
                  line.includes('ERROR') || line.includes('error') || line.includes('Failed')
                    ? 'text-red-400'
                    : line.includes('WARNING') || line.includes('warning')
                    ? 'text-yellow-400'
                    : line.includes('Successfully') ||
                      line.includes('successfully') ||
                      line.includes('Complete')
                    ? 'text-green-400'
                    : line.includes('Writing part') || line.includes('Connecting')
                    ? 'text-purple-400'
                    : line.includes('Downloaded')
                    ? 'text-blue-400'
                    : ''
                }`}
              >
                {line}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
};
