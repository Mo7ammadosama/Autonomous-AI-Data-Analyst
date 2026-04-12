'use client';

import { useState, useEffect, useCallback } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import { adminApi } from '@/lib/api';
import { useAuthStore } from '@/lib/store';
import {
  ShieldCheck, Users, Building2, Database, DollarSign, Sparkles,
  Activity, CheckCircle, XCircle, Search, RefreshCw, Trash2,
  UserX, UserCheck, ChevronDown
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ── Types ──────────────────────────────────────────────────────
interface Stats {
  total_users: number;
  active_users: number;
  suspended_users: number;
  total_companies: number;
  active_companies: number;
  suspended_companies: number;
  total_datasets: number;
  total_dashboards: number;
  llm_requests_today: number;
  llm_cost_today_usd: number;
  new_users_this_week: number;
}

interface Company {
  id: string;
  name: string;
  plan: string;
  member_count: number;
  dataset_count: number;
  is_suspended: boolean;
  created_at: string;
  suspended_reason?: string;
}

interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  workspace_id: string | null;
  workspace_name: string | null;
  dataset_count: number;
  created_at: string;
}

interface AuditEntry {
  id: string;
  actor_username: string;
  action: string;
  resource_type: string;
  resource_id: string;
  created_at: string;
}

// ── Stat Card ─────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, color, sub }: {
  icon: React.ElementType; label: string; value: number | string; color: string; sub?: string;
}) {
  return (
    <div className="glass rounded-2xl p-5 flex items-center gap-4">
      <div className={cn('w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0', color)}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div>
        <div className="text-2xl font-bold text-white">{value}</div>
        <div className="text-sm text-slate-400">{label}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

// ── Role Badge ────────────────────────────────────────────────
function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, string> = {
    superadmin: 'bg-red-500/20 text-red-300',
    admin: 'bg-green-500/20 text-green-300',
    analyst: 'bg-blue-500/20 text-blue-300',
    viewer: 'bg-slate-500/20 text-slate-400',
  };
  return (
    <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full', colors[role] ?? colors.viewer)}>
      {role}
    </span>
  );
}

// ── Status Badge ──────────────────────────────────────────────
function StatusBadge({ active }: { active: boolean }) {
  return (
    <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 w-fit',
      active ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300')}>
      <span className={cn('w-1.5 h-1.5 rounded-full', active ? 'bg-emerald-400' : 'bg-red-400')} />
      {active ? 'Active' : 'Suspended'}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────
export default function AdminPage() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'overview' | 'companies' | 'users' | 'audit' | 'llm'>('overview');

  // Overview
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [recentLogs, setRecentLogs] = useState<AuditEntry[]>([]);

  // Companies
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companySearch, setCompanySearch] = useState('');
  const [companyStatus, setCompanyStatus] = useState('');
  const [companyTotal, setCompanyTotal] = useState(0);

  // Users
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [userRole, setUserRole] = useState('');
  const [userStatus, setUserStatus] = useState('');
  const [userTotal, setUserTotal] = useState(0);

  // Audit
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);

  // LLM
  const [llmUsage, setLlmUsage] = useState<any>(null);
  const [llmGroupBy, setLlmGroupBy] = useState('day');

  const [loading, setLoading] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{ type: string; id: string; name: string } | null>(null);
  const [suspendReason, setSuspendReason] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [s, h, l] = await Promise.all([
        adminApi.stats(),
        adminApi.health(),
        adminApi.auditLogs({ limit: 10 }),
      ]);
      setStats(s.data);
      setHealth(h.data);
      setRecentLogs(l.data.logs ?? []);
    } catch {}
    setLoading(false);
  }, []);

  const loadCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.listCompanies({ search: companySearch || undefined, status: companyStatus || undefined });
      setCompanies(r.data.companies ?? []);
      setCompanyTotal(r.data.total ?? 0);
    } catch {}
    setLoading(false);
  }, [companySearch, companyStatus]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.listUsers({ search: userSearch || undefined, role: userRole || undefined, status: userStatus || undefined });
      setAdminUsers(r.data.users ?? []);
      setUserTotal(r.data.total ?? 0);
    } catch {}
    setLoading(false);
  }, [userSearch, userRole, userStatus]);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.auditLogs({ limit: 100 });
      setAuditLogs(r.data.logs ?? []);
      setAuditTotal(r.data.total ?? 0);
    } catch {}
    setLoading(false);
  }, []);

  const loadLlm = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.llmUsage({ group_by: llmGroupBy });
      setLlmUsage(r.data);
    } catch {}
    setLoading(false);
  }, [llmGroupBy]);

  useEffect(() => {
    if (activeTab === 'overview') loadOverview();
    else if (activeTab === 'companies') loadCompanies();
    else if (activeTab === 'users') loadUsers();
    else if (activeTab === 'audit') loadAudit();
    else if (activeTab === 'llm') loadLlm();
  }, [activeTab, loadOverview, loadCompanies, loadUsers, loadAudit, loadLlm]);

  const handleConfirm = async () => {
    if (!confirmAction) return;
    try {
      const { type, id } = confirmAction;
      if (type === 'suspend_company') await adminApi.suspendCompany(id, suspendReason);
      else if (type === 'activate_company') await adminApi.activateCompany(id);
      else if (type === 'delete_company') await adminApi.deleteCompany(id);
      else if (type === 'suspend_user') await adminApi.suspendUser(id, suspendReason);
      else if (type === 'activate_user') await adminApi.activateUser(id);
      else if (type === 'delete_user') await adminApi.deleteUser(id);

      setConfirmAction(null);
      setSuspendReason('');
      if (activeTab === 'companies') loadCompanies();
      else if (activeTab === 'users') loadUsers();
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? 'Action failed');
    }
  };

  const changeRole = async (userId: string, role: string) => {
    try {
      await adminApi.changeUserRole(userId, role);
      loadUsers();
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? 'Role change failed');
    }
  };

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'companies', label: `Companies${companyTotal ? ` (${companyTotal})` : ''}` },
    { id: 'users', label: `Users${userTotal ? ` (${userTotal})` : ''}` },
    { id: 'audit', label: 'Audit Log' },
    { id: 'llm', label: 'LLM Usage' },
  ] as const;

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <ShieldCheck className="w-7 h-7 text-red-400" />
              Admin Panel
            </h1>
            <p className="text-slate-400 mt-1">Platform management — visible to SuperAdmin only</p>
          </div>
          <button onClick={() => {
            if (activeTab === 'overview') loadOverview();
            else if (activeTab === 'companies') loadCompanies();
            else if (activeTab === 'users') loadUsers();
            else if (activeTab === 'audit') loadAudit();
            else loadLlm();
          }} className="btn-ghost flex items-center gap-2">
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Refresh
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 glass rounded-xl p-1 w-fit">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                activeTab === t.id ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Overview ── */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <StatCard icon={Building2} label="Companies" value={stats?.total_companies ?? '—'} color="bg-blue-600" sub={`${stats?.suspended_companies ?? 0} suspended`} />
              <StatCard icon={Users} label="Total Users" value={stats?.total_users ?? '—'} color="bg-emerald-600" sub={`${stats?.new_users_this_week ?? 0} new this week`} />
              <StatCard icon={UserX} label="Suspended Users" value={stats?.suspended_users ?? '—'} color="bg-red-600" />
              <StatCard icon={Database} label="Datasets" value={stats?.total_datasets ?? '—'} color="bg-violet-600" />
              <StatCard icon={DollarSign} label="LLM Cost Today" value={`$${stats?.llm_cost_today_usd?.toFixed(4) ?? '0'}`} color="bg-amber-600" />
              <StatCard icon={Sparkles} label="AI Requests Today" value={stats?.llm_requests_today ?? '—'} color="bg-indigo-600" />
            </div>

            {/* System Health */}
            <div className="glass rounded-2xl p-5">
              <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-400" />
                System Health
              </h3>
              {health ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 mb-1">
                      {health.db_status === 'healthy'
                        ? <CheckCircle className="w-5 h-5 text-emerald-400" />
                        : <XCircle className="w-5 h-5 text-red-400" />}
                    </div>
                    <div className="text-xs text-slate-400">Database</div>
                    <div className="text-sm font-medium text-white capitalize">{health.db_status}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-white">{health.db_latency_ms}ms</div>
                    <div className="text-xs text-slate-400">DB Latency</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-white">{health.version}</div>
                    <div className="text-xs text-slate-400">API Version</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-white capitalize">{health.environment}</div>
                    <div className="text-xs text-slate-400">Environment</div>
                  </div>
                </div>
              ) : <div className="text-slate-500 text-sm">Loading…</div>}
            </div>

            {/* Recent Activity */}
            <div className="glass rounded-2xl p-5">
              <h3 className="font-semibold text-white mb-4">Recent Activity</h3>
              <div className="space-y-2">
                {recentLogs.length === 0 && <div className="text-slate-500 text-sm">No activity yet.</div>}
                {recentLogs.map(log => (
                  <div key={log.id} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                    <div>
                      <span className="text-sm text-white font-medium">{log.actor_username}</span>
                      <span className="text-slate-400 text-sm"> · {log.action}</span>
                      {log.resource_type && <span className="text-slate-500 text-xs ml-2">({log.resource_type})</span>}
                    </div>
                    <div className="text-xs text-slate-500">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Companies ── */}
        {activeTab === 'companies' && (
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  value={companySearch}
                  onChange={e => setCompanySearch(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && loadCompanies()}
                  placeholder="Search companies…"
                  className="input-field pl-9 w-full"
                />
              </div>
              <select
                value={companyStatus}
                onChange={e => { setCompanyStatus(e.target.value); }}
                className="input-field"
              >
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
              <button onClick={loadCompanies} className="btn-primary">Search</button>
            </div>

            <div className="glass rounded-2xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    {['Company', 'Plan', 'Members', 'Datasets', 'Status', 'Created', 'Actions'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {companies.length === 0 && (
                    <tr><td colSpan={7} className="text-center py-8 text-slate-500">No companies found.</td></tr>
                  )}
                  {companies.map(c => (
                    <tr key={c.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                      <td className="px-4 py-3 font-medium text-white">{c.name}</td>
                      <td className="px-4 py-3 text-slate-400 capitalize">{c.plan}</td>
                      <td className="px-4 py-3 text-slate-300">{c.member_count}</td>
                      <td className="px-4 py-3 text-slate-300">{c.dataset_count}</td>
                      <td className="px-4 py-3"><StatusBadge active={!c.is_suspended} /></td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          {c.is_suspended ? (
                            <button onClick={() => setConfirmAction({ type: 'activate_company', id: c.id, name: c.name })}
                              className="text-xs px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 transition-colors flex items-center gap-1">
                              <UserCheck className="w-3 h-3" /> Activate
                            </button>
                          ) : (
                            <button onClick={() => { setConfirmAction({ type: 'suspend_company', id: c.id, name: c.name }); setSuspendReason(''); }}
                              className="text-xs px-2 py-1 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition-colors flex items-center gap-1">
                              <UserX className="w-3 h-3" /> Suspend
                            </button>
                          )}
                          <button onClick={() => setConfirmAction({ type: 'delete_company', id: c.id, name: c.name })}
                            className="text-xs px-2 py-1 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors flex items-center gap-1">
                            <Trash2 className="w-3 h-3" /> Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Users ── */}
        {activeTab === 'users' && (
          <div className="space-y-4">
            <div className="flex gap-3 flex-wrap">
              <div className="relative flex-1 min-w-48">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  value={userSearch}
                  onChange={e => setUserSearch(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && loadUsers()}
                  placeholder="Search users…"
                  className="input-field pl-9 w-full"
                />
              </div>
              <select value={userRole} onChange={e => setUserRole(e.target.value)} className="input-field">
                <option value="">All Roles</option>
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
              <select value={userStatus} onChange={e => setUserStatus(e.target.value)} className="input-field">
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
              <button onClick={loadUsers} className="btn-primary">Search</button>
            </div>

            <div className="glass rounded-2xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    {['User', 'Email', 'Role', 'Company', 'Datasets', 'Status', 'Actions'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.length === 0 && (
                    <tr><td colSpan={7} className="text-center py-8 text-slate-500">No users found.</td></tr>
                  )}
                  {adminUsers.map(u => (
                    <tr key={u.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                      <td className="px-4 py-3 font-medium text-white">{u.username}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{u.email}</td>
                      <td className="px-4 py-3">
                        {u.role === 'superadmin' ? (
                          <RoleBadge role={u.role} />
                        ) : (
                          <select
                            defaultValue={u.role}
                            onChange={e => changeRole(u.id, e.target.value)}
                            className="text-xs bg-transparent border border-white/10 rounded-lg px-2 py-1 text-slate-300 cursor-pointer"
                          >
                            <option value="viewer">viewer</option>
                            <option value="analyst">analyst</option>
                            <option value="admin">admin</option>
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{u.workspace_name ?? '—'}</td>
                      <td className="px-4 py-3 text-slate-300">{u.dataset_count}</td>
                      <td className="px-4 py-3"><StatusBadge active={u.is_active} /></td>
                      <td className="px-4 py-3">
                        {u.role !== 'superadmin' && (
                          <div className="flex gap-2">
                            {u.is_active ? (
                              <button onClick={() => { setConfirmAction({ type: 'suspend_user', id: u.id, name: u.username }); setSuspendReason(''); }}
                                className="text-xs px-2 py-1 rounded-lg bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition-colors flex items-center gap-1">
                                <UserX className="w-3 h-3" /> Suspend
                              </button>
                            ) : (
                              <button onClick={() => setConfirmAction({ type: 'activate_user', id: u.id, name: u.username })}
                                className="text-xs px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 transition-colors flex items-center gap-1">
                                <UserCheck className="w-3 h-3" /> Activate
                              </button>
                            )}
                            <button onClick={() => setConfirmAction({ type: 'delete_user', id: u.id, name: u.username })}
                              className="text-xs px-2 py-1 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors flex items-center gap-1">
                              <Trash2 className="w-3 h-3" /> Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Audit Log ── */}
        {activeTab === 'audit' && (
          <div className="glass rounded-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="font-semibold text-white">Audit Log ({auditTotal} total)</h3>
              <button onClick={loadAudit} className="btn-ghost text-sm flex items-center gap-1">
                <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} /> Refresh
              </button>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  {['Time', 'Actor', 'Action', 'Resource', 'ID'].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {auditLogs.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-8 text-slate-500">No audit entries yet.</td></tr>
                )}
                {auditLogs.map(log => (
                  <tr key={log.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="px-4 py-2.5 text-slate-400 text-xs whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-2.5 font-medium text-white text-xs">{log.actor_username}</td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs bg-indigo-500/10 text-indigo-300 px-2 py-0.5 rounded-md font-mono">{log.action}</span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-400 text-xs">{log.resource_type ?? '—'}</td>
                    <td className="px-4 py-2.5 text-slate-500 text-xs font-mono truncate max-w-[100px]">{log.resource_id ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── LLM Usage ── */}
        {activeTab === 'llm' && (
          <div className="space-y-4">
            <div className="flex gap-3 items-center">
              <span className="text-sm text-slate-400">Group by:</span>
              {['day', 'user', 'model'].map(g => (
                <button key={g} onClick={() => setLlmGroupBy(g)}
                  className={cn('text-sm px-3 py-1.5 rounded-lg transition-colors capitalize',
                    llmGroupBy === g ? 'bg-indigo-600 text-white' : 'glass text-slate-400 hover:text-white')}>
                  {g}
                </button>
              ))}
              <button onClick={loadLlm} className="btn-ghost ml-auto flex items-center gap-1 text-sm">
                <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} /> Reload
              </button>
            </div>

            {llmUsage && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="glass rounded-2xl p-5 text-center">
                    <div className="text-3xl font-bold text-white">{llmUsage.total_requests}</div>
                    <div className="text-sm text-slate-400 mt-1">Total Requests</div>
                  </div>
                  <div className="glass rounded-2xl p-5 text-center">
                    <div className="text-3xl font-bold text-amber-300">${llmUsage.total_cost_usd?.toFixed(4)}</div>
                    <div className="text-sm text-slate-400 mt-1">Total Cost</div>
                  </div>
                </div>

                <div className="glass rounded-2xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        {[llmGroupBy === 'day' ? 'Date' : llmGroupBy === 'user' ? 'User ID' : 'Model',
                          'Requests', 'Total Tokens', 'Cost (USD)', 'Errors'].map(h => (
                          <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(llmUsage.breakdown ?? []).map((row: any) => (
                        <tr key={row.key} className="border-b border-white/5 hover:bg-white/3">
                          <td className="px-4 py-2.5 font-medium text-white text-xs">{row.key}</td>
                          <td className="px-4 py-2.5 text-slate-300">{row.requests}</td>
                          <td className="px-4 py-2.5 text-slate-300">{row.total_tokens?.toLocaleString()}</td>
                          <td className="px-4 py-2.5 text-amber-300">${row.cost_usd?.toFixed(4)}</td>
                          <td className="px-4 py-2.5 text-red-400">{row.errors}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── Confirm Modal ── */}
        {confirmAction && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="glass rounded-2xl p-6 w-full max-w-md space-y-4">
              <h3 className="text-lg font-bold text-white capitalize">
                {confirmAction.type.replace(/_/g, ' ')}
              </h3>
              <p className="text-slate-400">
                Are you sure you want to <strong className="text-white">{confirmAction.type.replace(/_/g, ' ')}</strong>{' '}
                <strong className="text-indigo-300">&quot;{confirmAction.name}&quot;</strong>?
                {confirmAction.type.includes('delete') && (
                  <span className="block mt-2 text-red-400 text-sm">This action is irreversible.</span>
                )}
              </p>
              {confirmAction.type.includes('suspend') && (
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">Reason (optional)</label>
                  <input
                    value={suspendReason}
                    onChange={e => setSuspendReason(e.target.value)}
                    placeholder="e.g. Violation of terms"
                    className="input-field w-full"
                  />
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => setConfirmAction(null)} className="btn-ghost">Cancel</button>
                <button
                  onClick={handleConfirm}
                  className={cn('btn-primary', confirmAction.type.includes('delete') && 'bg-red-600 hover:bg-red-700')}
                >
                  Confirm
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
