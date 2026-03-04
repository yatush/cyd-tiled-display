import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Upload, RefreshCw, Wifi, WifiOff, Monitor, Square, ArrowLeft, ChevronDown, ChevronUp, Save, Usb, AlertTriangle, Wrench, CheckCircle } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { UsbInstallPanel } from './UsbInstallPanel';

interface Device {
  filename: string;
  device_name: string;
  friendly_name: string;
  screen_type: string | null;
  ip_address: string | null;
  address: string;
  online: boolean | null;
}

interface InstallDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onBack?: () => void;
  onSaveAndInstall: (deviceName: string, friendlyName: string, screenType: string, fileName: string, encryptionKey: string, otaPassword?: string, ipAddress?: string) => Promise<void>;
  /** Keep dialog DOM alive even when closed (e.g. USB compile running in background) */
  stayMounted?: boolean;
  /** Called when USB compile starts/stops to control stayMounted from parent */
  onCompileActiveChange?: (active: boolean) => void;
  /** Called when OTA install starts/finishes to control stayMounted from parent */
  onOtaActiveChange?: (active: boolean) => void;
  /** Current toolchain phase from App-level polling */
  toolchainPhase?: string;
  /** Called to update toolchain phase in App state after local build starts */
  onToolchainPhaseChange?: (phase: string) => void;
}

type InstallStatus = 'idle' | 'loading' | 'saving' | 'installing' | 'success' | 'error' | 'cancelled';
type InstallTab = 'ota' | 'usb';

