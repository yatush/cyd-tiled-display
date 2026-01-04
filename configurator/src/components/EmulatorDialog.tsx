import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import { apiFetch } from '../utils/api';

interface EmulatorDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EmulatorDialog: React.FC<EmulatorDialogProps> = ({ isOpen, onClose }) => {
  const [logs, setLogs] = useState<string>('');
  const [filterHa, setFilterHa] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollTop = useRef<number>(0);

  const fetchLogs = async () => {
    try {
      const res = await apiFetch('/emulator/logs');
      const text = await res.text();
      setLogs(text);
    } catch (e) {
      console.error("Failed to fetch logs", e);
    }
  };

  useEffect(() => {
    if (isOpen && autoRefresh) {
      fetchLogs();
      const interval = setInterval(fetchLogs, 500);
      return () => clearInterval(interval);
    }
  }, [isOpen, autoRefresh]);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  useLayoutEffect(() => {
    if (!filterHa && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = savedScrollTop.current;
    }
  }, [filterHa]);

  if (!isOpen) return null;

  // Strip ANSI color codes
  const cleanLogs = logs.replace(/\x1B\[[0-9;]*[a-zA-Z]/g, '');

  const filteredLogs = filterHa 
    ? cleanLogs.split('\n').filter(line => /\[ha_action(:\d+)?\]/.test(line)).join('\n')
    : cleanLogs;

  const vncUrl = `http://${window.location.hostname}:6080/vnc.html?autoconnect=true&resize=scale`;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-[200] flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl h-[80vh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-xl font-bold">Device Emulator</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div className="flex-1 flex overflow-hidden">
          {/* Emulator View */}
          <div className="w-1/2 bg-gray-900 flex items-center justify-center border-r relative">
             <iframe 
               src={vncUrl}
               className="w-full h-full border-0"
               title="NoVNC"
             />
          </div>

          {/* Log View */}
          <div className="w-1/2 flex flex-col bg-gray-50">
            <div className="p-2 border-b flex justify-between items-center bg-white">
              <div className="flex items-center space-x-4">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={filterHa} 
                    onChange={e => {
                      if (e.target.checked && scrollContainerRef.current) {
                        savedScrollTop.current = scrollContainerRef.current.scrollTop;
                      }
                      setFilterHa(e.target.checked);
                    }}
                    className="rounded text-blue-600"
                  />
                  <span className="text-sm font-medium">Show only HA Commands</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={autoRefresh} 
                    onChange={e => setAutoRefresh(e.target.checked)}
                    className="rounded text-blue-600"
                  />
                  <span className="text-sm font-medium">Auto-refresh</span>
                </label>
              </div>
              <button 
                onClick={fetchLogs}
                className="px-3 py-1 text-sm bg-gray-200 hover:bg-gray-300 rounded"
              >
                Refresh
              </button>
            </div>
            <div 
              ref={scrollContainerRef}
              className="flex-1 overflow-auto p-4 font-mono text-xs whitespace-pre-wrap"
            >
              {filteredLogs || "No logs available..."}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
