'use client';

import { useState, useEffect, useRef } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import {
  Cpu, Play, RefreshCw, CheckCircle2, AlertCircle, Clock,
  TrendingUp, Lightbulb, BookOpen, BarChart2, Download,
  ChevronDown, ChevronUp, ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, autonomousApi } from '@/lib/api';
import dynamic from 'next/dynamic';
import ReactMarkdown from 'react-markdown';
import Link from 'next/link';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Dataset { id: string; name: string; status: string; }

const STAGES = [
  { key: 'profiling',        label: 'Data Profiling' },
  { key: 'statistics',       label: 'Statistics' },
  { key: 'correlations',     label: 'Correlations' },
  { key: 'anomaly_detection',label: 'Anomaly Detection' },
  { key: 'forecasting',      label: 'Forecasting' },
  { key: 'insights',         label: 'AI Insights' },
  { key: 'recommendations',  label: 'Recommendations' },
  { key: 'storytelling',     label: 'Data Story' },
  { key: 'dashboard',        label: 'Auto Dashboard' },
  { key: 'complete',         label: 'Complete' },
];

type ActiveSection = 'story' | 'insights' | 'recommendations' | 'forecast' | 'charts';

export default function AutonomousPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [stages, setStages] = useState<string[]>([]);
  const [activeSection, setActiveSection] = useState<ActiveSection>('story');
  const [expandedChart, setExpandedChart] = useState<number | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    datasetsApi.list().then(r => {
      const ready = r.data.filter((d: Dataset) => d.status === 'ready');
      setDatasets(ready);
      if (ready.length > 0) setSelectedDataset(ready[0].id);
    });
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const startAnalysis = async () => {
    if (!selectedDataset) return;
    setRunning(true);
    setResult(null);
    setStages([]);
    try {
      await autonomousApi.analyze(selectedDataset);
      toast.success('Autonomous analysis started', { description: 'All 9 stages running in background' });

      // Poll for status every 3s
      pollRef.current = setInterval(async () => {
        try {
          const res = await autonomousApi.status(selectedDataset);
          const data = res.data;
          setStages(data.stages_completed || []);

          if (data.pipeline_status === 'complete' || data.pipeline_status === 'error') {
            clearInterval(pollRef.current!);
            setRunning(false);
            setResult(data);
            if (data.pipeline_status === 'complete') {
              toast.success('Analysis complete!', {
                description: `${data.stages_completed?.length || 0} stages · ${data.elapsed_seconds}s`,
              });
            } else {
              toast.error('Analysis encountered errors', { description: data.errors?.[0] });
            }
          }
        } catch {
          clearInterval(pollRef.current!);
          setRunning(false);
        }
      }, 3000);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to start analysis';
      toast.error('Failed to start', { description: msg });
      setRunning(false);
    }
  };

  const resetAnalysis = async () => {
    if (!selectedDataset) return;
    await autonomousApi.clearCache(selectedDataset).catch(() => {});
    setResult(null);
    setStages([]);
  };

  const stagesDone = stages.length;
  const totalStages = STAGES.length;
  const progressPct = running ? Math.round((stagesDone / totalStages) * 100) : (result ? 100 : 0);

  const SECTIONS: { id: ActiveSection; label: string; icon: any }[] = [
    { id: 'story',           label: 'Data Story',      icon: BookOpen },
    { id: 'insights',        label: 'Insights',        icon: Lightbulb },
    { id: 'recommendations', label: 'Recommendations', icon: TrendingUp },
    { id: 'forecast',        label: 'Forecast',        icon: BarChart2 },
    { id: 'charts',          label: 'Charts',          icon: BarChart2 },
  ];

  return (
    <AppLayout>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
            <Cpu className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Autonomous Data Analyst</h1>
            <p className="text-sm text-slate-400">
              Full end-to-end AI analysis: profiling → anomalies → forecasting → insights → story → dashboard
            </p>
          </div>
        </div>

        {/* Config + Run */}
        <div className="glass rounded-2xl p-5 border border-white/10 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4 items-end">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs text-slate-400">Select Dataset</label>
              <select
                value={selectedDataset}
                onChange={e => { setSelectedDataset(e.target.value); resetAnalysis(); }}
                className="w-full bg-white/5 border border-white/10 text-white text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:border-violet-500/50"
              >
                {datasets.length === 0 && <option value="">No datasets available</option>}
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div className="flex gap-2">
              {result && (
                <button
                  onClick={resetAnalysis}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 text-slate-400 hover:text-white hover:border-white/20 text-sm transition-colors"
                >
                  <RefreshCw className="w-4 h-4" /> Re-run
                </button>
              )}
              <button
                onClick={startAnalysis}
                disabled={running || !selectedDataset}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {running ? (
                  <><RefreshCw className="w-4 h-4 animate-spin" /> Analyzing...</>
                ) : (
                  <><Play className="w-4 h-4" /> Run Full Analysis</>
                )}
              </button>
            </div>
          </div>

          {/* Progress stages */}
          {(running || (result && stages.length > 0)) && (
            <div className="space-y-3">
              {/* Progress bar */}
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="text-xs text-slate-400 w-12 text-right">{progressPct}%</span>
              </div>

              {/* Stage chips */}
              <div className="flex flex-wrap gap-2">
                {STAGES.map((s, i) => {
                  const done = stages.includes(s.key);
                  const current = running && stages.length === i;
                  return (
                    <div
                      key={s.key}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-all ${
                        done
                          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                          : current
                          ? 'bg-violet-500/10 border-violet-500/30 text-violet-300 animate-pulse'
                          : 'bg-white/3 border-white/5 text-slate-600'
                      }`}
                    >
                      {done ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                      {s.label}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Results */}
        {result && result.pipeline_status === 'complete' && (
          <div className="space-y-5">
            {/* Summary banner */}
            <div className="flex items-start gap-3 p-4 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-300 text-sm">
              <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-semibold">{result.dataset_name}</span>
                {' '}— Complete analysis finished in{' '}
                <span className="font-semibold">{result.elapsed_seconds}s</span>
                {' '}·{' '}
                <span className="font-semibold">{result.stages_completed?.length}</span> stages
                {result.errors?.length > 0 && (
                  <span className="ml-2 text-amber-300">({result.errors.length} non-fatal warning{result.errors.length > 1 ? 's' : ''})</span>
                )}
              </div>
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Rows', value: result.profile?.shape?.rows ?? result.profile?.row_count ?? result.stats?.count?.toString() ?? '–' },
                { label: 'Columns', value: result.profile?.shape?.columns ?? result.profile?.column_count ?? '–' },
                { label: 'Insights', value: result.insights?.length ?? 0 },
                { label: 'Recommendations', value: result.recommendations?.length ?? 0 },
              ].map(s => (
                <div key={s.label} className="glass rounded-xl p-3 border border-white/10 text-center">
                  <div className="text-xl font-bold text-white">{s.value}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{s.label}</div>
                </div>
              ))}
            </div>

            {/* Dashboard link */}
            {result.dashboard_id && (
              <div className="flex items-center gap-3 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-sm">
                <BarChart2 className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                <span className="text-indigo-300">Auto-dashboard created!</span>
                <Link
                  href={`/dashboards`}
                  className="ml-auto flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  View Dashboard <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
            )}

            {/* Section tabs */}
            <div className="flex gap-1 border-b border-white/5 overflow-x-auto">
              {SECTIONS.map(sec => (
                <button
                  key={sec.id}
                  onClick={() => setActiveSection(sec.id)}
                  className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg whitespace-nowrap transition-colors border-b-2 ${
                    activeSection === sec.id
                      ? 'text-violet-400 border-violet-500'
                      : 'text-slate-500 border-transparent hover:text-slate-300'
                  }`}
                >
                  <sec.icon className="w-3.5 h-3.5" />
                  {sec.label}
                </button>
              ))}
            </div>

            {/* Section content */}
            <div className="min-h-[200px]">
              {/* Data Story */}
              {activeSection === 'story' && (
                <div className="glass rounded-2xl p-5 border border-white/10">
                  {result.story ? (
                    <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed">
                      <ReactMarkdown>{result.story}</ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">No data story generated.</p>
                  )}
                </div>
              )}

              {/* Insights */}
              {activeSection === 'insights' && (
                <div className="space-y-3">
                  {(result.insights || []).length === 0 && <p className="text-sm text-slate-500">No insights generated.</p>}
                  {(result.insights || []).map((ins: any, i: number) => (
                    <div
                      key={i}
                      className={`p-4 rounded-xl border ${
                        ins.severity === 'high' ? 'border-red-500/30 bg-red-500/5 text-red-300'
                        : ins.severity === 'medium' ? 'border-yellow-500/30 bg-yellow-500/5 text-yellow-300'
                        : 'border-blue-500/30 bg-blue-500/5 text-blue-300'
                      }`}
                    >
                      <div className="font-semibold text-sm mb-1">{ins.title}</div>
                      <div className="text-xs opacity-80">{ins.content}</div>
                      {ins.metric_value && <div className="mt-2 text-lg font-bold">{ins.metric_value}</div>}
                    </div>
                  ))}
                </div>
              )}

              {/* Recommendations */}
              {activeSection === 'recommendations' && (
                <div className="space-y-3">
                  {(result.recommendations || []).length === 0 && <p className="text-sm text-slate-500">No recommendations generated.</p>}
                  {(result.recommendations || []).map((rec: any, i: number) => {
                    const priorityColor = { high: 'text-red-400', medium: 'text-yellow-400', low: 'text-green-400' }[rec.priority as string] || 'text-slate-400';
                    return (
                      <div key={i} className="p-4 rounded-xl bg-white/3 border border-white/8 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold uppercase ${priorityColor}`}>{rec.priority}</span>
                          <span className="text-sm font-semibold text-white">{rec.title}</span>
                        </div>
                        <div className="text-xs text-slate-400 prose prose-invert prose-xs max-w-none">
                          <ReactMarkdown>{rec.description || ''}</ReactMarkdown>
                        </div>
                        <div className="text-xs text-violet-300 font-medium prose prose-invert prose-xs max-w-none">
                          → <ReactMarkdown>{rec.ai_action || rec.action || ''}</ReactMarkdown>
                        </div>
                        {rec.expected_impact && <div className="text-xs text-slate-500">Impact: {rec.expected_impact}</div>}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Forecast */}
              {activeSection === 'forecast' && (
                <div className="space-y-4">
                  {result.forecast ? (
                    <>
                      <div className="flex items-center gap-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-300">
                        <TrendingUp className="w-4 h-4 flex-shrink-0" />
                        <span>{result.forecast.summary}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        {result.forecast.metrics && Object.entries(result.forecast.metrics).map(([k, v]: any) => (
                          <div key={k} className="glass rounded-xl p-3 border border-white/10 text-center">
                            <div className="text-lg font-bold text-white">{typeof v === 'number' ? v.toFixed(2) : v}</div>
                            <div className="text-xs text-slate-500 uppercase">{k}</div>
                          </div>
                        ))}
                      </div>
                      {result.forecast.chart && (
                        <div className="glass rounded-2xl p-4 border border-white/10">
                          <Plot
                            data={result.forecast.chart.data}
                            layout={{
                              ...result.forecast.chart.layout,
                              paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                              font: { color: '#94a3b8', size: 11 },
                              xaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                              yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                              legend: { bgcolor: 'transparent' },
                              margin: { l: 50, r: 30, t: 20, b: 50 },
                              height: 300,
                            }}
                            config={{ displayModeBar: false, responsive: true }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="flex items-center gap-3 p-4 text-sm text-slate-500">
                      <AlertCircle className="w-4 h-4" />
                      Forecasting not available — dataset may not have a suitable time series column.
                    </div>
                  )}
                </div>
              )}

              {/* Charts */}
              {activeSection === 'charts' && (
                <div className="space-y-4">
                  {(!result.charts || result.charts.length === 0) && (
                    <p className="text-sm text-slate-500">No charts generated.</p>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {(result.charts || []).map((chart: any, i: number) => (
                      <div key={i} className="glass rounded-2xl border border-white/10 overflow-hidden">
                        <button
                          className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-white/3 transition-colors"
                          onClick={() => setExpandedChart(expandedChart === i ? null : i)}
                        >
                          <span className="text-xs font-medium text-slate-400">Chart {i + 1}</span>
                          {expandedChart === i ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
                        </button>
                        {(expandedChart === i || i < 2) && (
                          <div className="px-2 pb-2">
                            <Plot
                              data={chart.data}
                              layout={{
                                ...chart.layout,
                                paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                                font: { color: '#94a3b8', size: 10 },
                                xaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                                yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                                legend: { bgcolor: 'transparent' },
                                margin: { l: 40, r: 20, t: 30, b: 40 },
                                height: 240,
                              }}
                              config={{ displayModeBar: false, responsive: true }}
                              style={{ width: '100%' }}
                            />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Non-fatal errors */}
            {result.errors?.length > 0 && (
              <details className="glass rounded-xl border border-amber-500/20 overflow-hidden">
                <summary className="px-4 py-2.5 text-xs text-amber-400 cursor-pointer hover:bg-white/3">
                  ⚠ {result.errors.length} non-fatal warning{result.errors.length > 1 ? 's' : ''} (click to expand)
                </summary>
                <div className="px-4 pb-3 space-y-1">
                  {result.errors.map((e: string, i: number) => (
                    <div key={i} className="text-xs text-amber-300/70 font-mono">{e}</div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {/* Empty state */}
        {!result && !running && (
          <div className="text-center py-16 text-slate-500">
            <Cpu className="w-12 h-12 mx-auto mb-4 opacity-20" />
            <p className="text-sm">Select a dataset and click <strong className="text-slate-400">Run Full Analysis</strong></p>
            <p className="text-xs mt-1 opacity-60">Runs 9 analysis stages automatically: profiling, anomalies, forecasting, insights, story, dashboard, and more.</p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
