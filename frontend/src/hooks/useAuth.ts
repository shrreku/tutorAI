import { useState, useEffect, useCallback } from 'react';
import {
  type AuthUser,
  getToken,
  getUser,
  persistAuth,
  clearAuth,
} from '../stores/authStore';
import { apiClient } from '../api/client';

// ---------------------------------------------------------------------------
// Auth API types (mirror backend schemas)
// ---------------------------------------------------------------------------

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

interface RegisterPayload {
  email: string;
  password: string;
  display_name: string;
  consent_training: boolean;
  consent_personalization: boolean;
  invite_token?: string;
  access_code?: string;
  promo_code?: string;
}

interface LoginPayload {
  email: string;
  password: string;
}

interface RequestAccessPayload {
  email: string;
  display_name: string;
  promo_code?: string;
}

interface UserSettingsResponse {
  is_admin: boolean;
}

interface AuthConfigResponse {
  alpha_access_enabled: boolean;
  app_base_url: string;
}

interface RequestAccessResponse {
  status: 'submitted' | 'approved';
  message: string;
}

// ---------------------------------------------------------------------------
// Raw API calls (no auth header needed — these are public)
// ---------------------------------------------------------------------------

async function apiRegister(payload: RegisterPayload): Promise<AuthResponse> {
  return apiClient.postPublic<AuthResponse>('/auth/register', payload);
}

async function apiLogin(payload: LoginPayload): Promise<AuthResponse> {
  return apiClient.postPublic<AuthResponse>('/auth/login', payload);
}

async function apiRequestAccess(payload: RequestAccessPayload): Promise<RequestAccessResponse> {
  return apiClient.postPublic<RequestAccessResponse>('/auth/request-access', payload);
}

export async function apiGetAuthConfig(): Promise<AuthConfigResponse> {
  return apiClient.get<AuthConfigResponse>('/auth/config');
}

async function apiGetUserSettings(): Promise<UserSettingsResponse> {
  return apiClient.get<UserSettingsResponse>('/users/me/settings');
}

// ---------------------------------------------------------------------------
// React hook
// ---------------------------------------------------------------------------

export function useAuth() {
  const [token, setToken] = useState<string | null>(getToken);
  const [user, setUser] = useState<AuthUser | null>(getUser);

  // Listen for cross-component auth changes
  useEffect(() => {
    const sync = () => {
      setToken(getToken());
      setUser(getUser());
    };
    window.addEventListener('auth-change', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('auth-change', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;

    void apiGetUserSettings()
      .then((settings) => {
        if (cancelled) {
          return;
        }

        setUser((current) => {
          if (!current || current.is_admin === settings.is_admin) {
            return current;
          }
          const nextUser = { ...current, is_admin: settings.is_admin };
          persistAuth(token, nextUser);
          return nextUser;
        });
      })
      .catch(() => {
        // Ignore background refresh failures; auth state will still follow login/logout flows.
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const register = useCallback(async (payload: RegisterPayload) => {
    const data = await apiRegister(payload);
    persistAuth(data.access_token, data.user);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const data = await apiLogin(payload);
    persistAuth(data.access_token, data.user);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
  }, []);

  return {
    token,
    user,
    isAuthenticated: !!token,
    register,
    login,
    requestAccess: apiRequestAccess,
    logout,
  };
}
