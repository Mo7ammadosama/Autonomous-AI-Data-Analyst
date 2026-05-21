'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Brain, Upload, LayoutTemplate, Zap, ChevronRight, CheckCircle2, XCircle,
  Clock, TrendingUp, TrendingDown, Database, BarChart2, Sparkles, Bell,
  ArrowUpRight, Activity, FileText, Play, AlertTriangle
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import AppLayout from '@/components/layout/AppLayout';
import { agentApi, datasetsApi } from '@/lib/api';
import { useAuthStore } from '@/lib/store';

interface AgentRun {
  id: string;
  task: string;
  status: 'completed' | 'failed' | 'running' | 'pending';
  duration_seconds?: number | null;
  created_at: string;
}

const STATUS_CONFIG = {
  completed: { label: 'Completed', icon: CheckCircle2, className: 'text-emerald-400 bg-emerald-400/10' },
  failed:    { label: 'Failed',    icon: XCircle,       className: 'text-red-400 bg-red-400/10' },
  running:   { label: 'Running',   icon: Clock,         className: 'text-yellow-400 bg-yellow-400/10 animate-pulse' },
  pending:   { label: 'Pending',   icon: Clock,         className: 'text-slate-400 bg-slate-400/10' },
};

function formatDuration(secs?: number | null) {
  if (!secs) return null;
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffH = diffMs / 3_600_000;
  if (diffH < 1) return `${Math.round(diffMs / 60000)}m ago`;
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

const proactiveInsights = [
  { icon: TrendingDown, color: 'text-red-400 bg-red-400/10', title: 'Revenue anomaly detected', desc: 'Tuesday sales 23% below 6-week average — pattern consistent for 3 weeks', severity: 'high' },
  { icon: TrendingUp,   color: 'text-emerald-400 bg-emerald-400/10', title: 'Growth opportunity identified', desc: 'Product line C showing 2.4x conversion rate vs category average', severity: 'medium' },
  { icon: AlertTriangle, color: 'text-amber-400 bg-amber-400/10', title: 'Forecast deviation', desc: 'Q4 trajectory tracking 8% below plan — recommend budget reforecast', severity: 'medium' },
];

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [prompt, setPrompt] = useState('');
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [datasetCount, setDatasetCount] = useState<number | null>(null);

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });

  useEffect(() => {
    agentApi.getRuns()
      .then((res: { data: AgentRun[] }) => setRuns(Array.isArray(res?.data) ? res.data : []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
    datasetsApi.list()
      .then((res: any) => {
        const list = Array.isArray(res?.data) ? res.data : [];
        setDatasetCount(list.length);
      })
      .catch(() => setDatasetCount(0));
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = prompt.trim();
    if (!val) return;
    router.push(`/agent?task=${encodeURIComponent(val)}`);
  };

  const recentRuns = runs.slice(0, 5);
  const completedRuns = runs.filter(r => r.status === 'completed').length;
  const totalRuns = runs.length;
  const avgDuration = runs.filter(r => r.duration_seconds).reduce((a, b) => a + (b.duration_seconds || 0), 0) / Math.max(runs.filter(r => r.duration_seconds).length, 1);
  const estHoursSaved = Math.round(completedRuns * 2.4);

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* ── Top bar ─────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between">
          <motion.div initial={{ opacity: 1, y: 0 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            <h1 className="text-2xl font-bold text-white mb-1">
              Welcome back, <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">{user?.username || 'Analyst'}</span>
            </h1>
            <p className="text-sm text-slate-500">{today}</p>
          </motion.div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              AI Agent Online
            </div>
          </div>
        </div>

        {/* ── Quick action prompt ──────────────────────────────────────── */}
        <motion.div initial={{ opacity: 1, y: 0 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <form onSubmit={handleSubmit} className="relative">
            <div className="absolute left-4 top-1/2 -translate-y-1/2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                <Brain className="w-4 h-4 text-white" />
              </div>
            </div>
            <input
              type="text"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="What would you like to analyze today? e.g. 'Find anomalies in Q4 sales and give me executive insights'"
              className="w-full bg-white/[0.04] border border-white/10 rounded-2xl pl-14 pr-36 py-4 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 focus:bg-white/[0.06] transition-all text-sm shadow-xl"
            />
            <button
              type="submit"
              disabled={!prompt.trim()}
              className="absolute right-2 top-2 bottom-2 px-5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all flex items-center gap-2 shadow-lg shadow-indigo-500/25"
            >
              <Sparkles className="w-4 h-4" />
              Analyze
            </button>
          </form>
        </motion.div>

        {/* ── Quick actions ────────────────────────────────────────────── */}
        <motion.div
          className="grid grid-cols-2 lg:grid-cols-4 gap-4"
          initial={{ opacity: 1, y: 0 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0 }}
        >
          {[
            { icon: Upload, label: 'Analyze New Dataset', desc: 'Upload CSV, Excel, or connect a source', href: '/datasets', gradient: 'from-indigo-500 to-violet-600' },
            { icon: Play,   label: 'Continue Last Analysis', desc: recentRuns[0]?.task ? recentRuns[0].task.slice(0, 40) + '...' : 'No recent runs', href: recentRuns[0] ? `/agent?run_id=${recentRuns[0].id}` : '/agent', gradient: 'from-violet-500 to-purple-600' },
            { icon: LayoutTemplate, label: 'Browse Templates', desc: '20+ industry analysis templates', href: '/templates', gradient: 'from-cyan-500 to-blue-600' },
            { icon: Zap,    label: 'Intelligence Feed', desc: 'Proactive anomaly detection', href: '/proactive', gradient: 'from-amber-500 to-orange-600' },
          ].map((card, i) => (
            <motion.button
              key={card.label}
              onClick={() => router.push(card.href)}
              className="group relative rounded-2xl border border-white/8 bg-white/[0.03] p-5 text-left hover:bg-white/[0.07] hover:border-white/15 transition-all hover:shadow-xl"
              whileHover={{ y: -2 }}
              initial={{ opacity: 1, y: 0 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0 }}
            >
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${card.gradient} flex items-center justify-center mb-3 shadow-lg group-hover:scale-110 transition-transform`}>
                <card.icon className="w-5 h-5 text-white" />
              </div>
              <div className="font-semibold text-white text-sm mb-1">{card.label}</div>
              <div className="text-xs text-slate-500 leading-relaxed truncate">{card.desc}</div>
              <ArrowUpRight className="absolute top-4 right-4 w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors" />
            </motion.button>
          ))}
        </motion.div>

        {/* ── Stats row ────────────────────────────────────────────────── */}
        <motion.div
          className="grid grid-cols-2 lg:grid-cols-4 gap-4"
          initial={{ opacity: 1 }} animate={{ opacity: 1 }} transition={{ delay: 0 }}
        >
          {[
            { label: 'Total Analyses', val: totalRuns, icon: Activity, color: 'text-indigo-400', bg: 'bg-indigo-500/10' },
            { label: 'Datasets Loaded', val: datasetCount ?? '-', icon: Database, color: 'text-violet-400', bg: 'bg-violet-500/10' },
            { label: 'Insights Generated', val: completedRuns * 8, icon: Sparkles, color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
            { label: 'Hours Saved', val: `${estHoursSaved}h`, icon: Clock, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          ].map(({ label, val, icon: Icon, color, bg }) => (
            <div key={label} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-slate-500 font-medium">{label}</span>
                <div className={`w-7 h-7 rounded-lg ${bg} flex items-center justify-center`}>
                  <Icon className={`w-3.5 h-3.5 ${color}`} />
                </div>
              </div>
              <div className="text-2xl font-bold text-white">{val}</div>
            </div>
          ))}
        </motion.div>

        {/* ── Main grid: Recent runs + Proactive insights ──────────────── */}
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Recent Runs */}
          <motion.div
            className="lg:col-span-2 rounded-2xl border border-white/8 bg-white/[0.03]"
            initial={{ opacity: 1, y: 0 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0 }}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
              <div className="flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-white">Recent Analyses</h2>
              </div>
              <button onClick={() => router.push('/agent')} className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1">
                View all <ChevronRight className="w-3 h-3" />
              </button>
            </div>

            <div className="p-4 space-y-2">
              {loading ? (
                [...Array(4)].map((_, i) => <div key={i} className="h-14 rounded-xl bg-white/5 animate-pulse" />)
              ) : recentRuns.length === 0 ? (
                <div className="text-center py-10 text-slate-500 text-sm">
                  No analyses yet. Ask your first question above.
                </div>
              ) : (
                recentRuns.map(run => {
                  const cfg = STATUS_CONFIG[run.status] ?? STATUS_CONFIG.pending;
                  const StatusIcon = cfg.icon;
                  const dur = formatDuration(run.duration_seconds);
                  return (
                    <button
                      key={run.id}
                      onClick={() => router.push(`/agent?run_id=${run.id}`)}
                      className="w-full flex items-center gap-3 px-4 py-3 bg-white/[0.02] hover:bg-white/[0.06] border border-white/5 hover:border-white/12 rounded-xl text-left transition-all group"
                    >
                      <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium shrink-0 ${cfg.className}`}>
                        <StatusIcon className="w-3 h-3" />
                        {cfg.label}
                      </div>
                      <span className="flex-1 text-sm text-slate-300 truncate group-hover:text-white transition-colors">{run.task}</span>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-xs text-slate-600">{formatDate(run.created_at)}</span>
                        {dur && <span className="text-xs text-slate-500">{dur}</span>}
                        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors" />
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>

          {/* Proactive Insights */}
          <motion.div
            className="rounded-2xl border border-white/8 bg-white/[0.03]"
            initial={{ opacity: 1, y: 0 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0 }}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-400" />
                <h2 className="text-sm font-semibold text-white">Intelligence Feed</h2>
              </div>
              <button onClick={() => router.push('/proactive')} className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1">
                All <ChevronRight className="w-3 h-3" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              {proactiveInsights.map((insight, i) => (
                <motion.div
                  key={insight.title}
                  className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 hover:bg-white/[0.06] transition-all cursor-pointer group"
                  initial={{ opacity: 1, x: 0 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0 }}
                  onClick={() => router.push('/proactive')}
                >
                  <div className="flex items-start gap-3">
                    <div className={`w-7 h-7 rounded-lg ${insight.color} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                      <insight.icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold text-white mb-1 group-hover:text-indigo-300 transition-colors">{insight.title}</div>
                      <div className="text-xs text-slate-500 leading-relaxed">{insight.desc}</div>
                    </div>
                  </div>
                </motion.div>
              ))}
              <button
                onClick={() => router.push('/agent')}
                className="w-full mt-1 py-2.5 rounded-xl border border-indigo-500/20 bg-indigo-500/5 text-indigo-400 text-xs font-medium hover:bg-indigo-500/10 transition-all flex items-center justify-center gap-2"
              >
                <Brain className="w-3.5 h-3.5" />
                Investigate with AI Agent
              </button>
            </div>
          </motion.div>
        </div>

        {/* ── Usage stats strip ──────────────────────────────────────── */}
        <motion.div
          className="rounded-2xl border border-white/8 bg-gradient-to-r from-indigo-500/5 to-violet-500/5 p-5 flex flex-wrap items-center justify-between gap-4"
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0 }}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">DataMind AI — Professional Plan</div>
              <div className="text-xs text-slate-500">500 analyses/month · {Math.max(500 - totalRuns, 0)} remaining</div>
            </div>
          </div>
          <div className="flex-1 max-w-xs">
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>{totalRuns} used</span>
              <span>500 limit</span>
            </div>
            <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all"
                style={{ width: `${Math.min((totalRuns / 500) * 100, 100)}%` }}
              />
            </div>
          </div>
          <button
            onClick={() => router.push('/settings')}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-sm font-semibold hover:from-indigo-500 hover:to-violet-500 transition-all shadow-lg shadow-indigo-500/25 flex items-center gap-2"
          >
            <FileText className="w-4 h-4" />
            Upgrade Plan
          </button>
        </motion.div>

      </div>
    </AppLayout>
  );
}
