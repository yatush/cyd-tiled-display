import React, { useRef, useCallback, useState, useMemo, useEffect } from 'react';
import { dump } from 'js-yaml';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';
import { parseYamlToConfig, convertParsedYamlToConfig } from '../utils/yamlParser';
import { apiFetch, isAddon } from '../utils/api';
import {
  FileContext,
  DeviceFileMeta,
  getConfigSnapshot,
  extractDeviceMetaFromYamlData,
  loadStoredFileContext,
  saveStoredFileContext,
  loadStoredSnapshot,
  saveStoredSnapshot,
} from '../utils/fileContext';
import {
  buildTuyaBleFanYamlSections,
  configHasBleProxy,
  extractBleFansFromDeviceYaml,
} from '../utils/bleFanUtils';

export type QuickSaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function useFileOperations(
  config: Config,
  setConfig: (config: Config) => void,
  setActivePageId: (id: string) => void,
  onSaveSuccess?: () => void,
  onLoadSuccess?: () => void
) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileContext, setFileContextState] = useState<FileContext | null>(() => loadStoredFileContext());
  const [savedSnapshot, setSavedSnapshotState] = useState<string | null>(() => loadStoredSnapshot());
  const [saveStatus, setSaveStatus] = useState<QuickSaveStatus>('idle');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const setFileContext = useCallback((ctx: FileContext | null) => {
    setFileContextState(ctx);
    saveStoredFileContext(ctx);
  }, []);

  const setSavedSnapshot = useCallback((snapshot: string | null) => {
    setSavedSnapshotState(snapshot);
    saveStoredSnapshot(snapshot);
  }, []);

  const clearFileContext = useCallback(() => {
    setFileContext(null);
    setSavedSnapshot(null);
    setSaveStatus('idle');
  }, [setFileContext, setSavedSnapshot]);

  const markSavedStatus = useCallback((status: QuickSaveStatus) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaveStatus(status);
    if (status === 'saved' || status === 'error') {
      saveTimerRef.current = setTimeout(() => setSaveStatus('idle'), 2500);
    }
  }, []);

  const currentSnapshot = useMemo(() => getConfigSnapshot(config), [config]);
  const isDirty = useMemo(() => {
    if (!fileContext || savedSnapshot === null) return false;
    return currentSnapshot !== savedSnapshot;
  }, [fileContext, savedSnapshot, currentSnapshot]);

  const handleSaveToHa = useCallback(async (pathOverride?: string, silent?: boolean): Promise<boolean> => {
    if (!isAddon) {
      if (!silent) alert('Saving is disabled when not running in HA');
      return false;
    }
    try {
      const path = pathOverride || config.project_path || 'monitor_config/tiles.yaml';
      const res = await apiFetch('/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: config,
          path: path
        })
      });

      if (res.ok) {
        const data = await res.json();
        const savedPath = data.path || path;
        setFileContext({ kind: 'screen', path: savedPath });
        setSavedSnapshot(getConfigSnapshot(config));
        markSavedStatus('saved');
        if (!silent) alert(`Successfully saved to /config/esphome/${savedPath}`);
        if (onSaveSuccess) onSaveSuccess();
        return true;
      } else {
        const err = await res.json();
        markSavedStatus('error');
        if (!silent) alert(`Failed to save: ${err.error}`);
        return false;
      }
    } catch (err) {
      console.error('Failed to save to HA:', err);
      markSavedStatus('error');
      if (!silent) alert('Failed to save to Home Assistant. Check console for details.');
      return false;
    }
  }, [config, onSaveSuccess, setFileContext, setSavedSnapshot, markSavedStatus]);

  const handleLoadFromHa = useCallback(async (path?: string) => {
    try {
      const targetPath = path || config.project_path || 'monitor_config/tiles.yaml';
      const res = await apiFetch(`/load?path=${encodeURIComponent(targetPath)}`);
      if (res.ok) {
        let rawData = await res.json();
        let data = rawData;

        const isFullDevice = Boolean(rawData && rawData.tile_ui);
        const deviceMeta = isFullDevice ? extractDeviceMetaFromYamlData(rawData) : null;

        // Handle full device config nesting
        if (data && data.tile_ui) {
          data = data.tile_ui;
        }

        // If it's in ESPHome format (has screens), convert it
        if (data && data.screens && Array.isArray(data.screens)) {
          try {
            data = convertParsedYamlToConfig(data);
          } catch (e) {
            console.error("Failed to convert config", e);
            alert('Failed to parse the configuration file.');
            return;
          }
        }

        // Basic validation to ensure it's a valid config object
        if (!data || typeof data !== 'object' || !Array.isArray(data.pages)) {
          alert('Failed to load: The file does not appear to be a valid tile configuration.');
          return;
        }

        const loadedBleFans = isFullDevice ? extractBleFansFromDeviceYaml(rawData) : [];
        const loadedConfig: Config = {
          ...data,
          project_path: targetPath,
          ...(loadedBleFans.length > 0 ? { ble_fans: loadedBleFans } : {}),
        };
        setConfig(loadedConfig);
        setFileContext(
          isFullDevice && deviceMeta
            ? { kind: 'device', path: targetPath, deviceMeta }
            : { kind: 'screen', path: targetPath }
        );
        setSavedSnapshot(getConfigSnapshot(loadedConfig));
        setSaveStatus('idle');
        if (data.pages && data.pages.length > 0) {
          setActivePageId(data.pages[0].id);
        }
        if (onLoadSuccess) onLoadSuccess();
      } else {
        const err = await res.json();
        alert(`Failed to load: ${err.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to load from HA:', err);
      alert('Failed to load from Home Assistant. Check console for details.');
    }
  }, [config.project_path, setConfig, setActivePageId, setFileContext, setSavedSnapshot, onLoadSuccess]);

  const handleDownloadYaml = useCallback(async (suggestedName?: string): Promise<boolean> => {
    const yamlString = generateYaml(config);
    const fileName = suggestedName || 'monitor_tiles.yaml';

    try {
      // @ts-ignore - File System Access API
      if (window.showSaveFilePicker) {
        // @ts-ignore
        const handle = await window.showSaveFilePicker({
          suggestedName: fileName,
          types: [{
            description: 'YAML File',
            accept: { 'text/yaml': ['.yaml', '.yml'] },
          }],
        });
        const writable = await handle.createWritable();
        await writable.write(yamlString);
        await writable.close();
        setFileContext({ kind: 'local', path: handle.name || fileName });
        setSavedSnapshot(getConfigSnapshot(config));
        markSavedStatus('saved');
        return true;
      } else {
        const dataStr = "data:text/yaml;charset=utf-8," + encodeURIComponent(yamlString);
        const downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", fileName);
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
        setFileContext({ kind: 'local', path: fileName });
        setSavedSnapshot(getConfigSnapshot(config));
        markSavedStatus('saved');
        return true;
      }
    } catch (err) {
      console.error('Failed to save file:', err);
      return false;
    }
  }, [config, setFileContext, setSavedSnapshot, markSavedStatus]);

  const handleSaveYaml = useCallback(async () => {
    return handleSaveToHa();
  }, [handleSaveToHa]);

  const handleLoadProject = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;

        try {
          const parsedConfig = parseYamlToConfig(content);
          setConfig(parsedConfig);
          setFileContext({ kind: 'local', path: file.name });
          setSavedSnapshot(getConfigSnapshot(parsedConfig));
          setSaveStatus('idle');
          setActivePageId(parsedConfig.pages[0]?.id || 'main_page');
          if (onLoadSuccess) onLoadSuccess();
          return;
        } catch (yamlErr) {
          try {
            const parsed = JSON.parse(content);
            if (parsed.pages && Array.isArray(parsed.pages)) {
              setConfig(parsed);
              setFileContext({ kind: 'local', path: file.name });
              setSavedSnapshot(getConfigSnapshot(parsed));
              setSaveStatus('idle');
              setActivePageId(parsed.pages[0]?.id || 'main_page');
              if (onLoadSuccess) onLoadSuccess();
            } else {
              throw new Error("Invalid JSON format");
            }
          } catch (jsonErr) {
            throw new Error("Failed to parse file as YAML or JSON");
          }
        }
      } catch (err) {
        console.error(err);
        alert("Failed to parse project file. Please ensure it is a valid YAML or JSON file.");
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  }, [setConfig, setFileContext, setSavedSnapshot, setActivePageId, onLoadSuccess]);

  const handleExport = useCallback(() => {
    const yamlString = generateYaml(config);
    navigator.clipboard.writeText(yamlString).then(() => {
      alert("YAML configuration copied to clipboard!");
    }).catch(err => {
      console.error('Failed to copy: ', err);
      alert("Failed to copy to clipboard. Check console for output.");
    });
  }, [config]);

  const handleSaveDeviceConfig = useCallback(async (
    deviceName: string,
    friendlyName: string,
    screenType: string,
    fileName: string,
    encryptionKey: string,
    otaPassword?: string,
    ipAddress?: string,
    silent?: boolean,
    forceWrite?: boolean
  ): Promise<boolean> => {
    if (!isAddon && !forceWrite) {
      if (!silent) alert('Saving is disabled when not running in HA');
      return false;
    }
    try {
      let wifiSection = '';
      let externalComponentsSection = '';
      try {
        const loadRes = await apiFetch(`/load?path=${encodeURIComponent(fileName)}`);
        if (loadRes.ok) {
          const data = await loadRes.json();
          if (data.wifi) {
            // If we have a new IP address, update it in the wifi section
            if (ipAddress) {
              data.wifi.use_address = ipAddress;
            } else if (ipAddress === '') {
              // If explicitly cleared, remove it
              delete data.wifi.use_address;
            }
            wifiSection = dump({ wifi: data.wifi });
          } else if (ipAddress) {
            // If no wifi section but we have an IP, create it
            wifiSection = dump({ wifi: { use_address: ipAddress } });
          }
          // Preserve external_components from existing file
          if (data.external_components) {
            externalComponentsSection = dump({ external_components: data.external_components });
          }
        } else if (ipAddress) {
          // If load failed (new file) but we have an IP
          wifiSection = dump({ wifi: { use_address: ipAddress } });
        }
      } catch (e) {
        // ignore
      }

      // Default external_components if not found in existing file
      if (!externalComponentsSection) {
        externalComponentsSection = `external_components:
  - source:
      type: local
      path: external_components
`;
      }

      const otaSection = dump(
        otaPassword
          ? { ota: [{ platform: 'esphome', password: otaPassword }] }
          : { ota: [{ platform: 'esphome' }] }
      );

      // Fetch HA timezone so ESPHome can resolve it at compile time
      let timezone = 'UTC';  // fallback
      try {
        const tzRes = await apiFetch('/ha/timezone');
        if (tzRes.ok) {
          const tzData = await tzRes.json();
          if (tzData.timezone) {
            timezone = tzData.timezone;
          }
        }
      } catch (e) {
        // Use UTC fallback
      }

      const timeSection = `time:
  - id: !extend esptime
    timezone: ${JSON.stringify(timezone)}
`;

      const screensYaml = generateYaml(config, false, false);

      // Check if any tile in the config uses the BLE proxy display script or action
      const hasBleProxy = configHasBleProxy(config);
      const tuyaBle = buildTuyaBleFanYamlSections(config.ble_fans, hasBleProxy);

      const blePackageSection = `${tuyaBle.packageLine}${hasBleProxy ? '\n  ble_proxy: !include lib/ble_proxy.yaml' : ''}`;
      const substitutionsSection = dump({
        substitutions: {
          device_name: deviceName,
          friendly_name: friendlyName,
          ...tuyaBle.extraSubstitutions,
        }
      });
      const apiSection = dump({
        api: {
          encryption: {
            key: encryptionKey,
          }
        }
      });
      const tuyaBleComponentSection = tuyaBle.componentSection ? `${tuyaBle.componentSection}\n` : '';

      const fullYaml = `${substitutionsSection}
packages:
  device_base: !include lib/${screenType}_base.yaml
  lib: !include lib/lib.yaml${blePackageSection}

esphome:
  name: $device_name
  friendly_name: $friendly_name

${externalComponentsSection}
${apiSection}
${otaSection}
${wifiSection}
${timeSection}
${tuyaBleComponentSection}tile_ui:
${screensYaml.trimEnd().split('\n').map(line => '  ' + line).join('\n')}
`;

      const res = await apiFetch('/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: fullYaml,
          path: fileName
        })
      });

      if (res.ok) {
        const deviceMeta: DeviceFileMeta = {
          deviceName,
          friendlyName,
          screenType,
          encryptionKey,
          otaPassword,
          ipAddress,
        };
        setFileContext({ kind: 'device', path: fileName, deviceMeta });
        setSavedSnapshot(getConfigSnapshot(config));
        markSavedStatus('saved');
        if (!silent) alert(`Successfully saved device configuration to /config/esphome/${fileName}`);
        if (onSaveSuccess) onSaveSuccess();
        return true;
      } else {
        const err = await res.json();
        markSavedStatus('error');
        if (!silent) alert(`Failed to save: ${err.error}`);
        return false;
      }
    } catch (err) {
      console.error('Failed to save device config:', err);
      markSavedStatus('error');
      if (!silent) alert('Failed to save device configuration. Check console for details.');
      return false;
    }
  }, [config, onSaveSuccess, setFileContext, setSavedSnapshot, markSavedStatus]);

  const handleLoadDeviceConfig = useCallback(async (path: string) => {
    try {
      const res = await apiFetch(`/load?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const rawData = await res.json();
        const deviceMeta = extractDeviceMetaFromYamlData(rawData);
        const extractedBleFans = extractBleFansFromDeviceYaml(rawData);
        let data = rawData;

        // Use the tile_ui section if this is a full device configuration
        if (data.tile_ui) {
          data = data.tile_ui;
        }

        // If the data is in 'screens' format, convert it to internal 'pages' format
        if (data.screens && Array.isArray(data.screens)) {
          try {
            data = convertParsedYamlToConfig(data);
          } catch (e) {
            console.error("Failed to convert screens to pages", e);
            alert('Failed to parse the screen configuration.');
            return;
          }
        }

        // Basic validation
        if (!data || !data.pages || !Array.isArray(data.pages)) {
          alert('Failed to load: No valid tile configuration found in file.');
          return;
        }

        if (extractedBleFans.length > 0) {
          data = { ...data, ble_fans: extractedBleFans };
        }

        setConfig(data);
        setFileContext(
          deviceMeta
            ? { kind: 'device', path, deviceMeta }
            : { kind: 'screen', path }
        );
        setSavedSnapshot(getConfigSnapshot(data));
        setSaveStatus('idle');
        if (data.pages.length > 0) {
          setActivePageId(data.pages[0].id);
        }
        if (onLoadSuccess) onLoadSuccess();
      } else {
        const err = await res.json();
        alert(`Failed to load: ${err.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to load device config:', err);
      alert('Failed to load device configuration. Check console for details.');
    }
  }, [setConfig, setActivePageId, setFileContext, setSavedSnapshot, onLoadSuccess]);

  const handleQuickSave = useCallback(async (): Promise<boolean> => {
    if (!fileContext) return false;

    setSaveStatus('saving');

    if (fileContext.kind === 'device') {
      let meta: DeviceFileMeta | null = fileContext.deviceMeta || null;
      // Refresh metadata from disk so any external edits (IP/OTA/key) are preserved
      try {
        const res = await apiFetch(`/load?path=${encodeURIComponent(fileContext.path)}`);
        if (res.ok) {
          const raw = await res.json();
          const diskMeta = extractDeviceMetaFromYamlData(raw);
          if (diskMeta && diskMeta.encryptionKey) {
            meta = diskMeta;
          }
        }
      } catch {
        // Fall back to cached deviceMeta
      }

      if (!meta || !meta.deviceName || !meta.encryptionKey) {
        markSavedStatus('error');
        alert(`Cannot quick-save "${fileContext.path}" because device metadata is missing. Please use "Save Device As...".`);
        return false;
      }

      return handleSaveDeviceConfig(
        meta.deviceName,
        meta.friendlyName || meta.deviceName,
        meta.screenType || '2432s028',
        fileContext.path,
        meta.encryptionKey,
        meta.otaPassword,
        meta.ipAddress,
        true
      );
    }

    if (fileContext.kind === 'screen') {
      return handleSaveToHa(fileContext.path, true);
    }

    // Local YAML
    return handleDownloadYaml(fileContext.path);
  }, [fileContext, handleSaveDeviceConfig, handleSaveToHa, handleDownloadYaml, markSavedStatus]);

  const syncSavedSnapshot = useCallback((nextConfig: Config) => {
    setSavedSnapshot(getConfigSnapshot(nextConfig));
  }, []);

  return {
    fileInputRef,
    fileContext,
    isDirty,
    saveStatus,
    clearFileContext,
    syncSavedSnapshot,
    handleQuickSave,
    handleSaveYaml,
    handleDownloadYaml,
    handleSaveToHa,
    handleLoadProject,
    handleExport,
    handleLoadFromHa,
    handleSaveDeviceConfig,
    handleLoadDeviceConfig,
  };
}
