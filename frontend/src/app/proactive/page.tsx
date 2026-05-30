'use client';

import { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Zap, TrendingUp, TrendingDown, AlertTriangle, Trophy,
  RefreshCw, Settings, Bell, BellOff, CheckCheck,
  ChevronDown, ChevronUp, Filter, Clock, Database,
  ArrowUpRight, ArrowDownRight, Minus, Play
} from 'lucide-react';
import { toast } from 'sonner';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { apiClient } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────

interface ProactiveInsight {
  id: string;
  dataset_id?: string;
  metric_name?: string;
  insight_type: 'anomaly' | 'trend_shift' | 'record_high' | 'record_low' | 'data_quality';
  change_pct?: number;
  current_value?: number;
  previous_value?: number;
  drivers?: Array<{ dimension: string; value: string; contribution_pct: number; mean: number }>;
  narrative?: string;
  severity: 'info' | 'warning' | 'critical';
  is_read: boolean;
  sent_via?: string[];
  created_at: string;
}

interface ProactiveConfig {
  is_enabled: boolean;
  scan_frequency_minutes: number;
  notify_websocket: boolean;
  notify_email: boolean;
  notify_slack: boolean;
  slack_webhook_url?: string;
  monitored_datasets: string[];
  anomaly_sensitivity: 'low' | 'medium' | 'high';
}

// ── API helpers ───────────────────────────────────────────────

const proactiveApi = {
  getFeed: (params?: { unread_only?: boolean; severity?: string; limit?: number; offset?: number }) =>
    apiClient.get('/api/proactive/feed', { params }),
  getUnreadCount: () => apiClient.get('/api/proactive/feed/unread-count'),
  markRead: (id: string) => apiClient.post(`/api/proactive/feed/${id}/read`),
  markAllRead: () => apiClient.post('/api/proactive/feed/mark-all-read'),
  getConfig: () => apiClient.get('/api/proactive/config'),
  updateConfig: (data: Partial<ProactiveConfig>) => apiClient.post('/api/proactive/configure', data),
  scanNow: () => apiClient.post('/api/proactive/scan-now'),
};

// ── Insight type metadata ─────────────────────────────────────

