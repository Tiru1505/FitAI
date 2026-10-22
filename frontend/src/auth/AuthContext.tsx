import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, setUnauthorizedHandler, tokenStore } from "../api/client";

interface AuthState {
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  /** Creates a throwaway account with a starter profile and plan. */
  guest: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStore.get());
  const qc = useQueryClient();

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    qc.clear();
  }, [qc]);

  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const authenticate = useCallback(async (path: string, body?: { email: string; password: string }) => {
    const { data } = await api.post<{ access_token: string }>(path, body);
    qc.clear();
    tokenStore.set(data.access_token);
    setToken(data.access_token);
  }, [qc]);

  const value = useMemo<AuthState>(
    () => ({
      token,
      login: (e, p) => authenticate("/api/auth/login", { email: e, password: p }),
      register: (e, p) => authenticate("/api/auth/register", { email: e, password: p }),
      guest: () => authenticate("/api/auth/guest"),
      logout,
    }),
    [token, authenticate, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
