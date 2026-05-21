'use client';

import { useState, useEffect, useCallback } from 'react';
import { notificationsApi } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';
import AppLayout from '@/components/layout/AppLayout';
import { Activity, Filter, RefreshCw, Database, BarChart2, Bell, MessageSquare, Settings, File } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';

interface ActivityEntry {
  id: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

const resourceIcons: Record<string, React.ElementType> = {
  dataset: Database,
  dashboard: BarChart2,
  alert: Bell,
  chat: MessageSquare,
  settings: Settings,
};

const actionColors: Record<string, string> = {
  create: 'text-emerald-400 bg-emerald-500/10',
  upload: 'text-indigo-400 bg-indigo-500/10',
  delete: 'text-red-400 bg-red-500/10',
  update: 'text-amber-400 bg-amber-500/10',
  login: 'text-cyan-400 bg-cyan-500/10',
  logout: 'text-slate-400 bg-slate-500/10',
};

function getActionColor(action: string) {
  const verb = action.split('_')[0]?.toLowerCase() || '';
  return actionColors[verb] || 'text-slate-400 bg-slate-500/10';
}

const RESOURCE_TYPES = ['', 'dataset', 'dashboard', 'alert', 'chat', 'connection', 'report'];

export default function ActivityPage() {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationsApi.activity(filter || undefined, 100);
      setEntries(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <AppLayout>
    <div className="p-6 space-y-6 max-w-5xl">
      <PageHeader
        title="Activity Feed"
        description="Your recent platform activity and audit log"
        icon={<Activity className="w-6 h-6" />}
        action={
          <button onClick={load} className="btn-ghost flex items-center gap-2 text-sm">
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Refresh
          </button>
        }
      />

      {/* Filter */}
      <div className="glass rounded-xl p-4 flex items-center gap-3">
        <Filter className="w-4 h-4 text-slate-500 flex-shrink-0" />
        <span className="text-sm text-slate-400">Resource type:</span>
        <div className="flex gap-2 flex-wrap">
          {RESOURCE_TYPES.map((rt) => (
            <button
              key={rt || 'all'}
              onClick={() => setFilter(rt)}
              className={cn(
                'text-xs px-3 py-1 rounded-full border transition-all',
                filter === rt
                  ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                  : 'border-white/10 text-slate-400 hover:border-white/20'
              )}
            >
              {rt || 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div className="glass rounded-xl divide-y divide-white/5">
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="p-4 flex items-center gap-4">
              <div className="w-8 h-8 rounded-lg bg-white/5 animate-pulse flex-shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-3 bg-white/5 rounded animate-pulse w-1/3" />
                <div className="h-2 bg-white/5 rounded animate-pulse w-1/5" />
              </div>
            </div>
          ))
        ) : entries.length === 0 ? (
          <div className="p-12 text-center text-slate-500">No activity recorded yet.</div>
        ) : (
          entries.map((entry) => {
            const Icon = (entry.resource_type && resourceIcons[entry.resource_type]) || File;
            const colorClass = getActionColor(entry.action);
            return (
              <div key={entry.id} className="p-4 flex items-start gap-4 hover:bg-white/3 transition-colors">
                <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5', colorClass)}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-slate-200">{entry.action.replace(/_/g, ' ')}</span>
                    {entry.resource_type && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-slate-400 capitalize">
                        {entry.resource_type}
                      </span>
                    )}
                  </div>
                  {entry.details && Object.keys(entry.details).length > 0 && (
                    <p className="text-xs text-slate-500 mt-0.5 truncate">
                      {JSON.stringify(entry.details)}
                    </p>
                  )}
                </div>
                <span className="text-xs text-slate-600 flex-shrink-0 mt-0.5">
                  {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
    </AppLayout>
  );
}
