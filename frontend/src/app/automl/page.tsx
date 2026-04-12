'use client';

import { useState, useEffect, useRef } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import { Bot, Play, RefreshCw, Trash2, BarChart2, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, automlApi } from '@/lib/api';

interface Dataset { id: string; name: string; status: string; }
interface AutoMLJob {
  id: string;
  dataset_id: string;
  target_column: string;
  task_type: string;
  status: string;
  best_model: string;
  cv_score: number;
  metrics: Record<string, any>;
  feature_importance: Record<string, number>;
  confusion_matrix: number[][];
  result_data: any;
  error_message: string;
  created_at: string;
  completed_at: string;
}

const TASK_TYPES = [
  { value: 'classification', label: 'Classification', desc: 'Churn, fraud detection, category prediction' },
  { value: 'regression', label: 'Regression', desc: 'Sales forecasting, price prediction, revenue estimation' },
  { value: 'clustering', label: 'Clustering', desc: 'Customer segmentation, anomaly grouping' },
];

const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-amber-500/10 text-amber-300',
  training: 'bg-blue-500/10 text-blue-300',
  done: 'bg-emerald-500/10 text-emerald-300',
  error: 'bg-red-500/10 text-red-300',
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  queued: <Clock className="w-3 h-3" />,
  training: <RefreshCw className="w-3 h-3 animate-spin" />,
  done: <CheckCircle2 className="w-3 h-3" />,
  error: <AlertCircle className="w-3 h-3" />,
};

