'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Settings, Key, User, Shield, Bell, Database, Save, Eye, EyeOff,
  Activity, CheckCircle2, XCircle, Zap, Brain, TrendingUp, BarChart2,
  Cpu, GitCompare, Wand2, Palette
} from 'lucide-react';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { useAuthStore, ThemeAccent } from '@/lib/store';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import api, { authExtApi, apiKeysApi } from '@/lib/api';

const NOTIF_KEY = 'datamind_notifications';

const TABS = [
  { id: 'profile',      label: 'Profile',          icon: User     },
  { id: 'appearance',   label: 'Appearance',        icon: Palette  },
  { id: 'security',     label: 'Security',          icon: Key      },
  { id: 'apikeys',      label: 'API Keys',          icon: Key      },
  { id: 'ai',           label: 'AI Configuration', icon: Shield   },
  { id: 'platform',     label: 'Platform Status',  icon: Activity },
  { id: 'notifications',label: 'Notifications',    icon: Bell     },
];

const THEMES: { id: ThemeAccent; label: string; color: string; glow: string }[] = [
  { id: 'indigo',  label: 'Indigo',  color: '#6366f1', glow: 'rgba(99,102,241,0.4)'  },
  { id: 'violet',  label: 'Violet',  color: '#8b5cf6', glow: 'rgba(139,92,246,0.4)'  },
  { id: 'emerald', label: 'Emerald', color: '#10b981', glow: 'rgba(16,185,129,0.4)'  },
  { id: 'cyan',    label: 'Cyan',    color: '#06b6d4', glow: 'rgba(6,182,212,0.4)'   },
  { id: 'rose',    label: 'Rose',    color: '#f43f5e', glow: 'rgba(244,63,94,0.4)'   },
  { id: 'amber',   label: 'Amber',   color: '#f59e0b', glow: 'rgba(245,158,11,0.4)'  },
];

interface PlatformStatus {
  health: 'ok' | 'error';
  version: string;
  totalRoutes: number;
  features: { name: string; icon: any; color: string; status: 'live' }[];
}

const DEFAULT_NOTIFS = [
  { id: 'analysis_complete', label: 'Analysis Complete', desc: 'Get notified when analysis finishes', enabled: true },
  { id: 'new_insights', label: 'New Insights', desc: 'Alerts for newly detected insights', enabled: true },
  { id: 'dataset_errors', label: 'Dataset Errors', desc: 'Notifications for processing errors', enabled: false },
];

