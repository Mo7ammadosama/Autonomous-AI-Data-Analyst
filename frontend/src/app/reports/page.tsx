'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  FileText, Download, BarChart2, Lightbulb, Database, RefreshCw,
  BookOpen, Brain, TrendingUp, ShieldAlert
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import ChartGrid from '@/components/charts/ChartGrid';
import { toast } from 'sonner';
import { reportsApi, datasetsApi, pipelineApi } from '@/lib/api';
import { formatBytes } from '@/lib/utils';

export default function ReportsPage() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [summary, setSummary] = useState<any>(null);
  const [pipeline, setPipeline] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    datasetsApi.list().then(res => {
      setDatasets(res.data);
      if (res.data[0]) setSelectedId(res.data[0].id);
    });
  }, []);

  useEffect(() => {
    if (selectedId) {
      loadSummary();
      loadPipeline();
    }
  }, [selectedId]);

  const loadSummary = async () => {
    setLoading(true);
    setSummary(null);
    try {
      const res = await reportsApi.summary(selectedId);
      setSummary(res.data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const loadPipeline = async () => {
    try {
      const res = await pipelineApi.get(selectedId);
      setPipeline(res.data);
    } catch {
      setPipeline(null);
    }
  };

  const handleDownloadPdf = async () => {
    if (!selectedId) return;
    setDownloading(true);
    try {
      const res = await reportsApi.generatePdf(
        selectedId,
        summary?.dataset?.name ? `${summary.dataset.name} - Analysis Report` : undefined
      );
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${selectedId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF report downloaded', {
        description: summary?.dataset?.name ? `${summary.dataset.name} — full analysis report` : undefined,
      });
    } catch {
      toast.error('PDF generation failed', {
        description: 'Make sure reportlab is installed: pip install reportlab',
      });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-5 max-w-7xl">
        <PageHeader
          title="Reports"
          subtitle="Generate comprehensive analysis reports"
          icon={<FileText className="w-5 h-5 text-emerald-400" />}
          action={
            <div className="flex gap-3">
              <select
                value={selectedId}
                onChange={e => setSelectedId(e.target.value)}
                className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
              >
                <option value="">Select dataset...</option>
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              {selectedId && (
                <motion.button
                  onClick={handleDownloadPdf}
                  disabled={downloading || loading}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 rounded-xl text-sm font-medium border border-emerald-500/20 transition-colors disabled:opacity-50"
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                >
                  {downloading
                    ? <div className="w-4 h-4 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                    : <Download className="w-4 h-4" />
                  }
                  Download PDF
                </motion.button>
              )}
            </div>
          }
        />

        {!selectedId ? (
          <div className="glass rounded-xl p-16 text-center border border-white/5">
            <Database className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Select a dataset to generate a report</p>
          </div>
        ) : loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[0, 1, 2, 3].map(i => <div key={i} className="h-24 glass rounded-xl border border-white/5 shimmer" />)}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {[0, 1].map(i => <div key={i} className="h-64 glass rounded-xl border border-white/5 shimmer" />)}
            </div>
          </div>
        ) : summary ? (
          <div className="space-y-6">
            {/* Dataset overview cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { label: 'Total Rows',  value: summary.dataset?.rows?.toLocaleString() || '–',  icon: Database,   color: 'text-indigo-400' },
                { label: 'Columns',     value: summary.dataset?.columns || '–',                  icon: BarChart2,  color: 'text-violet-400' },
                { label: 'AI Insights', value: summary.insights?.length || 0,                    icon: Lightbulb,  color: 'text-amber-400'  },
                { label: 'Charts',      value: summary.charts?.length || 0,                      icon: FileText,   color: 'text-emerald-400' },
              ].map((s, i) => (
                <motion.div
                  key={s.label}
                  className="glass rounded-xl p-4 border border-white/5"
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
                >
                  <s.icon className={`w-5 h-5 ${s.color} mb-2`} />
                  <div className="text-2xl font-display font-bold text-white">{s.value}</div>
                  <div className="text-xs text-slate-500">{s.label}</div>
                </motion.div>
              ))}
            </div>

            {/* Pipeline Data Story — shown if pipeline ran */}
            {pipeline?.status === 'done' && pipeline?.story && (
              <motion.div
                className="glass rounded-xl border border-indigo-500/20 overflow-hidden"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
              >
                <div className="px-5 py-3.5 border-b border-white/5 flex items-center gap-2 bg-indigo-500/5">
                  <div className="p-1.5 rounded-lg bg-indigo-500/15 border border-indigo-500/25">
                    <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                  </div>
                  <span className="text-sm font-semibold text-white">AI Data Story</span>
                  <span className="text-xs text-slate-500 bg-white/5 px-2 py-0.5 rounded-full ml-1">Pipeline Generated</span>
                </div>
                <div className="p-5 prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed">
                  <ReactMarkdown>{pipeline.story}</ReactMarkdown>
                </div>
              </motion.div>
            )}

            {/* Pipeline Recommendations */}
            {pipeline?.status === 'done' && pipeline?.recommendations?.length > 0 && (
              <motion.div
                className="glass rounded-xl border border-white/8 overflow-hidden"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
              >
                <div className="px-5 py-3.5 border-b border-white/5 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-white">Business Recommendations</span>
                  <span className="text-xs text-slate-600 ml-1">({pipeline.recommendations.length})</span>
                </div>
                <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {pipeline.recommendations.map((rec: any, i: number) => {
                    const priorityColor: Record<string, string> = {
                      high: 'text-red-400', medium: 'text-yellow-400', low: 'text-green-400',
                    };
                    return (
                      <div key={i} className="p-3.5 rounded-xl bg-white/3 border border-white/8 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold uppercase ${priorityColor[rec.priority] || 'text-slate-400'}`}>
                            {rec.priority}
                          </span>
                          <span className="text-sm font-semibold text-white">{rec.title}</span>
                        </div>
                        <p className="text-xs text-slate-400">{rec.description}</p>
                        <div className="text-xs text-indigo-300 font-medium">→ {rec.ai_action || rec.action}</div>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}

            {/* Pipeline Anomalies */}
            {pipeline?.status === 'done' && pipeline?.anomalies?.summary_alerts?.length > 0 && (
              <motion.div
                className="glass rounded-xl border border-orange-500/15 overflow-hidden"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
              >
                <div className="px-5 py-3.5 border-b border-white/5 flex items-center gap-2 bg-orange-500/5">
                  <ShieldAlert className="w-4 h-4 text-orange-400" />
                  <span className="text-sm font-semibold text-white">Anomaly Alerts</span>
                </div>
                <div className="p-4 space-y-2">
                  {pipeline.anomalies.summary_alerts.map((alert: string, i: number) => (
                    <div key={i} className="flex items-start gap-2 p-3 rounded-lg bg-orange-500/8 border border-orange-500/15 text-orange-300 text-xs">
                      <ShieldAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      <span>{alert}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* Column profile */}
            {summary.profile?.columns && (
              <div className="glass rounded-xl border border-white/5 overflow-hidden">
                <div className="px-5 py-3 border-b border-white/5 flex items-center gap-2">
                  <Database className="w-4 h-4 text-slate-500" />
                  <h3 className="text-sm font-semibold text-white">Column Profile</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-white/5">
                        {['Column', 'Type', 'Unique', 'Missing %', 'Sample'].map(h => (
                          <th key={h} className="px-4 py-2.5 text-left text-slate-500 font-semibold">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(summary.profile.columns).slice(0, 15).map(([col, info]: any) => (
                        <tr key={col} className="border-b border-white/3 hover:bg-white/2">
                          <td className="px-4 py-2.5 text-white font-medium">{col}</td>
                          <td className="px-4 py-2.5">
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-indigo-500/15 text-indigo-300">
                              {info.semantic_type}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-slate-400">{info.unique_count?.toLocaleString()}</td>
                          <td className="px-4 py-2.5">
                            <span className={info.missing_pct > 10 ? 'text-amber-400' : 'text-slate-400'}>
                              {info.missing_pct}%
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-slate-500 truncate max-w-[120px]">
                            {info.sample_values?.slice(0, 2).join(', ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Quick Insights */}
            {summary.insights?.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Lightbulb className="w-4 h-4 text-amber-400" /> AI-Generated Insights
                </h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {summary.insights.map((ins: any, i: number) => (
                    <motion.div
                      key={i}
                      className="glass rounded-xl p-4 border border-white/5"
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.06 }}
                    >
                      <p className="text-sm font-semibold text-white mb-1">{ins.title}</p>
                      <p className="text-xs text-slate-400 leading-relaxed">{ins.content}</p>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}

            {/* Charts */}
            {summary.charts?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                  <BarChart2 className="w-4 h-4 text-indigo-400" /> Visualizations
                </h3>
                <ChartGrid charts={summary.charts} columns={2} />
              </div>
            )}
          </div>
        ) : null}
      </div>
    </AppLayout>
  );
}
