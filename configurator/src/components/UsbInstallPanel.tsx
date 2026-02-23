import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Usb, RefreshCw, ChevronDown, ChevronUp, Square, AlertTriangle, Key, Monitor, Plus, FolderOpen, Wifi, Eye, EyeOff } from 'lucide-react';
import { apiFetch, isAddon } from '../utils/api';

// Types for Web Serial API (not in standard TS lib)
declare global {
  interface Navigator {
    serial?: {
      getPorts(): Promise<SerialPort[]>;
      requestPort(options?: { filters?: Array<{ usbVendorId?: number; usbProductId?: number }> }): Promise<SerialPort>;
      addEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void;
    };
  }
  interface SerialPort {
    getInfo(): { usbVendorId?: number; usbProductId?: number };
    open(options: { baudRate: number }): Promise<void>;
    close(): Promise<void>;
    readable: ReadableStream | null;
    writable: WritableStream | null;
  }
}

const ESP_VENDOR_IDS = [
  0x10C4, // Silicon Labs CP210x
  0x1A86, // QinHeng CH340
  0x0403, // FTDI
  0x303A, // Espressif USB JTAG/Serial
];

interface DeviceListEntry {
  filename: string;
  device_name: string;
  friendly_name: string;
  screen_type: string | null;
}

interface UsbInstallPanelProps {
  onSaveAndInstall: (deviceName: string, friendlyName: string, screenType: string, fileName: string, encryptionKey: string, otaPassword?: string, ipAddress?: string) => Promise<void>;
  onCompileActiveChange?: (active: boolean) => void;
  hidden?: boolean;
}

type UsbStatus = 'idle' | 'saving' | 'compiling' | 'compiled' | 'downloading' | 'flashing' | 'success' | 'error';
type ConfigMode = 'existing' | 'new';

function generateEncryptionKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

/** Load device settings from an existing YAML file on the server. */
async function loadDeviceInfo(filename: string) {
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
}

