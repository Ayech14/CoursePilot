import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  api,
  onSessionExpired,
  refreshSession,
  setAccessToken,
  type AuthResponse,
  type User,
} from "../../lib/api";

export interface RegisterInput {
  email: string;
  password: string;
  display_name: string;
  timezone: string;
}

interface AuthContextValue {
  status: "loading" | "authenticated" | "anonymous";
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [user, setUserState] = useState<User | null>(null);

  const queryClient = useQueryClient();

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUserState(null);
    setStatus("anonymous");
    // Cached data must not be visible to the next person who signs in on this browser.
    queryClient.clear();
  }, [queryClient]);

  const acceptSession = useCallback((session: AuthResponse) => {
    setAccessToken(session.access_token);
    setUserState(session.user);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    onSessionExpired(clearSession);
    // After a page load the access token is gone; the HttpOnly cookie can restore the session.
    refreshSession()
      .then((session) => (session ? acceptSession(session) : clearSession()))
      .catch(clearSession);
    return () => onSessionExpired(null);
  }, [acceptSession, clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login: async (email, password) => {
        acceptSession(await api<AuthResponse>("/auth/login", "POST", { email, password }));
      },
      register: async (input) => {
        acceptSession(await api<AuthResponse>("/auth/register", "POST", input));
      },
      logout: async () => {
        try {
          await api<void>("/auth/logout", "POST");
        } finally {
          clearSession();
        }
      },
      setUser: setUserState,
    }),
    [status, user, acceptSession, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
