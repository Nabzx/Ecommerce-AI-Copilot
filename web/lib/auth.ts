'use client';

import { API_BASE } from '@/lib/api';

const KEY = 'storesense-token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(KEY);
}

export function setToken(token: string) {
  localStorage.setItem(KEY, token);
}

export function clearToken() {
  localStorage.removeItem(KEY);
}

/**
 * The header every request carries.
 *
 * Returns an empty object when there's no token, so callers can spread it
 * unconditionally rather than branching at each call site.
 */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface Health {
  status: string;
  store: string;
  auth_required: boolean;
  model_available: boolean;
  model: string;
}

export async function getHealth(): Promise<Health> {
  const response = await fetch(`${API_BASE}/health`, { cache: 'no-store' });
  if (!response.ok) throw new Error('The API is not responding.');
  return response.json();
}

export async function login(password: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });

  if (response.status === 429) {
    throw new Error('Too many attempts. Wait a minute and try again.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? 'Could not sign in.');
  }

  const { token } = await response.json();
  setToken(token);
  return token;
}
