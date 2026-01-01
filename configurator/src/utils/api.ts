// Standard Mode: http://localhost:8099 (Addon features hidden)
// Addon Mode: http://localhost:8099/?mode=ha (Addon features visible, including the "Update HA Esphome files" button and status indicator)
const searchParams = new URLSearchParams(window.location.search);

// Check for injected env var from server
const envIsAddon = (window as any).__ENV__?.IS_ADDON;

export const isAddon = envIsAddon !== null && envIsAddon !== undefined 
  ? envIsAddon 
  : (window.location.pathname.includes('/api/hassio_ingress/') || searchParams.get('mode') === 'ha');

export const API_BASE = isAddon ? './api' : '/api';

export async function apiFetch(path: string, options: RequestInit = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : '/' + path}`;
  return fetch(url, options);
}
