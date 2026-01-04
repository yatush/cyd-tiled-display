import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import Ansi from 'ansi-to-react';
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

  const filteredLogs = filterHa 
    ? logs.split('\n').filter(line => {
        const cleanLine = line.replace(/\x1B\[[0-9;]*[a-zA-Z]/g, '');
        return /\[ha_action(:\d+)?\]/.test(cleanLine);
      }).join('\n')
    : logs;

  // For local dev (HTTP on port 8099), use direct NoVNC on port 6080
  // For Cloud Run/production (port 8080 or HTTPS), use nginx-proxied websockify
  const isLocalDevDirect = window.location.port === '8099';
  const isSecure = window.location.protocol === 'https:';
  
  let vncUrl: string;
  if (isLocalDevDirect) {
    // Local development direct mode: use direct NoVNC proxy on port 6080
    vncUrl = `http://${window.location.hostname}:6080/vnc.html?autoconnect=true&resize=scale`;
  } else {
    // Cloud Run, production, or local nginx mode (port 8080): use nginx-proxied websockify
    vncUrl = `/novnc/vnc.html?autoconnect=true&resize=scale&path=websockify`;
  }

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
          <div className="w-1/2 flex flex-col bg-gray-900 text-gray-100">
            <div className="p-2 border-b flex justify-between items-center bg-gray-800 border-gray-700">
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
                    className="rounded text-blue-400 bg-gray-700 border-gray-600"
                  />
                  <span className="text-sm font-medium">Show only HA Commands</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={autoRefresh} 
                    onChange={e => setAutoRefresh(e.target.checked)}
                    className="rounded text-blue-400 bg-gray-700 border-gray-600"
                  />
                  <span className="text-sm font-medium">Auto-refresh</span>
                </label>
              </div>
              <button 
                onClick={fetchLogs}
                className="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded text-white border border-gray-600"
              >
                Refresh
              </button>
            </div>
            <div 
              ref={scrollContainerRef}
              className="flex-1 overflow-auto p-4 font-mono text-xs whitespace-pre-wrap"
            >
              <Ansi>{filteredLogs || "No logs available..."}</Ansi>
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
