'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  BarChart2, TrendingUp, AlertTriangle, GitBranch, Cpu, Database,
  Sparkles, Send, RefreshCw, Bot
} from 'lucide-react';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import ChartGrid from '@/components/charts/ChartGrid';
import { ChartSkeleton } from '@/components/ui/Skeleton';
import { datasetsApi, analyticsApi, analyticsExtApi } from '@/lib/api';
import { cn } from '@/lib/utils';

const TABS = [
  { id: 'overview',      label: 'Overview',         icon: BarChart2 },
  { id: 'correlations',  label: 'Correlations',     icon: GitBranch },
  { id: 'outliers',      label: 'Outliers',         icon: AlertTriangle },
  { id: 'ml',            label: 'Machine Learning', icon: Cpu },
  { id: 'ai_query',      label: 'AI Query',         icon: Sparkles },
];

function AnalyticsPageInner() {
  const searchParams = useSearchParams();
  const datasetIdParam = searchParams.get('id');
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState(datasetIdParam || '');
  const [tab, setTab] = useState('overview');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [mlType, setMlType] = useState('clustering');
  const [mlResult, setMlResult] = useState<any>(null);
  const [mlLoading, setMlLoading] = useState(false);

  // AI Query state
  const [nlQuestion, setNlQuestion] = useState('');
  const [nlResult, setNlResult] = useState<any>(null);
  const [nlLoading, setNlLoading] = useState(false);
  const [nlHistory, setNlHistory] = useState<{ question: string; result: any }[]>([]);

  useEffect(() => {
    datasetsApi.list().then(res => {
      setDatasets(res.data);
      if (!selectedId && res.data[0]) setSelectedId(res.data[0].id);
    });
  }, []);

  useEffect(() => {
    if (selectedId) loadTab();
  }, [selectedId, tab]);

  const loadTab = async () => {
    if (!selectedId) return;
    setLoading(true);
    setData(null);
    setLoadError('');
    try {
      let res;
      if (tab === 'overview') res = await analyticsApi.overview(selectedId);
      else if (tab === 'correlations') res = await analyticsApi.correlations(selectedId);
      else if (tab === 'outliers') res = await analyticsApi.outliers(selectedId);
      if (res) setData(res.data);
    } catch (e: any) {
      setLoadError(e?.response?.data?.detail || 'Failed to load analysis. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const runML = async () => {
    setMlLoading(true);
    setMlResult(null);
    try {
      const res = await analyticsApi.runML(selectedId, { analysis_type: mlType, n_clusters: 3 });
      setMlResult(res.data);
    } catch (e: any) {
      setMlResult({ error: e.response?.data?.detail || 'ML analysis failed' });
    } finally {
      setMlLoading(false);
    }
  };

  const runNlQuery = async (text?: string) => {
    const q = text ?? nlQuestion;
    if (!q.trim() || !selectedId || nlLoading) return;
    if (!text) setNlQuestion('');
    setNlLoading(true);
    try {
      const res = await analyticsExtApi.nlQuery(selectedId, q);
      const result = res.data;
      setNlResult(result);
      setNlHistory(prev => [{ question: q, result }, ...prev.slice(0, 9)]);
    } catch (e: any) {
      const errResult = { error: (e as any).response?.data?.detail || 'Query failed' };
      setNlResult(errResult);
    } finally {
      setNlLoading(false);
    }
  };

  const selectedDs = datasets.find(d => d.id === selectedId);

  return (
    <AppLayout>
      <div className="p-6 space-y-5 max-w-7xl">
        <PageHeader
          title="Analytics Explorer"
          subtitle="Deep-dive statistical analysis"
          icon={<BarChart2 className="w-5 h-5 text-violet-400" />}
          action={
            <select
              value={selectedId}
              onChange={e => setSelectedId(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white"
            >
              <option value="">Select dataset...</option>
              {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          }
        />

        {!selectedId ? (
          <div className="glass rounded-xl p-16 text-center border border-white/5">
            <Database className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Select a dataset to begin analysis</p>
          </div>
        ) : (
          <>
            {/* Dataset info */}
            {selectedDs && (
              <div className="flex items-center gap-3 px-4 py-2.5 glass rounded-xl border border-white/5 w-fit">
                <Database className="w-4 h-4 text-indigo-400" />
                <span className="text-sm text-slate-300 font-medium">{selectedDs.name}</span>
                <span className="text-xs text-slate-500">{selectedDs.row_count?.toLocaleString()} rows · {selectedDs.column_count} cols</span>
              </div>
            )}

            {/* Tabs */}
            <div className="flex gap-1 p-1 glass rounded-xl border border-white/5 w-fit">
              {TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                    tab === t.id ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/25' : 'text-slate-400 hover:text-slate-200'
                  )}
                >
                  <t.icon className="w-4 h-4" /> {t.label}
                </button>
              ))}
            </div>

            {/* Load error */}
            {loadError && (
              <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {loadError}
              </div>
            )}

            {/* Content */}
            {tab !== 'ml' && (
              loading ? (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {[0, 1, 2, 3].map(i => <ChartSkeleton key={i} />)}
                </div>
              ) : data ? (
                <div className="space-y-5">
                  {tab === 'overview' && (
                    <>
                      {/* Profile summary */}
                      {data.profile && (
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                          {[
                            { label: 'Rows', value: data.profile.shape?.rows?.toLocaleString() },
                            { label: 'Columns', value: data.profile.shape?.columns },
                            { label: 'Duplicates', value: data.profile.duplicates },
                            { label: 'Missing Cols', value: Object.keys(data.profile.missing_summary || {}).length },
                          ].map(s => (
                            <div key={s.label} className="glass rounded-xl p-4 border border-white/5">
                              <div className="text-2xl font-display font-bold text-white">{s.value ?? '–'}</div>
                              <div className="text-xs text-slate-500">{s.label}</div>
                            </div>
                          ))}
                        </div>
                      )}
                      <ChartGrid charts={data.charts || []} columns={2} />
                    </>
                  )}
                  {tab === 'correlations' && (
                    <div className="space-y-4">
                      {/* Not enough numeric columns — show info message */}
                      {!data.correlations && !data.chart && (
                        <div className="glass rounded-xl p-8 text-center border border-amber-500/20 bg-amber-500/5">
                          <GitBranch className="w-8 h-8 text-amber-400/50 mx-auto mb-3" />
                          <p className="text-amber-300 font-medium text-sm">
                            {data.message || 'Need at least 2 numeric columns for correlation analysis.'}
                          </p>
                          <p className="text-slate-500 text-xs mt-1.5">
                            Rank and year columns are excluded from correlation. Try the Overview or AI Query tabs instead.
                          </p>
                        </div>
                      )}
                      {data.chart && <ChartGrid charts={[data.chart]} columns={1} chartHeight={420} />}
                      {data.correlations?.strong_pairs?.length > 0 && (
                        <div className="glass rounded-xl p-5 border border-white/5">
                          <h3 className="text-sm font-semibold text-white mb-3">Strong Correlations (|r| ≥ 0.7)</h3>
                          <div className="space-y-2">
                            {data.correlations.strong_pairs.slice(0, 8).map((p: any, i: number) => (
                              <div key={i} className="flex items-center gap-3">
                                <span className="text-xs text-slate-300 w-48 truncate">{p.col1} ↔ {p.col2}</span>
                                <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                                  <div className={cn('h-full rounded-full', p.correlation > 0 ? 'bg-indigo-500' : 'bg-red-500')} style={{ width: `${Math.abs(p.correlation) * 100}%` }} />
                                </div>
                                <span className="text-xs font-mono text-slate-400 w-12 text-right">{p.correlation.toFixed(3)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {data.correlations && data.correlations.strong_pairs?.length === 0 && (
                        <div className="glass rounded-xl p-6 text-center border border-white/5">
                          <p className="text-slate-400 text-sm">No very strong correlations (|r| ≥ 0.7) found.</p>
                          <p className="text-slate-500 text-xs mt-1">The heatmap above shows all pairwise correlations.</p>
                        </div>
                      )}
                    </div>
                  )}
                  {tab === 'outliers' && (
                    <div className="space-y-4">
                      <ChartGrid charts={data.charts || []} columns={2} chartHeight={280} />
                      {Object.keys(data.outliers || {}).length > 0 ? (
                        <div className="glass rounded-xl p-5 border border-white/5">
                          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-400" /> Outlier Summary
                          </h3>
                          <div className="space-y-2">
                            {Object.entries(data.outliers).map(([col, info]: any) => (
                              <div key={col} className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
                                <span className="text-sm text-slate-300 font-medium flex-1">{col}</span>
                                <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">{info.count} outliers ({info.pct}%)</span>
                                <span className="text-xs text-slate-500">Range: [{info.lower_bound}, {info.upper_bound}]</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="glass rounded-xl p-8 text-center border border-white/5">
                          <p className="text-emerald-400 font-medium">No significant outliers detected ✓</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : null
            )}

            {/* ML tab */}
            {tab === 'ml' && (
              <div className="space-y-4">
                <div className="glass rounded-xl p-5 border border-white/5">
                  <h3 className="text-sm font-semibold text-white mb-4">Machine Learning Analysis</h3>
                  <div className="flex gap-3 items-center flex-wrap">
                    <select
                      value={mlType}
                      onChange={e => setMlType(e.target.value)}
                      className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white"
                    >
                      <option value="clustering">K-Means Clustering</option>
                      <option value="regression">Linear Regression</option>
                    </select>
                    <motion.button
                      onClick={runML}
                      disabled={mlLoading}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                      whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                    >
                      {mlLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Cpu className="w-4 h-4" />}
                      Run Analysis
                    </motion.button>
                  </div>
                </div>

                {mlResult && (
                  <motion.div className="glass rounded-xl p-5 border border-white/5" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    {mlResult.error ? (
                      <p className="text-red-400">{mlResult.error}</p>
                    ) : (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-white">{mlResult.type === 'clustering' ? 'Clustering Results' : 'Regression Results'}</h4>
                        {mlResult.type === 'clustering' && (
                          <>
                            <div className="flex gap-4">
                              <div className="glass rounded-lg p-3"><div className="text-lg font-bold text-indigo-400">{mlResult.n_clusters}</div><div className="text-xs text-slate-500">Clusters</div></div>
                              <div className="glass rounded-lg p-3"><div className="text-lg font-bold text-emerald-400">{mlResult.silhouette_score?.toFixed(3)}</div><div className="text-xs text-slate-500">Silhouette Score</div></div>
                            </div>
                            {Object.entries(mlResult.cluster_summary || {}).map(([name, info]: any) => (
                              <div key={name} className="border border-white/5 rounded-lg p-3">
                                <div className="text-sm font-medium text-slate-300 mb-1">{name} <span className="text-xs text-slate-500">({info.size} samples)</span></div>
                                <div className="flex gap-3 flex-wrap">
                                  {Object.entries(info.means || {}).slice(0, 4).map(([col, val]: any) => (
                                    <span key={col} className="text-xs text-slate-400">{col}: <span className="text-white">{val}</span></span>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </>
                        )}
                        {mlResult.type === 'regression' && (
                          <>
                            <div className="flex gap-4">
                              <div className="glass rounded-lg p-3"><div className="text-lg font-bold text-indigo-400">{mlResult.r2_score?.toFixed(4)}</div><div className="text-xs text-slate-500">R² Score</div></div>
                              <div className="glass rounded-lg p-3"><div className="text-lg font-bold text-violet-400">{mlResult.target}</div><div className="text-xs text-slate-500">Target Column</div></div>
                            </div>
                            <div>
                              <p className="text-xs text-slate-500 mb-2">Coefficients:</p>
                              <div className="space-y-1">
                                {Object.entries(mlResult.coefficients || {}).slice(0, 8).map(([col, val]: any) => (
                                  <div key={col} className="flex items-center gap-3">
                                    <span className="text-xs text-slate-300 w-32 truncate">{col}</span>
                                    <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                                      <div className={cn('h-full rounded-full', val >= 0 ? 'bg-indigo-500' : 'bg-red-500')} style={{ width: `${Math.min(Math.abs(val) * 20, 100)}%` }} />
                                    </div>
                                    <span className="text-xs font-mono text-slate-400">{val}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            )}

            {/* AI Query tab */}
            {tab === 'ai_query' && (
              <div className="space-y-4">
                {/* Intro */}
                <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-500/8 border border-indigo-500/20">
                  <div className="p-2 rounded-lg bg-indigo-500/15 border border-indigo-500/25 flex-shrink-0">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-indigo-300 mb-0.5">Natural Language Query</p>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Ask any question about your dataset in plain English. The AI will analyze it and return charts, insights, and explanations.
                    </p>
                  </div>
                </div>

                {/* Input */}
                <div className="glass rounded-xl border border-white/8 p-4">
                  <div className="flex gap-3 items-end">
                    <div className="flex-1">
                      <textarea
                        value={nlQuestion}
                        onChange={e => setNlQuestion(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runNlQuery(undefined); } }}
                        placeholder="e.g. What are the top 5 customers by revenue? Show me the sales trend over time..."
                        rows={2}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-600 resize-none focus:border-indigo-500/50 transition-all"
                      />
                    </div>
                    <motion.button
                      onClick={() => runNlQuery(undefined)}
                      disabled={!nlQuestion.trim() || nlLoading || !selectedId}
                      className="p-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-colors disabled:opacity-40 flex-shrink-0"
                      whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                    >
                      {nlLoading
                        ? <RefreshCw className="w-4 h-4 animate-spin" />
                        : <Send className="w-4 h-4" />
                      }
                    </motion.button>
                  </div>

                  {/* Suggestions */}
                  {!nlResult && !nlLoading && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {[
                        'Summarize the dataset',
                        'Find correlations',
                        'Show distribution of values',
                        'Detect anomalies',
                        'Top 10 records',
                        'Trend over time',
                      ].map(s => (
                        <button
                          key={s}
                          onClick={() => runNlQuery(s)}
                          className="text-xs px-3 py-1.5 rounded-lg bg-white/4 border border-white/8 text-slate-400 hover:text-slate-200 hover:border-indigo-500/30 transition-all"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Loading */}
                {nlLoading && (
                  <div className="flex items-center gap-3 p-4 glass rounded-xl border border-white/5">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center flex-shrink-0">
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                    <div className="flex gap-1">
                      {[0, 0.15, 0.3].map((d, i) => (
                        <div key={i} className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: `${d}s` }} />
                      ))}
                    </div>
                  </div>
                )}

                {/* Result */}
                {nlResult && !nlLoading && (
                  <motion.div
                    className="space-y-4"
                    initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  >
                    <div className="glass rounded-xl border border-indigo-500/20 overflow-hidden">
                      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 bg-indigo-500/5">
                        <Bot className="w-4 h-4 text-indigo-400" />
                        <span className="text-xs text-slate-400">AI Response</span>
                        {nlResult.intent && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 ml-auto">
                            {nlResult.intent}
                          </span>
                        )}
                      </div>
                      <div className="p-4">
                        {nlResult.error ? (
                          <p className="text-red-400 text-sm">{nlResult.error}</p>
                        ) : (
                          <p className="text-sm text-slate-200 leading-relaxed">{nlResult.answer || nlResult.content || JSON.stringify(nlResult)}</p>
                        )}
                      </div>
                    </div>

                    {/* Charts from NL result */}
                    {nlResult.charts?.length > 0 && (
                      <ChartGrid charts={nlResult.charts} columns={nlResult.charts.length > 1 ? 2 : 1} chartHeight={280} />
                    )}

                    {/* Insights */}
                    {nlResult.insights?.length > 0 && (
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {nlResult.insights.slice(0, 4).map((ins: any, i: number) => (
                          <div key={i} className="glass rounded-xl p-3.5 border border-white/5">
                            <div className="text-xs font-semibold text-white mb-0.5">{ins.title}</div>
                            <div className="text-xs text-slate-400">{ins.content}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}

                {/* Query history */}
                {nlHistory.length > 1 && (
                  <div className="glass rounded-xl border border-white/5 overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-white/5">
                      <span className="text-xs font-semibold text-slate-400">Query History</span>
                    </div>
                    <div className="divide-y divide-white/5">
                      {nlHistory.slice(1, 6).map((h, i) => (
                        <button
                          key={i}
                          onClick={() => setNlQuestion(h.question)}
                          className="w-full text-left px-4 py-2.5 text-xs text-slate-500 hover:text-slate-200 hover:bg-white/3 transition-colors truncate"
                        >
                          {h.question}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function AnalyticsPage() {
  return <Suspense><AnalyticsPageInner /></Suspense>;
}
