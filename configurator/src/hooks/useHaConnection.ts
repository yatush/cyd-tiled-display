import { useState, useEffect, useCallback } from 'react';
import { apiFetch, isAddon } from '../utils/api';

export type HaStatus = 'connected' | 'error' | 'mock' | 'idle';

export function useHaConnection() {
  const [haUrl, setHaUrl] = useState(() => localStorage.getItem('ha_url') || 'http://homeassistant.local:8123');
  const [haToken, setHaToken] = useState(() => localStorage.getItem('ha_token') || '');
  const [useMockData, setUseMockData] = useState(() => localStorage.getItem('ha_use_mock') === 'true');
  const [haEntities, setHaEntities] = useState<string[]>([]);
  const [haStatus, setHaStatus] = useState<HaStatus>('idle');

  useEffect(() => {
    localStorage.setItem('ha_url', haUrl);
    localStorage.setItem('ha_token', haToken);
    localStorage.setItem('ha_use_mock', useMockData.toString());
  }, [haUrl, haToken, useMockData]);

  const fetchHaEntities = useCallback(async () => {
    setHaStatus('idle');
    try {
      const headers: Record<string, string> = isAddon ? {} : {
        'x-ha-url': haUrl,
        'x-ha-token': haToken,
        'x-ha-mock': useMockData.toString()
      };

      const res = await apiFetch('/ha/states', { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const entities = data.map((s: any) => s.entity_id).sort();
          setHaEntities(entities);
          setHaStatus(isAddon ? 'connected' : (useMockData ? 'mock' : 'connected'));
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
  }, [haUrl, haToken, useMockData]);

  useEffect(() => {
    fetchHaEntities();
  }, [fetchHaEntities]);

  useEffect(() => {
    const timer = setTimeout(() => {
        fetchHaEntities();
    }, 1000);
    return () => clearTimeout(timer);
  }, [haUrl, haToken, useMockData, fetchHaEntities]);

  return {
    haUrl,
    setHaUrl,
    haToken,
    setHaToken,
    useMockData,
    setUseMockData,
    haEntities,
    haStatus,
    fetchHaEntities
  };
}
