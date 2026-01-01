import { useState, useEffect, useCallback } from 'react';
import { apiFetch, isAddon } from '../utils/api';
import { HaEntity } from '../types';

export type HaStatus = 'connected' | 'error' | 'mock' | 'idle';
export type ConnectionType = 'local' | 'remote' | 'mock';

export function useHaConnection() {
  const [haUrl, setHaUrl] = useState(() => localStorage.getItem('ha_url') || 'http://homeassistant.local:8123');
  const [haToken, setHaToken] = useState(() => localStorage.getItem('ha_token') || '');
  const [connectionType, setConnectionType] = useState<ConnectionType>(() => {
    const savedType = localStorage.getItem('ha_connection_type') as ConnectionType;
    
    // If we are in an addon, default to local unless explicitly set to something else
    if (isAddon) {
      if (savedType === 'remote' || savedType === 'mock') return savedType;
      return 'local';
    }
    
    // If not an addon, default to remote or mock
    if (savedType) return savedType;
    if (localStorage.getItem('ha_use_mock') === 'true') return 'mock';
    return 'remote';
  });
  const [haEntities, setHaEntities] = useState<HaEntity[]>([]);
  const [haStatus, setHaStatus] = useState<HaStatus>('idle');
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    localStorage.setItem('ha_url', haUrl);
    localStorage.setItem('ha_token', haToken);
    localStorage.setItem('ha_connection_type', connectionType);
    localStorage.setItem('ha_use_mock', (connectionType === 'mock').toString());
  }, [haUrl, haToken, connectionType]);

  const fetchHaEntities = useCallback(async () => {
    setHaStatus('idle');
    setHaEntities([]);
    
    try {
      const headers: Record<string, string> = {};
      
      if (connectionType === 'mock') {
        headers['x-ha-mock'] = 'true';
      } else if (connectionType === 'remote') {
        headers['x-ha-url'] = haUrl;
        headers['x-ha-token'] = haToken;
      }

      const res = await apiFetch('/ha/states', { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const entities = data.map((s: any) => ({
            entity_id: s.entity_id,
            friendly_name: s.attributes?.friendly_name
          })).sort((a: HaEntity, b: HaEntity) => a.entity_id.localeCompare(b.entity_id));
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
  }, [fetchHaEntities, refreshTrigger]);

  return {
    haUrl,
    setHaUrl,
    haToken,
    setHaToken,
    connectionType,
    setConnectionType,
    haEntities,
    haStatus,
    fetchHaEntities: () => setRefreshTrigger(prev => prev + 1)
  };
}
