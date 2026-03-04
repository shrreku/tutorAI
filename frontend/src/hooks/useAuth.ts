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
}

interface LoginPayload {
  email: string;
  password: string;
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
    logout,
  };
}