const INSIGHT_META: Record<string, { icon: React.ElementType; label: string; color: string; bg: string }> = {
  anomaly:      { icon: AlertTriangle, label: 'Anomaly',      color: 'text-orange-400', bg: 'bg-orange-900/30' },
  trend_shift:  { icon: TrendingUp,   label: 'Trend Shift',  color: 'text-blue-400',   bg: 'bg-blue-900/30'   },
  record_high:  { icon: Trophy,       label: 'Record High',  color: 'text-green-400',  bg: 'bg-green-900/30'  },
  record_low:   { icon: TrendingDown, label: 'Record Low',   color: 'text-red-400',    bg: 'bg-red-900/30'    },
  data_quality: { icon: Database,     label: 'Data Quality', color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
};

const SEVERITY_BADGE: Record<string, string> = {
  info:     'bg-blue-900/50 text-blue-300 border border-blue-700',
  warning:  'bg-orange-900/50 text-orange-300 border border-orange-700',
  critical: 'bg-red-900/50 text-red-300 border border-red-700',
};

// ── Sub-components ────────────────────────────────────────────

function InsightCard({ insight, onRead }: { insight: ProactiveInsight; onRead: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const meta = INSIGHT_META[insight.insight_type] || INSIGHT_META.anomaly;
  const Icon = meta.icon;

  const changeDir = (insight.change_pct ?? 0) > 0 ? 'up' : insight.change_pct === 0 ? 'flat' : 'down';
  const ChangeIcon = changeDir === 'up' ? ArrowUpRight : changeDir === 'down' ? ArrowDownRight : Minus;

  const handleClick = () => {
    setExpanded(!expanded);
    if (!insight.is_read) {
      onRead(insight.id);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border transition-all cursor-pointer ${
        insight.is_read
          ? 'border-white/10 bg-white/5'
          : 'border-indigo-500/40 bg-indigo-900/20 shadow-md shadow-indigo-900/20'
      }`}
      onClick={handleClick}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={`p-2 rounded-lg flex-shrink-0 ${meta.bg}`}>
            <Icon className={`w-5 h-5 ${meta.color}`} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${meta.color} ${meta.bg}`}>
                {meta.label}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${SEVERITY_BADGE[insight.severity]}`}>
                {insight.severity}
              </span>
              {!insight.is_read && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-600 text-white font-semibold">
                  New
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold text-white">
                {insight.metric_name || 'Metric'}
              </span>
              {insight.change_pct != null && (
                <span className={`flex items-center gap-0.5 text-sm font-bold ${
                  changeDir === 'up' ? 'text-green-400' : changeDir === 'down' ? 'text-red-400' : 'text-gray-400'
                }`}>
                  <ChangeIcon className="w-4 h-4" />
                  {Math.abs(insight.change_pct).toFixed(1)}%
                </span>
              )}
            </div>

            <div className="text-sm text-gray-300 leading-snug line-clamp-2 prose prose-invert prose-sm max-w-none">
              <ReactMarkdown>{insight.narrative || ''}</ReactMarkdown>
            </div>

            <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {new Date(insight.created_at).toLocaleString()}
              </span>
              {insight.sent_via && insight.sent_via.length > 0 && (
                <span>sent via {insight.sent_via.join(', ')}</span>
              )}
            </div>
          </div>

          <button className="text-gray-500 hover:text-white mt-1 flex-shrink-0">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>

        {/* Expanded: drivers */}
        <AnimatePresence>
          {expanded && insight.drivers && insight.drivers.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 pt-4 border-t border-white/10"
            >
              <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Top Drivers</p>
              <div className="space-y-2">
                {insight.drivers.map((d, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-300">
                          <span className="text-gray-500">{d.dimension}:</span> {d.value}
                        </span>
                        <span className="text-indigo-400 font-semibold">{d.contribution_pct.toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${Math.min(d.contribution_pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function ConfigPanel({ config, onSave }: {
  config: ProactiveConfig;
  onSave: (c: Partial<ProactiveConfig>) => void;
}) {
  const [draft, setDraft] = useState(config);

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Settings className="w-4 h-4 text-indigo-400" /> Monitoring Settings
      </h3>

      <label className="flex items-center justify-between">
        <span className="text-sm text-gray-300">Enable proactive monitoring</span>
        <input
          type="checkbox"
          checked={draft.is_enabled}
          onChange={e => setDraft({ ...draft, is_enabled: e.target.checked })}
          className="w-4 h-4 accent-indigo-500"
        />
      </label>

      <div>
        <label className="text-xs text-gray-400 mb-1 block">Anomaly Sensitivity</label>
        <select
          value={draft.anomaly_sensitivity}
          onChange={e => setDraft({ ...draft, anomaly_sensitivity: e.target.value as any })}
          className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-sm text-white"
        >
          <option value="low">Low — only major anomalies</option>
          <option value="medium">Medium — balanced</option>
          <option value="high">High — catch everything</option>
        </select>
      </div>

      <div className="space-y-2">
        <p className="text-xs text-gray-400">Notification Channels</p>
        {[
          { key: 'notify_websocket', label: 'In-App (WebSocket)' },
          { key: 'notify_email',     label: 'Email' },
          { key: 'notify_slack',     label: 'Slack' },
        ].map(({ key, label }) => (
          <label key={key} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={(draft as any)[key]}
              onChange={e => setDraft({ ...draft, [key]: e.target.checked })}
              className="w-4 h-4 accent-indigo-500"
            />
            {label}
          </label>
        ))}
      </div>

      <button
        onClick={() => onSave(draft)}
        className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium text-white transition-colors"
      >
        Save Settings
      </button>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────

export default function ProactivePage() {
  const [insights, setInsights] = useState<ProactiveInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [config, setConfig] = useState<ProactiveConfig | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [filter, setFilter] = useState<'all' | 'unread' | 'critical'>('all');

  const fetchFeed = useCallback(async () => {
    try {
      const params: any = { limit: 50 };
      if (filter === 'unread') params.unread_only = true;
      if (filter === 'critical') params.severity = 'critical';
      const res = await proactiveApi.getFeed(params);
      setInsights(res.data);
    } catch {
      toast.error('Failed to load intelligence feed');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const fetchConfig = async () => {
    try {
      const res = await proactiveApi.getConfig();
      setConfig(res.data);
    } catch { /* ok */ }
  };

  const fetchUnread = async () => {
    try {
      const res = await proactiveApi.getUnreadCount();
      setUnreadCount(res.data.unread_count);
    } catch { /* ok */ }
  };

  useEffect(() => {
    fetchFeed();
    fetchConfig();
    fetchUnread();
  }, [fetchFeed]);

  const handleMarkRead = async (id: string) => {
    await proactiveApi.markRead(id).catch(() => {});
    setInsights(prev => prev.map(i => i.id === id ? { ...i, is_read: true } : i));
    setUnreadCount(prev => Math.max(0, prev - 1));
  };

  const handleMarkAllRead = async () => {
    await proactiveApi.markAllRead();
    setInsights(prev => prev.map(i => ({ ...i, is_read: true })));
    setUnreadCount(0);
    toast.success('All insights marked as read');
  };

  const handleScanNow = async () => {
    setScanning(true);
    try {
      const res = await proactiveApi.scanNow();
      const stats = res.data.stats;
      toast.success(`Scan complete — ${stats?.insights_generated ?? 0} new insights generated`);
      await fetchFeed();
      await fetchUnread();
    } catch {
      toast.error('Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handleSaveConfig = async (updates: Partial<ProactiveConfig>) => {
    try {
      await proactiveApi.updateConfig(updates);
      setConfig(prev => prev ? { ...prev, ...updates } : null);
      toast.success('Settings saved');
    } catch {
      toast.error('Failed to save settings');
    }
  };

  const filtered = insights; // already filtered by API

  return (
    <AppLayout>
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        <PageHeader
          title="Intelligence Feed"
          subtitle={`${unreadCount} new insight${unreadCount !== 1 ? 's' : ''} — proactive monitoring active`}
          icon={<Zap className="w-6 h-6 text-indigo-400" />}
        />

        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Filter tabs */}
          <div className="flex gap-1 p-1 bg-white/5 rounded-lg border border-white/10">
            {(['all', 'unread', 'critical'] as const).map(f => (
              <button
                key={f}
                onClick={() => { setFilter(f); setLoading(true); }}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
                  filter === f
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {f}
                {f === 'unread' && unreadCount > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-indigo-500 rounded-full">
                    {unreadCount}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-sm text-gray-300 transition-colors"
              >
                <CheckCheck className="w-4 h-4" />
                Mark all read
              </button>
            )}
            <button
              onClick={handleScanNow}
              disabled={scanning}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white transition-colors disabled:opacity-50"
            >
              {scanning
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <Play className="w-4 h-4" />
              }
              {scanning ? 'Scanning…' : 'Scan Now'}
            </button>
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Feed */}
          <div className="lg:col-span-2 space-y-3">
            {loading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-28 rounded-xl bg-white/5 animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-20 text-gray-500">
                <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No insights yet.</p>
                <p className="text-xs mt-1">Click &quot;Scan Now&quot; to run your first analysis.</p>
              </div>
            ) : (
              <AnimatePresence mode="popLayout">
                {filtered.map(insight => (
                  <InsightCard key={insight.id} insight={insight} onRead={handleMarkRead} />
                ))}
              </AnimatePresence>
            )}
          </div>

          {/* Sidebar: config + stats */}
          <div className="space-y-4">
            {/* Stats */}
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">This Session</h3>
              {[
                { label: 'Total Insights', value: insights.length },
                { label: 'Unread', value: unreadCount },
                { label: 'Critical', value: insights.filter(i => i.severity === 'critical').length },
                { label: 'Anomalies', value: insights.filter(i => i.insight_type === 'anomaly').length },
                { label: 'Trend Shifts', value: insights.filter(i => i.insight_type === 'trend_shift').length },
                { label: 'Records', value: insights.filter(i => ['record_high', 'record_low'].includes(i.insight_type)).length },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between text-sm">
                  <span className="text-gray-400">{label}</span>
                  <span className="text-white font-semibold">{value}</span>
                </div>
              ))}
            </div>

            {/* Config panel */}
            {config && <ConfigPanel config={config} onSave={handleSaveConfig} />}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
