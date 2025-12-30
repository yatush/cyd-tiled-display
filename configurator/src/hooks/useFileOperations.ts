import React, { useRef, useCallback } from 'react';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';
import { parseYamlToConfig } from '../utils/yamlParser';
import { apiFetch, isAddon } from '../utils/api';

export function useFileOperations(config: Config, setConfig: (config: Config) => void, setActivePageId: (id: string) => void) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSaveToHa = useCallback(async () => {
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
        const data = await res.json();
        // Ensure we preserve the path in the loaded config
        setConfig({ ...data, project_path: targetPath });
        if (data.pages && data.pages.length > 0) {
          setActivePageId(data.pages[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to load from HA:', err);
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
    if (isAddon) {
      return handleSaveToHa();
    }
    return handleDownloadYaml();
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
            return;
        } catch (yamlErr) {
            try {
                const parsed = JSON.parse(content);
                if (parsed.pages && Array.isArray(parsed.pages)) {
                    setConfig(parsed);
                    setActivePageId(parsed.pages[0]?.id || 'main_page');
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

  return {
    fileInputRef,
    handleSaveYaml,
    handleDownloadYaml,
    handleSaveToHa,
    handleLoadProject,
    handleExport,
    handleLoadFromHa
  };
}
