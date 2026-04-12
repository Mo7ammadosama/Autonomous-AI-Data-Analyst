import { create } from 'zustand';
import { authApi } from './api';

export interface User {
  id: string;
  email: string;
  username: string;
  role: 'viewer' | 'analyst' | 'admin' | 'superadmin';
  workspace_id: string | null;
  is_superadmin: boolean;
}

export type ThemeAccent = 'indigo' | 'violet' | 'emerald' | 'cyan' | 'rose' | 'amber';
export type ColorMode = 'dark' | 'light';

interface AuthStore {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  theme: ThemeAccent;
  colorMode: ColorMode;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  updateProfile: (data: { username?: string; email?: string }) => Promise<void>;
  logout: () => void;
  initialize: () => void;
  setTheme: (theme: ThemeAccent) => void;
  setColorMode: (mode: ColorMode) => void;
}

function _readStoredTheme(): ThemeAccent {
  if (typeof window === 'undefined') return 'indigo';
  const t = localStorage.getItem('theme') as ThemeAccent;
  return (['indigo','violet','emerald','cyan','rose','amber'] as ThemeAccent[]).includes(t) ? t : 'indigo';
}

function _readStoredColorMode(): ColorMode {
  if (typeof window === 'undefined') return 'dark';
  const m = localStorage.getItem('color_mode') as ColorMode;
  return m === 'light' ? 'light' : 'dark';
}

// Read auth state synchronously at module load time (before first render)
function _readStoredAuth(): { user: User | null; token: string | null; isAuthenticated: boolean } {
  if (typeof window === 'undefined') return { user: null, token: null, isAuthenticated: false };
  try {
    const token = localStorage.getItem('auth_token');
    const userStr = localStorage.getItem('auth_user');
    if (token && userStr) {
      const user = JSON.parse(userStr) as User;
      return { user, token, isAuthenticated: true };
    }
  } catch {}
  return { user: null, token: null, isAuthenticated: false };
}

const _initial = _readStoredAuth();

export const useAuthStore = create<AuthStore>((set) => ({
  user: _initial.user,
  token: _initial.token,
  isLoading: false,
  isAuthenticated: _initial.isAuthenticated,
  theme: _readStoredTheme(),
  colorMode: _readStoredColorMode(),

  setTheme: (theme: ThemeAccent) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('theme', theme);
      document.documentElement.setAttribute('data-theme', theme);
    }
    set({ theme });
  },

  setColorMode: (mode: ColorMode) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('color_mode', mode);
      if (mode === 'light') {
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
      } else {
        document.documentElement.classList.remove('light');
        document.documentElement.classList.add('dark');
      }
    }
    set({ colorMode: mode });
  },

  // No-op — state already initialized at module load; kept for compatibility
  initialize: () => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token');
      const userStr = localStorage.getItem('auth_user');
      if (token && userStr) {
        try {
          const user = JSON.parse(userStr);
          set({ user, token, isAuthenticated: true });
        } catch {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('auth_user');
        }
      }
    }
  },

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const resp = await authApi.login(email, password);
      const { access_token, refresh_token, user } = resp.data;
      localStorage.setItem('auth_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, token: access_token, isAuthenticated: true, isLoading: false });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  register: async (email, username, password) => {
    set({ isLoading: true });
    try {
      const resp = await authApi.register(email, username, password);
      const { access_token, refresh_token, user } = resp.data;
      localStorage.setItem('auth_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, token: access_token, isAuthenticated: true, isLoading: false });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  demoLogin: async () => {
    set({ isLoading: true });
    try {
      const resp = await authApi.demoLogin();
      const { access_token, refresh_token, user } = resp.data;
      localStorage.setItem('auth_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, token: access_token, isAuthenticated: true, isLoading: false });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  updateProfile: async (data) => {
    const resp = await authApi.updateMe(data);
    const updatedUser = resp.data;
    localStorage.setItem('auth_user', JSON.stringify(updatedUser));
    set({ user: updatedUser });
  },

  logout: () => {
    const refreshToken = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null;
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => {}); // best-effort server-side revocation
    }
    localStorage.removeItem('auth_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('auth_user');
    set({ user: null, token: null, isAuthenticated: false });
  },
}));
