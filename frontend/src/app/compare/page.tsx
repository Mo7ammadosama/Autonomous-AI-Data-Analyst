'use client';

import { useState, useEffect } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import { GitCompare, Plus, X, BarChart2, TrendingUp, Activity, AlertCircle, GitMerge } from 'lucide-react';
import { datasetsApi, analyticsApi, compareApi } from '@/lib/api';
import { cn, formatBytes } from '@/lib/utils';
import { toast } from 'sonner';
import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Dataset { id: string; name: string; row_count: number; column_count: number; file_size: number; status: string; }
interface DSState { dataset: Dataset | null; overview: any; loading: boolean; }

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444'];

// Static slot-count to grid-class map (avoids dynamic Tailwind class purging)
const SLOT_GRID: Record<number, string> = { 2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-4' };

const CHART_LAYOUT_BASE = {
  height: 220,
  showlegend: false,
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#94a3b8', size: 10 },
  yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
  xaxis: { color: '#64748b' },
  margin: { l: 40, r: 10, t: 30, b: 50 },
};

export default function ComparePage() {
  const [allDatasets, setAllDatasets] = useState<Dataset[]>([]);
  const [slots, setSlots] = useState<DSState[]>([
    { dataset: null, overview: null, loading: false },
    { dataset: null, overview: null, loading: false },
  ]);
  const [activeView, setActiveView] = useState<'kpi' | 'columns' | 'stats' | 'quality' | 'drift'>('kpi');
  const [driftReport, setDriftReport] = useState<any>(null);
  const [driftLoading, setDriftLoading] = useState(false);

  useEffect(() => {
    datasetsApi.list().then(r => setAllDatasets(r.data.filter((d: Dataset) => d.status === 'ready')));
  }, []);

  const loadSlot = async (slotIdx: number, dsId: string) => {
    const ds = allDatasets.find(d => d.id === dsId);
    if (!ds) return;
    setSlots(prev => { const n = [...prev]; n[slotIdx] = { ...n[slotIdx], dataset: ds, loading: true }; return n; });
    try {
      const res = await analyticsApi.overview(dsId);
      setSlots(prev => { const n = [...prev]; n[slotIdx] = { dataset: ds, overview: res.data, loading: false }; return n; });
    } catch {
      toast.error(`Failed to load overview for ${ds.name}`);
      setSlots(prev => { const n = [...prev]; n[slotIdx] = { ...n[slotIdx], loading: false }; return n; });
    }
  };

  const addSlot = () => {
    if (slots.length >= 4) return;
    setSlots(prev => [...prev, { dataset: null, overview: null, loading: false }]);
  };

  const removeSlot = (idx: number) => {
    if (slots.length <= 2) return;
    setSlots(prev => prev.filter((_, i) => i !== idx));
  };

  const clearSlot = (idx: number) => {
    setSlots(prev => { const n = [...prev]; n[idx] = { dataset: null, overview: null, loading: false }; return n; });
  };

  const runDriftAnalysis = async () => {
    if (filledSlots.length < 2) return;
    setDriftLoading(true);
    try {
      const res = await compareApi.compare(filledSlots[0].dataset!.id, filledSlots[1].dataset!.id);
      setDriftReport(res.data);
      setActiveView('drift');
    } catch {
      toast.error('Drift analysis failed');
    } finally {
      setDriftLoading(false);
    }
  };

  const filledSlots = slots.filter(s => s.dataset && s.overview);
  const slotCount = Math.min(slots.length, 4);
  const filledCount = filledSlots.length;

  // Common numeric columns across ALL filled slots
  const getCommonNumericColumns = () => {
    if (filledCount < 2) return [];
    const colSets = filledSlots.map(s => {
      const keys: string[] = [];
      if (s.overview?.column_stats) {
        Object.entries(s.overview.column_stats).forEach(([col, info]: any) => {
          if (info?.mean !== undefined) keys.push(col);
        });
      }
      return new Set(keys);
    });
    return Array.from(colSets[0]).filter(col => colSets.every(s => s.has(col))).slice(0, 6);
  };
  const commonCols = getCommonNumericColumns();

  // Build a grouped bar chart comparing a metric across filled datasets
  const buildBarChart = (title: string, getValue: (s: DSState) => number) => ({
    data: filledSlots.map((s, i) => ({
      type: 'bar' as const,
      name: s.dataset!.name,
      x: [s.dataset!.name],
      y: [getValue(s)],
      marker: { color: COLORS[i] },
    })),
    layout: { ...CHART_LAYOUT_BASE, title: { text: title, font: { color: '#94a3b8', size: 12 } } },
  });

  return (
    <AppLayout>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20">
              <GitCompare className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Dataset Comparison</h1>
              <p className="text-sm text-slate-400">Compare up to 4 datasets side-by-side — KPIs, columns, statistics, and data quality</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {filledSlots.length === 2 && (
              <button
                onClick={runDriftAnalysis}
                disabled={driftLoading}
                className="flex items-center gap-2 px-3 py-2 rounded-xl bg-violet-500/20 border border-violet-500/30 text-violet-300 hover:bg-violet-500/30 text-sm transition-colors disabled:opacity-50"
              >
                <GitMerge className="w-4 h-4" /> {driftLoading ? 'Analyzing...' : 'Drift Analysis'}
              </button>
            )}
            {slots.length < 4 && (
              <button
                onClick={addSlot}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-white/10 text-slate-400 hover:text-white hover:border-white/20 text-sm transition-colors"
              >
                <Plus className="w-4 h-4" /> Add Dataset
              </button>
            )}
          </div>
        </div>

        {/* Slot selectors — static class lookup to avoid Tailwind purging */}
        <div className={cn('grid gap-4', SLOT_GRID[slotCount] || 'grid-cols-2')}>
          {slots.map((slot, i) => (
            <div key={i} className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: COLORS[i] }} />
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Dataset {i + 1}</span>
                {slot.dataset && (
                  <button onClick={() => clearSlot(i)} className="ml-auto p-1 text-slate-600 hover:text-slate-400 transition-colors" title="Clear">
                    <X className="w-3 h-3" />
                  </button>
                )}
                {slots.length > 2 && !slot.dataset && (
                  <button onClick={() => removeSlot(i)} className="ml-auto p-1 text-slate-600 hover:text-red-400 transition-colors" title="Remove slot">
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
              <div className={cn('glass rounded-xl p-3 border transition-colors', slot.dataset ? 'border-white/15' : 'border-white/8 border-dashed')}>
                <select
                  value={slot.dataset?.id || ''}
                  onChange={e => { if (e.target.value) loadSlot(i, e.target.value); else clearSlot(i); }}
                  className="w-full bg-transparent text-white text-xs focus:outline-none cursor-pointer"
                >
                  <option value="">— Select a dataset —</option>
                  {allDatasets
                    .filter(d => !slots.some((s, si) => si !== i && s.dataset?.id === d.id))
                    .map(d => <option key={d.id} value={d.id}>{d.name}</option>)
                  }
                </select>
                {slot.loading && (
                  <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-500">
                    <div className="w-3 h-3 border border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
                    Loading overview...
                  </div>
                )}
                {slot.dataset && !slot.loading && (
                  <div className="mt-2 space-y-0.5 text-xs text-slate-500">
                    <div className="font-medium text-slate-300 truncate">{slot.dataset.name}</div>
                    <div>{slot.dataset.row_count?.toLocaleString()} rows · {slot.dataset.column_count} cols · {formatBytes(slot.dataset.file_size)}</div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Empty state */}
        {filledCount < 2 && (
          <div className="text-center py-16 text-slate-500">
            <GitCompare className="w-12 h-12 mx-auto mb-4 opacity-20" />
            <p className="text-sm">Select at least <strong className="text-slate-400">2 datasets</strong> above to compare</p>
            <p className="text-xs mt-1 opacity-60">Compares KPIs, column distributions, statistical summaries, and data quality metrics</p>
          </div>
        )}

        {/* Comparison content */}
        {filledCount >= 2 && (
          <div className="space-y-5">
            {/* View tabs */}
            <div className="flex gap-1 border-b border-white/5 overflow-x-auto">
              {[
                { id: 'kpi',     label: 'KPI Overview', icon: Activity },
                { id: 'columns', label: 'Columns',       icon: BarChart2 },
                { id: 'stats',   label: 'Statistics',    icon: TrendingUp },
                { id: 'quality', label: 'Data Quality',  icon: AlertCircle },
                { id: 'drift',   label: 'Drift Report',  icon: GitMerge },
              ].map(v => (
                <button
                  key={v.id}
                  onClick={() => setActiveView(v.id as any)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg whitespace-nowrap transition-colors border-b-2',
                    activeView === v.id
                      ? 'text-cyan-400 border-cyan-500'
                      : 'text-slate-500 border-transparent hover:text-slate-300'
                  )}
                >
                  <v.icon className="w-3.5 h-3.5" />{v.label}
                </button>
              ))}
            </div>

            {/* ── KPI Overview ─────────────────────────────────────────── */}
            {activeView === 'kpi' && (
              <div className="space-y-5">
                {/* Side-by-side cards */}
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${filledCount}, minmax(0, 1fr))`, gap: '0.75rem' }}>
                  {filledSlots.map((s, i) => (
                    <div key={i} className="glass rounded-xl p-4 border space-y-3" style={{ borderColor: `${COLORS[i]}40` }}>
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: COLORS[i] }} />
                        <span className="text-sm font-bold text-white truncate">{s.dataset!.name}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { label: 'Rows',           value: s.dataset!.row_count?.toLocaleString() },
                          { label: 'Columns',        value: s.dataset!.column_count },
                          { label: 'File Size',      value: formatBytes(s.dataset!.file_size) },
                          { label: 'Numeric Cols',   value: s.overview?.numeric_columns?.length ?? '–' },
                          { label: 'Missing %',      value: s.overview?.missing_percentage != null ? `${s.overview.missing_percentage.toFixed(1)}%` : '–' },
                          { label: 'Duplicates',     value: s.overview?.duplicate_count ?? '–' },
                        ].map(kpi => (
                          <div key={kpi.label} className="text-center p-2 bg-white/3 rounded-lg border border-white/5">
                            <div className="text-sm font-bold text-white">{kpi.value}</div>
                            <div className="text-xs text-slate-500 leading-tight">{kpi.label}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Bar charts */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { title: 'Row Count',    getValue: (s: DSState) => s.dataset!.row_count },
                    { title: 'Column Count', getValue: (s: DSState) => s.dataset!.column_count },
                  ].map(cfg => {
                    const chart = buildBarChart(cfg.title, cfg.getValue);
                    return (
                      <div key={cfg.title} className="glass rounded-xl p-4 border border-white/10">
                        <Plot
                          data={chart.data as any}
                          layout={chart.layout as any}
                          config={{ displayModeBar: false, responsive: true }}
                          style={{ width: '100%' }}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Columns ────────────────────────────────────────────────── */}
            {activeView === 'columns' && (
              <div className="glass rounded-xl border border-white/10 overflow-x-auto">
                {/* Use inline gridTemplateColumns for dynamic column count */}
                <div
                  style={{ display: 'grid', gridTemplateColumns: `180px repeat(${filledCount}, minmax(0, 1fr))` }}
                  className="divide-y divide-white/5"
                >
                  {/* Header row */}
                  <div className="px-4 py-2.5 bg-white/3 text-xs font-semibold text-slate-400 border-b border-white/5">Column</div>
                  {filledSlots.map((s, i) => (
                    <div
                      key={i}
                      className="px-4 py-2.5 bg-white/3 text-xs font-semibold text-white truncate border-b border-white/5"
                      style={{ borderLeft: `2px solid ${COLORS[i]}` }}
                    >
                      {s.dataset!.name}
                    </div>
                  ))}

                  {/* Data rows */}
                  {commonCols.length > 0 ? commonCols.map(col => (
                    <>
                      <div key={`lbl-${col}`} className="px-4 py-2.5 text-xs text-slate-300 font-mono border-t border-white/5 truncate self-center">{col}</div>
                      {filledSlots.map((s, i) => {
                        const stats = s.overview?.column_stats?.[col];
                        return (
                          <div key={`${col}-${i}`} className="px-4 py-2.5 text-xs text-slate-400 border-t border-white/5" style={{ borderLeft: `2px solid ${COLORS[i]}20` }}>
                            {stats ? (
                              <div className="space-y-0.5">
                                <div>μ={typeof stats.mean === 'number' ? stats.mean.toFixed(2) : '–'}</div>
                                <div>σ={typeof stats.std === 'number' ? stats.std.toFixed(2) : '–'}</div>
                                <div className="text-slate-600">min={typeof stats.min === 'number' ? stats.min.toFixed(2) : '–'}</div>
                                <div className="text-slate-600">max={typeof stats.max === 'number' ? stats.max.toFixed(2) : '–'}</div>
                              </div>
                            ) : <span className="text-slate-600">N/A in this dataset</span>}
                          </div>
                        );
                      })}
                    </>
                  )) : (
                    <div className="px-4 py-8 col-span-full text-sm text-slate-500 text-center">
                      No common numeric columns found across all selected datasets.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Statistics ─────────────────────────────────────────────── */}
            {activeView === 'stats' && (
              <div className="space-y-4">
                {commonCols.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {commonCols.map(col => {
                      const chartData = filledSlots.map((s, i) => {
                        const stats = s.overview?.column_stats?.[col];
                        return {
                          type: 'bar' as const,
                          name: s.dataset!.name,
                          x: ['Mean', 'Median', 'Std Dev'],
                          y: [stats?.mean ?? 0, stats?.median ?? 0, stats?.std ?? 0],
                          marker: { color: COLORS[i] },
                        };
                      });
                      return (
                        <div key={col} className="glass rounded-xl p-4 border border-white/10">
                          <div className="text-xs font-semibold text-slate-400 mb-2 font-mono">{col}</div>
                          <Plot
                            data={chartData as any}
                            layout={{
                              height: 200,
                              barmode: 'group',
                              showlegend: filledCount > 2,
                              paper_bgcolor: 'transparent',
                              plot_bgcolor: 'transparent',
                              font: { color: '#94a3b8', size: 10 },
                              yaxis: { gridcolor: 'rgba(255,255,255,0.05)', color: '#64748b' },
                              xaxis: { color: '#64748b' },
                              legend: { bgcolor: 'transparent', font: { size: 9 } },
                              margin: { l: 35, r: 10, t: 10, b: 40 },
                            }}
                            config={{ displayModeBar: false, responsive: true }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-12 text-slate-500">
                    <p className="text-sm">No common numeric columns found — select datasets with overlapping column names.</p>
                  </div>
                )}
              </div>
            )}

            {/* ── Data Quality ───────────────────────────────────────────── */}
            {activeView === 'quality' && (
              <div className="glass rounded-xl border border-white/10 overflow-x-auto">
                <table className="w-full text-xs min-w-[500px]">
                  <thead>
                    <tr className="border-b border-white/5 bg-white/3">
                      <th className="text-left px-4 py-3 text-slate-400 font-semibold">Quality Metric</th>
                      {filledSlots.map((s, i) => (
                        <th key={i} className="text-center px-4 py-3 text-white font-semibold" style={{ borderLeft: `3px solid ${COLORS[i]}` }}>
                          <div className="flex items-center justify-center gap-1.5">
                            <div className="w-2 h-2 rounded-full" style={{ background: COLORS[i] }} />
                            <span className="truncate max-w-[120px]">{s.dataset!.name}</span>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {[
                      { label: '📊 Total Rows',        fn: (s: DSState) => s.dataset!.row_count?.toLocaleString() },
                      { label: '📋 Total Columns',     fn: (s: DSState) => String(s.dataset!.column_count) },
                      { label: '💾 File Size',         fn: (s: DSState) => formatBytes(s.dataset!.file_size) },
                      { label: '❓ Missing Values %',  fn: (s: DSState) => s.overview?.missing_percentage != null ? `${s.overview.missing_percentage.toFixed(2)}%` : '–' },
                      { label: '🔁 Duplicate Rows',    fn: (s: DSState) => String(s.overview?.duplicate_count ?? '–') },
                      { label: '🔢 Numeric Columns',   fn: (s: DSState) => String(s.overview?.numeric_columns?.length ?? '–') },
                      { label: '🔤 Categorical Cols',  fn: (s: DSState) => String(s.overview?.categorical_columns?.length ?? '–') },
                      { label: '📅 Date Columns',      fn: (s: DSState) => String(s.overview?.datetime_columns?.length ?? '–') },
                    ].map(row => (
                      <tr key={row.label} className="hover:bg-white/2 transition-colors">
                        <td className="px-4 py-3 text-slate-400">{row.label}</td>
                        {filledSlots.map((s, i) => {
                          const val = row.fn(s);
                          return (
                            <td key={i} className="px-4 py-3 text-center text-white font-medium" style={{ borderLeft: `2px solid ${COLORS[i]}20` }}>
                              {val}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {/* ── Drift Report ────────────────────────────────────────────── */}
            {activeView === 'drift' && (
              <div className="space-y-4">
                {!driftReport ? (
                  <div className="text-center py-12 text-slate-500">
                    <GitMerge className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">Click <strong className="text-violet-300">Drift Analysis</strong> above to compare two datasets statistically.</p>
                  </div>
                ) : (
                  <>
                    {/* Summary bullets */}
                    {driftReport.summary?.length > 0 && (
                      <div className="glass rounded-xl p-4 border border-violet-500/20 space-y-2">
                        <p className="text-xs font-semibold text-violet-300 mb-2">Summary</p>
                        {driftReport.summary.map((s: string, i: number) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-slate-300">
                            <span className="text-violet-400 mt-0.5">→</span> {s}
                          </div>
                        ))}
                      </div>
                    )}
                    {/* Column drift table */}
                    <div className="glass rounded-xl border border-white/10 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-white/5 bg-white/3">
                            <th className="text-left px-4 py-3 text-slate-400">Column</th>
                            <th className="text-center px-4 py-3 text-slate-400">{driftReport.datasets?.[0] ?? 'A'} Mean</th>
                            <th className="text-center px-4 py-3 text-slate-400">{driftReport.datasets?.[1] ?? 'B'} Mean</th>
                            <th className="text-center px-4 py-3 text-slate-400">Drift %</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {Object.entries(driftReport.column_stats || {}).map(([col, info]: [string, any]) => (
                            <tr key={col} className="hover:bg-white/2">
                              <td className="px-4 py-2.5 font-mono text-slate-300">{col}</td>
                              <td className="px-4 py-2.5 text-center text-slate-400">{info.stats1?.mean ?? '–'}</td>
                              <td className="px-4 py-2.5 text-center text-slate-400">{info.stats2?.mean ?? '–'}</td>
                              <td className="px-4 py-2.5 text-center">
                                {info.mean_diff_pct != null ? (
                                  <span className={cn('px-2 py-0.5 rounded-full font-bold', info.mean_diff_pct > 20 ? 'text-red-400 bg-red-400/10' : info.mean_diff_pct > 5 ? 'text-amber-400 bg-amber-400/10' : 'text-emerald-400 bg-emerald-400/10')}>
                                    {info.mean_diff_pct.toFixed(1)}%
                                  </span>
                                ) : <span className="text-slate-600">N/A</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
