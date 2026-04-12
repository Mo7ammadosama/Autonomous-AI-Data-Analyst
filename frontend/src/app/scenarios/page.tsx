'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Sliders, Play, Save, Share2, BarChart2, ArrowUpRight,
  ArrowDownRight, Minus, RefreshCw, ChevronDown, Database
} from 'lucide-react';
import { toast } from 'sonner';
import dynamic from 'next/dynamic';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { apiClient } from '@/lib/api';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface FeatureMeta {
  name: string;
  min: number;
  max: number;
  mean: number;
  std: number;
}

interface AutoMLJob {
  id: string;
  target_column: string;
  task_type: string;
  status: string;
  best_model?: string;
}

interface SimulationResult {
  baseline_prediction: number;
  scenario_prediction: number;
  delta: number;
  delta_pct: number;
  feature_impacts: Array<{ feature: string; prediction_impact: number; direction: string; baseline_value: number; scenario_value: number }>;
  chart?: any;
}

export default function ScenariosPage() {
  const [jobs, setJobs] = useState<AutoMLJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<AutoMLJob | null>(null);
  const [features, setFeatures] = useState<FeatureMeta[]>([]);
  const [sliders, setSliders] = useState<Record<string, number>>({});
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scenarioName, setScenarioName] = useState('');

  useEffect(() => {
    apiClient.get('/api/automl/jobs').then(res => {
      const done = (Array.isArray(res.data) ? res.data : res.data?.jobs || [])
        .filter((j: AutoMLJob) => j.status === 'done');
      setJobs(done);
      if (done.length > 0) selectJob(done[0]);
    }).catch(() => {});
  }, []);

  const selectJob = async (job: AutoMLJob) => {
    setSelectedJob(job);
    setResult(null);
    try {
      const res = await apiClient.get(`/api/scenarios/model-features/${job.id}`);
      const feats: FeatureMeta[] = res.data.features || [];
      setFeatures(feats);
      const initial: Record<string, number> = {};
      feats.forEach(f => { initial[f.name] = f.mean; });
      setSliders(initial);
    } catch {
      toast.error('Failed to load model features');
    }
  };

  const runSimulation = async () => {
    if (!selectedJob) return;
    setLoading(true);
    try {
      const res = await apiClient.post('/api/scenarios/simulate', {
        automl_job_id: selectedJob.id,
        input_assumptions: sliders,
        save: false,
      });
      setResult(res.data);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Simulation failed');
    } finally {
      setLoading(false);
    }
  };

  const saveScenario = async () => {
    if (!selectedJob || !result) return;
    setSaving(true);
    try {
      await apiClient.post('/api/scenarios/simulate', {
        automl_job_id: selectedJob.id,
        input_assumptions: sliders,
        name: scenarioName || `Scenario ${new Date().toLocaleString()}`,
        save: true,
      });
      toast.success('Scenario saved!');
    } catch {
      toast.error('Failed to save scenario');
    } finally {
      setSaving(false);
    }
  };

  const resetSliders = () => {
    const reset: Record<string, number> = {};
    features.forEach(f => { reset[f.name] = f.mean; });
    setSliders(reset);
    setResult(null);
  };

  const deltaDir = result ? (result.delta > 0 ? 'up' : result.delta < 0 ? 'down' : 'flat') : 'flat';
  const DeltaIcon = deltaDir === 'up' ? ArrowUpRight : deltaDir === 'down' ? ArrowDownRight : Minus;

  return (
    <AppLayout>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <PageHeader
          title="What-If Scenarios"
          subtitle="Adjust input assumptions and see how predictions change — Qlik AutoML style"
          icon={<Sliders className="w-6 h-6 text-indigo-400" />}
        />

        {/* Job selector */}
        {jobs.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No trained AutoML models found.</p>
            <p className="text-sm mt-1">Go to the AutoML page to train a model first.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Sliders */}
            <div className="lg:col-span-2 space-y-4">
              {/* Model selector */}
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <label className="text-xs text-gray-400 mb-2 block">Select Trained Model</label>
                <div className="flex flex-wrap gap-2">
                  {jobs.map(job => (
                    <button
                      key={job.id}
                      onClick={() => selectJob(job)}
                      className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                        selectedJob?.id === job.id
                          ? 'bg-indigo-600 text-white'
                          : 'bg-white/5 border border-white/10 text-gray-300 hover:bg-white/10'
                      }`}
                    >
                      {job.target_column} ({job.task_type})
                    </button>
                  ))}
                </div>
              </div>

              {/* Feature sliders */}
              {features.length > 0 && (
                <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-white">Adjust Input Features</h3>
                    <button
                      onClick={resetSliders}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-white"
                    >
                      <RefreshCw className="w-3 h-3" /> Reset to baseline
                    </button>
                  </div>

                  {features.map(feat => (
                    <div key={feat.name}>
                      <div className="flex justify-between items-center mb-1.5">
                        <span className="text-sm text-gray-300">{feat.name}</span>
                        <div className="flex items-center gap-2">
                          {sliders[feat.name] !== feat.mean && (
                            <span className={`text-xs font-medium ${
                              sliders[feat.name] > feat.mean ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {sliders[feat.name] > feat.mean ? '▲' : '▼'} {Math.abs(((sliders[feat.name] - feat.mean) / (feat.mean || 1)) * 100).toFixed(0)}%
                            </span>
                          )}
                          <input
                            type="number"
                            value={sliders[feat.name]?.toFixed(2) || feat.mean}
                            onChange={e => setSliders({ ...sliders, [feat.name]: parseFloat(e.target.value) || 0 })}
                            className="w-24 px-2 py-1 text-xs bg-white/10 border border-white/20 rounded text-white text-right"
                          />
                        </div>
                      </div>
                      <input
                        type="range"
                        min={feat.min}
                        max={feat.max}
                        step={(feat.max - feat.min) / 100}
                        value={sliders[feat.name] || feat.mean}
                        onChange={e => setSliders({ ...sliders, [feat.name]: parseFloat(e.target.value) })}
                        className="w-full h-2 rounded-full accent-indigo-500 cursor-pointer"
                      />
                      <div className="flex justify-between text-xs text-gray-600 mt-0.5">
                        <span>{feat.min.toFixed(2)}</span>
                        <span className="text-gray-500">baseline: {feat.mean.toFixed(2)}</span>
                        <span>{feat.max.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}

                  <button
                    onClick={runSimulation}
                    disabled={loading}
                    className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-xl text-white font-medium transition-colors flex items-center justify-center gap-2"
                  >
                    {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    {loading ? 'Simulating…' : 'Run Simulation'}
                  </button>
                </div>
              )}
            </div>

            {/* Right: Results */}
            <div className="space-y-4">
              {result ? (
                <>
                  {/* Prediction comparison */}
                  <div className="bg-white/5 border border-white/10 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-gray-400 mb-4">Prediction Comparison</h3>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-400">Baseline</span>
                        <span className="text-white font-mono">{result.baseline_prediction.toFixed(4)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-400">Scenario</span>
                        <span className="text-white font-mono font-bold">{result.scenario_prediction.toFixed(4)}</span>
                      </div>
                      <div className="h-px bg-white/10" />
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-400">Change</span>
                        <span className={`flex items-center gap-1 font-bold ${
                          deltaDir === 'up' ? 'text-green-400' : deltaDir === 'down' ? 'text-red-400' : 'text-gray-400'
                        }`}>
                          <DeltaIcon className="w-4 h-4" />
                          {Math.abs(result.delta_pct).toFixed(2)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Feature impacts */}
                  {result.feature_impacts.length > 0 && (
                    <div className="bg-white/5 border border-white/10 rounded-xl p-5">
                      <h3 className="text-sm font-semibold text-gray-400 mb-3">Feature Impacts</h3>
                      <div className="space-y-2">
                        {result.feature_impacts.slice(0, 5).map(imp => (
                          <div key={imp.feature}>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-gray-300">{imp.feature}</span>
                              <span className={imp.direction === 'positive' ? 'text-green-400' : 'text-red-400'}>
                                {imp.direction === 'positive' ? '+' : ''}{imp.prediction_impact.toFixed(4)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Save */}
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
                    <input
                      type="text"
                      placeholder="Scenario name (optional)"
                      value={scenarioName}
                      onChange={e => setScenarioName(e.target.value)}
                      className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-sm text-white placeholder-gray-500"
                    />
                    <button
                      onClick={saveScenario}
                      disabled={saving}
                      className="w-full py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 rounded-lg text-sm text-white transition-colors flex items-center justify-center gap-2"
                    >
                      <Save className="w-4 h-4" />
                      {saving ? 'Saving…' : 'Save Scenario'}
                    </button>
                  </div>
                </>
              ) : (
                <div className="bg-white/5 border border-white/10 rounded-xl p-8 text-center text-gray-500">
                  <BarChart2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">Adjust the sliders and click</p>
                  <p className="text-sm">&quot;Run Simulation&quot; to see results</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Waterfall chart */}
        {result?.chart && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white/5 border border-white/10 rounded-xl p-5"
          >
            <h3 className="text-sm font-semibold text-white mb-4">What-If Impact Waterfall</h3>
            <Plot
              data={result.chart.data}
              layout={{ ...result.chart.layout, autosize: true }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '400px' }}
            />
          </motion.div>
        )}
      </div>
    </AppLayout>
  );
}
