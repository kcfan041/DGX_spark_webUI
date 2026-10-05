import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "@/api/client";
import type { Me } from "@/api/types";

interface AuthState {
  authenticated: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean>(() => Boolean(getToken()));

  const logout = useCallback(() => {
    setToken(null);
    setAuthenticated(false);
  }, []);

  const login = useCallback(async (token: string) => {
    await api<Me>("/auth/login", { method: "POST", body: JSON.stringify({ token }) });
    setToken(token);
    setAuthenticated(true);
  }, []);

  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const value = useMemo(() => ({ authenticated, login, logout }), [authenticated, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
