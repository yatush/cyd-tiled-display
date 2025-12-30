export const isAddon = window.location.pathname.includes('/api/hassio_ingress/');
export const API_BASE = isAddon ? './api' : '/api';

export async function apiFetch(path: string, options: RequestInit = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : '/' + path}`;
  return fetch(url, options);
}