export default function SettingsPage() {
  const { user, updateProfile, theme, setTheme } = useAuthStore();
  const [tab, setTab] = useState('profile');
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [platform, setPlatform] = useState<PlatformStatus | null>(null);
  const [platformLoading, setPlatformLoading] = useState(false);
  const [notifs, setNotifs] = useState(DEFAULT_NOTIFS);
  const [form, setForm] = useState({
    username: user?.username || '',
    email: user?.email || '',
    openaiKey: '',
    useOllama: false,
    ollamaModel: 'llama3',
  });
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' });
  const [pwSaving, setPwSaving] = useState(false);
  const [apiKeys, setApiKeys] = useState<{ id: string; name: string; key_prefix: string; scopes: string[]; is_active: boolean; last_used_at: string | null; expires_at: string | null; created_at: string }[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyResult, setNewKeyResult] = useState<{ key: string; name: string } | null>(null);

  const loadApiKeys = async () => {
    setApiKeysLoading(true);
    try {
      const res = await apiKeysApi.list();
      setApiKeys(res.data);
    } catch (e) { console.error(e); }
    finally { setApiKeysLoading(false); }
  };

  const createApiKey = async () => {
    if (!newKeyName) return;
    try {
      const res = await apiKeysApi.create({ name: newKeyName });
      setNewKeyResult({ key: res.data.key, name: res.data.name });
      setNewKeyName('');
      loadApiKeys();
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to create key');
    }
  };

  const revokeApiKey = async (id: string) => {
    if (!confirm('Revoke this API key? This cannot be undone.')) return;
    await apiKeysApi.revoke(id);
    loadApiKeys();
  };

  // Load saved notification prefs
  useEffect(() => {
    try {
      const stored = localStorage.getItem(NOTIF_KEY);
      if (stored) setNotifs(JSON.parse(stored));
    } catch {}
  }, []);

  useEffect(() => {
    if (tab === 'platform') loadPlatform();
    if (tab === 'apikeys') loadApiKeys();
  }, [tab]);

  const loadPlatform = async () => {
    setPlatformLoading(true);
    try {
      const [healthRes, openapiRes] = await Promise.all([
        api.get('/health'),
        api.get('/openapi.json'),
      ]);
      const paths = Object.keys(openapiRes.data.paths || {});
      setPlatform({
        health: 'ok',
        version: openapiRes.data.info?.version || '1.0.0',
        totalRoutes: paths.length,
        features: [
          { name: 'AI Copilot',           icon: Brain,       color: 'text-indigo-400',  status: 'live' },
          { name: 'Auto Pipeline',         icon: Zap,         color: 'text-amber-400',   status: 'live' },
          { name: 'Forecasting',           icon: TrendingUp,  color: 'text-emerald-400', status: 'live' },
          { name: 'Anomaly Detection',     icon: Shield,      color: 'text-red-400',     status: 'live' },
          { name: 'NL Data Queries',       icon: BarChart2,   color: 'text-violet-400',  status: 'live' },
          { name: 'Recommendation Engine', icon: Activity,    color: 'text-cyan-400',    status: 'live' },
          { name: 'Autonomous Analyst',    icon: Cpu,         color: 'text-violet-400',  status: 'live' },
          { name: 'Dataset Cleaning UI',   icon: Wand2,       color: 'text-pink-400',    status: 'live' },
          { name: 'Multi-Dataset Compare', icon: GitCompare,  color: 'text-cyan-400',    status: 'live' },
        ],
      });
    } catch {
      setPlatform({ health: 'error', version: '–', totalRoutes: 0, features: [] });
    } finally {
      setPlatformLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save notification prefs to localStorage
      localStorage.setItem(NOTIF_KEY, JSON.stringify(notifs));

      // If on profile tab, persist to backend
      if (tab === 'profile') {
        await updateProfile({ username: form.username, email: form.email });
      }

      setSaved(true);
      toast.success('Settings saved');
      setTimeout(() => setSaved(false), 2500);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to save settings';
      toast.error('Save failed', { description: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-5 max-w-4xl">
        <PageHeader
          title="Settings"
          subtitle="Configure your workspace and AI preferences"
          icon={<Settings className="w-5 h-5 text-slate-400" />}
        />

        <div className="flex gap-1 p-1 glass rounded-xl border border-white/5 w-fit">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                tab === t.id ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
              )}
            >
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        <div className="glass rounded-xl border border-white/5 p-6">
          {tab === 'profile' && (
            <div className="space-y-5">
              <h3 className="text-base font-display font-bold text-white">Profile Information</h3>
              <div className="flex items-center gap-4 p-4 bg-white/3 rounded-xl border border-white/5">
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xl font-bold">
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </div>
                <div>
                  <div className="text-white font-semibold">{user?.username}</div>
                  <div className="text-sm text-slate-500">{user?.email}</div>
                  <div className="text-xs text-indigo-400 mt-0.5 capitalize">{user?.role}</div>
                </div>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Username</label>
                  <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
                  <input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white" />
                </div>
              </div>
            </div>
          )}

          {tab === 'security' && (
            <div className="space-y-5">
              <h3 className="text-base font-display font-bold text-white">Change Password</h3>
              <div className="space-y-4 max-w-sm">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Current Password</label>
                  <input
                    type="password"
                    value={pwForm.current}
                    onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
                    placeholder="Current password"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">New Password</label>
                  <input
                    type="password"
                    value={pwForm.newPw}
                    onChange={e => setPwForm(f => ({ ...f, newPw: e.target.value }))}
                    placeholder="At least 8 characters"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Confirm New Password</label>
                  <input
                    type="password"
                    value={pwForm.confirm}
                    onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))}
                    placeholder="Repeat new password"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600"
                  />
                </div>
                <button
                  disabled={pwSaving || !pwForm.current || !pwForm.newPw}
                  onClick={async () => {
                    if (pwForm.newPw !== pwForm.confirm) { toast.error('Passwords do not match'); return; }
                    if (pwForm.newPw.length < 8) { toast.error('Password must be at least 8 characters'); return; }
                    setPwSaving(true);
                    try {
                      await authExtApi.changePassword(pwForm.current, pwForm.newPw);
                      toast.success('Password changed successfully');
                      setPwForm({ current: '', newPw: '', confirm: '' });
                    } catch (e: any) {
                      toast.error(e?.response?.data?.detail || 'Failed to change password');
                    } finally { setPwSaving(false); }
                  }}
                  className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {pwSaving ? 'Updating...' : 'Update Password'}
                </button>
              </div>
            </div>
          )}

          {tab === 'apikeys' && (
            <div className="space-y-5">
              <h3 className="text-base font-display font-bold text-white">API Keys</h3>
              <p className="text-xs text-slate-500">Create API keys for programmatic access. Keys are shown once — store them securely.</p>

              {/* Create key */}
              <div className="flex gap-3">
                <input
                  className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600"
                  placeholder="Key name (e.g. CI/CD pipeline)"
                  value={newKeyName}
                  onChange={e => setNewKeyName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') createApiKey(); }}
                />
                <button onClick={createApiKey} disabled={!newKeyName} className="btn-primary text-sm px-4 disabled:opacity-50">
                  Create Key
                </button>
              </div>

              {/* New key reveal */}
              {newKeyResult && (
                <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl space-y-2">
                  <p className="text-xs font-semibold text-emerald-400">Key created: {newKeyResult.name}</p>
                  <code className="block text-xs font-mono text-emerald-300 bg-black/30 px-3 py-2 rounded-lg break-all">{newKeyResult.key}</code>
                  <p className="text-xs text-emerald-600">Copy this key now. It will not be shown again.</p>
                  <button onClick={() => setNewKeyResult(null)} className="text-xs text-slate-500 hover:text-slate-300">Dismiss</button>
                </div>
              )}

              {/* Keys list */}
              {apiKeysLoading ? (
                <div className="space-y-2">{[1,2].map(i => <div key={i} className="h-12 bg-white/5 rounded-xl animate-pulse" />)}</div>
              ) : apiKeys.length === 0 ? (
                <p className="text-sm text-slate-500 py-6 text-center">No API keys yet.</p>
              ) : (
                <div className="space-y-2">
                  {apiKeys.map(k => (
                    <div key={k.id} className="flex items-center gap-4 p-3 bg-white/3 rounded-xl border border-white/5">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-200">{k.name}</span>
                          <span className={cn('text-xs px-2 py-0.5 rounded-full', k.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-500/10 text-slate-500')}>
                            {k.is_active ? 'active' : 'inactive'}
                          </span>
                        </div>
                        <p className="text-xs font-mono text-slate-500 mt-0.5">{k.key_prefix}••••••••</p>
                      </div>
                      {k.last_used_at && (
                        <span className="text-xs text-slate-600 flex-shrink-0">
                          Used {new Date(k.last_used_at).toLocaleDateString()}
                        </span>
                      )}
                      <button onClick={() => revokeApiKey(k.id)} className="text-slate-600 hover:text-red-400 transition-colors flex-shrink-0">
                        <XCircle className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'ai' && (
            <div className="space-y-5">
              <h3 className="text-base font-display font-bold text-white">AI Configuration</h3>
              <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-xl">
                <p className="text-sm text-amber-300/80">Configure your AI backend. OpenAI provides cloud inference; Ollama enables local models. The platform works without either (rule-based fallback).</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5 flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5" /> OpenAI API Key
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={form.openaiKey}
                    onChange={e => setForm(f => ({ ...f, openaiKey: e.target.value }))}
                    placeholder="sk-..."
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 pr-10"
                  />
                  <button onClick={() => setShowKey(!showKey)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-slate-600 mt-1">Add your OpenAI API key to the backend .env file for production use</p>
              </div>

              <div className="flex items-center justify-between p-4 bg-white/3 rounded-xl border border-white/5">
                <div>
                  <div className="text-sm font-medium text-white">Use Local Ollama</div>
                  <div className="text-xs text-slate-500 mt-0.5">Run LLM locally via Ollama (requires Ollama installed)</div>
                </div>
                <button
                  onClick={() => setForm(f => ({ ...f, useOllama: !f.useOllama }))}
                  className={cn('w-11 h-6 rounded-full transition-colors relative', form.useOllama ? 'bg-indigo-600' : 'bg-white/10')}
                >
                  <div className={cn('w-4 h-4 rounded-full bg-white absolute top-1 transition-all', form.useOllama ? 'left-6' : 'left-1')} />
                </button>
              </div>

              {form.useOllama && (
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Ollama Model</label>
                  <select value={form.ollamaModel} onChange={e => setForm(f => ({ ...f, ollamaModel: e.target.value }))} className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white">
                    <option value="llama3">llama3</option>
                    <option value="llama3.1">llama3.1</option>
                    <option value="mistral">mistral</option>
                    <option value="codellama">codellama</option>
                  </select>
                </div>
              )}
            </div>
          )}

          {tab === 'platform' && (
            <div className="space-y-5">
              <h3 className="text-base font-display font-bold text-white">Platform Status</h3>

              {platformLoading ? (
                <div className="flex items-center gap-2 text-slate-500 text-sm py-8 justify-center">
                  <div className="w-4 h-4 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                  Checking platform status...
                </div>
              ) : platform ? (
                <>
                  {/* Status cards */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="glass rounded-xl p-4 border border-white/5 text-center">
                      <div className="flex items-center justify-center gap-1.5 mb-1">
                        {platform.health === 'ok'
                          ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          : <XCircle className="w-4 h-4 text-red-400" />
                        }
                        <span className={`text-xs font-bold ${platform.health === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                          {platform.health === 'ok' ? 'ONLINE' : 'OFFLINE'}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500">Backend API</div>
                    </div>
                    <div className="glass rounded-xl p-4 border border-white/5 text-center">
                      <div className="text-lg font-bold text-white mb-0.5">{platform.totalRoutes}</div>
                      <div className="text-xs text-slate-500">API Routes</div>
                    </div>
                    <div className="glass rounded-xl p-4 border border-white/5 text-center">
                      <div className="text-lg font-bold text-indigo-400 mb-0.5">v{platform.version}</div>
                      <div className="text-xs text-slate-500">API Version</div>
                    </div>
                  </div>

                  {/* Feature matrix */}
                  <div className="glass rounded-xl border border-white/5 overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5">
                      <span className="text-sm font-semibold text-white">Feature Availability</span>
                    </div>
                    <div className="divide-y divide-white/5">
                      {platform.features.map((f, i) => (
                        <div key={i} className="flex items-center justify-between px-5 py-3">
                          <div className="flex items-center gap-3">
                            <f.icon className={`w-4 h-4 ${f.color}`} />
                            <span className="text-sm text-slate-300">{f.name}</span>
                          </div>
                          <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> LIVE
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Stack info */}
                  <div className="glass rounded-xl border border-white/5 p-4 space-y-2">
                    <div className="text-xs font-semibold text-slate-400 mb-3">Technology Stack</div>
                    {[
                      { label: 'Backend',    value: 'FastAPI + SQLAlchemy + SQLite · 51 routes' },
                      { label: 'Frontend',   value: 'Next.js 14 + TypeScript + Tailwind · 11 pages' },
                      { label: 'AI Engine',  value: 'pandas + scikit-learn + statsmodels + Plotly' },
                      { label: 'Auth',       value: 'JWT (python-jose) + bcrypt 4.0.1 + PATCH /me' },
                      { label: 'ML Models',  value: 'ARIMA, Exp. Smoothing, IsolationForest, K-Means' },
                      { label: 'Autonomous', value: '9-stage pipeline: profile→forecast→insights→story→dashboard' },
                    ].map(s => (
                      <div key={s.label} className="flex items-center gap-3 text-xs">
                        <span className="text-slate-500 w-24 flex-shrink-0">{s.label}</span>
                        <span className="text-slate-300">{s.value}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          )}

          {tab === 'appearance' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-base font-display font-bold text-white mb-1">Accent Color</h3>
                <p className="text-xs text-slate-500 mb-4">Choose the primary color for the interface. Changes apply instantly.</p>
                <div className="flex flex-wrap gap-4">
                  {THEMES.map(t => (
                    <button
                      key={t.id}
                      onClick={() => { setTheme(t.id); toast.success(`Theme changed to ${t.label}`); }}
                      title={t.label}
                      className={cn(
                        'flex flex-col items-center gap-2 p-3 rounded-xl border-2 transition-all',
                        theme === t.id
                          ? 'border-white/60 scale-105'
                          : 'border-transparent opacity-60 hover:opacity-100 hover:scale-105'
                      )}
                    >
                      <div
                        className="w-10 h-10 rounded-full"
                        style={{
                          background: t.color,
                          boxShadow: theme === t.id ? `0 0 16px ${t.glow}` : 'none',
                        }}
                      />
                      <span className="text-xs text-slate-400">{t.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="p-4 bg-white/3 rounded-xl border border-white/5">
                <div className="text-sm font-medium text-slate-200 mb-2">Preview</div>
                <div className="flex gap-3 flex-wrap">
                  <div className="px-4 py-2 rounded-xl text-sm font-medium text-white" style={{ background: THEMES.find(t => t.id === theme)?.color }}>Primary Button</div>
                  <div className="px-4 py-2 rounded-xl text-sm border" style={{ borderColor: THEMES.find(t => t.id === theme)?.color, color: THEMES.find(t => t.id === theme)?.color }}>Outline Button</div>
                  <div className="px-4 py-2 rounded-xl text-sm text-white/60" style={{ background: `${THEMES.find(t => t.id === theme)?.color}20` }}>Subtle Badge</div>
                </div>
              </div>
            </div>
          )}

          {tab === 'notifications' && (
            <div className="space-y-4">
              <h3 className="text-base font-display font-bold text-white">Notification Preferences</h3>
              <p className="text-xs text-slate-500">Preferences are saved locally and persist across sessions.</p>
              {notifs.map(item => (
                <div key={item.id} className="flex items-center justify-between p-4 bg-white/3 rounded-xl border border-white/5">
                  <div>
                    <div className="text-sm font-medium text-white">{item.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{item.desc}</div>
                  </div>
                  <button
                    onClick={() => setNotifs(prev => prev.map(n => n.id === item.id ? { ...n, enabled: !n.enabled } : n))}
                    className={cn('w-11 h-6 rounded-full relative transition-colors', item.enabled ? 'bg-indigo-600' : 'bg-white/10')}
                  >
                    <div className={cn('w-4 h-4 rounded-full bg-white absolute top-1 transition-all', item.enabled ? 'left-6' : 'left-1')} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="mt-6 pt-5 border-t border-white/5 flex justify-end">
            <motion.button
              onClick={handleSave}
              disabled={saving}
              className={cn('flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-60', saved ? 'bg-emerald-600 text-white' : 'bg-indigo-600 hover:bg-indigo-500 text-white')}
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            >
              {saving ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Saving...</>
              ) : (
                <><Save className="w-4 h-4" />{saved ? 'Saved!' : 'Save Changes'}</>
              )}
            </motion.button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
