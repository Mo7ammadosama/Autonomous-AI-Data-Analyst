'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Sparkles, Loader2, ExternalLink, AlertCircle,
  CheckCircle2, BarChart2, ChevronRight,
} from 'lucide-react';
import { agentApi, datasetsApi, getErrorMessage } from '@/lib/api';
import { cn } from '@/lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Dataset { id: string; name: string; status: string; }

interface AgentRecommendation {
  action: string;
  priority: 'high' | 'medium' | 'low';
  expected_impact: string;
}

interface StructuredResult {
  executive_summary: string;
  key_findings: string[];
  root_causes?: string[];
  recommendations?: AgentRecommendation[];
  risks?: string[];
  confidence?: string;
  data_quality_notes?: string;
}

type RunStatus = 'idle' | 'running' | 'done' | 'failed';

interface Props { onClose: () => void; }

const PRIORITY_BORDER: Record<string, string> = {
  high:   'border-red-500/40 bg-red-500/5',
  medium: 'border-yellow-500/40 bg-yellow-500/5',
  low:    'border-green-500/40 bg-green-500/5',
};
const PRIORITY_BADGE: Record<string, string> = {
  high:   'bg-red-500/20 text-red-300',
  medium: 'bg-yellow-500/20 text-yellow-300',
  low:    'bg-green-500/20 text-green-300',
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function CopilotPanel({ onClose }: Props) {
  const [task, setTask] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [status, setStatus] = useState<RunStatus>('idle');
  const [result, setResult] = useState<StructuredResult | string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  const esRef = useRef<EventSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load datasets
  useEffect(() => {
    datasetsApi.list().then(r => {
      const ready = (Array.isArray(r.data) ? r.data : r.data?.datasets || [])
        .filter((d: Dataset) => d.status === 'ready');
      setDatasets(ready);
      if (ready.length > 0) setDatasetId(ready[0].id);
    }).catch(() => {});
  }, []);

  // Clean up SSE on unmount
  useEffect(() => () => { esRef.current?.close(); }, []);

  const currentDate = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  const tryParseStructured = (text: string): StructuredResult | null => {
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === 'object' && 'executive_summary' in parsed) {
        return parsed as StructuredResult;
      }
    } catch { /* not JSON */ }
    return null;
  };

  const analyze = useCallback(async () => {
    if (!task.trim() || status === 'running') return;
    setStatus('running');
    setResult(null);
    setRunId(null);
    setErrorMsg('');
    esRef.current?.close();

    try {
      const resp = await agentApi.run(
        task.trim(),
        datasetId || undefined,
        undefined,
        undefined,
      );
      const id: string = resp.data.run_id;
      setRunId(id);

      const es = agentApi.streamRun(id);
      esRef.current = es;

      es.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          if (event.type === 'done') {
            es.close();
            const summary: string = event.summary || '';
            const structured = tryParseStructured(summary);
            setResult(structured ?? summary);
            setStatus(event.status === 'completed' ? 'done' : 'failed');
            if (event.status !== 'completed') {
              setErrorMsg(summary || 'Agent failed');
            }
          } else if (event.type === 'error' || event.type === 'timeout') {
            es.close();
            setStatus('failed');
            setErrorMsg(event.message || 'Agent error');
          }
        } catch { /* ignore parse errors */ }
      };

      es.onerror = () => {
        es.close();
        // Poll once as fallback
        agentApi.getRun(id).then(r => {
          const run = r.data;
          if (run.status === 'completed') {
            const structured = tryParseStructured(run.result_summary || '');
            setResult(structured ?? run.result_summary ?? '');
            setStatus('done');
          } else {
            setStatus('failed');
            setErrorMsg(run.result_summary || 'Stream disconnected');
          }
        }).catch(() => {
          setStatus('failed');
          setErrorMsg('Connection lost');
        });
      };
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      const status = e?.response?.status;
      const detail = getErrorMessage(err, 'Failed to start analysis');
      const isAiKeyMissing =
        status === 402 ||
        (status === 400 && /credit|api.?key|quota|billing/i.test(detail));
      const msg = isAiKeyMissing
        ? 'AI features require an API key. Set ANTHROPIC_API_KEY in your backend .env file.'
        : detail;
      setStatus('failed');
      setErrorMsg(msg);
    }
  }, [task, datasetId, status]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); analyze(); }
  };

  const reset = () => {
    esRef.current?.close();
    setStatus('idle');
    setResult(null);
    setRunId(null);
    setErrorMsg('');
    setTask('');
  };

  const structuredResult = typeof result === 'object' && result !== null ? result as StructuredResult : null;
  const plainResult = typeof result === 'string' ? result : null;

  return (
    <motion.div
      initial={{ x: '100%', opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: '100%', opacity: 0 }}
      transition={{ type: 'spring', damping: 28, stiffness: 280 }}
      className="fixed right-0 top-0 h-full w-[440px] max-w-full z-50 flex flex-col
                 bg-[#0d0d14] border-l border-white/10 shadow-2xl"
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600
                          flex items-center justify-center shadow-lg shadow-indigo-900/40">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-white">Ask DataMind</p>
            <p className="text-[10px] text-slate-500">{currentDate}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-white/10 text-white/50 hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto flex flex-col">
        {/* ── Input section ── */}
        <div className="px-5 py-4 space-y-3 border-b border-white/5 flex-shrink-0">
          {/* Dataset selector */}
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5 block">
              Dataset (optional)
            </label>
            <select
              value={datasetId}
              onChange={e => setDatasetId(e.target.value)}
              disabled={status === 'running'}
              className="w-full text-xs bg-white/5 border border-white/10 rounded-lg px-3 py-2
                         text-slate-300 focus:outline-none focus:border-indigo-500/50 disabled:opacity-50"
            >
              <option value="">No dataset — general question</option>
              {datasets.map(d => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {/* Textarea */}
          <div>
            <label className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5 block">
              Your question
            </label>
            <textarea
              ref={textareaRef}
              value={task}
              onChange={e => setTask(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask anything about your data… e.g. Why did revenue drop in Q3? Which customers are at risk of churning?"
              rows={4}
              disabled={status === 'running'}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm
                         text-white placeholder-slate-600 resize-none focus:outline-none
                         focus:border-indigo-500/50 transition-all disabled:opacity-50 leading-relaxed"
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-2">
            <button
              onClick={analyze}
              disabled={!task.trim() || status === 'running'}
              className="flex-1 flex items-center justify-center gap-2 py-2 bg-indigo-600
                         hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed
                         text-white rounded-xl text-sm font-medium transition-colors"
            >
              {status === 'running' ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Analyzing…
                </>
              ) : (
                <>
                  <BarChart2 className="w-3.5 h-3.5" />
                  Analyze
                </>
              )}
            </button>
            {status !== 'idle' && (
              <button
                onClick={reset}
                className="px-3 py-2 bg-white/5 hover:bg-white/10 text-slate-400 rounded-xl
                           text-sm transition-colors border border-white/10"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        {/* ── Running state ── */}
        {status === 'running' && (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-slate-500">
            <div className="relative">
              <div className="w-12 h-12 rounded-full bg-indigo-500/10 flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-indigo-400" />
              </div>
              <div className="absolute inset-0 rounded-full border-2 border-indigo-500/30 animate-ping" />
            </div>
            <div className="text-center">
              <p className="text-sm text-slate-300 font-medium">Agent is analyzing…</p>
              <p className="text-xs text-slate-600 mt-1">This may take 30–90 seconds</p>
            </div>
          </div>
        )}

        {/* ── Error state ── */}
        {status === 'failed' && (
          <div className="mx-5 my-4 p-4 rounded-xl border border-red-500/20 bg-red-500/5">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-300 mb-1">Analysis failed</p>
                <p className="text-xs text-red-400/70 leading-relaxed">{errorMsg}</p>
              </div>
            </div>
          </div>
        )}

        {/* ── Structured result ── */}
        {status === 'done' && structuredResult && (
          <div className="px-5 py-4 space-y-4">
            {/* Executive Summary — teal/blue box with quote icon */}
            <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal-400" />
                <p className="text-[10px] text-teal-400 font-semibold uppercase tracking-wider">
                  Executive Summary
                </p>
                {structuredResult.confidence && (
                  <span className={cn(
                    'ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded uppercase',
                    structuredResult.confidence === 'high' ? 'bg-emerald-500/20 text-emerald-300'
                    : structuredResult.confidence === 'medium' ? 'bg-yellow-500/20 text-yellow-300'
                    : 'bg-red-500/20 text-red-300'
                  )}>
                    {structuredResult.confidence} confidence
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-200 leading-relaxed">
                &ldquo;{structuredResult.executive_summary}&rdquo;
              </p>
            </div>

            {/* Top 3 Key Findings */}
            {(structuredResult.key_findings?.length ?? 0) > 0 && (
              <div>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">
                  Key Findings
                </p>
                <div className="space-y-1.5">
                  {structuredResult.key_findings.slice(0, 3).map((f, i) => (
                    <div key={i} className="flex gap-2.5 rounded-lg border border-white/5 bg-white/3 px-3 py-2.5">
                      <span className="w-5 h-5 rounded-full bg-indigo-500/20 text-indigo-300 text-[9px]
                                       font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <p className="text-xs text-slate-300 leading-relaxed">{f}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top 2 Recommendations */}
            {(structuredResult.recommendations?.length ?? 0) > 0 && (
              <div>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">
                  Top Recommendations
                </p>
                <div className="space-y-2">
                  {(structuredResult.recommendations ?? []).slice(0, 2).map((rec, i) => (
                    <div key={i} className={cn(
                      'rounded-lg border px-3 py-2.5 space-y-1',
                      PRIORITY_BORDER[rec.priority] || 'border-white/10 bg-white/3'
                    )}>
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          'text-[9px] font-bold px-1.5 py-0.5 rounded uppercase',
                          PRIORITY_BADGE[rec.priority] || 'bg-slate-500/20 text-slate-300'
                        )}>
                          {rec.priority}
                        </span>
                        <p className="text-xs text-slate-200 font-medium leading-snug">{rec.action}</p>
                      </div>
                      {rec.expected_impact && (
                        <p className="text-[11px] text-emerald-400 pl-7">{rec.expected_impact}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Open Full Analysis link */}
            {runId && (
              <a
                href="/agent"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl
                           border border-indigo-500/30 bg-indigo-500/5 hover:bg-indigo-500/15
                           text-indigo-300 text-sm font-medium transition-colors group"
              >
                Open Full Analysis
                <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </a>
            )}
          </div>
        )}

        {/* ── Plain text result fallback ── */}
        {status === 'done' && plainResult && (
          <div className="px-5 py-4 space-y-3">
            <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">
              Analysis Result
            </p>
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {plainResult.slice(0, 800)}
              {plainResult.length > 800 && '…'}
            </p>
            {runId && (
              <a
                href="/agent"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl
                           border border-indigo-500/30 bg-indigo-500/5 hover:bg-indigo-500/15
                           text-indigo-300 text-sm font-medium transition-colors group"
              >
                Open Full Analysis
                <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </a>
            )}
          </div>
        )}

        {/* ── Idle state ── */}
        {status === 'idle' && (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-slate-600">
            <Sparkles className="w-10 h-10 opacity-20" />
            <p className="text-sm text-center leading-relaxed px-6">
              Ask a business question about your data and DataMind will deliver an executive-grade analysis.
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
}
