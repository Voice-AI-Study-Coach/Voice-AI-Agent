"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch {
      // The cookie is HttpOnly, so a failed /me is the only way to learn the
      // session is gone.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* clearing local state matters more than the request succeeding */
    }
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Redirects to /login when a request comes back 401, so an expired cookie
 *  does not leave the user staring at a broken screen. */
export function useApiErrorHandler() {
  const router = useRouter();
  return useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push("/login");
        return "Your session expired. Please sign in again.";
      }
      return err instanceof Error ? err.message : "Something went wrong";
    },
    [router],
  );
}
