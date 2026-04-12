'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDropzone } from 'react-dropzone';
import {
  Database, Upload, Trash2, BarChart2, MessageSquare, Eye,
  RefreshCw, FileText, CheckCircle, XCircle, Clock,
  Sparkles, X, TrendingUp, ChevronRight, Wand2, CheckCheck, Download
} from 'lucide-react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { toast } from 'sonner';
import { datasetsApi, exportApi } from '@/lib/api';
import { formatBytes, formatDate, cn } from '@/lib/utils';

// Dynamic import to avoid SSR issues
const PipelineResults = dynamic(
  () => import('@/components/pipeline/PipelineResults'),
  { ssr: false, loading: () => (
    <div className="flex items-center justify-center py-12 text-slate-500">
      <RefreshCw className="w-4 h-4 animate-spin mr-2" />
      <span className="text-sm">Loading analysis...</span>
    </div>
  )}
);

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [previewDs, setPreviewDs] = useState<any>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [analysisDs, setAnalysisDs] = useState<any>(null); // pipeline panel
  const [cleanDs, setCleanDs] = useState<any>(null);
  const [cleanOpts, setCleanOpts] = useState({
    missing_strategy: 'median' as 'median' | 'mean' | 'mode' | 'drop',
    remove_outliers: false,
    outlier_threshold: 3.0,
    column_renames: {} as Record<string, string>,
    drop_columns: [] as string[],
  });
  const [cleaning, setCleaning] = useState(false);
  const [cleanReport, setCleanReport] = useState<any>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const load = async () => {
    try {
      const res = await datasetsApi.list();
      const data: any[] = res.data;
      setDatasets(data);

      // Auto-poll only while datasets are processing (interval: 8s instead of 5s)
      const hasPending = data.some(d => d.status !== 'ready' && d.status !== 'error');
      if (hasPending && !pollRef.current) {
        pollRef.current = setInterval(async () => {
          try {
            const r = await datasetsApi.list();
            setDatasets(r.data);
            const stillPending = r.data.some((d: any) => d.status !== 'ready' && d.status !== 'error');
            if (!stillPending) { clearInterval(pollRef.current!); pollRef.current = null; }
          } catch { clearInterval(pollRef.current!); pollRef.current = null; }
        }, 8000);
      }
    } catch {} finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    for (const file of acceptedFiles) {
      setUploading(true);
      setUploadProgress(0);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('name', file.name.replace(/\.[^/.]+$/, ''));
      try {
        const interval = setInterval(() => setUploadProgress(p => Math.min(p + 10, 85)), 300);
        await datasetsApi.upload(formData);
        clearInterval(interval);
        setUploadProgress(100);
        await load();
        toast.success(`"${file.name.replace(/\.[^/.]+$/, '')}" uploaded successfully`, {
          description: 'AI pipeline analysis has started in the background.',
        });
      } catch (err: any) {
        console.error('Upload error:', err);
        toast.error('Upload failed', {
          description: err?.response?.data?.detail || 'Please check the file format and try again.',
        });
      } finally {
        setTimeout(() => { setUploading(false); setUploadProgress(0); }, 500);
      }
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/json': ['.json'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    multiple: true,
  });

  const handleExport = async (id: string, name: string, fmt: string = 'csv') => {
    try {
      const res = await exportApi.download(id, fmt);
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${name}.${fmt === 'excel' ? 'xlsx' : fmt}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported as ${fmt.toUpperCase()}`);
    } catch {
      toast.error('Export failed');
    }
  };

  const handleDelete = async (id: string) => {
    const ds = datasets.find(d => d.id === id);
    if (!confirm('Delete this dataset?')) return;
    try {
      await datasetsApi.delete(id);
      setDatasets(prev => prev.filter(d => d.id !== id));
      if (analysisDs?.id === id) setAnalysisDs(null);
      toast.success(`"${ds?.name || 'Dataset'}" deleted`);
    } catch {
      toast.error('Failed to delete dataset');
    }
  };

  const handlePreview = async (ds: any) => {
    setPreviewDs(ds);
    try {
      const res = await datasetsApi.preview(ds.id, 10);
      setPreviewData(res.data);
    } catch {}
  };

  const openClean = (ds: any) => {
    setCleanDs(ds);
    setCleanReport(null);
    // Build default rename map from columns
    const renames: Record<string, string> = {};
    (ds.columns_meta || []).forEach((c: any) => { renames[c.name] = c.name; });
    setCleanOpts(prev => ({ ...prev, column_renames: renames, drop_columns: [] }));
  };

  const handleClean = async () => {
    if (!cleanDs) return;
    setCleaning(true);
    try {
      // Build renames: only include changed names
      const renames: Record<string, string> = {};
      Object.entries(cleanOpts.column_renames).forEach(([orig, newName]) => {
        if (orig !== newName && newName.trim()) renames[orig] = newName.trim();
      });
      const res = await datasetsApi.clean(cleanDs.id, {
        missing_strategy: cleanOpts.missing_strategy,
        remove_outliers: cleanOpts.remove_outliers,
        outlier_threshold: cleanOpts.outlier_threshold,
        column_renames: Object.keys(renames).length > 0 ? renames : undefined,
        drop_columns: cleanOpts.drop_columns.length > 0 ? cleanOpts.drop_columns : undefined,
      });
      setCleanReport(res.data.report);
      toast.success('Dataset cleaned successfully', {
        description: `${res.data.report.operations?.length || 0} operations applied`,
      });
      await load();
    } catch (err: any) {
      toast.error('Cleaning failed', { description: err?.response?.data?.detail || 'Unknown error' });
    } finally {
      setCleaning(false);
    }
  };

  const statusIcon = (status: string) => {
    if (status === 'ready') return <CheckCircle className="w-4 h-4 text-emerald-400" />;
    if (status === 'error') return <XCircle className="w-4 h-4 text-red-400" />;
    return <Clock className="w-4 h-4 text-amber-400 animate-spin" />;
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-7xl">
        <PageHeader
          title="Dataset Manager"
          subtitle="Upload and manage your data sources"
          icon={<Database className="w-5 h-5 text-indigo-400" />}
        />

        {/* Upload zone */}
        <motion.div
          {...(getRootProps() as any)}
          className={cn(
            'rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer transition-all',
            isDragActive
              ? 'border-indigo-500 bg-indigo-500/10'
              : 'border-white/10 hover:border-indigo-500/40 hover:bg-white/2'
          )}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          whileHover={{ scale: 1.005 }}
        >
          <input {...getInputProps()} />
          <motion.div
            className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-4"
            animate={isDragActive ? { scale: 1.1 } : {}}
          >
            <Upload className={cn('w-8 h-8', isDragActive ? 'text-indigo-400' : 'text-slate-500')} />
          </motion.div>

          {uploading ? (
            <div>
              <p className="text-white font-semibold mb-2">Uploading & analyzing...</p>
              <div className="w-48 h-2 bg-white/10 rounded-full mx-auto overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          ) : (
            <>
              <p className="text-white font-semibold mb-1">
                {isDragActive ? 'Drop files here' : 'Drag & drop datasets'}
              </p>
              <p className="text-slate-500 text-sm">Supports CSV, JSON, Excel (.xlsx, .xls)</p>
              <p className="text-indigo-400 text-sm mt-2 font-medium">or click to browse</p>
            </>
          )}
        </motion.div>

        {/* Dataset list */}
        {loading ? (
          <TableSkeleton />
        ) : datasets.length === 0 ? (
          <div className="glass rounded-xl p-12 text-center border border-white/5">
            <FileText className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No datasets uploaded yet</p>
          </div>
        ) : (
          <div className="glass rounded-xl border border-white/5 overflow-hidden">
            <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-300">{datasets.length} datasets</span>
              <button onClick={load} className="text-slate-500 hover:text-slate-300 transition-colors">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
            <div className="divide-y divide-white/5">
              {datasets.map((ds, i) => (
                <div key={ds.id}>
                  <motion.div
                    className={cn(
                      'px-5 py-4 flex items-center gap-4 transition-colors cursor-pointer',
                      analysisDs?.id === ds.id
                        ? 'bg-indigo-500/5 hover:bg-indigo-500/8'
                        : 'hover:bg-white/2'
                    )}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.04 }}
                    onClick={() => setAnalysisDs(analysisDs?.id === ds.id ? null : ds)}
                  >
                    <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/15 flex items-center justify-center flex-shrink-0">
                      <Database className="w-5 h-5 text-indigo-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white truncate">{ds.name}</span>
                        {statusIcon(ds.status)}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {ds.row_count?.toLocaleString() || '–'} rows · {ds.column_count || '–'} cols
                        · {formatBytes(ds.file_size || 0)} · {ds.file_type?.toUpperCase()}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                      {/* AI Analysis button — highlight when active */}
                      <button
                        onClick={() => setAnalysisDs(analysisDs?.id === ds.id ? null : ds)}
                        className={cn(
                          'p-2 rounded-lg transition-all flex items-center gap-1.5 text-xs font-medium',
                          analysisDs?.id === ds.id
                            ? 'text-indigo-300 bg-indigo-500/20 hover:bg-indigo-500/30'
                            : 'text-slate-500 hover:text-indigo-300 hover:bg-indigo-500/10'
                        )}
                        title="AI Analysis"
                        disabled={ds.status !== 'ready'}
                      >
                        <Sparkles className="w-4 h-4" />
                        <span className="hidden sm:inline">Analysis</span>
                        <ChevronRight className={cn(
                          'w-3 h-3 transition-transform hidden sm:block',
                          analysisDs?.id === ds.id ? 'rotate-90' : ''
                        )} />
                      </button>

                      <button
                        onClick={() => handlePreview(ds)}
                        className="p-2 text-slate-500 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                        title="Preview"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openClean(ds)}
                        className="p-2 text-slate-500 hover:text-violet-400 hover:bg-violet-500/10 rounded-lg transition-all"
                        title="Clean Dataset"
                        disabled={ds.status !== 'ready'}
                      >
                        <Wand2 className="w-4 h-4" />
                      </button>
                      <Link href={`/analytics?id=${ds.id}`}>
                        <button
                          className="p-2 text-slate-500 hover:text-indigo-400 hover:bg-indigo-500/10 rounded-lg transition-all"
                          title="Analyze"
                        >
                          <BarChart2 className="w-4 h-4" />
                        </button>
                      </Link>
                      <Link href={`/forecasting?dataset=${ds.id}`}>
                        <button
                          className="p-2 text-slate-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-all"
                          title="Forecast"
                        >
                          <TrendingUp className="w-4 h-4" />
                        </button>
                      </Link>
                      <Link href={`/chat?dataset=${ds.id}`}>
                        <button
                          className="p-2 text-slate-500 hover:text-violet-400 hover:bg-violet-500/10 rounded-lg transition-all"
                          title="Chat"
                        >
                          <MessageSquare className="w-4 h-4" />
                        </button>
                      </Link>
                      <button
                        onClick={() => handleExport(ds.id, ds.name, 'csv')}
                        disabled={ds.status !== 'ready'}
                        className="p-2 text-slate-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-all disabled:opacity-40"
                        title="Export CSV"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(ds.id)}
                        className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </motion.div>

                  {/* Inline pipeline results panel */}
                  <AnimatePresence>
                    {analysisDs?.id === ds.id && ds.status === 'ready' && (
                      <motion.div
                        key={`pipeline-${ds.id}`}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: 'easeInOut' }}
                        className="overflow-hidden"
                      >
                        <div className="mx-5 mb-5 p-5 rounded-2xl bg-white/3 border border-indigo-500/20">
                          {/* Panel header */}
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                              <div className="p-1.5 rounded-lg bg-indigo-500/15 border border-indigo-500/25">
                                <Sparkles className="w-4 h-4 text-indigo-400" />
                              </div>
                              <div>
                                <h3 className="text-sm font-semibold text-white">AI Analysis Pipeline</h3>
                                <p className="text-xs text-slate-500">{ds.name}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Link href={`/analytics?id=${ds.id}`}>
                                <button className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors">
                                  <BarChart2 className="w-3.5 h-3.5" />
                                  Full Analytics
                                </button>
                              </Link>
                              <button
                                onClick={() => setAnalysisDs(null)}
                                className="text-slate-500 hover:text-white transition-colors ml-2"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          </div>

                          {/* Pipeline results */}
                          <PipelineResults datasetId={ds.id} />
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Dataset Cleaning Modal */}
        <AnimatePresence>
          {cleanDs && (
            <motion.div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            >
              <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => { setCleanDs(null); setCleanReport(null); }} />
              <motion.div
                className="relative z-10 glass rounded-2xl border border-white/10 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
                initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
              >
                <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Wand2 className="w-4 h-4 text-violet-400" />
                    <h3 className="font-bold text-white">Clean Dataset</h3>
                    <span className="text-xs text-slate-500 ml-1">— {cleanDs.name}</span>
                  </div>
                  <button onClick={() => { setCleanDs(null); setCleanReport(null); }} className="text-slate-500 hover:text-white transition-colors">
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="overflow-y-auto flex-1 p-5 space-y-5">
                  {cleanReport ? (
                    /* ── Results ── */
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
                        <CheckCheck className="w-4 h-4" /> Cleaning Complete
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="glass rounded-xl p-3 border border-white/5 text-center">
                          <div className="text-lg font-bold text-white">{cleanReport.rows_before?.toLocaleString()}</div>
                          <div className="text-xs text-slate-500">Rows before</div>
                        </div>
                        <div className="glass rounded-xl p-3 border border-white/5 text-center">
                          <div className="text-lg font-bold text-emerald-400">{cleanReport.rows_after?.toLocaleString()}</div>
                          <div className="text-xs text-slate-500">Rows after</div>
                        </div>
                      </div>
                      <div className="glass rounded-xl border border-white/5 divide-y divide-white/5 overflow-hidden">
                        {(cleanReport.operations || []).length === 0 && (
                          <div className="px-4 py-3 text-sm text-slate-500">No operations were needed — data is already clean.</div>
                        )}
                        {(cleanReport.operations || []).map((op: string, i: number) => (
                          <div key={i} className="px-4 py-2.5 text-xs text-slate-300 flex items-center gap-2">
                            <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                            {op}
                          </div>
                        ))}
                      </div>
                      <button
                        onClick={() => setCleanReport(null)}
                        className="text-xs text-violet-400 hover:text-violet-300 transition-colors"
                      >
                        ← Back to options
                      </button>
                    </div>
                  ) : (
                    /* ── Options ── */
                    <div className="space-y-5">
                      {/* Missing values */}
                      <div className="space-y-2">
                        <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Missing Value Strategy</label>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                          {(['median', 'mean', 'mode', 'drop'] as const).map(s => (
                            <button
                              key={s}
                              onClick={() => setCleanOpts(prev => ({ ...prev, missing_strategy: s }))}
                              className={cn(
                                'py-2 rounded-xl text-sm font-medium border transition-colors capitalize',
                                cleanOpts.missing_strategy === s
                                  ? 'bg-violet-600/20 border-violet-500/50 text-violet-300'
                                  : 'bg-white/3 border-white/8 text-slate-400 hover:text-white hover:border-white/20'
                              )}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                        <p className="text-xs text-slate-600">
                          {cleanOpts.missing_strategy === 'drop' ? 'Rows with any missing value will be dropped.' : `Numeric columns filled with ${cleanOpts.missing_strategy}, text with mode.`}
                        </p>
                      </div>

                      {/* Outlier removal */}
                      <div className="flex items-center justify-between p-4 bg-white/3 rounded-xl border border-white/5">
                        <div>
                          <div className="text-sm font-medium text-white">Remove Outliers</div>
                          <div className="text-xs text-slate-500 mt-0.5">Z-score method on numeric columns</div>
                        </div>
                        <button
                          onClick={() => setCleanOpts(prev => ({ ...prev, remove_outliers: !prev.remove_outliers }))}
                          className={cn('w-11 h-6 rounded-full relative transition-colors', cleanOpts.remove_outliers ? 'bg-violet-600' : 'bg-white/10')}
                        >
                          <div className={cn('w-4 h-4 rounded-full bg-white absolute top-1 transition-all', cleanOpts.remove_outliers ? 'left-6' : 'left-1')} />
                        </button>
                      </div>
                      {cleanOpts.remove_outliers && (
                        <div className="space-y-1.5">
                          <label className="text-xs text-slate-400">Z-score Threshold: <strong className="text-white">{cleanOpts.outlier_threshold}</strong></label>
                          <input
                            type="range" min="1.5" max="5" step="0.5"
                            value={cleanOpts.outlier_threshold}
                            onChange={e => setCleanOpts(prev => ({ ...prev, outlier_threshold: parseFloat(e.target.value) }))}
                            className="w-full accent-violet-500"
                          />
                          <div className="flex justify-between text-xs text-slate-600"><span>Aggressive (1.5)</span><span>Lenient (5.0)</span></div>
                        </div>
                      )}

                      {/* Column renames */}
                      {(cleanDs.columns_meta || []).length > 0 && (
                        <div className="space-y-2">
                          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Column Names</label>
                          <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                            {(cleanDs.columns_meta || []).map((col: any) => (
                              <div key={col.name} className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={!cleanOpts.drop_columns.includes(col.name)}
                                  onChange={e => setCleanOpts(prev => ({
                                    ...prev,
                                    drop_columns: e.target.checked
                                      ? prev.drop_columns.filter(c => c !== col.name)
                                      : [...prev.drop_columns, col.name]
                                  }))}
                                  className="accent-violet-500 flex-shrink-0"
                                />
                                <span className="text-xs text-slate-500 w-32 truncate flex-shrink-0" title={col.name}>{col.name}</span>
                                <input
                                  value={cleanOpts.column_renames[col.name] ?? col.name}
                                  onChange={e => setCleanOpts(prev => ({
                                    ...prev,
                                    column_renames: { ...prev.column_renames, [col.name]: e.target.value }
                                  }))}
                                  disabled={cleanOpts.drop_columns.includes(col.name)}
                                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1 text-xs text-white disabled:opacity-30 focus:outline-none focus:border-violet-500/50"
                                />
                                <span className="text-xs text-slate-600 flex-shrink-0">{col.type}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {!cleanReport && (
                  <div className="px-5 py-4 border-t border-white/5 flex items-center justify-between">
                    <p className="text-xs text-slate-600">Changes overwrite the dataset file.</p>
                    <button
                      onClick={handleClean}
                      disabled={cleaning}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors disabled:opacity-60"
                    >
                      {cleaning ? (
                        <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Cleaning...</>
                      ) : (
                        <><Wand2 className="w-4 h-4" /> Apply Cleaning</>
                      )}
                    </button>
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Data Preview modal */}
        <AnimatePresence>
          {previewDs && (
            <motion.div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            >
              <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setPreviewDs(null)} />
              <motion.div
                className="relative z-10 glass rounded-2xl border border-white/10 w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col"
                initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
              >
                <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
                  <div>
                    <h3 className="font-display font-bold text-white">{previewDs.name}</h3>
                    <p className="text-xs text-slate-500">{previewDs.row_count?.toLocaleString()} total rows</p>
                  </div>
                  <button
                    onClick={() => setPreviewDs(null)}
                    className="text-slate-500 hover:text-white transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <div className="overflow-auto flex-1 p-4">
                  {previewData ? (
                    <table className="w-full text-xs">
                      <thead>
                        <tr>
                          {previewData.columns?.map((col: string) => (
                            <th
                              key={col}
                              className="text-left px-3 py-2 text-slate-400 font-semibold border-b border-white/5 whitespace-nowrap"
                            >
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.rows?.map((row: any, i: number) => (
                          <tr key={i} className="border-b border-white/3 hover:bg-white/2">
                            {previewData.columns?.map((col: string) => (
                              <td
                                key={col}
                                className="px-3 py-2 text-slate-300 whitespace-nowrap max-w-[150px] overflow-hidden text-ellipsis"
                              >
                                {row[col]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="flex items-center justify-center h-32">
                      <div className="w-6 h-6 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
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
