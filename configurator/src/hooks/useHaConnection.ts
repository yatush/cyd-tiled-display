import { useState, useEffect, useCallback } from 'react';
import { apiFetch, isAddon } from '../utils/api';

export type HaStatus = 'connected' | 'error' | 'mock' | 'idle';
export type ConnectionType = 'local' | 'remote' | 'mock';

export function useHaConnection() {
  const [haUrl, setHaUrl] = useState(() => localStorage.getItem('ha_url') || 'http://homeassistant.local:8123');
  const [haToken, setHaToken] = useState(() => localStorage.getItem('ha_token') || '');
  const [connectionType, setConnectionType] = useState<ConnectionType>(() => {
    if (localStorage.getItem('ha_use_mock') === 'true') return 'mock';
    if (isAddon && !localStorage.getItem('ha_url')) return 'local';
    return 'remote';
  });
  const [haEntities, setHaEntities] = useState<string[]>([]);
  const [haStatus, setHaStatus] = useState<HaStatus>('idle');

  useEffect(() => {
    localStorage.setItem('ha_url', connectionType === 'local' ? '' : haUrl);
    localStorage.setItem('ha_token', connectionType === 'local' ? '' : haToken);
    localStorage.setItem('ha_use_mock', (connectionType === 'mock').toString());
  }, [haUrl, haToken, connectionType]);

  const fetchHaEntities = useCallback(async () => {
    setHaStatus('idle');
    try {
      const headers: Record<string, string> = {};
      
      if (connectionType === 'mock') {
        headers['x-ha-mock'] = 'true';
      } else if (connectionType === 'remote') {
        headers['x-ha-url'] = haUrl;
        headers['x-ha-token'] = haToken;
      }
      // If 'local', we send no headers and server.py uses SUPERVISOR_TOKEN

      const res = await apiFetch('/ha/states', { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const entities = data.map((s: any) => s.entity_id).sort();
          setHaEntities(entities);
          setHaStatus(connectionType === 'mock' ? 'mock' : 'connected');
        } else {
          setHaStatus('error');
        }
      } else {
        setHaStatus('error');
      }
    } catch (err) {
      console.error("Failed to fetch HA entities", err);
      setHaStatus('error');
    }
  }, [haUrl, haToken, connectionType]);

  useEffect(() => {
    fetchHaEntities();
  }, [fetchHaEntities]);

  return {
    haUrl,
    setHaUrl,
    haToken,
    setHaToken,
    connectionType,
    setConnectionType,
    haEntities,
    haStatus,
    fetchHaEntities
  };
}
