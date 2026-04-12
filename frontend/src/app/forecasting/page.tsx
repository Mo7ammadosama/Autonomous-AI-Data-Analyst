'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import AppLayout from '@/components/layout/AppLayout';
import { TrendingUp, Play, RefreshCw, AlertCircle, CheckCircle2, Download } from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, forecastingApi } from '@/lib/api';
import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Dataset { id: string; name: string; status: string; }
interface ForecastColumns {
  date_columns: string[];
  numeric_columns: string[];
  auto_detected: { date_column?: string; target_column?: string };
  is_time_series: boolean;
  not_time_series_reason?: string;
}
interface ForecastResult {
  date_column: string;
  target_column: string;
  method: string;
  periods: number;
  historical: { dates: string[]; values: number[] };
  forecast: { dates: string[]; predictions: number[]; lower: number[]; upper: number[] };
  metrics: { mae: number; rmse: number; mape: number };
  chart: any;
  summary: string;
}

const METHODS = [
  { value: 'auto', label: 'Auto (recommended)' },
  { value: 'arima', label: 'ARIMA' },
  { value: 'exp_smoothing', label: 'Exponential Smoothing' },
  { value: 'linear', label: 'Linear Trend' },
];

function ForecastingContent() {
  const searchParams = useSearchParams();
  const datasetParam = searchParams.get('dataset');

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState('');
  const [columns, setColumns] = useState<ForecastColumns | null>(null);
  const [dateCol, setDateCol] = useState('');
  const [targetCol, setTargetCol] = useState('');
  const [periods, setPeriods] = useState(30);
  const [method, setMethod] = useState('auto');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    datasetsApi.list().then((r) => {
      const ready = r.data.filter((d: Dataset) => d.status === 'ready');
      setDatasets(ready);
      // Prefer query param dataset, else first ready dataset
      const preselect = datasetParam && ready.find((d: Dataset) => d.id === datasetParam);
      if (preselect) setSelectedDataset(preselect.id);
      else if (ready.length > 0) setSelectedDataset(ready[0].id);
    });
  }, [datasetParam]);

  // Load forecastable columns when dataset changes
  useEffect(() => {
    if (!selectedDataset) return;
    forecastingApi.columns(selectedDataset).then((r) => {
      setColumns(r.data);
      setDateCol(r.data.auto_detected?.date_column || r.data.date_columns[0] || '');
      setTargetCol(r.data.auto_detected?.target_column || r.data.numeric_columns[0] || '');
    }).catch(() => {});
    setResult(null);
    setError('');
  }, [selectedDataset]);

  const runForecast = async () => {
    if (!selectedDataset) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await forecastingApi.forecast(selectedDataset, {
        date_column: dateCol || undefined,
        target_column: targetCol || undefined,
        periods,
        method,
      });
      setResult(res.data);
      toast.success('Forecast complete', {
        description: `${res.data.method.toUpperCase()} · ${res.data.periods} periods · target: ${res.data.target_column}`,
      });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Forecast failed. Ensure your dataset has a date column.';
      setError(msg);
      toast.error('Forecast failed', { description: msg });
    } finally {
      setLoading(false);
    }
  };

  const downloadCsv = () => {
    if (!result) return;
    const rows = [
      ['Date', 'Prediction', 'Lower_95', 'Upper_95'],
      ...result.forecast.dates.map((d: string, i: number) => [
        d,
        result.forecast.predictions[i]?.toFixed(4) ?? '',
        result.forecast.lower[i]?.toFixed(4) ?? '',
        result.forecast.upper[i]?.toFixed(4) ?? '',
      ]),
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `forecast_${result.target_column}_${result.method}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Forecast CSV downloaded');
  };

  return (
    <AppLayout>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Time Series Forecasting</h1>
            <p className="text-sm text-slate-400">Predict future values using ARIMA, Exponential Smoothing, or Linear Trend</p>
          </div>
        </div>

        {/* Config panel */}
        <div className="glass rounded-2xl p-5 border border-white/10 space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Forecast Configuration</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Dataset */}
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Dataset</label>
              <select
                value={selectedDataset}
                onChange={(e) => setSelectedDataset(e.target.value)}
                className="w-full bg-white/5 border border-white/10 text-white text-sm rounded-xl px-3 py-2
                           focus:outline-none focus:border-indigo-500/50"
              >
                {datasets.length === 0 && <option value="">No datasets</option>}
                {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>

            {/* Date column */}
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Date Column</label>
              <select
                value={dateCol}
                onChange={(e) => setDateCol(e.target.value)}
                className="w-full bg-white/5 border border-white/10 text-white text-sm rounded-xl px-3 py-2
                           focus:outline-none focus:border-indigo-500/50"
              >
                <option value="">Auto-detect</option>
                {columns?.date_columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Target column */}
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Target Column</label>
              <select
                value={targetCol}
                onChange={(e) => setTargetCol(e.target.value)}
                className="w-full bg-white/5 border border-white/10 text-white text-sm rounded-xl px-3 py-2
                           focus:outline-none focus:border-indigo-500/50"
              >
                <option value="">Auto-detect</option>
                {columns?.numeric_columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Periods */}
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Forecast Periods</label>
              <input
                type="number"
                min={1}
                max={365}
                value={periods}
                onChange={(e) => setPeriods(Number(e.target.value))}
                className="w-full bg-white/5 border border-white/10 text-white text-sm rounded-xl px-3 py-2
                           focus:outline-none focus:border-indigo-500/50"
              />
            </div>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            {/* Method */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Method:</label>
              <div className="flex gap-1.5">
                {METHODS.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => setMethod(m.value)}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
                      method === m.value
                        ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300'
                        : 'border-white/10 text-slate-400 hover:border-white/20'
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Run button — disabled when dataset is not a time series */}
            <button
              onClick={runForecast}
              disabled={loading || !selectedDataset || columns?.is_time_series === false}
              title={
                columns?.is_time_series === false
                  ? 'This dataset does not contain a time series'
                  : undefined
              }
              className="ml-auto flex items-center gap-2 px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500
                         text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? (
                <><RefreshCw className="w-4 h-4 animate-spin" /> Running...</>
              ) : (
                <><Play className="w-4 h-4" /> Run Forecast</>
              )}
            </button>
          </div>
        </div>

        {/* Non-time-series warning */}
        {columns && columns.is_time_series === false && (
          <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-semibold">Forecasting Not Available for This Dataset</p>
              <p className="mt-1 text-amber-400/80">
                {columns.not_time_series_reason ||
                  'This dataset does not contain a time series. Forecasting requires multiple time periods.'}
              </p>
              <p className="mt-1.5 text-xs text-amber-500/70">
                Try the <strong>Analytics</strong> or <strong>Auto Analyst</strong> pages for distribution,
                correlation, and ranking analysis instead.
              </p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-5">
            {/* Summary */}
            <div className="flex items-start gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm">
              <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{result.summary}</span>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: 'MAE', value: result.metrics?.mae, desc: 'Mean Absolute Error' },
                { label: 'RMSE', value: result.metrics?.rmse, desc: 'Root Mean Squared Error' },
                { label: 'MAPE', value: result.metrics?.mape !== undefined ? `${result.metrics.mape}%` : '–', desc: 'Mean Abs. Percentage Error' },
              ].map((m) => (
                <div key={m.label} className="glass rounded-2xl p-4 border border-white/10 text-center">
                  <div className="text-2xl font-bold text-white">{m.value ?? '–'}</div>
                  <div className="text-sm font-semibold text-slate-300 mt-0.5">{m.label}</div>
                  <div className="text-xs text-slate-500">{m.desc}</div>
                </div>
              ))}
            </div>

            {/* Chart */}
            {result.chart && (
              <div className="glass rounded-2xl p-5 border border-white/10">
                <h3 className="text-sm font-semibold text-slate-300 mb-4">
                  {result.target_column} Forecast — {result.method.toUpperCase()} · Next {result.periods} periods
                </h3>
                <Plot
                  data={result.chart.data}
                  layout={{
                    ...result.chart.layout,
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: { color: '#94a3b8', size: 11 },
                    xaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                    yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                    legend: { bgcolor: 'transparent', bordercolor: 'transparent' },
                    margin: { l: 50, r: 30, t: 20, b: 50 },
                    height: 380,
                  }}
                  config={{ displayModeBar: true, displaylogo: false, responsive: true }}
                  style={{ width: '100%' }}
                />
              </div>
            )}

            {/* Forecast table */}
            <div className="glass rounded-2xl border border-white/10 overflow-hidden">
              <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-300">
                  Forecast Values
                  <span className="text-slate-500 font-normal ml-2">(first 10 of {result.forecast.dates.length} periods)</span>
                </h3>
                <button
                  onClick={downloadCsv}
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-emerald-400 transition-colors px-3 py-1.5 rounded-lg hover:bg-emerald-500/10 border border-transparent hover:border-emerald-500/20"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download CSV
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/5">
                      <th className="text-left px-5 py-3 text-xs text-slate-500 font-medium">Date</th>
                      <th className="text-right px-5 py-3 text-xs text-slate-500 font-medium">Prediction</th>
                      <th className="text-right px-5 py-3 text-xs text-slate-500 font-medium">Lower (95%)</th>
                      <th className="text-right px-5 py-3 text-xs text-slate-500 font-medium">Upper (95%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.forecast.dates.slice(0, 10).map((date, i) => (
                      <tr key={date} className="border-b border-white/5 hover:bg-white/2 transition-colors">
                        <td className="px-5 py-2.5 text-slate-300">{date}</td>
                        <td className="px-5 py-2.5 text-right font-semibold text-white">
                          {result.forecast.predictions[i]?.toFixed(2)}
                        </td>
                        <td className="px-5 py-2.5 text-right text-slate-500">
                          {result.forecast.lower[i]?.toFixed(2)}
                        </td>
                        <td className="px-5 py-2.5 text-right text-slate-500">
                          {result.forecast.upper[i]?.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && !error && columns?.is_time_series !== false && (
          <div className="text-center py-16 text-slate-500">
            <TrendingUp className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-sm">Select a dataset and click <strong className="text-slate-400">Run Forecast</strong> to get started.</p>
            <p className="text-xs mt-1 opacity-60">Requires a dataset with at least one date column and multiple time periods.</p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

export default function ForecastingPage() {
  return (
    <Suspense fallback={null}>
      <ForecastingContent />
    </Suspense>
  );
}
