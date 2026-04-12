'use client';

import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Loader2, CheckCircle2, AlertTriangle, XCircle,
  BookOpen, Lightbulb, TrendingUp, ShieldAlert, RefreshCw
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { pipelineApi } from '@/lib/api';

interface Props {
  datasetId: string;
  /** If true, auto-start a run if no pipeline result exists */
  autoStart?: boolean;
}

type Tab = 'story' | 'insights' | 'recommendations' | 'anomalies';

const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: 'story',           label: 'Data Story',       icon: BookOpen },
  { id: 'insights',        label: 'Insights',         icon: Lightbulb },
  { id: 'recommendations', label: 'Recommendations',  icon: TrendingUp },
  { id: 'anomalies',       label: 'Anomalies',        icon: ShieldAlert },
];

const POLL_INTERVAL_MS = 4000;

const SEVERITY_COLORS: Record<string, string> = {
  high:    'border-red-500/30 bg-red-500/5 text-red-300',
  medium:  'border-yellow-500/30 bg-yellow-500/5 text-yellow-300',
  low:     'border-green-500/30 bg-green-500/5 text-green-300',
  info:    'border-blue-500/30 bg-blue-500/5 text-blue-300',
  warning: 'border-orange-500/30 bg-orange-500/5 text-orange-300',
  success: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300',
};

export default function PipelineResults({ datasetId, autoStart = false }: Props) {
  const [pipeline, setPipeline] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('story');
  const [running, setRunning] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const res = await pipelineApi.get(datasetId);
        const data = res.data;
        setPipeline(data);
        if (data.status === 'done' || data.status === 'error') {
          stopPolling();
          setRunning(false);
        }
      } catch { stopPolling(); setRunning(false); }
    }, POLL_INTERVAL_MS);
  };

  const fetchPipeline = async () => {
    setLoading(true);
    try {
      const res = await pipelineApi.get(datasetId);
      const data = res.data;
      setPipeline(data);
      // If still running, start polling immediately
      if (data && data.status === 'running') {
        setRunning(true);
        startPolling();
      }
    } catch {
      setPipeline(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (datasetId) fetchPipeline();
    return () => stopPolling();
  }, [datasetId]);

  const triggerRun = async () => {
    setRunning(true);
    try {
      await pipelineApi.run(datasetId);
      startPolling();
    } catch {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        <span className="text-sm">Loading analysis pipeline...</span>
      </div>
    );
  }

  if (!pipeline) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-slate-400 mb-4">Auto-analysis pipeline has not run yet.</p>
        <button
          onClick={triggerRun}
          disabled={running}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500
                     text-white text-sm font-medium transition-colors disabled:opacity-50"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {running ? 'Running analysis...' : 'Run Full Analysis'}
        </button>
      </div>
    );
  }

  // Status badges
  const statusIcon = pipeline.status === 'done'
    ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
    : pipeline.status === 'running'
    ? <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
    : pipeline.status === 'error'
    ? <XCircle className="w-4 h-4 text-red-400" />
    : <AlertTriangle className="w-4 h-4 text-yellow-400" />;

  return (
    <div className="space-y-4">
      {/* Status bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          {statusIcon}
          <span className="text-slate-400">
            Pipeline: <span className="text-white font-medium capitalize">{pipeline.status}</span>
          </span>
          {pipeline.updated_at && (
            <span className="text-xs text-slate-600">
              · {new Date(pipeline.updated_at).toLocaleString()}
            </span>
          )}
        </div>
        <button
          onClick={triggerRun}
          disabled={running || pipeline.status === 'running'}
          className="text-xs text-slate-500 hover:text-white flex items-center gap-1.5 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
          Re-run
        </button>
      </div>

      {pipeline.status === 'error' && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs">
          {pipeline.error_message || 'Pipeline failed. Click re-run to try again.'}
        </div>
      )}

      {pipeline.status === 'done' && (
        <>
          {/* Tabs */}
          <div className="flex gap-1 border-b border-white/5">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'text-indigo-400 border-indigo-500'
                    : 'text-slate-500 border-transparent hover:text-slate-300'
                }`}
              >
                <tab.icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <motion.div key={activeTab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>

            {/* Data Story */}
            {activeTab === 'story' && (
              <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed">
                <ReactMarkdown>{pipeline.story || 'No story generated.'}</ReactMarkdown>
              </div>
            )}

            {/* Insights */}
            {activeTab === 'insights' && (
              <div className="space-y-3">
                {(pipeline.insights || []).length === 0 && (
                  <p className="text-sm text-slate-500">No insights generated.</p>
                )}
                {(pipeline.insights || []).map((ins: any, i: number) => (
                  <div
                    key={i}
                    className={`p-4 rounded-xl border ${SEVERITY_COLORS[ins.severity] || SEVERITY_COLORS.info}`}
                  >
                    <div className="font-semibold text-sm mb-1">{ins.title}</div>
                    <div className="text-xs opacity-80">{ins.content}</div>
                    {ins.metric_value && (
                      <div className="mt-2 text-lg font-bold">{ins.metric_value}</div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Recommendations */}
            {activeTab === 'recommendations' && (
              <div className="space-y-3">
                {(pipeline.recommendations || []).length === 0 && (
                  <p className="text-sm text-slate-500">No recommendations generated.</p>
                )}
                {(pipeline.recommendations || []).map((rec: any, i: number) => {
                  const priorityColor = {
                    high: 'text-red-400',
                    medium: 'text-yellow-400',
                    low: 'text-green-400',
                  }[rec.priority as string] || 'text-slate-400';
                  return (
                    <div key={i} className="p-4 rounded-xl bg-white/3 border border-white/8 space-y-2">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold uppercase ${priorityColor}`}>{rec.priority}</span>
                        <span className="text-sm font-semibold text-white">{rec.title}</span>
                      </div>
                      <p className="text-xs text-slate-400">{rec.description}</p>
                      <div className="text-xs text-indigo-300 font-medium">
                        → {rec.ai_action || rec.action}
                      </div>
                      {rec.expected_impact && (
                        <div className="text-xs text-slate-500">Impact: {rec.expected_impact}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Anomalies */}
            {activeTab === 'anomalies' && (
              <div className="space-y-3">
                {pipeline.anomalies?.summary_alerts?.length === 0 && (
                  <div className="flex items-center gap-2 text-emerald-400 text-sm">
                    <CheckCircle2 className="w-4 h-4" />
                    No significant anomalies detected.
                  </div>
                )}
                {(pipeline.anomalies?.summary_alerts || []).map((alert: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 p-3 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-300 text-xs">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    <span>{alert}</span>
                  </div>
                ))}
                {pipeline.anomalies?.multivariate_anomalies && (
                  <div className="p-3 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-400">
                    {pipeline.anomalies.multivariate_anomalies.description}
                  </div>
                )}
              </div>
            )}

          </motion.div>
        </>
      )}
    </div>
  );
}
