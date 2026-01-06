import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import Ansi from 'ansi-to-react';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface EmulatorDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EmulatorDialog: React.FC<EmulatorDialogProps> = ({ isOpen, onClose }) => {
  const [logs, setLogs] = useState<string>('');
  const [filterHa, setFilterHa] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isIframeLoaded, setIsIframeLoaded] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollTop = useRef<number>(0);

  const fetchLogs = async () => {
    try {
      const res = await apiFetch('/emulator/logs');
      const text = await res.text();
      setLogs(text);
    } catch (e) {
      // console.error("Failed to fetch logs", e);
    }
  };

  useEffect(() => {
    if (!isOpen) {
      setIsIframeLoaded(false);
      return;
    }
    
    if (autoRefresh) {
      fetchLogs();
      const interval = setInterval(fetchLogs, 1000); // 1s is enough and less taxing
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

  // For local dev (HTTP on port 8099 or 5173), use direct NoVNC on port 6080
  // For Cloud Run/production (port 8080 or HTTPS), use nginx-proxied websockify
  const isLocalDevDirect = window.location.port === '8099' || window.location.port === '5173';
  const isSecure = window.location.protocol === 'https:';
  
  let vncUrl: string;
  if (isLocalDevDirect) {
    // Local development direct mode: use direct NoVNC proxy on port 6080
    vncUrl = `http://${window.location.hostname}:6080/vnc.html?autoconnect=true&resize=scale`;
  } else {
    // Cloud Run, production, HA Ingress, or local nginx mode: use nginx-proxied websockify
    const encryptParam = isSecure ? '&encrypt=true' : '';
    
    let pathPrefix = window.location.pathname;
    if (pathPrefix.endsWith('/index.html')) {
      pathPrefix = pathPrefix.slice(0, -11);
    }
    pathPrefix = pathPrefix.replace(/\/$/, '');
    
    // Ensure we don't have double slashes if pathPrefix is empty
    const wsPath = `${pathPrefix}/novnc/websockify`.replace(/^\//, '');
    
    vncUrl = `${pathPrefix}/novnc/vnc.html?autoconnect=true&resize=scale&host=${window.location.hostname}&port=${window.location.port || (isSecure ? '443' : '80')}&path=${encodeURIComponent(wsPath)}${encryptParam}`;
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[9999] flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden border border-slate-200">
        <div className="flex justify-between items-center p-4 border-b bg-slate-50">
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
            Device Emulator
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div className="flex-1 flex overflow-hidden">
          {/* Emulator View */}
          <div className="w-1/2 bg-slate-900 flex items-center justify-center border-r relative">
             {!isIframeLoaded && (
               <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-3 bg-slate-900 z-10">
                 <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                 <span className="text-sm font-medium animate-pulse">Connecting to VNC...</span>
               </div>
             )}
             
             <iframe 
               src={vncUrl}
               className={`w-full h-full border-0 transition-opacity duration-500 ${isIframeLoaded ? 'opacity-100' : 'opacity-0'}`}
               title="NoVNC"
               onLoad={() => setIsIframeLoaded(true)}
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
              className="flex-1 overflow-auto p-4 font-mono text-xs whitespace-pre-wrap bg-slate-950 text-slate-300"
            >
              {filteredLogs ? (
                 <Ansi>{filteredLogs}</Ansi>
              ) : (
                 <div className="text-slate-500 italic">No logs available...</div>
              )}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
