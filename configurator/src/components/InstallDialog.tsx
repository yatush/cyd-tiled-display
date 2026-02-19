import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Upload, RefreshCw, Wifi, WifiOff, Monitor, Square, ArrowLeft, ChevronDown, ChevronUp, Save } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface Device {
  filename: string;
  device_name: string;
  friendly_name: string;
  screen_type: string | null;
  ip_address: string | null;
  address: string;
  online: boolean;
}

interface InstallDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  onSaveAndInstall: (deviceName: string, friendlyName: string, screenType: string, fileName: string, encryptionKey: string, otaPassword?: string, ipAddress?: string) => Promise<void>;
}

type InstallStatus = 'idle' | 'loading' | 'saving' | 'installing' | 'success' | 'error' | 'cancelled';

export const InstallDialog: React.FC<InstallDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  onSaveAndInstall
}) => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [status, setStatus] = useState<InstallStatus>('idle');
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState('');
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [logsExpanded, setLogsExpanded] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDevices = useCallback(async () => {
    setLoadingDevices(true);
    try {
      const res = await apiFetch('/esphome/devices');
      if (res.ok) {
        const data = await res.json();
        setDevices(data.devices || []);
      } else {
        console.error('Failed to fetch devices');
        setDevices([]);
      }
    } catch (e) {
      console.error('Failed to fetch devices:', e);
      setDevices([]);
    } finally {
      setLoadingDevices(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchDevices();
      setStatus('idle');
      setLogs([]);
      setStatusMessage('');
      setSelectedDevice(null);
    } else {
      // Cleanup on close
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, [isOpen, fetchDevices]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Load full device info from the YAML file for saving
  const loadDeviceInfo = async (filename: string) => {
    try {
      const res = await apiFetch(`/load?path=${encodeURIComponent(filename)}`);
      if (!res.ok) return null;
      const data = await res.json();

      let screenType: string | null = null;
      const deviceBase = data?.packages?.device_base;
      if (typeof deviceBase === 'string') {
        if (deviceBase.includes('2432s028')) screenType = '2432s028';
        else if (deviceBase.includes('3248s035')) screenType = '3248s035';
      }

      let otaPassword: string | undefined;
      if (data?.ota) {
        if (Array.isArray(data.ota)) {
          const esphomeOta = data.ota.find((o: any) => o.platform === 'esphome');
          if (esphomeOta?.password) otaPassword = esphomeOta.password;
        } else if (data.ota?.password) {
          otaPassword = data.ota.password;
        }
      }

      return {
        deviceName: data?.substitutions?.device_name || data?.esphome?.name || '',
        friendlyName: data?.substitutions?.friendly_name || data?.esphome?.friendly_name || '',
        screenType: screenType || '2432s028',
        encryptionKey: data?.api?.encryption?.key || '',
        otaPassword,
        ipAddress: data?.wifi?.use_address || undefined,
      };
    } catch (e) {
      console.error('Failed to load device info:', e);
      return null;
    }
  };

  const handleInstall = async () => {
    if (!selectedDevice) return;

    const device = devices.find(d => d.filename === selectedDevice);
    if (!device) return;

    setLogs([]);
    setStatusMessage('');
    setLogsExpanded(true);

    // Step 1: Save the current editor config into the device file
    setStatus('saving');
    setLogs(prev => [...prev, `Loading device settings from ${selectedDevice}...`]);

    const info = await loadDeviceInfo(selectedDevice);
    if (!info) {
      setStatus('error');
      setStatusMessage(`Failed to read device settings from ${selectedDevice}`);
      return;
    }

    if (!info.encryptionKey) {
      setStatus('error');
      setStatusMessage(`No API encryption key found in ${selectedDevice}. Please save the device config first via "Save Device".`);
      return;
    }

    setLogs(prev => [...prev, `Saving current tile configuration to ${selectedDevice}...`]);

    try {
      await onSaveAndInstall(
        info.deviceName,
        info.friendlyName,
        info.screenType,
        selectedDevice,
        info.encryptionKey,
        info.otaPassword,
        info.ipAddress
      );
    } catch (e) {
      setStatus('error');
      setStatusMessage(`Failed to save config: ${(e as Error).message}`);
      return;
    }

    setLogs(prev => [...prev, `Configuration saved. Starting OTA install...`]);

    // Step 2: Start install (returns immediately, process runs in background)
    setStatus('installing');

    try {
      const res = await apiFetch('/esphome/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selectedDevice }),
      });

      if (!res.ok) {
        let errorMsg = `Server returned ${res.status}`;
        try {
          const text = await res.text();
          try {
            const err = JSON.parse(text);
            errorMsg = err.error || errorMsg;
          } catch {
            errorMsg = `Server error (${res.status}). Check addon logs for details.`;
          }
        } catch { /* ignore */ }
        setStatus('error');
        setStatusMessage(errorMsg);
        return;
      }

      const startData = await res.json();
      setLogs(prev => [...prev, startData.message || 'Install started...']);

      // Step 3: Poll for progress
      let offset = 0;
      const poll = async () => {
        try {
          const statusRes = await apiFetch(`/esphome/install/status?offset=${offset}`);
          if (!statusRes.ok) {
            // Install state gone (404) — process was cleaned up
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            if (status === 'installing') {
              setStatus('error');
              setStatusMessage('Lost connection to install process');
            }
            return;
          }
          const data = await statusRes.json();

          if (data.lines && data.lines.length > 0) {
            setLogs(prev => [...prev, ...data.lines]);
          }
          offset = data.offset;

          if (data.status === 'success') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setStatus('success');
            setStatusMessage(data.message);
          } else if (data.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setStatus('error');
            setStatusMessage(data.message);
          }
        } catch (e) {
          console.error('Poll error:', e);
          // Don't stop polling on transient network errors
        }
      };

      // Poll every 1.5 seconds
      pollRef.current = setInterval(poll, 1500);
      // Also poll immediately
      poll();

    } catch (e) {
      setStatus('error');
      setStatusMessage(`Installation failed: ${(e as Error).message}`);
    }
  };

  const handleCancel = async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    try {
      await apiFetch('/esphome/install/cancel', { method: 'POST' });
    } catch {
      // Ignore
    }
    setStatus('cancelled');
    setStatusMessage('Installation cancelled');
  };

  const handleClose = () => {
    if (status === 'installing' || status === 'saving') {
      if (!confirm('Installation is in progress. Cancel and close?')) return;
      handleCancel();
    }
    onClose();
  };

  if (!isOpen) return null;

  const isWorking = status === 'installing' || status === 'saving';
  const isDone = status === 'success' || status === 'error' || status === 'cancelled';
  const selected = devices.find(d => d.filename === selectedDevice);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[200] p-4 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b bg-slate-50 flex-shrink-0">
          <div className="flex items-center gap-2">
            {onBack && !isWorking && (
              <button onClick={onBack} className="p-1 hover:bg-slate-200 rounded-full transition-colors mr-1">
                <ArrowLeft size={20} className="text-slate-500" />
              </button>
            )}
            <Upload className="text-green-600" size={20} />
            <h2 className="font-bold text-slate-800">Install to Device</h2>
          </div>
          <button onClick={handleClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Device List */}
          {!isWorking && !isDone && (
            <div className="p-4 flex-1 overflow-auto">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs text-slate-500">
                  Select a device to save your current tile config and install via OTA.
                </p>
                <button
                  onClick={fetchDevices}
                  disabled={loadingDevices}
                  className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors text-slate-500"
                  title="Refresh device list"
                >
                  <RefreshCw size={14} className={loadingDevices ? 'animate-spin' : ''} />
                </button>
              </div>

              {loadingDevices ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw size={24} className="animate-spin text-blue-500" />
                  <span className="ml-2 text-sm text-slate-500">Scanning devices...</span>
                </div>
              ) : devices.length === 0 ? (
                <div className="text-center py-12">
                  <Monitor size={32} className="mx-auto text-slate-300 mb-2" />
                  <p className="text-sm text-slate-500">No device configurations found.</p>
                  <p className="text-xs text-slate-400 mt-1">Save a device configuration first using File Management &gt; Save Device.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {devices.map(device => (
                    <button
                      key={device.filename}
                      onClick={() => setSelectedDevice(device.filename)}
                      className={`w-full text-left p-3 rounded-lg border-2 transition-all ${
                        selectedDevice === device.filename
                          ? 'border-green-500 bg-green-50'
                          : 'border-slate-100 hover:border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <Monitor size={16} className={selectedDevice === device.filename ? 'text-green-600' : 'text-slate-400'} />
                          <div className="min-w-0">
                            <div className="font-bold text-sm text-slate-800 truncate">
                              {device.friendly_name}
                            </div>
                            <div className="text-[10px] text-slate-400 font-mono truncate">
                              {device.filename}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                          {device.screen_type && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-bold">
                              {device.screen_type === '2432s028' ? '2.8"' : '3.5"'}
                            </span>
                          )}
                          {device.online ? (
                            <span className="flex items-center gap-1 text-[10px] text-green-600 font-bold">
                              <Wifi size={12} /> Online
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-[10px] text-slate-400 font-bold">
                              <WifiOff size={12} /> Offline
                            </span>
                          )}
                        </div>
                      </div>
                      {device.address && (
                        <div className="text-[10px] text-slate-400 mt-1 font-mono pl-6">
                          {device.address}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Install Progress / Logs */}
          {(isWorking || isDone) && (
            <div className="p-4 flex-1 overflow-hidden flex flex-col">
              {/* Status Banner */}
              <div className={`p-3 rounded-lg mb-3 flex items-center gap-2 flex-shrink-0 ${
                status === 'saving' ? 'bg-amber-50 text-amber-700' :
                status === 'installing' ? 'bg-blue-50 text-blue-700' :
                status === 'success' ? 'bg-green-50 text-green-700' :
                status === 'cancelled' ? 'bg-yellow-50 text-yellow-700' :
                'bg-red-50 text-red-700'
              }`}>
                {status === 'saving' && (
                  <>
                    <Save size={16} className="animate-pulse flex-shrink-0" />
                    <div>
                      <div className="font-bold text-sm">Saving config to {selected?.friendly_name}...</div>
                      <div className="text-[10px] opacity-70">Updating tile configuration while preserving device settings (API key, WiFi, OTA).</div>
                    </div>
                  </>
                )}
                {status === 'installing' && (
                  <>
                    <RefreshCw size={16} className="animate-spin flex-shrink-0" />
                    <div>
                      <div className="font-bold text-sm">Installing to {selected?.friendly_name}...</div>
                      <div className="text-[10px] opacity-70">Compiling and uploading via OTA. This may take a few minutes.</div>
                    </div>
                  </>
                )}
                {status === 'success' && (
                  <div>
                    <div className="font-bold text-sm">Installation Complete!</div>
                    <div className="text-[10px] opacity-70">{statusMessage}</div>
                  </div>
                )}
                {status === 'error' && (
                  <div>
                    <div className="font-bold text-sm">Installation Failed</div>
                    <div className="text-[10px] opacity-70">{statusMessage}</div>
                  </div>
                )}
                {status === 'cancelled' && (
                  <div>
                    <div className="font-bold text-sm">Installation Cancelled</div>
                    <div className="text-[10px] opacity-70">{statusMessage}</div>
                  </div>
                )}
              </div>

              {/* Logs */}
              <div className="flex-1 overflow-hidden flex flex-col min-h-0">
                <button 
                  onClick={() => setLogsExpanded(!logsExpanded)}
                  className="flex items-center justify-between text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 hover:text-slate-700 flex-shrink-0"
                >
                  <span>Build Logs ({logs.length} lines)</span>
                  {logsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
                {logsExpanded && (
                  <div className="flex-1 bg-slate-900 rounded-lg p-3 overflow-auto font-mono text-[11px] text-slate-300 min-h-[200px]">
                    {logs.map((line, i) => (
                      <div key={i} className={`whitespace-pre-wrap break-all ${
                        line.includes('ERROR') || line.includes('error') ? 'text-red-400' :
                        line.includes('WARNING') || line.includes('warning') ? 'text-yellow-400' :
                        line.includes('Successfully') || line.includes('successfully') ? 'text-green-400' :
                        line.includes('Uploading') || line.includes('OTA') ? 'text-blue-400' :
                        ''
                      }`}>
                        {line}
                      </div>
                    ))}
                    <div ref={logsEndRef} />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t bg-slate-50 flex justify-end gap-3 flex-shrink-0">
          {!isWorking && !isDone && (
            <>
              <button
                onClick={handleClose}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleInstall}
                disabled={!selectedDevice}
                className="px-4 py-2 text-sm font-bold bg-green-600 text-white rounded-lg hover:bg-green-700 shadow-sm transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Upload size={16} /> Save & Install
              </button>
            </>
          )}
          {isWorking && (
            <button
              onClick={handleCancel}
              className="px-4 py-2 text-sm font-bold bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-sm transition-all flex items-center gap-2"
            >
              <Square size={16} /> Cancel Install
            </button>
          )}
          {isDone && (
            <>
              <button
                onClick={() => {
                  setStatus('idle');
                  setLogs([]);
                  setStatusMessage('');
                  fetchDevices();
                }}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Back to Devices
              </button>
              <button
                onClick={handleClose}
                className="px-4 py-2 text-sm font-bold bg-slate-700 text-white rounded-lg hover:bg-slate-800 shadow-sm transition-all"
              >
                Close
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
