'use client';

import { useState, useEffect, useRef } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import { SearchCode, Play, RefreshCw, ChevronDown, TrendingDown, TrendingUp, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, rcaApi } from '@/lib/api';
import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Dataset { id: string; name: string; status: string; }
interface RCAResult {
  id: string;
  metric_column: string;
  comparison_period: string;
  change_pct: number;
  confidence: number;
  status: string;
  narrative: string;
  chart: any;
  result_data: { top_drivers: any[]; segments: any[] };
  created_at: string;
}

const PERIOD_OPTIONS = [
  { value: 'week', label: 'Last Week vs Prior Week' },
  { value: 'month', label: 'Last Month vs Prior Month' },
  { value: 'quarter', label: 'Last Quarter vs Prior Quarter' },
];

export default function RootCausePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [numericColumns, setNumericColumns] = useState<string[]>([]);
  const [metricColumn, setMetricColumn] = useState('');
  const [dateColumn, setDateColumn] = useState('');
  const [period, setPeriod] = useState('month');
  const [running, setRunning] = useState(false);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [currentRca, setCurrentRca] = useState<RCAResult | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    datasetsApi.list().then(r => setDatasets(r.data.filter((d: Dataset) => d.status === 'ready')));
    rcaApi.history().then(r => setHistory(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedDataset) {
      setLoadingColumns(true);
      setColumns([]);
      setNumericColumns([]);
      setMetricColumn('');
      setDateColumn('');
      datasetsApi.get(selectedDataset).then(r => {
        const meta = r.data.columns_meta || [];
        const isNumericDtype = (dtype: string) =>
          dtype && (dtype.includes('int') || dtype.includes('float') || dtype.includes('number') || dtype === 'numeric');
        let cols: string[];
        let numCols: string[];
        if (Array.isArray(meta)) {
          cols = meta.map((c: { name?: string }) => c.name || String(c)).filter(Boolean);
          numCols = meta
            .filter((c: { name?: string; dtype?: string; type?: string }) =>
              isNumericDtype(c.dtype || '') || isNumericDtype(c.type || ''))
            .map((c: { name?: string }) => c.name || String(c))
            .filter(Boolean);
        } else {
          cols = Object.keys(meta);
          numCols = cols.filter(k => isNumericDtype(String(meta[k])));
        }
        setColumns(cols);
        setNumericColumns(numCols.length > 0 ? numCols : cols);
      }).finally(() => setLoadingColumns(false));
    }
  }, [selectedDataset]);

  const handleAnalyze = async () => {
    if (!selectedDataset || !metricColumn) { toast.error('Select dataset and metric column'); return; }
    setRunning(true);
    setCurrentRca(null);
    try {
      const res = await rcaApi.analyze({
        dataset_id: selectedDataset,
        metric_column: metricColumn,
        date_column: dateColumn || undefined,
        comparison_period: period,
      });
      const rcaId = res.data.rca_id;
      pollRca(rcaId);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to start analysis');
      setRunning(false);
    }
  };

  const pollRca = (rcaId: string) => {
    const poll = async () => {
      try {
        const res = await rcaApi.get(rcaId);
        const rca = res.data;
        if (rca.status === 'done') {
          setCurrentRca(rca);
          setHistory(prev => [rca, ...prev.filter(h => h.id !== rca.id)]);
          setRunning(false);
          toast.success('Root cause analysis complete');
        } else if (rca.status === 'error') {
          toast.error(`Analysis failed: ${rca.error_message}`);
          setRunning(false);
        } else {
          pollRef.current = setTimeout(poll, 2000);
        }
      } catch {
        setRunning(false);
      }
    };
    poll();
  };

  const changeColor = currentRca
    ? currentRca.change_pct > 0 ? 'text-emerald-400' : 'text-red-400'
    : '';

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <SearchCode className="w-6 h-6 text-indigo-400" />
            Root Cause Analysis
          </h1>
          <p className="text-slate-400 mt-1">AI-powered explanation for why a metric changed — like having a senior analyst on call 24/7</p>
        </div>

        {/* Controls */}
        <div className="glass rounded-2xl p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Dataset</label>
              <select
                value={selectedDataset}
                onChange={e => setSelectedDataset(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">— Select dataset —</option>
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">
                Metric to Analyze {loadingColumns && <span className="text-indigo-400 text-xs ml-1">Loading…</span>}
              </label>
              <select
                value={metricColumn}
                onChange={e => setMetricColumn(e.target.value)}
                disabled={!columns.length || loadingColumns}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                <option value="">{loadingColumns ? '— Loading columns… —' : '— Select numeric column —'}</option>
                {numericColumns.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Date Column (optional)</label>
              <select
                value={dateColumn}
                onChange={e => setDateColumn(e.target.value)}
                disabled={!columns.length || loadingColumns}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                <option value="">— Auto-detect —</option>
                {columns.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Comparison Period</label>
              <select
                value={period}
                onChange={e => setPeriod(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                {PERIOD_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={running || !selectedDataset || !metricColumn}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50 transition-colors"
          >
            {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {running ? 'Analyzing…' : 'Run Root Cause Analysis'}
          </button>
        </div>

        {/* Result */}
        {currentRca && (
          <div className="space-y-6">
            {/* Change summary */}
            <div className="grid grid-cols-3 gap-4">
              <div className="glass rounded-2xl p-5">
                <div className="text-slate-400 text-sm mb-1">Metric Change</div>
                <div className={`text-3xl font-bold flex items-center gap-2 ${changeColor}`}>
                  {currentRca.change_pct > 0
                    ? <TrendingUp className="w-6 h-6" />
                    : <TrendingDown className="w-6 h-6" />
                  }
                  {currentRca?.change_pct != null ? `${currentRca.change_pct > 0 ? '+' : ''}${currentRca.change_pct.toFixed(1)}%` : 'N/A'}
                </div>
              </div>
              <div className="glass rounded-2xl p-5">
                <div className="text-slate-400 text-sm mb-1">Metric</div>
                <div className="text-xl font-semibold text-white">{currentRca.metric_column}</div>
                <div className="text-xs text-slate-500 mt-1">vs prior {currentRca.comparison_period}</div>
              </div>
              <div className="glass rounded-2xl p-5">
                <div className="text-slate-400 text-sm mb-1">Confidence</div>
                <div className="text-3xl font-bold text-blue-400">{Math.round(currentRca.confidence * 100)}%</div>
              </div>
            </div>

            {/* Waterfall chart */}
            {currentRca.chart && (
              <div className="glass rounded-2xl p-4">
                <Plot
                  data={currentRca.chart.data}
                  layout={{ ...currentRca.chart.layout, autosize: true }}
                  style={{ width: '100%', height: 380 }}
                  config={{ responsive: true, displayModeBar: false }}
                />
              </div>
            )}

            {/* AI narrative */}
            <div className="glass rounded-2xl p-6">
              <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                <SearchCode className="w-4 h-4 text-indigo-400" />
                AI Explanation
              </h3>
              <div className="text-slate-300 text-sm leading-relaxed prose prose-invert prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: currentRca.narrative?.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>') || '' }}
              />
            </div>

            {/* Top drivers */}
            {currentRca.result_data?.top_drivers?.length > 0 && (
              <div className="glass rounded-2xl p-6">
                <h3 className="text-white font-semibold mb-4">Top Correlated Drivers</h3>
                <div className="space-y-2">
                  {currentRca.result_data.top_drivers.slice(0, 5).map((d: any) => (
                    <div key={d.column} className="flex items-center gap-3">
                      <span className="text-slate-300 text-sm w-40 truncate">{d.column}</span>
                      <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${d.correlation > 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.abs(d.correlation) * 100}%` }}
                        />
                      </div>
                      <span className={`text-sm font-mono w-14 text-right ${d.correlation > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {d.correlation > 0 ? '+' : ''}{d.correlation.toFixed(3)}
                      </span>
                      <span className="text-xs text-slate-500 w-16">{d.strength}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* History */}
        {history.length > 0 && !currentRca && (
          <div className="glass rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Recent Analyses</h2>
            <div className="space-y-2">
              {history.slice(0, 10).map(h => (
                <button
                  key={h.id}
                  onClick={() => setCurrentRca(h)}
                  className="w-full flex items-center gap-4 p-3 rounded-xl glass-hover text-left"
                >
                  <Clock className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <span className="text-slate-200 text-sm font-medium">{h.metric_column}</span>
                  <span className="text-slate-500 text-xs">{h.comparison_period}</span>
                  {h.change_pct != null && (
                    <span className={`text-sm font-mono ml-auto ${h.change_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {h.change_pct > 0 ? '+' : ''}{h.change_pct.toFixed(1)}%
                    </span>
                  )}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    h.status === 'done' ? 'bg-emerald-500/10 text-emerald-300' :
                    h.status === 'error' ? 'bg-red-500/10 text-red-300' : 'bg-amber-500/10 text-amber-300'
                  }`}>{h.status}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
