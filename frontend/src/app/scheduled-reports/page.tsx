'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, Plus, Trash2, Send, Clock, RefreshCw,
  Calendar, Mail, ToggleLeft, ToggleRight, CheckCircle2
} from 'lucide-react';
import { toast } from 'sonner';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import api from '@/lib/api';

interface ScheduledReport {
  id: string;
  dataset_id: string;
  title: string;
  frequency: string;
  email_recipient: string;
  is_active: boolean;
  last_sent?: string;
  next_run?: string;
  created_at: string;
}

interface Dataset { id: string; name: string; status: string; }

const FREQ_LABELS: Record<string, { label: string; color: string }> = {
  daily:   { label: 'Daily',   color: 'text-emerald-400 bg-emerald-400/10' },
  weekly:  { label: 'Weekly',  color: 'text-indigo-400 bg-indigo-400/10' },
  monthly: { label: 'Monthly', color: 'text-violet-400 bg-violet-400/10' },
};

export default function ScheduledReportsPage() {
  const [reports, setReports] = useState<ScheduledReport[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [form, setForm] = useState({
    dataset_id: '', title: '', frequency: 'weekly', email_recipient: '',
  });

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [rRes, dRes] = await Promise.all([
        api.get('/api/scheduled-reports/'),
        api.get('/api/datasets/'),
      ]);
      setReports(rRes.data);
      setDatasets(dRes.data.filter((d: Dataset) => d.status === 'ready'));
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!form.dataset_id || !form.title || !form.email_recipient)
      return toast.error('All fields required');
    try {
      await api.post('/api/scheduled-reports/', form);
      toast.success('Report schedule created');
      setShowCreate(false);
      setForm({ dataset_id: '', title: '', frequency: 'weekly', email_recipient: '' });
      await loadAll();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Failed to create'); }
  }

  async function sendNow(id: string) {
    setSending(id);
    try {
      await api.post(`/api/scheduled-reports/${id}/send-now`);
      toast.success('Report queued for delivery');
    } catch { toast.error('Failed to send'); }
    finally { setSending(null); }
  }

  async function toggle(report: ScheduledReport) {
    try {
      await api.put(`/api/scheduled-reports/${report.id}`, { is_active: !report.is_active });
      setReports(prev => prev.map(r => r.id === report.id ? { ...r, is_active: !r.is_active } : r));
      toast.success(report.is_active ? 'Schedule paused' : 'Schedule activated');
    } catch { toast.error('Update failed'); }
  }

  async function remove(id: string) {
    if (!confirm('Delete this schedule?')) return;
    try {
      await api.delete(`/api/scheduled-reports/${id}`);
      setReports(prev => prev.filter(r => r.id !== id));
      toast.success('Schedule deleted');
    } catch { toast.error('Delete failed'); }
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <div className="flex items-center justify-between">
          <PageHeader
            title="Scheduled Reports"
            description="Automatically generate and email PDF reports on a recurring schedule"
            icon={<Calendar className="w-5 h-5 text-rose-400" />}
          />
          <button onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors">
            <Plus className="w-4 h-4" /> New Schedule
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Schedules', value: reports.length, color: 'text-indigo-400' },
            { label: 'Active',    value: reports.filter(r => r.is_active).length, color: 'text-emerald-400' },
            { label: 'Sent Total', value: reports.filter(r => r.last_sent).length, color: 'text-violet-400' },
          ].map(s => (
            <div key={s.label} className="glass rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">{s.label}</p>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Create form */}
        <AnimatePresence>
          {showCreate && (
            <motion.form onSubmit={create}
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              className="glass rounded-2xl p-6 border border-indigo-500/20 grid grid-cols-2 gap-4">
              <h3 className="col-span-2 text-sm font-semibold text-white flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-400" /> New Report Schedule
              </h3>

              <div>
                <label className="text-xs text-slate-400 mb-1 block">Report Title *</label>
                <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="Weekly Sales Summary" required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
              </div>

              <div>
                <label className="text-xs text-slate-400 mb-1 block">Dataset *</label>
                <select value={form.dataset_id} onChange={e => setForm(f => ({ ...f, dataset_id: e.target.value }))} required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                  <option value="">Select dataset…</option>
                  {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-400 mb-1 block">Frequency</label>
                <select value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1"><Mail className="w-3 h-3" /> Recipient Email *</label>
                <input type="email" value={form.email_recipient} onChange={e => setForm(f => ({ ...f, email_recipient: e.target.value }))}
                  placeholder="you@company.com" required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
              </div>

              <div className="col-span-2 flex justify-end gap-2">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl text-sm text-slate-400 hover:text-white hover:bg-white/5 transition-colors">Cancel</button>
                <button type="submit"
                  className="px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors">
                  Create Schedule
                </button>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        {/* Reports list */}
        {loading ? (
          <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="glass rounded-xl h-20 animate-pulse" />)}</div>
        ) : reports.length === 0 ? (
          <div className="glass rounded-2xl p-12 text-center">
            <FileText className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No scheduled reports yet</p>
            <p className="text-slate-600 text-xs mt-1">Set up automated PDF report delivery to your inbox</p>
          </div>
        ) : (
          <div className="space-y-3">
            {reports.map(report => {
              const freq = FREQ_LABELS[report.frequency] || { label: report.frequency, color: 'text-slate-400 bg-slate-400/10' };
              return (
                <motion.div key={report.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                  className="glass rounded-xl p-4 flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-rose-500/20 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-rose-400" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-medium text-white truncate">{report.title}</p>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${freq.color}`}>{freq.label}</span>
                      {!report.is_active && <span className="text-[10px] text-slate-500 bg-slate-500/10 px-2 py-0.5 rounded-full">Paused</span>}
                    </div>
                    <p className="text-xs text-slate-500">
                      <Mail className="w-3 h-3 inline mr-1" />{report.email_recipient}
                      {report.last_sent && <> · Last sent: {new Date(report.last_sent).toLocaleDateString()}</>}
                      {report.next_run && <> · Next: {new Date(report.next_run).toLocaleDateString()}</>}
                    </p>
                  </div>

                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => sendNow(report.id)} disabled={sending === report.id} title="Send now"
                      className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-400/10 transition-colors disabled:opacity-40">
                      {sending === report.id ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                    <button onClick={() => toggle(report)} title={report.is_active ? 'Pause' : 'Activate'}
                      className="p-2 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-indigo-400/10 transition-colors">
                      {report.is_active
                        ? <ToggleRight className="w-4 h-4 text-indigo-400" />
                        : <ToggleLeft className="w-4 h-4" />}
                    </button>
                    <button onClick={() => remove(report.id)} title="Delete"
                      className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
