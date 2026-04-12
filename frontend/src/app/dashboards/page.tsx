'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  PanelsTopLeft, Plus, Trash2, Eye, Sparkles, BarChart2,
  Zap, Database, X, RefreshCw, CheckCircle2
} from 'lucide-react';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import ChartGrid from '@/components/charts/ChartGrid';
import { toast } from 'sonner';
import { dashboardsApi, datasetsApi, analyticsApi } from '@/lib/api';
import { formatDate } from '@/lib/utils';

const TEMPLATES = [
  { id: 'overview', label: 'Overview', desc: 'Top metrics + distribution charts', icon: BarChart2, chartCount: 4 },
  { id: 'trends', label: 'Trends', desc: 'Time series + growth analysis', icon: Sparkles, chartCount: 4 },
  { id: 'custom', label: 'Custom', desc: 'Describe what you want with AI', icon: Zap, chartCount: 6 },
];

export default function DashboardsPage() {
  const [dashboards, setDashboards] = useState<any[]>([]);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<any>(null);
  const [form, setForm] = useState({ title: '', command: '', dataset_id: '', template: 'overview' });
  const [loading, setLoading] = useState(true);
  const [createLoading, setCreateLoading] = useState(false);
  const [createStep, setCreateStep] = useState<'idle' | 'generating' | 'saving'>('idle');

  useEffect(() => {
    Promise.all([dashboardsApi.list(), datasetsApi.list()]).then(([db, ds]) => {
      setDashboards(db.data);
      const ready = ds.data.filter((d: any) => d.status === 'ready');
      setDatasets(ready);
      if (ready.length > 0) setForm(f => ({ ...f, dataset_id: ready[0].id }));
      setLoading(false);
    });
  }, []);

  const handleCreate = async () => {
    if (!form.title) return;
    setCreateLoading(true);
    setCreateStep('generating');

    try {
      let charts: any[] = [];

      // Auto-generate charts from dataset if one is selected
      if (form.dataset_id) {
        try {
          const chartsRes = await analyticsApi.charts(form.dataset_id, 6);
          charts = chartsRes.data.charts || [];
        } catch {}
      }

      setCreateStep('saving');

      // Build the description from template + command
      const templateDescriptions: Record<string, string> = {
        overview: 'Overview dashboard with key metrics and distributions',
        trends: 'Trends dashboard with time series and growth analysis',
        custom: form.command || 'Custom analytics dashboard',
      };
      const description = form.template === 'custom' && form.command
        ? form.command
        : templateDescriptions[form.template];

      const res = await dashboardsApi.create({
        title: form.title,
        description,
        dataset_id: form.dataset_id || undefined,
        charts,
      });

      setDashboards(prev => [res.data, ...prev]);
      setViewing({ ...res.data, charts });
      setCreating(false);
      setForm({ title: '', command: '', dataset_id: datasets[0]?.id || '', template: 'overview' });
      toast.success(`Dashboard "${form.title}" created`, {
        description: charts.length > 0 ? `${charts.length} charts auto-generated.` : undefined,
      });
    } catch {
      toast.error('Failed to create dashboard', { description: 'Please try again.' });
    } finally {
      setCreateLoading(false);
      setCreateStep('idle');
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this dashboard?')) return;
    try {
      await dashboardsApi.delete(id);
      setDashboards(d => d.filter(x => x.id !== id));
      if (viewing?.id === id) setViewing(null);
      toast.success('Dashboard deleted');
    } catch {
      toast.error('Failed to delete dashboard');
    }
  };

  const loadDashboard = async (id: string) => {
    try {
      const res = await dashboardsApi.get(id);
      setViewing(res.data);
    } catch {
      toast.error('Failed to load dashboard', { description: 'Please try again.' });
    }
  };

  const getStepLabel = () => {
    if (createStep === 'generating') return 'Generating charts from dataset...';
    if (createStep === 'saving') return 'Saving dashboard...';
    return '';
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-5 max-w-7xl">
        <PageHeader
          title="Dashboards"
          subtitle="Build and manage your analytics dashboards"
          icon={<PanelsTopLeft className="w-5 h-5 text-cyan-400" />}
          action={
            <motion.button
              onClick={() => setCreating(true)}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition-colors shadow-lg shadow-indigo-500/25"
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            >
              <Plus className="w-4 h-4" /> New Dashboard
            </motion.button>
          }
        />

        {/* Create modal */}
        <AnimatePresence>
          {creating && (
            <motion.div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            >
              <div
                className="absolute inset-0 bg-black/70 backdrop-blur-sm"
                onClick={() => !createLoading && setCreating(false)}
              />
              <motion.div
                className="relative z-10 glass rounded-2xl border border-white/10 w-full max-w-lg p-6"
                initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }}
              >
                <div className="flex items-center justify-between mb-5">
                  <h3 className="text-lg font-display font-bold text-white">Create Dashboard</h3>
                  <button onClick={() => !createLoading && setCreating(false)} className="text-slate-500 hover:text-white transition-colors">
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="space-y-4">
                  {/* Title */}
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">Dashboard Title *</label>
                    <input
                      value={form.title}
                      onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                      placeholder="Sales Performance Dashboard"
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50"
                    />
                  </div>

                  {/* Dataset picker */}
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">
                      Dataset <span className="text-slate-600">(auto-generates charts)</span>
                    </label>
                    <select
                      value={form.dataset_id}
                      onChange={e => setForm(f => ({ ...f, dataset_id: e.target.value }))}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500/50"
                    >
                      <option value="">No dataset (empty dashboard)</option>
                      {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </div>

                  {/* Template selector */}
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-2">Template</label>
                    <div className="grid grid-cols-3 gap-2">
                      {TEMPLATES.map(t => (
                        <button
                          key={t.id}
                          onClick={() => setForm(f => ({ ...f, template: t.id }))}
                          className={`p-3 rounded-xl border text-left transition-all ${
                            form.template === t.id
                              ? 'bg-indigo-500/20 border-indigo-500/50 text-white'
                              : 'bg-white/3 border-white/10 text-slate-400 hover:border-white/20'
                          }`}
                        >
                          <t.icon className="w-4 h-4 mb-1.5" />
                          <div className="text-xs font-semibold">{t.label}</div>
                          <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">{t.desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Custom AI command */}
                  {form.template === 'custom' && (
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">AI Command</label>
                      <textarea
                        value={form.command}
                        onChange={e => setForm(f => ({ ...f, command: e.target.value }))}
                        placeholder="Create a sales performance dashboard focused on monthly revenue trends and top products..."
                        rows={3}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 resize-none focus:outline-none focus:border-indigo-500/50"
                      />
                    </div>
                  )}

                  {/* Progress message */}
                  {createLoading && (
                    <div className="flex items-center gap-2 text-xs text-indigo-300 bg-indigo-500/10 border border-indigo-500/20 rounded-lg px-3 py-2">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      {getStepLabel()}
                    </div>
                  )}

                  <div className="flex gap-3 pt-1">
                    <button
                      onClick={() => setCreating(false)}
                      disabled={createLoading}
                      className="flex-1 py-2.5 rounded-xl border border-white/10 text-slate-400 hover:text-white text-sm transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <motion.button
                      onClick={handleCreate}
                      disabled={!form.title || createLoading}
                      className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                      whileTap={{ scale: 0.98 }}
                    >
                      {createLoading
                        ? <><RefreshCw className="w-4 h-4 animate-spin" /> Creating...</>
                        : <><Sparkles className="w-4 h-4" /> Create Dashboard</>
                      }
                    </motion.button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Dashboard list */}
        {loading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {[0, 1, 2].map(i => <div key={i} className="h-48 glass rounded-xl border border-white/5 shimmer" />)}
          </div>
        ) : dashboards.length === 0 ? (
          <motion.div
            className="glass rounded-xl p-16 text-center border border-white/5"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          >
            <PanelsTopLeft className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <h3 className="text-slate-300 font-semibold mb-2">No dashboards yet</h3>
            <p className="text-slate-500 text-sm mb-6 max-w-xs mx-auto">
              Create a dashboard and DataMind will auto-generate charts from your dataset.
            </p>
            <button
              onClick={() => setCreating(true)}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition-colors flex items-center gap-2 mx-auto"
            >
              <Plus className="w-4 h-4" /> Create First Dashboard
            </button>
          </motion.div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {dashboards.map((db, i) => (
              <motion.div
                key={db.id}
                className="glass rounded-xl border border-white/5 overflow-hidden cursor-pointer card-hover group"
                onClick={() => loadDashboard(db.id)}
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
              >
                {/* Thumbnail */}
                <div className="h-28 bg-gradient-to-br from-indigo-600/10 to-violet-600/10 flex items-center justify-center border-b border-white/5 relative overflow-hidden">
                  <BarChart2 className="w-10 h-10 text-indigo-400/30 group-hover:text-indigo-400/50 transition-colors" />
                  {db.chart_count > 0 && (
                    <div className="absolute bottom-2 right-3 flex items-center gap-1 text-xs text-slate-500">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      {db.chart_count} charts
                    </div>
                  )}
                </div>
                <div className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-white group-hover:text-indigo-300 transition-colors">
                        {db.title}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {db.chart_count || 0} charts · {db.created_at ? formatDate(db.created_at) : ''}
                      </p>
                      {db.description && (
                        <p className="text-xs text-slate-600 mt-1 truncate max-w-[180px]">{db.description}</p>
                      )}
                    </div>
                    <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={(e) => { e.stopPropagation(); loadDashboard(db.id); }}
                        title="View dashboard"
                        className="p-1.5 text-slate-500 hover:text-indigo-400 transition-colors rounded-lg hover:bg-indigo-500/10"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={e => handleDelete(db.id, e)}
                        className="p-1.5 text-slate-500 hover:text-red-400 transition-colors rounded-lg hover:bg-red-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* View dashboard modal */}
        <AnimatePresence>
          {viewing && (
            <motion.div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            >
              <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => setViewing(null)} />
              <motion.div
                className="relative z-10 glass rounded-2xl border border-white/10 w-full max-w-6xl max-h-[90vh] overflow-auto"
                initial={{ scale: 0.95 }} animate={{ scale: 1 }}
              >
                <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between sticky top-0 glass z-10">
                  <div>
                    <h3 className="font-display font-bold text-white">{viewing.title}</h3>
                    {viewing.description && (
                      <p className="text-xs text-slate-500 mt-0.5">{viewing.description}</p>
                    )}
                  </div>
                  <button onClick={() => setViewing(null)} className="text-slate-500 hover:text-white transition-colors">
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <div className="p-6">
                  {viewing.charts?.length > 0 ? (
                    <ChartGrid charts={viewing.charts} columns={2} chartHeight={280} />
                  ) : (
                    <div className="text-center py-16 text-slate-500">
                      <BarChart2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
                      <p className="text-sm">No charts in this dashboard.</p>
                      <p className="text-xs mt-1 opacity-70">
                        Delete and re-create with a dataset selected to auto-generate charts.
                      </p>
                    </div>
                  )}
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </AppLayout>
  );
}
