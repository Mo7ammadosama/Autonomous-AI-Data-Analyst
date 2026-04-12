'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bell, Plus, Trash2, PlayCircle, CheckCircle2, AlertTriangle,
  XCircle, ChevronDown, ChevronUp, RefreshCw, Clock,
  Send, Hash, Globe
} from 'lucide-react';
import { toast } from 'sonner';
import { alertsApi, datasetsApi } from '@/lib/api';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';

interface Alert {
  id: string;
  name: string;
  description?: string;
  dataset_id?: string;
  column_name?: string;
  condition: string;
  threshold?: number;
  aggregation?: string;
  notify_email: boolean;
  email_recipient?: string;
  notify_slack: boolean;
  slack_webhook_url?: string;
  notify_teams: boolean;
  teams_webhook_url?: string;
  notify_telegram: boolean;
  telegram_chat_id?: string;
  is_active: boolean;
  status: string;
  last_checked?: string;
  last_triggered?: string;
  trigger_count: number;
  created_at: string;
}

interface Dataset {
  id: string;
  name: string;
  status: string;
  columns_meta?: Record<string, unknown>;
}

const CONDITIONS = [
  { value: 'gt',      label: 'Greater than (>)' },
  { value: 'lt',      label: 'Less than (<)' },
  { value: 'gte',     label: 'Greater than or equal (>=)' },
  { value: 'lte',     label: 'Less than or equal (<=)' },
  { value: 'eq',      label: 'Equal to (=)' },
  { value: 'anomaly', label: 'Anomaly detected' },
];

const AGGREGATIONS = [
  { value: 'mean',   label: 'Mean (average)' },
  { value: 'sum',    label: 'Sum (total)' },
  { value: 'max',    label: 'Maximum' },
  { value: 'min',    label: 'Minimum' },
  { value: 'count',  label: 'Count (rows)' },
  { value: 'latest', label: 'Latest value' },
];

const statusColors: Record<string, string> = {
  active: 'text-emerald-400 bg-emerald-400/10',
  fired:  'text-amber-400 bg-amber-400/10',
  paused: 'text-slate-400 bg-slate-400/10',
};

const statusIcons: Record<string, React.ReactNode> = {
  active: <CheckCircle2 className="w-3.5 h-3.5" />,
  fired:  <AlertTriangle className="w-3.5 h-3.5" />,
  paused: <XCircle className="w-3.5 h-3.5" />,
};

const EMPTY_FORM = {
  name: '',
  description: '',
  dataset_id: '',
  column_name: '',
  condition: 'gt',
  threshold: '',
  aggregation: 'mean',
  // Email
  notify_email: true,
  email_recipient: '',
  // Slack
  notify_slack: false,
  slack_webhook_url: '',
  // Teams
  notify_teams: false,
  teams_webhook_url: '',
  // Telegram
  notify_telegram: false,
  telegram_bot_token: '',
  telegram_chat_id: '',
};

