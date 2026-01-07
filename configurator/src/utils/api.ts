// Standard Mode: http://localhost:8099 (Addon features hidden)
// Addon Mode: http://localhost:8099/?mode=ha (Addon features visible, including the "Update HA Esphome files" button and status indicator)
const searchParams = new URLSearchParams(window.location.search);

// Check for injected env var from server
const envIsAddon = (window as any).__ENV__?.IS_ADDON;

export const isAddon = envIsAddon !== null && envIsAddon !== undefined 
  ? envIsAddon 
  : (window.location.pathname.includes('/api/hassio_ingress/') || searchParams.get('mode') === 'ha');

export const API_BASE = isAddon ? './api' : '/api';

// Generate a unique session ID for this browser tab
// Always generate a new ID to ensure duplicated tabs get separate sessions
const sessionId = Math.random().toString(36).substring(2, 15);

export const SESSION_ID = sessionId;

// Generate a new session ID (for emulator starts)
export function generateNewSessionId(): string {
  return Math.random().toString(36).substring(2, 15);
}

export async function apiFetch(path: string, options: RequestInit = {}, overrideSessionId?: string) {
  const url = `${API_BASE}${path.startsWith('/') ? path : '/' + path}`;
  
  // Create headers with session ID (use override if provided, otherwise use default)
  const headers = new Headers(options.headers || {});
  const sessionIdToUse = overrideSessionId || SESSION_ID;
  headers.set('X-Session-Id', sessionIdToUse);
  
  return fetch(url, { 
    ...options, 
    headers 
  });
}
