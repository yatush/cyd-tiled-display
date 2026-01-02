import React, { useRef, useCallback } from 'react';
import { dump } from 'js-yaml';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';
import { parseYamlToConfig, convertParsedYamlToConfig } from '../utils/yamlParser';
import { apiFetch, isAddon } from '../utils/api';

export function useFileOperations(config: Config, setConfig: (config: Config) => void, setActivePageId: (id: string) => void, onSaveSuccess?: () => void, onLoadSuccess?: () => void) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSaveToHa = useCallback(async () => {
    if (!isAddon) {
      alert('Saving is disabled when not running in HA');
      return;
    }
    try {
      const path = config.project_path || 'monitor_config/tiles.yaml';
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
        alert(`Successfully saved to /config/esphome/${data.path}`);
        if (onSaveSuccess) onSaveSuccess();
      } else {
        const err = await res.json();
        alert(`Failed to save: ${err.error}`);
      }
    } catch (err) {
      console.error('Failed to save to HA:', err);
      alert('Failed to save to Home Assistant. Check console for details.');
    }
  }, [config]);

  const handleLoadFromHa = useCallback(async (path?: string) => {
    try {
      const targetPath = path || config.project_path || 'monitor_config/tiles.yaml';
      const res = await apiFetch(`/load?path=${encodeURIComponent(targetPath)}`);
      if (res.ok) {
        let data = await res.json();
        
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

        // Ensure we preserve the path in the loaded config
        setConfig({ ...data, project_path: targetPath });
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
  }, [config.project_path, setConfig, setActivePageId]);

  const handleDownloadYaml = async () => {
    const yamlString = generateYaml(config);
    
    try {
      // @ts-ignore - File System Access API
      if (window.showSaveFilePicker) {
        // @ts-ignore
        const handle = await window.showSaveFilePicker({
          suggestedName: 'monitor_tiles.yaml',
          types: [{
            description: 'YAML File',
            accept: {'text/yaml': ['.yaml', '.yml']},
          }],
        });
        const writable = await handle.createWritable();
        await writable.write(yamlString);
        await writable.close();
      } else {
        const dataStr = "data:text/yaml;charset=utf-8," + encodeURIComponent(yamlString);
        const downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", "monitor_tiles.yaml");
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
      }
    } catch (err) {
      console.error('Failed to save file:', err);
    }
  };

  const handleSaveYaml = async () => {
    return handleSaveToHa();
  };

  const handleLoadProject = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        
        try {
            const parsedConfig = parseYamlToConfig(content);
            setConfig(parsedConfig);
            setActivePageId(parsedConfig.pages[0]?.id || 'main_page');
            if (onLoadSuccess) onLoadSuccess();
            return;
        } catch (yamlErr) {
            try {
                const parsed = JSON.parse(content);
                if (parsed.pages && Array.isArray(parsed.pages)) {
                    setConfig(parsed);
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
  };

  const handleExport = () => {
    const yamlString = generateYaml(config);
    navigator.clipboard.writeText(yamlString).then(() => {
      alert("YAML configuration copied to clipboard!");
    }).catch(err => {
      console.error('Failed to copy: ', err);
      alert("Failed to copy to clipboard. Check console for output.");
    });
  };

  const handleSaveDeviceConfig = useCallback(async (deviceName: string, friendlyName: string, screenType: string, fileName: string, encryptionKey: string) => {
    if (!isAddon) {
      alert('Saving is disabled when not running in HA');
      return;
    }
    try {
      let wifiSection = '';
      try {
          const loadRes = await apiFetch(`/load?path=${encodeURIComponent(fileName)}`);
          if (loadRes.ok) {
              const data = await loadRes.json();
              if (data.wifi) {
                  wifiSection = dump({ wifi: data.wifi });
              }
          }
      } catch (e) {
          // ignore
      }

      const screensYaml = generateYaml(config);
      
      const fullYaml = `substitutions:
  device_name: "${deviceName}"
  friendly_name: ${friendlyName}

packages:
  device_base: !include lib/${screenType}_base.yaml
  lib: !include lib/lib.yaml

esphome:
  name: $device_name
  friendly_name: $friendly_name

api:
  encryption:
    key: "${encryptionKey}"

${wifiSection}
tile_ui:
${screensYaml.split('\\n').map(line => '  ' + line).join('\\n')}
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
        alert(`Successfully saved device configuration to /config/esphome/${fileName}`);
        if (onSaveSuccess) onSaveSuccess();
      } else {
        const err = await res.json();
        alert(`Failed to save: ${err.error}`);
      }
    } catch (err) {
      console.error('Failed to save device config:', err);
      alert('Failed to save device configuration. Check console for details.');
    }
  }, [config]);

  const handleLoadDeviceConfig = useCallback(async (path: string) => {
    try {
      const res = await apiFetch(`/load?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        
        // Check if it's a full device config (has tile_ui key)
        if (data.tile_ui) {
            // Handle both 'pages' (internal) and 'screens' (YAML) keys
            const pagesData = data.tile_ui.pages || data.tile_ui.screens;
            
            if (!pagesData || !Array.isArray(pagesData)) {
                 alert('Failed to load: The device configuration is missing valid tile_ui screens/pages.');
                 return;
            }
            
            // If the data is in 'screens' format (from YAML), we might need to parse it
            // But setConfig expects the internal format. 
            // If the loaded JSON already matches the internal structure, we can use it directly.
            // However, 'screens' usually implies the YAML structure where tiles are wrapped in their type key.
            
            let configToSet = data.tile_ui;
            
            // If we have 'screens', we likely need to normalize it to 'pages' and flatten tiles
            if (data.tile_ui.screens) {
                // We can use the existing parser logic if we convert the tile_ui object to a YAML string and back,
                // OR we can just map it manually here.
                // Let's try to use the parser if possible, or replicate its logic.
                // Actually, since we have the object, let's just map it.
                
                const pages = data.tile_ui.screens.map((screen: any) => {
                    const tiles = (screen.tiles || []).map((tileItem: any) => {
                        // Check if tile is already in internal format (has type property)
                        if (tileItem.type) return tileItem;
                        
                        // Otherwise assume YAML format: { type: { ...props } }
                        const type = Object.keys(tileItem)[0];
                        const props = tileItem[type];
                        return {
                            id: Math.random().toString(36).substr(2, 9),
                            type,
                            ...props
                        };
                    });
                    
                    return {
                        ...screen,
                        tiles
                    };
                });
                
                configToSet = { ...data.tile_ui, pages };
                delete configToSet.screens;
            }

            setConfig(configToSet);
            if (configToSet.pages.length > 0) {
                setActivePageId(configToSet.pages[0].id);
            }
            alert(`Successfully loaded device configuration from ${path}`);
        } else {
            // Fallback: try to load as a screens config
             if (!data || typeof data !== 'object' || !Array.isArray(data.pages)) {
                alert('Failed to load: The file does not appear to be a valid device or tile configuration.');
                return;
            }
            setConfig(data);
            if (data.pages && data.pages.length > 0) {
                setActivePageId(data.pages[0].id);
            }
            alert(`Successfully loaded configuration from ${path}`);
        }
      } else {
        const err = await res.json();
        alert(`Failed to load: ${err.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to load device config:', err);
      alert('Failed to load device configuration. Check console for details.');
    }
  }, [setConfig, setActivePageId]);

  return {
    fileInputRef,
    handleSaveYaml,
    handleDownloadYaml,
    handleSaveToHa,
    handleLoadProject,
    handleExport,
    handleLoadFromHa,
    handleSaveDeviceConfig,
    handleLoadDeviceConfig
  };
}
