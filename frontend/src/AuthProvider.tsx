import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { API_ROOT } from "./config";
import { clearSession, readSession, writeSession } from "./session";
import type { Session, User } from "./types";

interface AuthValue {
  session: Session | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Session>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => readSession());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const current = readSession();
    if (!current?.access_token) { setLoading(false); return; }
    const controller = new AbortController();
    fetch(`${API_ROOT}/auth/session`, { headers: { Authorization: `Bearer ${current.access_token}` }, signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Phiên đăng nhập đã hết hạn.");
        const user = await response.json() as User;
        const restored = { ...current, user };
        writeSession(restored);
        setSession(restored);
      })
      .catch((error) => { if (error.name !== "AbortError") { clearSession(); setSession(null); } })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch(`${API_ROOT}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Không thể đăng nhập.");
    writeSession(data as Session);
    setSession(data as Session);
    return data as Session;
  }, []);

  const logout = useCallback(async () => {
    const token = session?.access_token;
    try {
      if (token) await fetch(`${API_ROOT}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    } finally {
      clearSession();
      setSession(null);
    }
  }, [session]);

  const value = useMemo(() => ({ session, loading, login, logout }), [session, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