export const UsbInstallPanel: React.FC<UsbInstallPanelProps> = ({
  onSaveAndInstall,
  onCompileActiveChange,
  hidden,
}) => {
  const [serialSupported] = useState(() => !!navigator.serial);
  const [port, setPort] = useState<SerialPort | null>(null);
  const [status, setStatus] = useState<UsbStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [logsExpanded, setLogsExpanded] = useState(true);
  const [flashProgress, setFlashProgress] = useState(0);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const compiledDeviceNameRef = useRef<string>('');

  // Config mode: use existing file or create new
  const [configMode, setConfigMode] = useState<ConfigMode>('existing');

  // Existing config state
  const [deviceConfigs, setDeviceConfigs] = useState<DeviceListEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [loadingConfigs, setLoadingConfigs] = useState(false);

  // New config form fields
  const [screenType, setScreenType] = useState<'2432s028' | '3248s035' | null>(null);
  const [deviceName, setDeviceName] = useState('');
  const [friendlyName, setFriendlyName] = useState('');
  const [encryptionKey, setEncryptionKey] = useState(() => generateEncryptionKey());
  const [overwriteConfirmed, setOverwriteConfirmed] = useState(false);

  // WiFi credentials dialog
  const [showWifiDialog, setShowWifiDialog] = useState(false);
  const [wifiSsid, setWifiSsid] = useState('');
  const [wifiPassword, setWifiPassword] = useState('');
  const [wifiShowPassword, setWifiShowPassword] = useState(false);
  const [wifiSaving, setWifiSaving] = useState(false);
  const [wifiConfigured, setWifiConfigured] = useState<boolean | null>(null); // null = not checked yet
  const [wifiConfiguredSsid, setWifiConfiguredSsid] = useState('');
  const pendingFlashRef = useRef(false);

  // ── Notify parent of compile activity ────────────────────────
  const notifyCompileActive = useCallback((active: boolean) => {
    onCompileActiveChange?.(active);
  }, [onCompileActiveChange]);

  // ── Fetch device configs and WiFi status on mount ─────────────
  useEffect(() => {
    const fetchConfigs = async () => {
      setLoadingConfigs(true);
      try {
        const res = await apiFetch('/esphome/devices');
        if (res.ok) {
          const data = await res.json();
          const devices = data.devices || [];
          setDeviceConfigs(devices);
          if (devices.length === 0) setConfigMode('new');
        }
      } catch (e) {
        console.error('Failed to fetch device configs:', e);
      } finally {
        setLoadingConfigs(false);
      }
    };
    const fetchWifiStatus = async () => {
      try {
        const res = await apiFetch('/esphome/wifi');
        if (res.ok) {
          const data = await res.json();
          setWifiConfigured(data.configured);
          if (data.configured) setWifiConfiguredSsid(data.ssid);
        }
      } catch { /* OK */ }
    };
    fetchConfigs();
    fetchWifiStatus();
  }, []);

  // ── Auto-scroll logs (only when visible) ─────────────────────
  useEffect(() => {
    if (!hidden) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, hidden]);

  // ── Cleanup poll on unmount ──────────────────────────────────
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  // ── Check for already-granted serial ports ───────────────────
  useEffect(() => {
    if (!serialSupported) return;
    navigator.serial!.getPorts().then(ports => {
      const espPort = ports.find(p => {
        const info = p.getInfo();
        return info.usbVendorId && ESP_VENDOR_IDS.includes(info.usbVendorId);
      });
      if (espPort) setPort(espPort);
    });
  }, [serialSupported]);

  // ── Listen for serial connect/disconnect ─────────────────────
  useEffect(() => {
    if (!serialSupported) return;
    const onConnect = () => {
      navigator.serial!.getPorts().then(ports => {
        const espPort = ports.find(p => {
          const info = p.getInfo();
          return info.usbVendorId && ESP_VENDOR_IDS.includes(info.usbVendorId);
        });
        if (espPort) setPort(espPort);
      });
    };
    const onDisconnect = () => {
      navigator.serial!.getPorts().then(ports => {
        const espPort = ports.find(p => {
          const info = p.getInfo();
          return info.usbVendorId && ESP_VENDOR_IDS.includes(info.usbVendorId);
        });
        if (!espPort) setPort(null);
      });
    };
    navigator.serial!.addEventListener('connect', onConnect);
    navigator.serial!.addEventListener('disconnect', onDisconnect);
    return () => {
      navigator.serial!.removeEventListener('connect', onConnect);
      navigator.serial!.removeEventListener('disconnect', onDisconnect);
    };
  }, [serialSupported]);

  // ── Check for active compile on mount (recovery after dialog close/reopen) ──
  useEffect(() => {
    const checkActiveCompile = async () => {
      if (status !== 'idle') return;
      try {
        const res = await apiFetch('/esphome/compile/status?offset=0');
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'running') {
          setStatus('compiling');
          notifyCompileActive(true);
          if (data.lines?.length > 0) setLogs(data.lines);
          if (data.device_name) compiledDeviceNameRef.current = data.device_name;
          startCompilePoll(data.offset || 0);
        }
      } catch {
        // No active compile
      }
    };
    checkActiveCompile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Compile polling ──────────────────────────────────────────
  const startCompilePoll = useCallback((initialOffset: number) => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    let offset = initialOffset;

    const poll = async () => {
      try {
        const statusRes = await apiFetch(`/esphome/compile/status?offset=${offset}`);
        if (!statusRes.ok) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus('error');
          setStatusMessage('Lost connection to compile process');
          notifyCompileActive(false);
          return;
        }
        const data = await statusRes.json();
        if (data.lines?.length > 0) setLogs(prev => [...prev, ...data.lines]);
        offset = data.offset;
        if (data.device_name) compiledDeviceNameRef.current = data.device_name;

        if (data.status === 'success') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus('compiled');
          notifyCompileActive(false);
        } else if (data.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus('error');
          setStatusMessage(data.message || 'Compilation failed');
          notifyCompileActive(false);
        }
      } catch (e) {
        console.error('Compile poll error:', e);
      }
    };

    pollRef.current = setInterval(poll, 1500);
    poll();
  }, [notifyCompileActive]);

  // ── When compile finishes, auto-proceed to firmware download + flash ──
  useEffect(() => {
    if (status !== 'compiled') return;
    downloadAndFlash();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const handleRequestPort = async () => {
    if (!serialSupported) return;
    try {
      const selected = await navigator.serial!.requestPort({
        filters: ESP_VENDOR_IDS.map(id => ({ usbVendorId: id }))
      });
      setPort(selected);
    } catch (e) {
      console.log('Port request cancelled or failed:', e);
    }
  };

  const getPortLabel = useCallback(() => {
    if (!port) return '';
    const info = port.getInfo();
    const vid = info.usbVendorId;
    if (vid === 0x10C4) return 'CP210x (Silicon Labs)';
    if (vid === 0x1A86) return 'CH340 (QinHeng)';
    if (vid === 0x0403) return 'FTDI';
    if (vid === 0x303A) return 'ESP32 USB';
    return `USB Device (VID: 0x${vid?.toString(16) || '?'})`;
  }, [port]);

  const sanitizeDeviceName = (name: string) => {
    return name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  };

  // ── Download firmware + flash via serial ─────────────────────
  const downloadAndFlash = async () => {
    const deviceNameForFirmware = compiledDeviceNameRef.current;
    if (!deviceNameForFirmware) {
      setStatus('error');
      setStatusMessage('No device name found from compilation');
      return;
    }

    if (!port) {
      setStatus('error');
      setStatusMessage('USB port disconnected. Please reconnect your ESP32 and try again.');
      return;
    }

    setLogs(prev => [...prev, 'Compilation complete! Fetching firmware manifest...']);
    setStatus('downloading');

    let manifest: { name: string; parts: { path: string; offset: number }[] };
    try {
      const manifestRes = await apiFetch(`/esphome/firmware/${encodeURIComponent(deviceNameForFirmware)}/manifest.json`);
      if (!manifestRes.ok) {
        const err = await manifestRes.json().catch(() => ({ error: 'Unknown error' }));
        setStatus('error');
        setStatusMessage(err.error || 'Failed to fetch firmware manifest');
        return;
      }
      manifest = await manifestRes.json();
    } catch (e) {
      setStatus('error');
      setStatusMessage(`Failed to fetch firmware manifest: ${(e as Error).message}`);
      return;
    }

    setLogs(prev => [...prev, `Firmware manifest loaded: ${manifest.parts.length} part(s)`]);
    setLogs(prev => [...prev, 'Downloading firmware binaries...']);

    const fileArray: { data: string; address: number }[] = [];
    try {
      for (const part of manifest.parts) {
        // Strip /api prefix if present — apiFetch already prepends API_BASE
        const fetchPath = part.path.startsWith('/api/') ? part.path.substring(4) : part.path;
        const binRes = await apiFetch(fetchPath);
        if (!binRes.ok) throw new Error(`Failed to download ${part.path} (HTTP ${binRes.status})`);
        const blob = await binRes.blob();
        const arrayBuffer = await blob.arrayBuffer();
        const bytes = new Uint8Array(arrayBuffer);
        if (bytes.length < 1024) {
          throw new Error(`Firmware file ${part.path.split('/').pop()} is only ${bytes.length} bytes — expected a valid firmware binary`);
        }
        // esptool-js expects a raw binary string (1 char = 1 byte), NOT base64
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        fileArray.push({ data: binary, address: part.offset });
        setLogs(prev => [...prev, `  Downloaded ${part.path.split('/').pop()} (${(bytes.length / 1024).toFixed(1)} KB)`]);
      }
    } catch (e) {
      setStatus('error');
      setStatusMessage(`Failed to download firmware: ${(e as Error).message}`);
      // Clean up server files even on download failure in cloud mode
      if (!isAddon) apiFetch('/esphome/compile/cleanup', { method: 'POST' }).catch(() => {});
      return;
    }

    // Firmware is now fully in browser memory — clean up server files in cloud mode
    if (!isAddon) {
      apiFetch('/esphome/compile/cleanup', { method: 'POST' }).catch(() => {});
    }

    // Flash via Web Serial — two-phase approach:
    // Phase 1: Try auto-reset (DTR/RTS toggling) — works on some boards
    // Phase 2: If auto-reset fails, ask user to manually enter bootloader and retry
    setStatus('flashing');
    setLogs(prev => [...prev, '', '── Connecting to ESP32 via USB ──']);

    const { ESPLoader, Transport } = await import('esptool-js');

    const closePort = async () => {
      try {
        if (port.readable || port.writable) {
          await port.close();
          await new Promise(r => setTimeout(r, 300));
        }
      } catch { /* OK */ }
    };

    const makeTerminal = () => ({
      clean: () => {},
      writeLine: (data: string) => { if (data.trim()) setLogs(prev => [...prev, data]); },
      write: (data: string) => { if (data.trim()) setLogs(prev => [...prev, data]); },
    });

    const tryConnect = async (mode: string, attempts: number): Promise<{ loader: InstanceType<typeof ESPLoader>; transport: InstanceType<typeof Transport>; chip: string } | null> => {
      await closePort();
      const t = new Transport(port, false);
      const loader = new ESPLoader({
        transport: t,
        baudrate: 460800,
        terminal: makeTerminal(),
        romBaudrate: 115200,
        enableTracing: false,
      });
      try {
        const chip = await loader.main(mode);
        return { loader, transport: t, chip };
      } catch {
        try { await t.disconnect(); } catch { /* OK */ }
        return null;
      }
    };

    let result: { loader: InstanceType<typeof ESPLoader>; transport: InstanceType<typeof Transport>; chip: string } | null = null;

    // Phase 1: Auto-reset (quick — 3 attempts)
    setLogs(prev => [...prev, 'Phase 1: Trying automatic reset into bootloader...']);
    result = await tryConnect('default_reset', 3);

    // Phase 2: Manual bootloader entry
    if (!result) {
      setLogs(prev => [
        ...prev,
        '',
        '⚠ Auto-reset failed. Manual bootloader entry needed.',
        '',
        '  ┌─────────────────────────────────────────┐',
        '  │  1. Hold the BOOT button                │',
        '  │  2. While holding BOOT, press RESET     │',
        '  │  3. Release RESET, then release BOOT    │',
        '  │  4. Waiting 8 seconds for you...         │',
        '  └─────────────────────────────────────────┘',
        '',
      ]);

      // Give user time to enter bootloader mode
      for (let countdown = 8; countdown > 0; countdown--) {
        setLogs(prev => {
          const last = prev[prev.length - 1];
          const line = `  Retrying in ${countdown} seconds...`;
          if (last?.startsWith('  Retrying in')) return [...prev.slice(0, -1), line];
          return [...prev, line];
        });
        await new Promise(r => setTimeout(r, 1000));
      }

      setLogs(prev => [...prev, 'Phase 2: Connecting in no-reset mode...']);
      result = await tryConnect('no_reset', 5);
    }

    if (!result) {
      setStatus('error');
      setStatusMessage(
        'Failed to connect to ESP32 bootloader.\n' +
        '1. Hold BOOT, press & release RESET, release BOOT\n' +
        '2. Click "Try Again" within 5 seconds'
      );
      return;
    }

    const { loader, transport: activeTransport, chip } = result;
    setLogs(prev => [...prev, `Connected! Chip: ${chip}`]);
    setLogs(prev => [...prev, 'Writing firmware...']);

    try {
      await loader.writeFlash({
        fileArray,
        flashSize: 'keep',
        flashMode: 'keep',
        flashFreq: 'keep',
        eraseAll: false,
        compress: true,
        reportProgress: (fileIndex: number, written: number, total: number) => {
          const pct = Math.round((written / total) * 100);
          setFlashProgress(pct);
          if (pct % 10 === 0) {
            setLogs(prev => {
              const last = prev[prev.length - 1];
              const progressLine = `  Writing part ${fileIndex + 1}/${fileArray.length}: ${pct}%`;
              if (last?.startsWith('  Writing part')) return [...prev.slice(0, -1), progressLine];
              return [...prev, progressLine];
            });
          }
        },
        calculateMD5Hash: (_image: string) => '',
      });

      setLogs(prev => [...prev, '', '✅ Firmware written successfully!']);
      setFlashProgress(100);
      setStatus('success');
      setStatusMessage('Flash complete! Unplug and re-plug the USB cable to start the new firmware.');

      // Attempt auto-reset (best-effort, won't work on most CYD boards)
      try {
        const resetTimeout = new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000));
        await Promise.race([loader.hardReset(), resetTimeout]);
        setLogs(prev => [...prev, 'Device reset automatically.']);
      } catch {
        setLogs(prev => [...prev, '⚠ Auto-reset not supported on this board.', '  → Unplug and re-plug the USB cable to start the new firmware.']);
      }
      try { await activeTransport.disconnect(); } catch { /* OK */ }
    } catch (e) {
      const msg = (e as Error).message || String(e);
      setStatus('error');
      try { await activeTransport.disconnect(); } catch { /* OK */ }
      if (msg.includes('Failed to execute') || msg.includes('denied') || msg.includes('NetworkError') || msg.includes('already open')) {
        setStatusMessage('Cannot open serial port. Make sure no other program (e.g. ESPHome Dashboard, Arduino IDE) is using it. Try unplugging and reconnecting your ESP32.');
      } else {
        setStatusMessage(`Flash failed: ${msg}`);
      }
    }
  };

  // ── WiFi credentials check ──────────────────────────────────
  const checkWifiConfigured = async (): Promise<boolean> => {
    try {
      const res = await apiFetch('/esphome/wifi');
      if (res.ok) {
        const data = await res.json();
        setWifiConfigured(data.configured);
        if (data.configured) setWifiConfiguredSsid(data.ssid);
        return data.configured;
      }
    } catch (e) {
      console.error('Failed to check WiFi config:', e);
    }
    return false;
  };

  const saveWifiCredentials = async () => {
    if (!wifiSsid.trim() || !wifiPassword.trim()) return;
    setWifiSaving(true);
    try {
      const res = await apiFetch('/esphome/wifi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid: wifiSsid.trim(), password: wifiPassword.trim() }),
      });
      if (res.ok) {
        setWifiConfigured(true);
        setWifiConfiguredSsid(wifiSsid.trim());
        setShowWifiDialog(false);
        // Continue the flash that was paused for WiFi
        if (pendingFlashRef.current) {
          pendingFlashRef.current = false;
          setTimeout(() => doFlash(), 100);
        }
      } else {
        const err = await res.json().catch(() => ({ error: 'Unknown error' }));
        alert(err.error || 'Failed to save WiFi credentials');
      }
    } catch (e) {
      alert(`Failed to save WiFi credentials: ${(e as Error).message}`);
    } finally {
      setWifiSaving(false);
    }
  };

  // ── Start the full flash flow: save → compile → (auto) download+flash ──
  const handleFlash = async () => {
    if (!port) return;

    // Check WiFi credentials before starting
    const isConfigured = await checkWifiConfigured();
    if (!isConfigured) {
      pendingFlashRef.current = true;
      setShowWifiDialog(true);
      return;
    }

    doFlash();
  };

  const doFlash = async () => {
    if (!port) return;

    setLogs([]);
    setStatusMessage('');
    setLogsExpanded(true);
    setFlashProgress(0);

    let flashDeviceName: string;
    let flashFriendlyName: string;
    let flashScreenType: string;
    let flashFileName: string;
    let flashEncryptionKey: string;
    let flashOtaPassword: string | undefined;
    let flashIpAddress: string | undefined;

    if (configMode === 'existing') {
      if (!selectedFile) return;
      setStatus('saving');
      setLogs(prev => [...prev, `Loading device settings from ${selectedFile}...`]);

      const info = await loadDeviceInfo(selectedFile);
      if (!info) {
        setStatus('error');
        setStatusMessage(`Failed to read device settings from ${selectedFile}`);
        return;
      }
      if (!info.encryptionKey) {
        setStatus('error');
        setStatusMessage(`No API encryption key found in ${selectedFile}. Please save the device config first via "Save Device".`);
        return;
      }

      flashDeviceName = info.deviceName;
      flashFriendlyName = info.friendlyName;
      flashScreenType = info.screenType;
      flashFileName = selectedFile;
      flashEncryptionKey = info.encryptionKey;
      flashOtaPassword = info.otaPassword;
      flashIpAddress = info.ipAddress;
    } else {
      const cleanName = sanitizeDeviceName(deviceName);
      if (!cleanName) {
        setStatus('error');
        setStatusMessage('Please enter a valid device name.');
        return;
      }
      const targetFile = `${cleanName}.yaml`;
      const existingMatch = deviceConfigs.find(dc => dc.filename === targetFile);
      if (existingMatch && !overwriteConfirmed) return;

      flashDeviceName = cleanName;
      flashFriendlyName = friendlyName || cleanName;
      if (!screenType) {
        setStatus('error');
        setStatusMessage('Please select a screen type.');
        return;
      }
      flashScreenType = screenType;
      flashFileName = targetFile;
      flashEncryptionKey = encryptionKey;
      setStatus('saving');
    }

    setLogs(prev => [...prev, `Saving tile configuration to ${flashFileName}...`]);

    try {
      await onSaveAndInstall(
        flashDeviceName, flashFriendlyName, flashScreenType,
        flashFileName, flashEncryptionKey, flashOtaPassword, flashIpAddress,
      );
    } catch (e) {
      setStatus('error');
      setStatusMessage(`Failed to save config: ${(e as Error).message}`);
      return;
    }

    setLogs(prev => [...prev, 'Configuration saved. Starting compilation...']);

    // Start compile on server
    setStatus('compiling');
    notifyCompileActive(true);
    compiledDeviceNameRef.current = flashDeviceName;

    try {
      const res = await apiFetch('/esphome/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: flashFileName }),
      });

      if (!res.ok) {
        let errorMsg = `Server returned ${res.status}`;
        try {
          const text = await res.text();
          try { errorMsg = JSON.parse(text).error || errorMsg; } catch { /* */ }
        } catch { /* */ }
        setStatus('error');
        setStatusMessage(errorMsg);
        notifyCompileActive(false);
        return;
      }

      const startData = await res.json();
      if (startData.device_name) compiledDeviceNameRef.current = startData.device_name;
      setLogs(prev => [...prev, startData.message || 'Compilation started...']);

      // Start polling — compile success triggers download+flash via useEffect
      startCompilePoll(0);

    } catch (e) {
      setStatus('error');
      setStatusMessage(`Compilation failed: ${(e as Error).message}`);
      notifyCompileActive(false);
    }
  };

  const handleCancel = async () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (status === 'compiling') {
      try { await apiFetch('/esphome/compile/cancel', { method: 'POST' }); } catch { /* */ }
    }
    if (!isAddon) {
      apiFetch('/esphome/compile/cleanup', { method: 'POST' }).catch(() => {});
    }
    setStatus('error');
    setStatusMessage('Operation cancelled');
    notifyCompileActive(false);
  };

  const reset = () => {
    setStatus('idle');
    setLogs([]);
    setStatusMessage('');
    setFlashProgress(0);
    compiledDeviceNameRef.current = '';
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    notifyCompileActive(false);
  };

  if (!serialSupported) {
    return (
      <div className="p-4 text-center" style={{ display: hidden ? 'none' : undefined }}>
        <AlertTriangle size={32} className="mx-auto text-amber-400 mb-2" />
        <p className="text-sm font-bold text-slate-700">Web Serial Not Supported</p>
        <p className="text-xs text-slate-500 mt-1">
          USB flashing requires Chrome, Edge, or Opera.<br />
          Firefox and Safari are not supported.
        </p>
      </div>
    );
  }

  const isWorking = status === 'saving' || status === 'compiling' || status === 'compiled' || status === 'downloading' || status === 'flashing';
  const isDone = status === 'success' || status === 'error';
  const cleanName = sanitizeDeviceName(deviceName);
  const fileExists = configMode === 'new' && !!cleanName && deviceConfigs.some(dc => dc.filename === `${cleanName}.yaml`);
  const canFlash = !!port && (
    configMode === 'existing' ? !!selectedFile : (!!cleanName && !!screenType)
  ) && (!fileExists || overwriteConfirmed);

  return (
    <div className="flex flex-col flex-1 min-h-0" style={{ display: hidden ? 'none' : 'flex' }}>
      {/* ── Idle: form ─────────────────────────────────────── */}
      {status === 'idle' && (
        <div className="p-4 flex-1 overflow-y-auto space-y-3">
          <p className="text-xs text-slate-500">
            Flash firmware directly to an ESP32 connected via USB to <strong>this computer</strong>.
          </p>

          {/* USB Port */}
          <div className={`p-3 rounded-lg border-2 ${port ? 'border-green-300 bg-green-50' : 'border-slate-200 bg-slate-50'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Usb size={18} className={port ? 'text-green-600' : 'text-slate-400'} />
                <div>
                  <div className="text-sm font-bold text-slate-800">
                    {port ? 'ESP32 Connected' : 'No ESP32 Detected'}
                  </div>
                  {port ? (
                    <div className="text-[10px] text-green-600 font-mono">{getPortLabel()}</div>
                  ) : (
                    <div className="text-[10px] text-slate-400">Plug in an ESP32 and click "Select USB Port"</div>
                  )}
                </div>
              </div>
              <button
                onClick={handleRequestPort}
                className="px-3 py-1.5 text-xs font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                {port ? 'Change' : 'Select USB Port'}
              </button>
            </div>
          </div>

          {/* WiFi Status */}
          <div className={`p-3 rounded-lg border-2 ${
            wifiConfigured === true ? 'border-green-300 bg-green-50' :
            wifiConfigured === false ? 'border-amber-300 bg-amber-50' :
            'border-slate-200 bg-slate-50'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wifi size={18} className={wifiConfigured ? 'text-green-600' : 'text-amber-500'} />
                <div>
                  <div className="text-sm font-bold text-slate-800">
                    {wifiConfigured === null ? 'Checking WiFi...' :
                     wifiConfigured ? `WiFi: ${wifiConfiguredSsid}` :
                     'WiFi Not Configured'}
                  </div>
                  {!wifiConfigured && wifiConfigured !== null && (
                    <div className="text-[10px] text-amber-600">Credentials needed before flashing</div>
                  )}
                </div>
              </div>
              <button
                onClick={() => setShowWifiDialog(true)}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors ${
                  wifiConfigured
                    ? 'text-slate-600 hover:bg-slate-200'
                    : 'bg-amber-500 text-white hover:bg-amber-600'
                }`}
              >
                {wifiConfigured ? 'Change' : 'Configure'}
              </button>
            </div>
          </div>

          {/* Config Mode Toggle */}
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Device Configuration</label>
            <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5">
              <button
                onClick={() => setConfigMode('existing')}
                className={`flex-1 py-1.5 px-2 rounded-md text-xs font-bold flex items-center justify-center gap-1 transition-all ${
                  configMode === 'existing'
                    ? 'bg-white text-purple-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <FolderOpen size={12} /> Existing Config
              </button>
              <button
                onClick={() => setConfigMode('new')}
                className={`flex-1 py-1.5 px-2 rounded-md text-xs font-bold flex items-center justify-center gap-1 transition-all ${
                  configMode === 'new'
                    ? 'bg-white text-purple-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <Plus size={12} /> New Device
              </button>
            </div>
          </div>

          {/* ── Existing Config ─────────────────────────────── */}
          {configMode === 'existing' && (
            <div>
              {loadingConfigs ? (
                <div className="flex items-center gap-2 text-xs text-slate-400 py-3 justify-center">
                  <RefreshCw size={12} className="animate-spin" /> Loading configs...
                </div>
              ) : deviceConfigs.length === 0 ? (
                <div className="text-xs text-slate-400 bg-slate-50 p-3 rounded-lg border border-slate-200 text-center">
                  No device configs found.<br />
                  <button onClick={() => setConfigMode('new')} className="text-purple-600 font-bold mt-1 hover:underline">
                    Create a new device instead
                  </button>
                </div>
              ) : (
                <div className="space-y-1.5 max-h-[180px] overflow-y-auto">
                  {deviceConfigs.map(dc => (
                    <button
                      key={dc.filename}
                      onClick={() => setSelectedFile(dc.filename)}
                      className={`w-full text-left px-3 py-2 rounded-lg border-2 transition-all flex items-center gap-2 ${
                        selectedFile === dc.filename
                          ? 'border-purple-400 bg-purple-50'
                          : 'border-slate-100 hover:border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <Monitor size={14} className={selectedFile === dc.filename ? 'text-purple-600' : 'text-slate-400'} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-bold text-slate-800 truncate">{dc.friendly_name}</div>
                        <div className="text-[10px] text-slate-400 font-mono truncate">{dc.filename}</div>
                      </div>
                      {dc.screen_type && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-bold flex-shrink-0">
                          {dc.screen_type === '2432s028' ? '2.8"' : '3.5"'}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── New Device ──────────────────────────────────── */}
          {configMode === 'new' && (
            <div className="space-y-3">
              {/* Screen Type */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Screen Type</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setScreenType('2432s028')}
                    className={`flex-1 py-2 px-3 rounded-lg border-2 text-sm font-bold transition-all ${
                      screenType === '2432s028'
                        ? 'border-purple-400 bg-purple-50 text-purple-700'
                        : 'border-slate-200 text-slate-500 hover:border-slate-300'
                    }`}
                  >
                    2.8" (2432S028)
                  </button>
                  <button
                    onClick={() => setScreenType('3248s035')}
                    className={`flex-1 py-2 px-3 rounded-lg border-2 text-sm font-bold transition-all ${
                      screenType === '3248s035'
                        ? 'border-purple-400 bg-purple-50 text-purple-700'
                        : 'border-slate-200 text-slate-500 hover:border-slate-300'
                    }`}
                  >
                    3.5" (3248S035)
                  </button>
                </div>
              </div>

              {/* Device Name */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Device Name</label>
                <input
                  type="text"
                  value={deviceName}
                  onChange={(e) => {
                    setDeviceName(e.target.value);
                    setFriendlyName(
                      e.target.value.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                    );
                    setOverwriteConfirmed(false);
                  }}
                  placeholder="e.g. cyd-kitchen"
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-400"
                />
                {cleanName && (
                  <div className="text-[10px] text-slate-400 mt-1 font-mono">
                    File: {cleanName}.yaml
                  </div>
                )}
                {fileExists && !overwriteConfirmed && (
                  <div className="mt-2 p-2.5 rounded-lg bg-amber-50 border border-amber-300">
                    <div className="flex items-center gap-1.5 text-amber-700 text-xs font-bold">
                      <AlertTriangle size={14} />
                      A config named <span className="font-mono">{cleanName}.yaml</span> already exists!
                    </div>
                    <p className="text-[10px] text-amber-600 mt-1">
                      Flashing will overwrite the existing device configuration.
                    </p>
                    <button
                      onClick={() => setOverwriteConfirmed(true)}
                      className="mt-1.5 px-3 py-1 text-[11px] font-bold bg-amber-600 text-white rounded hover:bg-amber-700 transition-colors"
                    >
                      Overwrite existing config
                    </button>
                  </div>
                )}
                {fileExists && overwriteConfirmed && (
                  <div className="mt-1 text-[10px] text-amber-600 flex items-center gap-1">
                    <AlertTriangle size={10} /> Will overwrite existing config
                  </div>
                )}
              </div>

              {/* Friendly Name */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Friendly Name</label>
                <input
                  type="text"
                  value={friendlyName}
                  onChange={(e) => setFriendlyName(e.target.value)}
                  placeholder="e.g. Kitchen Display"
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-400"
                />
              </div>

              {/* API Encryption Key */}
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">API Encryption Key</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={encryptionKey}
                    onChange={(e) => setEncryptionKey(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-lg border border-slate-200 text-[11px] font-mono focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-400"
                  />
                  <button
                    onClick={() => setEncryptionKey(generateEncryptionKey())}
                    className="px-2.5 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors text-slate-500"
                    title="Generate new key"
                  >
                    <Key size={14} />
                  </button>
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  Auto-generated. Needed later in Home Assistant to connect to the device.
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Progress / Done ────────────────────────────────── */}
      {(isWorking || isDone) && (
        <div className="p-4 flex-1 overflow-hidden flex flex-col min-h-0">
          {/* Status Banner */}
          <div className={`p-3 rounded-lg mb-3 flex items-center gap-2 flex-shrink-0 ${
            status === 'saving' ? 'bg-amber-50 text-amber-700' :
            status === 'compiling' || status === 'compiled' || status === 'downloading' ? 'bg-blue-50 text-blue-700' :
            status === 'flashing' ? 'bg-purple-50 text-purple-700' :
            status === 'success' ? 'bg-green-50 text-green-700' :
            'bg-red-50 text-red-700'
          }`}>
            {(status === 'saving' || status === 'compiling' || status === 'compiled' || status === 'downloading') && (
              <>
                <RefreshCw size={16} className="animate-spin flex-shrink-0" />
                <div>
                  <div className="font-bold text-sm">
                    {status === 'saving' ? 'Saving configuration...' :
                     status === 'downloading' ? 'Downloading firmware...' :
                     'Compiling firmware...'}
                  </div>
                  <div className="text-[10px] opacity-70">
                    {status === 'compiling' ? 'This may take a few minutes. You can close this dialog — compilation continues in the background.' :
                     status === 'saving' ? 'Preparing device config.' :
                     status === 'downloading' ? 'Fetching compiled firmware from server.' :
                     'Preparing flash...'}
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
                    <div className="bg-purple-600 h-1.5 rounded-full transition-all" style={{ width: `${flashProgress}%` }} />
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
              onClick={() => setLogsExpanded(!logsExpanded)}
              className="flex items-center justify-between text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 hover:text-slate-700 flex-shrink-0"
            >
              <span>Logs ({logs.length} lines)</span>
              {logsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {logsExpanded && (
              <div className="flex-1 h-0 bg-slate-900 rounded-lg p-3 overflow-y-auto font-mono text-[11px] text-slate-300 leading-relaxed">
                {logs.map((line, i) => (
                  <div key={i} className={`whitespace-pre-wrap break-all ${
                    line.includes('ERROR') || line.includes('error') || line.includes('Failed') ? 'text-red-400' :
                    line.includes('WARNING') || line.includes('warning') ? 'text-yellow-400' :
                    line.includes('Successfully') || line.includes('successfully') || line.includes('Complete') ? 'text-green-400' :
                    line.includes('Writing part') || line.includes('Connecting') ? 'text-purple-400' :
                    line.includes('Downloaded') ? 'text-blue-400' : ''
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

      {/* ── Footer ─────────────────────────────────────────── */}
      <div className="p-4 border-t bg-slate-50 flex justify-end gap-3 flex-shrink-0">
        {status === 'idle' && (
          <button
            onClick={handleFlash}
            disabled={!canFlash}
            className="px-4 py-2 text-sm font-bold bg-purple-600 text-white rounded-lg hover:bg-purple-700 shadow-sm transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Usb size={16} /> Flash via USB
          </button>
        )}
        {isWorking && (
          <button
            onClick={handleCancel}
            className="px-4 py-2 text-sm font-bold bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-sm transition-all flex items-center gap-2"
          >
            <Square size={16} /> Stop
          </button>
        )}
        {isDone && (
          <button
            onClick={reset}
            className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Try Again
          </button>
        )}
      </div>

      {/* ── WiFi Credentials Dialog ──────────────────────────── */}
      {showWifiDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[300] p-4 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm overflow-hidden animate-in fade-in zoom-in duration-200">
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
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">WiFi Network (SSID)</label>
                <input
                  type="text"
                  value={wifiSsid}
                  onChange={e => setWifiSsid(e.target.value)}
                  placeholder="Your WiFi network name"
                  className="w-full px-3 py-2 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-400 focus:outline-none transition-colors"
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') document.getElementById('wifi-password-input')?.focus(); }}
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Password</label>
                <div className="relative">
                  <input
                    id="wifi-password-input"
                    type={wifiShowPassword ? 'text' : 'password'}
                    value={wifiPassword}
                    onChange={e => setWifiPassword(e.target.value)}
                    placeholder="WiFi password"
                    className="w-full px-3 py-2 pr-10 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-400 focus:outline-none transition-colors"
                    onKeyDown={e => { if (e.key === 'Enter' && wifiSsid.trim() && wifiPassword.trim()) saveWifiCredentials(); }}
                  />
                  <button
                    type="button"
                    onClick={() => setWifiShowPassword(!wifiShowPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600"
                  >
                    {wifiShowPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
            <div className="p-4 border-t bg-slate-50 flex justify-end gap-2">
              <button
                onClick={() => { setShowWifiDialog(false); pendingFlashRef.current = false; }}
                className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveWifiCredentials}
                disabled={!wifiSsid.trim() || !wifiPassword.trim() || wifiSaving}
                className="px-4 py-1.5 text-sm font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {wifiSaving ? <RefreshCw size={14} className="animate-spin" /> : <Wifi size={14} />}
                {wifiSaving ? 'Saving...' : 'Save & Continue'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