export default function AlertsPage() {
  const [alerts, setAlerts]   = useState<Alert[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [evaluating, setEvaluating] = useState<string | null>(null);
  const [expandedLogs, setExpandedLogs] = useState<string | null>(null);
  const [logs, setLogs] = useState<Record<string, any[]>>({});
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [datasetColumns, setDatasetColumns] = useState<string[]>([]);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [alertsRes, datasetsRes] = await Promise.all([
        alertsApi.list(),
        datasetsApi.list(),
      ]);
      setAlerts(alertsRes.data);
      setDatasets(datasetsRes.data.filter((d: Dataset) => d.status === 'ready'));
    } catch {
      toast.error('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }

  async function onDatasetChange(datasetId: string) {
    setForm(f => ({ ...f, dataset_id: datasetId, column_name: '' }));
    if (!datasetId) { setDatasetColumns([]); return; }
    try {
      const res = await datasetsApi.profile(datasetId);
      const cols = Object.keys(res.data?.columns || {}).filter(c => {
        const info = res.data?.columns?.[c];
        return info?.dtype?.includes('float') || info?.dtype?.includes('int');
      });
      setDatasetColumns(cols);
    } catch {
      setDatasetColumns([]);
    }
  }

  async function createAlert(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Alert name is required');
    if (form.condition !== 'anomaly' && !form.threshold) return toast.error('Threshold is required');
    if (form.notify_slack && !form.slack_webhook_url) return toast.error('Slack webhook URL is required');
    if (form.notify_teams && !form.teams_webhook_url) return toast.error('Teams webhook URL is required');
    if (form.notify_telegram && (!form.telegram_bot_token || !form.telegram_chat_id))
      return toast.error('Telegram bot token and chat ID are required');

    try {
      await alertsApi.create({
        ...form,
        threshold: form.threshold ? parseFloat(form.threshold) : undefined,
      });
      toast.success('Alert created');
      setShowCreate(false);
      setForm({ ...EMPTY_FORM });
      await loadData();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create alert');
    }
  }

  async function deleteAlert(id: string) {
    if (!confirm('Delete this alert?')) return;
    try {
      await alertsApi.delete(id);
      toast.success('Alert deleted');
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch {
      toast.error('Failed to delete alert');
    }
  }

  async function toggleAlert(alert: Alert) {
    try {
      await alertsApi.update(alert.id, { is_active: !alert.is_active });
      setAlerts(prev => prev.map(a => a.id === alert.id ? { ...a, is_active: !a.is_active } : a));
      toast.success(alert.is_active ? 'Alert paused' : 'Alert activated');
    } catch {
      toast.error('Failed to update alert');
    }
  }

  async function evaluateAlert(id: string) {
    setEvaluating(id);
    try {
      const res = await alertsApi.evaluate(id);
      const result = res.data?.results?.[0];
      if (result?.triggered) {
        toast.warning(`Alert fired: ${result.message}`);
      } else {
        toast.success(`OK: ${result?.message || 'Condition not met'}`);
      }
      await loadData();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Evaluation failed');
    } finally {
      setEvaluating(null);
    }
  }

  async function loadLogs(alertId: string) {
    if (expandedLogs === alertId) { setExpandedLogs(null); return; }
    try {
      const res = await alertsApi.logs(alertId, 10);
      setLogs(prev => ({ ...prev, [alertId]: res.data }));
      setExpandedLogs(alertId);
    } catch {
      toast.error('Failed to load logs');
    }
  }

  // Channel badges shown per alert card
  function channelBadges(alert: Alert) {
    const badges = [];
    if (alert.notify_email) badges.push({ label: 'Email', color: 'bg-blue-400/10 text-blue-400' });
    if (alert.notify_slack) badges.push({ label: 'Slack', color: 'bg-emerald-400/10 text-emerald-400' });
    if (alert.notify_teams) badges.push({ label: 'Teams', color: 'bg-violet-400/10 text-violet-400' });
    if (alert.notify_telegram) badges.push({ label: 'Telegram', color: 'bg-cyan-400/10 text-cyan-400' });
    return badges;
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <PageHeader
            title="Data Alerts"
            description="Monitor your datasets with threshold-based and anomaly detection alerts"
            icon={<Bell className="w-5 h-5 text-amber-400" />}
          />
          <div className="flex items-center gap-2">
            <button onClick={loadData} className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" /> New Alert
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Total Alerts', value: alerts.length, color: 'text-indigo-400' },
            { label: 'Active', value: alerts.filter(a => a.is_active).length, color: 'text-emerald-400' },
            { label: 'Fired Today', value: alerts.filter(a => a.status === 'fired').length, color: 'text-amber-400' },
          ].map(stat => (
            <div key={stat.label} className="glass rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">{stat.label}</p>
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Create form */}
        <AnimatePresence>
          {showCreate && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="glass rounded-2xl p-6 border border-indigo-500/20"
            >
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-400" /> Create New Alert
              </h3>
              <form onSubmit={createAlert} className="space-y-5">
                {/* ── Core fields ── */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="text-xs text-slate-400 mb-1 block">Alert Name *</label>
                    <input
                      value={form.name}
                      onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      placeholder="e.g. Revenue drops below 10k"
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      required
                    />
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Dataset</label>
                    <select
                      value={form.dataset_id}
                      onChange={e => onDatasetChange(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      <option value="">No dataset</option>
                      {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Column</label>
                    {datasetColumns.length > 0 ? (
                      <select
                        value={form.column_name}
                        onChange={e => setForm(f => ({ ...f, column_name: e.target.value }))}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                      >
                        <option value="">Select column</option>
                        {datasetColumns.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    ) : (
                      <input
                        value={form.column_name}
                        onChange={e => setForm(f => ({ ...f, column_name: e.target.value }))}
                        placeholder="e.g. revenue"
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    )}
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Condition *</label>
                    <select
                      value={form.condition}
                      onChange={e => setForm(f => ({ ...f, condition: e.target.value }))}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      {CONDITIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </div>

                  {form.condition !== 'anomaly' && (
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">Threshold *</label>
                      <input
                        type="number"
                        value={form.threshold}
                        onChange={e => setForm(f => ({ ...f, threshold: e.target.value }))}
                        placeholder="e.g. 10000"
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  )}

                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">Aggregation</label>
                    <select
                      value={form.aggregation}
                      onChange={e => setForm(f => ({ ...f, aggregation: e.target.value }))}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      {AGGREGATIONS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                    </select>
                  </div>
                </div>

                {/* ── Notification channels ── */}
                <div className="border border-white/10 rounded-xl p-4 space-y-4">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Notification Channels</p>

                  {/* Email */}
                  <div>
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer mb-2">
                      <input
                        type="checkbox"
                        checked={form.notify_email}
                        onChange={e => setForm(f => ({ ...f, notify_email: e.target.checked }))}
                        className="rounded border-white/20 bg-white/5"
                      />
                      <Send className="w-3.5 h-3.5 text-blue-400" /> Email
                    </label>
                    {form.notify_email && (
                      <input
                        type="email"
                        value={form.email_recipient}
                        onChange={e => setForm(f => ({ ...f, email_recipient: e.target.value }))}
                        placeholder="recipient@example.com"
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    )}
                  </div>

                  {/* Slack */}
                  <div>
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer mb-2">
                      <input
                        type="checkbox"
                        checked={form.notify_slack}
                        onChange={e => setForm(f => ({ ...f, notify_slack: e.target.checked }))}
                        className="rounded border-white/20 bg-white/5"
                      />
                      <Hash className="w-3.5 h-3.5 text-emerald-400" /> Slack
                    </label>
                    {form.notify_slack && (
                      <input
                        type="url"
                        value={form.slack_webhook_url}
                        onChange={e => setForm(f => ({ ...f, slack_webhook_url: e.target.value }))}
                        placeholder="https://hooks.slack.com/services/..."
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    )}
                  </div>

                  {/* Teams */}
                  <div>
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer mb-2">
                      <input
                        type="checkbox"
                        checked={form.notify_teams}
                        onChange={e => setForm(f => ({ ...f, notify_teams: e.target.checked }))}
                        className="rounded border-white/20 bg-white/5"
                      />
                      <Globe className="w-3.5 h-3.5 text-violet-400" /> Microsoft Teams
                    </label>
                    {form.notify_teams && (
                      <input
                        type="url"
                        value={form.teams_webhook_url}
                        onChange={e => setForm(f => ({ ...f, teams_webhook_url: e.target.value }))}
                        placeholder="https://outlook.office.com/webhook/..."
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    )}
                  </div>

                  {/* Telegram */}
                  <div>
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer mb-2">
                      <input
                        type="checkbox"
                        checked={form.notify_telegram}
                        onChange={e => setForm(f => ({ ...f, notify_telegram: e.target.checked }))}
                        className="rounded border-white/20 bg-white/5"
                      />
                      <Send className="w-3.5 h-3.5 text-cyan-400" /> Telegram
                    </label>
                    {form.notify_telegram && (
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          value={form.telegram_bot_token}
                          onChange={e => setForm(f => ({ ...f, telegram_bot_token: e.target.value }))}
                          placeholder="Bot token"
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        />
                        <input
                          value={form.telegram_chat_id}
                          onChange={e => setForm(f => ({ ...f, telegram_chat_id: e.target.value }))}
                          placeholder="Chat ID"
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => setShowCreate(false)}
                    className="px-4 py-2 rounded-xl text-sm text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors"
                  >
                    Create Alert
                  </button>
                </div>
              </form>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Alerts list */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="glass rounded-xl h-20 animate-pulse" />)}
          </div>
        ) : alerts.length === 0 ? (
          <div className="glass rounded-2xl p-12 text-center">
            <Bell className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No alerts configured yet</p>
            <p className="text-slate-600 text-xs mt-1">Create an alert to get notified when your data crosses a threshold</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map(alert => (
              <motion.div
                key={alert.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass rounded-xl overflow-hidden"
              >
                <div className="p-4 flex items-center gap-4">
                  {/* Status */}
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${statusColors[alert.status] || statusColors.active}`}>
                    {statusIcons[alert.status] || statusIcons.active}
                    {alert.status}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{alert.name}</p>
                    <div className="flex items-center gap-2 flex-wrap mt-0.5">
                      <span className="text-xs text-slate-500">
                        {alert.column_name && `${alert.aggregation}(${alert.column_name}) `}
                        {CONDITIONS.find(c => c.value === alert.condition)?.label}
                        {alert.threshold != null && ` ${alert.threshold}`}
                        {' · '}Triggered {alert.trigger_count}×
                        {alert.last_triggered && ` · Last: ${new Date(alert.last_triggered).toLocaleDateString()}`}
                      </span>
                      {/* Channel badges */}
                      {channelBadges(alert).map(b => (
                        <span key={b.label} className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${b.color}`}>{b.label}</span>
                      ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => evaluateAlert(alert.id)}
                      disabled={evaluating === alert.id || !alert.dataset_id}
                      title="Evaluate now"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-400/10 transition-colors disabled:opacity-40"
                    >
                      {evaluating === alert.id
                        ? <RefreshCw className="w-4 h-4 animate-spin" />
                        : <PlayCircle className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => toggleAlert(alert)}
                      title={alert.is_active ? 'Pause' : 'Activate'}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-indigo-400/10 transition-colors"
                    >
                      {alert.is_active ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => loadLogs(alert.id)}
                      title="View logs"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
                    >
                      {expandedLogs === alert.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => deleteAlert(alert.id)}
                      title="Delete"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Logs panel */}
                <AnimatePresence>
                  {expandedLogs === alert.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-white/5 bg-black/20 px-4 py-3"
                    >
                      <p className="text-xs text-slate-500 mb-2 font-medium uppercase tracking-wider">Trigger History</p>
                      {!logs[alert.id] || logs[alert.id].length === 0 ? (
                        <p className="text-xs text-slate-600">No trigger events recorded</p>
                      ) : (
                        <div className="space-y-1.5">
                          {logs[alert.id].map(log => (
                            <div key={log.id} className="flex items-start gap-2 text-xs">
                              <Clock className="w-3 h-3 text-slate-600 mt-0.5 flex-shrink-0" />
                              <span className="text-slate-500 flex-shrink-0">
                                {new Date(log.triggered_at).toLocaleString()}
                              </span>
                              <span className="text-slate-300">{log.message}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
