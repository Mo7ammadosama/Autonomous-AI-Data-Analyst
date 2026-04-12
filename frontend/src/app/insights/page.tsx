'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb, RefreshCw, TrendingUp, AlertTriangle, CheckCircle, Info,
  Sparkles, Database, Brain, BookOpen, ShieldAlert
} from 'lucide-react';
import dynamic from 'next/dynamic';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { datasetsApi, insightsApi } from '@/lib/api';
import { cn } from '@/lib/utils';

const PipelineResults = dynamic(
  () => import('@/components/pipeline/PipelineResults'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center py-16 text-slate-500">
        <RefreshCw className="w-4 h-4 animate-spin mr-2" />
        <span className="text-sm">Loading pipeline analysis...</span>
      </div>
    ),
  }
);

const typeConfig: Record<string, { icon: any; color: string }> = {
  metric:       { icon: TrendingUp,    color: 'text-indigo-400' },
  comparison:   { icon: CheckCircle,   color: 'text-emerald-400' },
  anomaly:      { icon: AlertTriangle, color: 'text-amber-400' },
  warning:      { icon: AlertTriangle, color: 'text-amber-400' },
  correlation:  { icon: Sparkles,      color: 'text-violet-400' },
  distribution: { icon: Info,          color: 'text-blue-400' },
  general:      { icon: Lightbulb,     color: 'text-cyan-400' },
};

type Tab = 'quick' | 'pipeline';

export default function InsightsPage() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [insights, setInsights] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('quick');

  useEffect(() => {
    datasetsApi.list().then(res => {
      setDatasets(res.data);
      if (res.data[0]) setSelectedId(res.data[0].id);
    });
  }, []);

  useEffect(() => {
    if (selectedId) loadInsights();
  }, [selectedId]);

  const loadInsights = async (refresh = false) => {
    setLoading(true);
    try {
      const res = await insightsApi.get(selectedId, refresh);
      setInsights(res.data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const TABS: { id: Tab; label: string; icon: any; desc: string }[] = [
    {
      id: 'quick',
      label: 'Quick Insights',
      icon: Lightbulb,
      desc: 'Statistical insights from data profiling',
    },
    {
      id: 'pipeline',
      label: 'Deep Analysis',
      icon: Brain,
      desc: 'AI pipeline: story, recommendations, anomalies',
    },
  ];

  return (
    <AppLayout>
      <div className="p-6 space-y-5 max-w-7xl">
        <PageHeader
          title="AI Insights"
          subtitle="Automatically generated data intelligence"
          icon={<Lightbulb className="w-5 h-5 text-amber-400" />}
          action={
            <div className="flex gap-3">
              <select
                value={selectedId}
                onChange={e => { setSelectedId(e.target.value); setActiveTab('quick'); }}
                className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
              >
                <option value="">Select dataset...</option>
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              {activeTab === 'quick' && (
                <button
                  onClick={() => loadInsights(true)}
                  disabled={loading || !selectedId}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 rounded-xl text-sm font-medium border border-indigo-500/20 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                  Regenerate
                </button>
              )}
            </div>
          }
        />

        {!selectedId ? (
          <div className="glass rounded-xl p-16 text-center border border-white/5">
            <Database className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Select a dataset to generate insights</p>
          </div>
        ) : (
          <>
            {/* Tab switcher */}
            <div className="flex gap-1 p-1 glass rounded-xl border border-white/8 w-fit">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                    activeTab === tab.id
                      ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/30'
                      : 'text-slate-500 hover:text-slate-300'
                  )}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </button>
              ))}
            </div>

            <AnimatePresence mode="wait">
              {/* Quick Insights tab */}
              {activeTab === 'quick' && (
                <motion.div
                  key="quick"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                >
                  {loading ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {Array(4).fill(0).map((_, i) => (
                        <div key={i} className="glass rounded-xl p-5 border border-white/5 h-32 shimmer" />
                      ))}
                    </div>
                  ) : insights.length === 0 ? (
                    <div className="glass rounded-xl p-16 text-center border border-white/5">
                      <Lightbulb className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                      <p className="text-slate-400 mb-4">No quick insights generated yet</p>
                      <button
                        onClick={() => loadInsights(true)}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition-colors"
                      >
                        Generate Insights
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {insights.map((ins, i) => {
                        const config = typeConfig[ins.type || ins.insight_type || 'general'] || typeConfig.general;
                        const IconComp = config.icon;
                        return (
                          <motion.div
                            key={ins.id || i}
                            className="glass rounded-xl p-5 border border-white/5 card-hover"
                            initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.07 }}
                          >
                            <div className="flex items-start gap-4">
                              <div className={cn(
                                'p-2.5 rounded-xl bg-white/5 flex-shrink-0',
                                config.color.replace('text-', 'bg-').replace('-400', '-400/10')
                              )}>
                                <IconComp className={cn('w-5 h-5', config.color)} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                  <h3 className="text-sm font-semibold text-white leading-tight">{ins.title}</h3>
                                  {ins.metric_value && (
                                    <span className="text-sm font-bold text-indigo-400 flex-shrink-0">{ins.metric_value}</span>
                                  )}
                                </div>
                                <p className="text-sm text-slate-400 leading-relaxed">{ins.content}</p>
                                {ins.metric_change != null && (
                                  <div className={cn(
                                    'mt-2 text-xs font-medium flex items-center gap-1',
                                    ins.metric_change >= 0 ? 'text-emerald-400' : 'text-red-400'
                                  )}>
                                    <TrendingUp className="w-3 h-3" />
                                    {ins.metric_change >= 0 ? '+' : ''}{ins.metric_change.toFixed(1)}% difference
                                  </div>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  )}
                </motion.div>
              )}

              {/* Deep Analysis (Pipeline) tab */}
              {activeTab === 'pipeline' && (
                <motion.div
                  key="pipeline"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                >
                  {/* Intro banner */}
                  <div className="flex items-start gap-3 p-4 mb-5 rounded-xl bg-indigo-500/8 border border-indigo-500/20">
                    <div className="p-2 rounded-lg bg-indigo-500/15 border border-indigo-500/25 flex-shrink-0">
                      <Brain className="w-4 h-4 text-indigo-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-indigo-300 mb-0.5">Full AI Analysis Pipeline</p>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Runs automatic profiling → anomaly detection → insights → recommendations → data story.
                        If the pipeline hasn&apos;t run yet, click <strong className="text-slate-300">Run Full Analysis</strong> below.
                      </p>
                    </div>
                  </div>

                  <div className="glass rounded-xl border border-white/8 p-5">
                    <PipelineResults datasetId={selectedId} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}
      </div>
    </AppLayout>
  );
}
