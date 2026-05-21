'use client';

import { useState, useEffect } from 'react';
import { metricsApi } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';
import StatCard from '@/components/ui/StatCard';
import AppLayout from '@/components/layout/AppLayout';
import { BarChart3, Database, MessageSquare, Bell, PanelsTopLeft, RefreshCw, Users, Server } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UserMetrics {
  generated_at: string;
  datasets: { total: number; ready: number; uploaded_this_week: number; total_rows: number; total_size_bytes: number };
  ai: { chat_sessions: number; chat_messages: number; nl2sql_queries: number; nl2sql_success_rate: number };
  alerts: { total: number; active: number; total_triggers: number; triggers_this_week: number };
  platform: { dashboards: number; connections: number; scheduled_reports: number };
}

interface SystemMetrics {
  generated_at: string;
  users: { total: number; active_last_24h: number; active_last_7d: number };
  content: { datasets: number; dashboards: number; nl2sql_queries: number; alerts: number };
  platform_version: string;
}

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatNumber(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function MetricsPage() {
  const [userMetrics, setUserMetrics] = useState<UserMetrics | null>(null);
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'user' | 'system'>('user');

  const load = async () => {
    setLoading(true);
    try {
      const [um, sm] = await Promise.all([metricsApi.user(), metricsApi.system()]);
      setUserMetrics(um.data);
      setSystemMetrics(sm.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <AppLayout>
    <div className="p-6 space-y-6 max-w-7xl">
      <PageHeader
        title="Platform Metrics"
        description="Usage statistics and platform health"
        icon={<BarChart3 className="w-6 h-6" />}
        action={
          <button onClick={load} className="btn-ghost flex items-center gap-2 text-sm">
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Refresh
          </button>
        }
      />

      {/* Tabs */}
      <div className="flex gap-2">
        {(['user', 'system'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-2 rounded-xl text-sm font-medium transition-all',
              tab === t ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'text-slate-400 hover:text-slate-200 border border-transparent'
            )}
          >
            {t === 'user' ? 'My Usage' : 'System'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="glass rounded-xl p-4 h-24 animate-pulse" />
          ))}
        </div>
      ) : tab === 'user' && userMetrics ? (
        <div className="space-y-6">
          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Datasets</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard title="Total Datasets" value={userMetrics.datasets.total} icon={Database} />
              <StatCard title="Ready" value={userMetrics.datasets.ready} icon={Database} iconColor="text-emerald-400" />
              <StatCard title="Total Rows" value={formatNumber(userMetrics.datasets.total_rows)} icon={Database} />
              <StatCard title="Storage Used" value={formatBytes(userMetrics.datasets.total_size_bytes)} icon={Server} />
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">AI Usage</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard title="Chat Sessions" value={userMetrics.ai.chat_sessions} icon={MessageSquare} iconColor="text-indigo-400" />
              <StatCard title="Messages Sent" value={userMetrics.ai.chat_messages} icon={MessageSquare} iconColor="text-indigo-400" />
              <StatCard title="SQL Queries" value={userMetrics.ai.nl2sql_queries} icon={BarChart3} iconColor="text-violet-400" />
              <StatCard title="SQL Success Rate" value={`${userMetrics.ai.nl2sql_success_rate}%`} icon={BarChart3} iconColor="text-emerald-400" />
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Alerts</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard title="Total Alerts" value={userMetrics.alerts.total} icon={Bell} iconColor="text-amber-400" />
              <StatCard title="Active Alerts" value={userMetrics.alerts.active} icon={Bell} iconColor="text-emerald-400" />
              <StatCard title="Total Triggers" value={userMetrics.alerts.total_triggers} icon={Bell} iconColor="text-red-400" />
              <StatCard title="Triggers This Week" value={userMetrics.alerts.triggers_this_week} icon={Bell} iconColor="text-orange-400" />
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Platform</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <StatCard title="Dashboards" value={userMetrics.platform.dashboards} icon={PanelsTopLeft} iconColor="text-cyan-400" />
              <StatCard title="Connections" value={userMetrics.platform.connections} icon={Server} />
              <StatCard title="Scheduled Reports" value={userMetrics.platform.scheduled_reports} icon={BarChart3} />
            </div>
          </section>
        </div>
      ) : tab === 'system' && systemMetrics ? (
        <div className="space-y-6">
          <div className="glass rounded-xl p-4 flex items-center justify-between">
            <span className="text-sm text-slate-400">Platform Version</span>
            <span className="text-sm font-mono text-indigo-400">v{systemMetrics.platform_version}</span>
          </div>

          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Users</h2>
            <div className="grid grid-cols-3 gap-4">
              <StatCard title="Total Users" value={systemMetrics.users.total} icon={Users} iconColor="text-indigo-400" />
              <StatCard title="Active (24h)" value={systemMetrics.users.active_last_24h} icon={Users} iconColor="text-emerald-400" />
              <StatCard title="Active (7d)" value={systemMetrics.users.active_last_7d} icon={Users} iconColor="text-cyan-400" />
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Platform Content</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard title="Datasets" value={systemMetrics.content.datasets} icon={Database} />
              <StatCard title="Dashboards" value={systemMetrics.content.dashboards} icon={PanelsTopLeft} iconColor="text-violet-400" />
              <StatCard title="SQL Queries" value={systemMetrics.content.nl2sql_queries} icon={BarChart3} iconColor="text-indigo-400" />
              <StatCard title="Alerts" value={systemMetrics.content.alerts} icon={Bell} iconColor="text-amber-400" />
            </div>
          </section>
        </div>
      ) : null}
    </div>
    </AppLayout>
  );
}