export const InstallDialog: React.FC<InstallDialogProps> = ({
  isOpen,
  onClose,
  onBack,
  onSaveAndInstall,
  stayMounted,
  onCompileActiveChange,
  onOtaActiveChange,
  toolchainPhase,
  onToolchainPhaseChange,
}) => {
  // ── Toolchain state ──────────────────────────────────────────────────────
  // localBuild* tracks the progress of a user-triggered local build.
  const [localBuildPhase, setLocalBuildPhase]       = useState<string | null>(null);
  const [localBuildProgress, setLocalBuildProgress] = useState(0);
  const [localBuildMessage, setLocalBuildMessage]   = useState('');
  const [buildLogs, setBuildLogs]                   = useState<string>('');
  const [buildEsphomeVersion, setBuildEsphomeVersion] = useState<string>('');
  const [buildSource, setBuildSource]               = useState<string>('');
  // Whether the initial toolchain status fetch has completed for this open.
  // Until it has, we treat the toolchain as not-yet-known (keep UI disabled).
  const [toolchainChecked, setToolchainChecked] = useState(false);
  const localBuildPollRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef         = useRef<ReturnType<typeof setInterval> | null>(null);
  const buildLogsEndRef    = useRef<HTMLDivElement>(null);

  // Start polling /api/toolchain/status when a local build is in progress
  useEffect(() => {
    if (localBuildPhase === null || localBuildPhase === 'ready') return;
    if (localBuildPollRef.current) return;
    localBuildPollRef.current = setInterval(async () => {
      try {
        const res = await apiFetch('/toolchain/status');
        if (!res.ok) return;
        const data = await res.json();
        setLocalBuildPhase(data.phase);
        setLocalBuildProgress(data.progress ?? 0);
        setLocalBuildMessage(data.message ?? '');
        if (data.esphome_version) setBuildEsphomeVersion(data.esphome_version);
        if (data.phase === 'ready') {
          setBuildSource(data.fallback ? 'Built locally' : 'Downloaded pre-built release');
          clearInterval(localBuildPollRef.current!);
          localBuildPollRef.current = null;
          onToolchainPhaseChange?.('ready');
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => {
      if (localBuildPollRef.current) {
        clearInterval(localBuildPollRef.current);
        localBuildPollRef.current = null;
      }
    };
  }, [localBuildPhase, onToolchainPhaseChange]);

  // Poll log while a local build is running
  useEffect(() => {
    const isBuilding = localBuildPhase != null &&
      localBuildPhase !== 'ready' && localBuildPhase !== 'no_toolchain';
    if (!isBuilding) {
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
      return;
    }
    const fetchLog = async () => {
      try {
        const res = await apiFetch('/toolchain/log?lines=300');
        if (res.ok) {
          const text = await res.text();
          setBuildLogs(text);
          // Auto-scroll to bottom
          buildLogsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
      } catch { /* ignore */ }
    };
    fetchLog();
    logPollRef.current = setInterval(fetchLog, 2000);
    return () => {
      if (logPollRef.current) {
        clearInterval(logPollRef.current);
        logPollRef.current = null;
      }
    };
  }, [localBuildPhase]);

  // Fetch toolchain status immediately when dialog opens, so we don't have
  // to wait for the App-level 3-second poll cycle.
  useEffect(() => {
    if (!isOpen) {
      // Reset checked flag so next open re-fetches
      setToolchainChecked(false);
      return;
    }
    apiFetch('/toolchain/status')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        setToolchainChecked(true);
        if (!data) return;
        const phase: string = data.phase;
        // Only update if not currently running a local build
        if (localBuildPhase === null || localBuildPhase === 'no_toolchain') {
          // Mirror ANY non-idle phase into localBuildPhase so progress/log
          // UI appears even when the build was started outside this dialog.
          if (phase !== 'ready' && phase !== 'starting') {
            setLocalBuildPhase(phase);
          }
          onToolchainPhaseChange?.(phase);
        }
      })
      .catch(() => {
        // On error, assume toolchain is ready so we don't block forever
        setToolchainChecked(true);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const handleStartLocalBuild = async () => {
    setLocalBuildPhase('building');
    setLocalBuildProgress(0);
    setLocalBuildMessage('Starting local build...');
    setBuildLogs('');
    try {
      await apiFetch('/toolchain/start_local_build', { method: 'POST' });
    } catch {
      setLocalBuildMessage('Failed to start build. Check server logs.');
    }
  };

  const handleCancelBuild = async () => {
    try {
      await apiFetch('/toolchain/cancel', { method: 'POST' });
    } catch { /* ignore */ }
    // Stop polls
    if (localBuildPollRef.current) { clearInterval(localBuildPollRef.current); localBuildPollRef.current = null; }
    if (logPollRef.current)        { clearInterval(logPollRef.current);        logPollRef.current = null; }
    setBuildLogs('');
    setLocalBuildProgress(0);
    setLocalBuildMessage('');
    setBuildSource('');
    setLocalBuildPhase('no_toolchain');
    onToolchainPhaseChange?.('no_toolchain');
  };

  // Effective toolchain phase: prefer local-build tracking when active,
  // fall back to App-level phase
  const effectivePhase = localBuildPhase ?? toolchainPhase;
  const showNoToolchain = effectivePhase === 'no_toolchain';
  const showLocalBuildProgress = effectivePhase != null && effectivePhase !== 'ready' && effectivePhase !== 'no_toolchain' && effectivePhase !== 'starting';
  // Toolchain is ready only once we have a confirmed status AND it's not blocking.
  // toolchainChecked guards against the race between dialog open and the fetch response.
  const isToolchainReady = toolchainChecked && (effectivePhase == null || effectivePhase === 'ready');
  const isToolchainStarting = toolchainChecked && effectivePhase === 'starting';
  // ── End toolchain state ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<InstallTab>('ota');
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [status, setStatus] = useState<InstallStatus>('idle');
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState('');
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [logsExpanded, setLogsExpanded] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track whether an OTA install is running in the background (dialog hidden)
  const otaRunningRef = useRef(false);
  // Elapsed timer for the installing phase
  const [elapsed, setElapsed] = useState(0);
  const installStartRef = useRef<number | null>(null);
  const [lastLogAge, setLastLogAge] = useState(0);
  const lastLogTimeRef = useRef<number | null>(null);

  // On mount: check if an install is already running (page reload / reconnect)
  useEffect(() => {
    apiFetch('/esphome/install/status?offset=0')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || data.status !== 'running') return;
        // Resume: populate logs and start polling
        if (data.lines?.length) setLogs(data.lines);
        setStatus('installing');
        setLogsExpanded(true);
        otaRunningRef.current = true;
        onOtaActiveChange?.(true);
        let offset = data.offset ?? (data.lines?.length ?? 0);
        const poll = async () => {
          try {
            const sr = await apiFetch(`/esphome/install/status?offset=${offset}`);
            if (!sr.ok) {
              clearInterval(pollRef.current!); pollRef.current = null;
              otaRunningRef.current = false; onOtaActiveChange?.(false);
              setStatus('error'); setStatusMessage('Lost connection to install process');
              return;
            }
            const d = await sr.json();
            if (d.lines?.length) setLogs(prev => [...prev, ...d.lines]);
            offset = d.offset;
            if (d.status === 'success') {
              clearInterval(pollRef.current!); pollRef.current = null;
              otaRunningRef.current = false; onOtaActiveChange?.(false);
              setStatus('success'); setStatusMessage(d.message);
            } else if (d.status === 'error') {
              clearInterval(pollRef.current!); pollRef.current = null;
              otaRunningRef.current = false; onOtaActiveChange?.(false);
              setStatus('error'); setStatusMessage(d.message);
            }
          } catch { /* transient, keep polling */ }
        };
        pollRef.current = setInterval(poll, 1500);
        poll();
      })
      .catch(() => {});
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchDevices = useCallback(async () => {
    setLoadingDevices(true);
    let deviceList: Device[] = [];
    try {
      const res = await apiFetch('/esphome/devices');
      if (res.ok) {
        const data = await res.json();
        deviceList = data.devices || [];
        setDevices(deviceList);
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

    // Ping devices asynchronously after the list is already shown
    if (deviceList.length === 0) return;
    try {
      const pingRes = await apiFetch('/esphome/devices/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          devices: deviceList.map(d => ({ address: d.address, filename: d.filename }))
        }),
      });
      if (pingRes.ok) {
        const { results } = await pingRes.json();
        setDevices(prev => prev.map(d => ({
          ...d,
          online: results[d.filename] ?? d.online,
        })));
      }
    } catch (e) {
      console.error('Failed to ping devices:', e);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      // If OTA is running in the background, just re-attach — don't wipe state
      if (!otaRunningRef.current) {
        fetchDevices();
        setStatus('idle');
        setLogs([]);
        setStatusMessage('');
        setSelectedDevice(null);
      }
    } else {
      // When closing, only stop polling if OTA is NOT running in background
      if (!otaRunningRef.current && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, [isOpen, fetchDevices]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    if (logs.length > 0) lastLogTimeRef.current = Date.now();
  }, [logs]);

  // Elapsed / last-log-age ticker while installing
  useEffect(() => {
    if (status === 'installing') {
      if (!installStartRef.current) installStartRef.current = Date.now();
      if (!lastLogTimeRef.current) lastLogTimeRef.current = Date.now();
      const timer = setInterval(() => {
        setElapsed(Math.floor((Date.now() - installStartRef.current!) / 1000));
        setLastLogAge(Math.floor((Date.now() - lastLogTimeRef.current!) / 1000));
      }, 1000);
      return () => clearInterval(timer);
    } else {
      installStartRef.current = null;
      lastLogTimeRef.current = null;
      setElapsed(0);
      setLastLogAge(0);
    }
  }, [status]);

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
            otaRunningRef.current = false;
            onOtaActiveChange?.(false);
            setStatus('success');
            setStatusMessage(data.message);
          } else if (data.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            otaRunningRef.current = false;
            onOtaActiveChange?.(false);
            setStatus('error');
            setStatusMessage(data.message);
          }
        } catch (e) {
          console.error('Poll error:', e);
          // Don't stop polling on transient network errors
        }
      };

      // Mark OTA as running in background so closing the dialog won't cancel it
      otaRunningRef.current = true;
      onOtaActiveChange?.(true);

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
    otaRunningRef.current = false;
    onOtaActiveChange?.(false);
    try {
      await apiFetch('/esphome/install/cancel', { method: 'POST' });
    } catch {
      // Ignore
    }
    setStatus('cancelled');
    setStatusMessage('Installation cancelled');
  };

  const handleClose = () => {
    // OTA install runs in background — just close the dialog, don't cancel
    onClose();
  };

  // Keep the dialog DOM alive (but hidden) when USB compile is running in background
  if (!isOpen && !stayMounted) return null;
  const dialogHidden = !isOpen && stayMounted;

  const isWorking = status === 'installing' || status === 'saving';
  const isDone = status === 'success' || status === 'error' || status === 'cancelled';
  const selected = devices.find(d => d.filename === selectedDevice);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[200] p-4 backdrop-blur-sm" style={{ display: dialogHidden ? 'none' : undefined }} onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[85vh]" onClick={(e) => e.stopPropagation()}>
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

        {/* Tabs */}
        {!isWorking && !isDone && (
          <div className="flex border-b bg-white flex-shrink-0">
            <button
              onClick={() => setActiveTab('ota')}
              className={`flex-1 px-4 py-2.5 text-sm font-bold flex items-center justify-center gap-1.5 transition-colors border-b-2 ${
                activeTab === 'ota'
                  ? 'text-green-700 border-green-600 bg-green-50/50'
                  : 'text-slate-500 border-transparent hover:bg-slate-50 hover:text-slate-700'
              }`}
            >
              <Wifi size={14} /> OTA Devices
            </button>
            <button
              onClick={() => setActiveTab('usb')}
              className={`flex-1 px-4 py-2.5 text-sm font-bold flex items-center justify-center gap-1.5 transition-colors border-b-2 ${
                activeTab === 'usb'
                  ? 'text-purple-700 border-purple-600 bg-purple-50/50'
                  : 'text-slate-500 border-transparent hover:bg-slate-50 hover:text-slate-700'
              }`}
            >
              <Usb size={14} /> USB Flash
            </button>
          </div>
        )}

        {/* No-toolchain warning — shown when no ESP32 toolchain is installed */}
        {showNoToolchain && (
          <div className="mx-4 mt-4 mb-2 rounded-lg border border-amber-300 bg-amber-50 p-4">
            <div className="flex gap-3">
              <AlertTriangle className="text-amber-500 shrink-0 mt-0.5" size={20} />
              <div className="flex-1">
                <p className="font-semibold text-amber-800 text-sm">No ESP32 toolchain installed</p>
                <p className="text-amber-700 text-xs mt-1 leading-relaxed">
                  The first compile/install requires building the toolchain locally.
                  This is a one-time process that takes <strong>10–15 minutes</strong>.
                  After that, all future installs will be fast.
                </p>
                <button
                  onClick={handleStartLocalBuild}
                  className="mt-3 flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  <Wrench size={13} />
                  Build toolchain locally & proceed
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Local build progress */}
        {showLocalBuildProgress && (
          <div className="mx-4 mt-4 mb-2 rounded-lg border border-blue-200 bg-blue-50 p-4">
            <div className="flex gap-3">
              <Wrench className="text-blue-500 shrink-0 mt-0.5 animate-pulse" size={20} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <p className="font-semibold text-blue-800 text-sm shrink-0">Building toolchain locally...</p>
                    {buildEsphomeVersion && (
                      <span className="text-blue-500 text-xs font-mono shrink-0">ESPHome {buildEsphomeVersion}</span>
                    )}
                    {buildSource && (
                      <span className="text-blue-400 text-xs shrink-0">· {buildSource}</span>
                    )}
                  </div>
                  <button
                    onClick={handleCancelBuild}
                    className="shrink-0 flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-red-600 border border-red-200 bg-white hover:bg-red-50 transition-colors"
                  >
                    <Square size={10} className="fill-red-500" />
                    Cancel
                  </button>
                </div>
                <p className="text-blue-600 text-xs mt-0.5 truncate">{localBuildMessage}</p>
                <div className="mt-2 h-2 bg-blue-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${localBuildProgress}%` }}
                  />
                </div>
                <p className="text-blue-500 text-xs mt-1">{localBuildProgress}% — install will start automatically when done</p>
                {/* Live log */}
                <div className="mt-3 rounded bg-slate-900 text-green-400 font-mono text-[10px] leading-relaxed p-2 h-40 overflow-y-auto">
                  <pre className="whitespace-pre-wrap break-all">{buildLogs || 'Waiting for output...'}</pre>
                  <div ref={buildLogsEndRef} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Checking spinner — shown briefly while toolchain_setup.py is still starting */}
          {isToolchainStarting && (
            <div className="mx-4 mt-4 mb-2 rounded-lg border border-slate-200 bg-slate-50 p-3 flex items-center gap-2 text-slate-500 text-xs">
              <RefreshCw size={13} className="animate-spin shrink-0" />
              Checking toolchain status...
            </div>
          )}

        {/* Content (disabled until toolchain is ready) */}
        <div className={`flex-1 overflow-hidden flex flex-col min-h-0${
          !isToolchainReady ? ' opacity-40 pointer-events-none' : ''
        }`}>
        {/* USB Flash Tab – always mounted, CSS-hidden when OTA tab is active */}
          <UsbInstallPanel
            onSaveAndInstall={onSaveAndInstall}
            onCompileActiveChange={onCompileActiveChange}
            hidden={activeTab !== 'usb'}
          />

          {/* OTA Device List */}
          {activeTab === 'ota' && !isWorking && !isDone && (
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
                          {device.online === true ? (
                            <span className="flex items-center gap-1 text-[10px] text-green-600 font-bold">
                              <Wifi size={12} /> Online
                            </span>
                          ) : device.online === false ? (
                            <span className="flex items-center gap-1 text-[10px] text-slate-400 font-bold">
                              <WifiOff size={12} /> Offline
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-[10px] text-slate-400">
                              <RefreshCw size={10} className="animate-spin" />
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
                    <div className="flex-1">
                      <div className="font-bold text-sm flex items-center gap-2">
                        Installing to {selected?.friendly_name}...
                        <span className="font-mono text-xs opacity-60">{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')}</span>
                      </div>
                      <div className="text-[10px] opacity-70">
                        {lastLogAge >= 10
                          ? `No new output for ${lastLogAge}s — compiling (this is normal for CMake/ESP-IDF phases)`
                          : 'Compiling and uploading via OTA. This may take a few minutes.'}
                      </div>
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

        {/* Footer - only for OTA tab (USB panel has its own) */}
        {(activeTab === 'ota' || isWorking || isDone) && (
        <div className="p-4 border-t bg-slate-50 flex justify-end gap-3 flex-shrink-0">
          {activeTab === 'ota' && !isWorking && !isDone && (
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
        )}
      </div>
    </div>
  );
};
