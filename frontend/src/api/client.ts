import axios, { AxiosError } from "axios";

const TOKEN_KEY = "fitai.token";
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "";

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: session-only login */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export const api = axios.create({ baseURL: API_BASE, timeout: 20000 });

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/api/auth/")) onUnauthorized?.();
    return Promise.reject(error);
  },
);

/** Turns FastAPI error payloads (string detail or validation error list) into readable text. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".") || "input"}: ${d.msg}`)
        .join("; ");
    }
    if (!error.response) return "Cannot reach the FitAI server. Is the backend running?";
    return `Request failed (${error.response.status})`;
  }
  return error instanceof Error ? error.message : "Unexpected error";
}

export function liveSocketUrl(token: string): string {
  const base = API_BASE ? new URL(API_BASE) : new URL(window.location.href);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${base.host}/api/inference/live?token=${encodeURIComponent(token)}`;
}
