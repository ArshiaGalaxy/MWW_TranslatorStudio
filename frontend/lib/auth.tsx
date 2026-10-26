"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Me {
  authenticated: boolean;
  id?: number;
  username?: string;
  email?: string;
}

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({
  me: null,
  loading: true,
  refresh: async () => {},
  login: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/api/auth/me/"));
    } catch {
      setMe({ authenticated: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await api.get("/api/auth/csrf/");
      } catch {
        /* ignore */
      }
      await refresh();
    })();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      await api.post("/api/auth/login/", { username, password });
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout/");
    } finally {
      setMe({ authenticated: false });
    }
  }, []);

  return (
    <Ctx.Provider value={{ me, loading, refresh, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