export default function AutoMLPage() {
  const [tab, setTab] = useState<'train' | 'models' | 'predict'>('train');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [targetColumn, setTargetColumn] = useState('');
  const [taskType, setTaskType] = useState('classification');
  const [training, setTraining] = useState(false);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [jobs, setJobs] = useState<AutoMLJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<AutoMLJob | null>(null);
  const [predictRecords, setPredictRecords] = useState('');
  const [predictions, setPredictions] = useState<any[]>([]);
  const [predicting, setPredicting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    datasetsApi.list().then(r => setDatasets(r.data.filter((d: Dataset) => d.status === 'ready')));
    fetchJobs();
  }, []);

  useEffect(() => {
    if (selectedDataset) {
      setLoadingColumns(true);
      setColumns([]);
      setTargetColumn('');
      datasetsApi.get(selectedDataset).then(r => {
        const meta = r.data.columns_meta || [];
        const cols = Array.isArray(meta)
          ? meta.map((c: { name?: string }) => c.name || String(c)).filter(Boolean)
          : Object.keys(meta);
        setColumns(cols);
      }).finally(() => setLoadingColumns(false));
    }
  }, [selectedDataset]);

  const fetchJobs = async () => {
    try {
      const res = await automlApi.listJobs();
      setJobs(res.data);
    } catch {}
  };

  const handleTrain = async () => {
    if (!selectedDataset || !targetColumn) { toast.error('Select dataset and target column'); return; }
    if (taskType === 'classification' && (targetColumn === 'date' || targetColumn.toLowerCase().includes('date'))) {
      toast.error('Date columns cannot be used as classification targets. Select a categorical column.');
      return;
    }
    setTraining(true);
    try {
      const res = await automlApi.train({ dataset_id: selectedDataset, target_column: targetColumn, task_type: taskType });
      const jobId = res.data.job_id;
      toast.success('Training started!');
      setTab('models');
      pollJob(jobId);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Training failed');
    } finally {
      setTraining(false);
    }
  };

  const pollJob = (jobId: string) => {
    const poll = async () => {
      try {
        const res = await automlApi.getJob(jobId);
        const job = res.data;
        setJobs(prev => {
          const updated = prev.filter(j => j.id !== job.id);
          return [job, ...updated];
        });
        if (job.status === 'done') {
          toast.success(`Training complete! Best model: ${job.best_model}`);
        } else if (job.status === 'error') {
          toast.error(`Training failed: ${job.error_message}`);
        } else {
          pollRef.current = setTimeout(poll, 3000);
        }
      } catch {}
    };
    poll();
  };

  const handleDelete = async (jobId: string) => {
    try {
      await automlApi.deleteModel(jobId);
      setJobs(prev => prev.filter(j => j.id !== jobId));
      if (selectedJob?.id === jobId) setSelectedJob(null);
      toast.success('Model deleted');
    } catch {
      toast.error('Failed to delete model');
    }
  };

  const handlePredict = async () => {
    if (!selectedJob) { toast.error('Select a model first'); return; }
    let records: any[];
    try {
      records = JSON.parse(predictRecords);
      if (!Array.isArray(records)) records = [records];
    } catch {
      toast.error('Invalid JSON — enter an array of records');
      return;
    }
    setPredicting(true);
    try {
      const res = await automlApi.predict(selectedJob.id, records);
      setPredictions(res.data.predictions);
      toast.success(`${res.data.count} predictions generated`);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Prediction failed');
    } finally {
      setPredicting(false);
    }
  };

  const topFeatures = selectedJob?.feature_importance
    ? Object.entries(selectedJob.feature_importance).slice(0, 10)
    : [];

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Bot className="w-6 h-6 text-indigo-400" />
            AutoML
          </h1>
          <p className="text-slate-400 mt-1">No-code machine learning — train classification, regression, and clustering models in minutes</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          {(['train', 'models', 'predict'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-xl text-sm font-medium capitalize transition-colors ${
                tab === t ? 'bg-indigo-600 text-white' : 'glass text-slate-400 hover:text-white'
              }`}
            >
              {t === 'train' ? 'Train Model' : t === 'models' ? 'My Models' : 'Predictions'}
            </button>
          ))}
        </div>

        {/* Train Tab */}
        {tab === 'train' && (
          <div className="glass rounded-2xl p-6 space-y-6">
            <h2 className="text-lg font-semibold text-white">Configure Training</h2>

            {/* Task type selection */}
            <div>
              <label className="text-sm text-slate-400 mb-2 block">Task Type</label>
              <div className="grid grid-cols-3 gap-3">
                {TASK_TYPES.map(t => (
                  <button
                    key={t.value}
                    onClick={() => setTaskType(t.value)}
                    className={`p-4 rounded-xl border text-left transition-all ${
                      taskType === t.value
                        ? 'border-indigo-500 bg-indigo-500/10'
                        : 'border-white/5 glass hover:border-white/20'
                    }`}
                  >
                    <div className="font-medium text-white text-sm">{t.label}</div>
                    <div className="text-xs text-slate-400 mt-1">{t.desc}</div>
                  </button>
                ))}
              </div>
            </div>

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
              {taskType !== 'clustering' && (
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">
                    Target Column (what to predict) {loadingColumns && <span className="text-indigo-400 text-xs ml-1">Loading…</span>}
                  </label>
                  <select
                    value={targetColumn}
                    onChange={e => setTargetColumn(e.target.value)}
                    disabled={!columns.length || loadingColumns}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
                  >
                    <option value="">{loadingColumns ? '— Loading columns… —' : '— Select target column —'}</option>
                    {columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              )}
            </div>

            <button
              onClick={handleTrain}
              disabled={training || !selectedDataset || (taskType !== 'clustering' && !targetColumn)}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50 transition-colors"
            >
              {training ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {training ? 'Starting training…' : 'Start Training'}
            </button>
          </div>
        )}

        {/* Models Tab */}
        {tab === 'models' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold text-white">Trained Models</h2>
              <button onClick={fetchJobs} className="text-slate-400 hover:text-white">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
            {jobs.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center text-slate-400">
                No models trained yet. Go to Train Model tab to get started.
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map(job => (
                  <div
                    key={job.id}
                    onClick={() => setSelectedJob(job.id === selectedJob?.id ? null : job)}
                    className={`glass rounded-2xl p-5 cursor-pointer transition-all ${
                      selectedJob?.id === job.id ? 'border border-indigo-500/50' : 'border border-transparent hover:border-white/10'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${STATUS_STYLES[job.status] || ''}`}>
                          {STATUS_ICONS[job.status]}
                          {job.status}
                        </span>
                        <span className="text-white font-medium">{job.task_type}</span>
                        <span className="text-slate-400 text-sm">→ {job.target_column}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        {job.best_model && (
                          <span className="text-slate-300 text-sm">{job.best_model}</span>
                        )}
                        {job.cv_score != null && (
                          <span className="text-indigo-400 font-mono text-sm">
                            score: {job.cv_score.toFixed(3)}
                          </span>
                        )}
                        <button
                          onClick={e => { e.stopPropagation(); handleDelete(job.id); }}
                          className="text-slate-600 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Expanded details */}
                    {selectedJob?.id === job.id && job.status === 'done' && (
                      <div className="mt-4 pt-4 border-t border-white/5 space-y-4">
                        {/* Feature importance */}
                        {topFeatures.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
                              <BarChart2 className="w-4 h-4" />
                              Feature Importance
                            </h4>
                            <div className="space-y-2">
                              {topFeatures.map(([feat, imp]) => (
                                <div key={feat} className="flex items-center gap-3">
                                  <span className="text-xs text-slate-400 w-36 truncate">{feat}</span>
                                  <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                                    <div
                                      className="h-full rounded-full bg-indigo-500"
                                      style={{ width: `${(imp as number) * 100}%` }}
                                    />
                                  </div>
                                  <span className="text-xs font-mono text-slate-400 w-12 text-right">
                                    {((imp as number) * 100).toFixed(1)}%
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <button
                          onClick={() => { setSelectedJob(job); setTab('predict'); }}
                          className="text-sm text-indigo-400 hover:text-indigo-300"
                        >
                          Run predictions with this model →
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Predict Tab */}
        {tab === 'predict' && (
          <div className="glass rounded-2xl p-6 space-y-5">
            <h2 className="text-lg font-semibold text-white">Run Predictions</h2>

            {/* Model selector */}
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Select Trained Model</label>
              <select
                value={selectedJob?.id || ''}
                onChange={e => setSelectedJob(jobs.find(j => j.id === e.target.value) || null)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">— Select a trained model —</option>
                {jobs.filter(j => j.status === 'done').map(j => (
                  <option key={j.id} value={j.id}>{j.task_type} → {j.target_column} ({j.best_model})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm text-slate-400 mb-1 block">Input Data (JSON array of records)</label>
              <textarea
                value={predictRecords}
                onChange={e => setPredictRecords(e.target.value)}
                placeholder={'[{"age": 35, "income": 75000, "tenure": 24}]'}
                rows={6}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-indigo-500 resize-none"
              />
            </div>

            <button
              onClick={handlePredict}
              disabled={predicting || !selectedJob || !predictRecords.trim()}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50 transition-colors"
            >
              {predicting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
              {predicting ? 'Predicting…' : 'Run Prediction'}
            </button>

            {predictions.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-slate-300 mb-3">Results</h3>
                <div className="space-y-2">
                  {predictions.map((p: any, i) => (
                    <div key={i} className="flex items-center gap-4 p-3 rounded-xl bg-white/3">
                      <span className="text-xs text-slate-500">#{i + 1}</span>
                      <span className="text-white font-medium">
                        {p.prediction !== undefined ? String(p.prediction) : `Cluster ${p.cluster}`}
                      </span>
                      {p.confidence !== undefined && (
                        <span className="text-indigo-400 text-sm ml-auto">{(p.confidence * 100).toFixed(1)}% confidence</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
