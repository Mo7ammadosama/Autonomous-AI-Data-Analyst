'use client';

import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import AppLayout from '@/components/layout/AppLayout';
import {
  Bot, Play, Square, ChevronRight, ChevronDown, Code2,
  Eye, FileText, Zap, Clock, Coins, AlertCircle, CheckCircle2,
  Loader2, BarChart2, Brain, Trash2, Sparkles, MessageSquare,
  X, Plus, History, Flame, Rocket, TrendingUp
} from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, agentApi } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const getAuthToken = () => (typeof window !== 'undefined' ? localStorage.getItem('auth_token') || '' : '');
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

interface Dataset { id: string; name: string; status: string; }

interface AgentStep {
  iteration: number;
  thought: string;
  action: string;
  action_input: Record<string, unknown>;
  observation: string;
  figures: string[];
  error: boolean;
}

interface StreamEvent {
  type: 'step' | 'done' | 'error' | 'timeout';
  step?: AgentStep;
  status?: string;
  summary?: string;
  charts?: { title: string; base64: string }[];
  token_usage?: number;
  duration_seconds?: number;
  message?: string;
}

interface Recommendation {
  action: string;
  priority: 'high' | 'medium' | 'low';
  expected_impact: string;
}

interface StructuredResult {
  executive_summary: string;
  key_findings: string[];
  root_causes: string[];
  recommendations: Recommendation[];
  risks: string[];
  confidence: 'high' | 'medium' | 'low';
  data_quality_notes: string;
}

interface PastRun {
  id: string;
  task: string;
  status: string;
  domain?: string;
  token_usage: number;
  duration_seconds?: number;
  created_at: string;
}

interface Memory {
  id: string;
  memory_type: string;
  key: string;
  value: string;
  importance: number;
  access_count: number;
  created_at: string;
}

const DOMAINS = ['', 'finance', 'retail', 'healthcare', 'marketing', 'hr', 'operations'];

const AGENT_TIERS = [
  { key: 'lite',  label: 'DataMind Lite',  icon: Zap,    desc: 'Quick answers for everyday questions',          color: 'text-slate-300 border-white/10 hover:border-indigo-500/40' },
  { key: 'pro',   label: 'DataMind Pro',   icon: Flame,  desc: 'Deep analysis & visualizations',                color: 'text-indigo-300 border-indigo-500/50 bg-indigo-500/10'   },
  { key: 'max',   label: 'DataMind Max',   icon: Rocket, desc: 'Research-grade analysis for complex datasets',  color: 'text-violet-300 border-violet-500/30 hover:border-violet-500/50' },
] as const;

const SUGGESTED_PROMPTS = [
  'Fully analyze this dataset and give me executive insights',
  'Find anomalies and explain what caused them',
  'Build me a complete financial performance report',
  'Predict next quarter\'s revenue trend',
  'Compare this month vs last month and explain the delta',
];

const ACTION_COLORS: Record<string, string> = {
  execute_python:           'bg-indigo-500/10 text-indigo-300 border-indigo-500/20',
  execute_sql:              'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
  get_dataset_info:         'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  get_column_stats:         'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  compare_periods:          'bg-blue-500/10 text-blue-300 border-blue-500/20',
  detect_anomalies:         'bg-orange-500/10 text-orange-300 border-orange-500/20',
  generate_executive_summary:'bg-teal-500/10 text-teal-300 border-teal-500/20',
  search_domain_template:   'bg-amber-500/10 text-amber-300 border-amber-500/20',
  auto_visualize:           'bg-violet-500/10 text-violet-300 border-violet-500/20',
  save_chart:               'bg-violet-500/10 text-violet-300 border-violet-500/20',
  write_report_section:     'bg-rose-500/10 text-rose-300 border-rose-500/20',
  final_answer:             'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  error:                    'bg-red-500/10 text-red-300 border-red-500/20',
};

const PRIORITY_STYLES: Record<string, string> = {
  high:   'bg-red-500/15 text-red-300 border-red-500/30',
  medium: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  low:    'bg-green-500/15 text-green-300 border-green-500/30',
};

const CONFIDENCE_STYLES: Record<string, string> = {
  high:   'text-emerald-400 bg-emerald-500/10',
  medium: 'text-yellow-400 bg-yellow-500/10',
  low:    'text-red-400 bg-red-500/10',
};

function tryParseStructured(summary: string): StructuredResult | null {
  try {
    const parsed = JSON.parse(summary);
    if (parsed && typeof parsed === 'object' && 'executive_summary' in parsed) {
      return parsed as StructuredResult;
    }
  } catch { /* not JSON */ }
  return null;
}

const MEMORY_TYPE_COLORS: Record<string, string> = {
  preference:       'bg-indigo-500/15 text-indigo-300 border-indigo-500/25',
  domain_knowledge: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  past_analysis:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  correction:       'bg-rose-500/15 text-rose-300 border-rose-500/25',
};

// ── Step card ────────────────────────────────────────────────────────────────

function StepCard({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(true);
  const [showCode, setShowCode] = useState(false);
  const colorClass = ACTION_COLORS[step.action] || 'bg-slate-500/10 text-slate-300 border-slate-500/20';

  const hasCode = step.action === 'execute_python' && typeof step.action_input?.code === 'string';
  const hasSql  = step.action === 'execute_sql'    && typeof step.action_input?.query === 'string';
  const hasCollapsibleCode = hasCode || hasSql;

  return (
    <motion.div
      className={cn('rounded-xl border overflow-hidden bg-white/2', step.error ? 'border-red-500/30' : 'border-white/5')}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-white/5 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <span className="w-5 h-5 rounded-full bg-indigo-500/20 text-indigo-300 text-[10px] font-bold flex items-center justify-center flex-shrink-0">
          {step.iteration}
        </span>
        <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full border', colorClass)}>
          {step.action}
        </span>
        <span className="flex-1 text-xs text-slate-400 truncate">{step.thought.slice(0, 90)}</span>
        {step.error && <AlertCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />}
        {open
          ? <ChevronDown className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
          : <ChevronRight className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
        }
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 space-y-2.5 border-t border-white/5">
              {/* THOUGHT — always visible */}
              <div className="pt-2.5">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 flex items-center gap-1">
                  <Zap className="w-2.5 h-2.5" /> Thought
                </p>
                <p className="text-xs text-slate-300 leading-relaxed">{step.thought}</p>
              </div>

              {/* CODE / SQL — collapsed by default, toggle button */}
              {hasCollapsibleCode && (
                <div>
                  <button
                    onClick={() => setShowCode(v => !v)}
                    className="flex items-center gap-1.5 text-[11px] font-mono text-slate-500 hover:text-slate-300 transition-colors py-0.5"
                  >
                    <Code2 className="w-3 h-3" />
                    {showCode ? '{ } Hide Code' : '{ } Show Code'}
                  </button>
                  <AnimatePresence initial={false}>
                    {showCode && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <pre className="mt-1.5 text-[11px] bg-black/50 rounded-lg p-3 overflow-x-auto text-slate-300 font-mono max-h-44 leading-relaxed">
                          {hasCode
                            ? (step.action_input.code as string)
                            : (step.action_input.query as string)}
                        </pre>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* OBSERVATION — always visible */}
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 flex items-center gap-1">
                  <Eye className="w-2.5 h-2.5" /> Observation
                </p>
                <pre className="text-[11px] bg-black/30 rounded-lg p-3 overflow-x-auto text-slate-400 font-mono max-h-36 whitespace-pre-wrap leading-relaxed">
                  {step.observation.slice(0, 1000)}
                </pre>
              </div>

              {step.figures.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {step.figures.map((fig, i) => (
                    <img
                      key={i}
                      src={`data:image/png;base64,${fig}`}
                      alt={`Figure ${i + 1}`}
                      className="rounded-lg border border-white/10 w-full"
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Inner page (uses searchParams) ───────────────────────────────────────────

function AgentPageInner() {
  const searchParams = useSearchParams();
  const initialTask = searchParams.get('task') || '';
  const initialDataset = searchParams.get('dataset') || '';

  const [task, setTask] = useState(initialTask);
  const [domain, setDomain] = useState('');
  const [agentTier, setAgentTier] = useState<'lite' | 'pro' | 'max'>('pro');
  const [datasetId, setDatasetId] = useState(initialDataset);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [summary, setSummary] = useState('');
  const [charts, setCharts] = useState<{ title: string; base64: string }[]>([]);
  const [tokenUsage, setTokenUsage] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');

  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<string>('');

  const [pastRuns, setPastRuns] = useState<PastRun[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [correctionText, setCorrectionText] = useState('');
  const [showCorrectionInput, setShowCorrectionInput] = useState(false);

  const esRef = useRef<EventSource | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stepsEndRef = useRef<HTMLDivElement>(null);

  // Load datasets, past runs, memories
  useEffect(() => {
    datasetsApi.list().then(r => {
      const data = r.data;
      setDatasets(Array.isArray(data) ? data : (data?.datasets || []));
    }).catch(() => {});

    agentApi.getRuns().then(r => setPastRuns(r.data || [])).catch(() => {});
    agentApi.getMemories().then(r => setMemories(r.data || [])).catch(() => {});
  }, []);

  // Auto-launch if task was in URL
  useEffect(() => {
    if (initialTask) {
      setTimeout(() => startRun(), 300);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps]);

  useEffect(() => {
    if (running) {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [running]);

  const openStream = useCallback((runId: string) => {
    let retries = 0;
    const MAX_RETRIES = 3;

    const connect = () => {
      const es = agentApi.streamRun(runId);
      esRef.current = es;

      es.onmessage = (ev) => {
        try {
          const event: StreamEvent = JSON.parse(ev.data);
          if (event.type === 'step' && event.step) {
            setSteps(prev => [...prev, event.step!]);
          } else if (event.type === 'done') {
            const isOk = event.status === 'completed';
            setStatus(isOk ? 'completed' : 'failed');
            const summaryText = event.summary || (event as any).error || '';
            setSummary(summaryText);
            // Extract confidence from structured result if available
            const structured = tryParseStructured(summaryText);
            if (structured?.confidence) setConfidence(structured.confidence);
            setCharts(event.charts || []);
            setTokenUsage(event.token_usage || 0);
            setRunning(false);
            es.close();
            if (isOk) toast.success('Analysis complete!');
            else toast.error(`Agent failed: ${(event.summary || '').slice(0, 120)}`);
            agentApi.getRuns().then(r => setPastRuns(r.data || [])).catch(() => {});
            agentApi.getMemories().then(r => setMemories(r.data || [])).catch(() => {});
          } else if (event.type === 'error') {
            setStatus('failed');
            setSummary(event.message || 'Agent error');
            setRunning(false);
            es.close();
            toast.error(event.message || 'Agent error');
          } else if (event.type === 'timeout') {
            setStatus('failed');
            setSummary('Analysis timed out after 3 minutes');
            setRunning(false);
            es.close();
            toast.error('Agent timed out');
          }
          // 'ping' events are ignored — they just keep the connection alive
        } catch {}
      };

      es.onerror = () => {
        es.close();
        if (retries < MAX_RETRIES) {
          retries++;
          setTimeout(connect, 1500 * retries); // backoff: 1.5s, 3s, 4.5s
        } else {
          setStatus('failed');
          setRunning(false);
          // Poll once to get the actual result in case the run finished
          agentApi.getRun(runId).then(r => {
            const run = r.data;
            if (run.status === 'completed') {
              setStatus('completed');
              setSummary(run.result_summary || '');
              setCharts(run.charts || []);
              setTokenUsage(run.token_usage || 0);
              setSteps(run.steps || []);
              toast.success('Analysis complete!');
            } else {
              const errMsg = run.result_summary || 'Stream disconnected after 3 retries';
              setSummary(errMsg);
              toast.error(errMsg.slice(0, 120));
            }
          }).catch(() => {
            setSummary('Stream disconnected. Check the backend logs.');
            toast.error('Stream disconnected');
          });
        }
      };
    };

    connect();
  }, []);

  const startRun = useCallback(async () => {
    if (!task.trim()) { toast.error('Please enter a task'); return; }
    setRunning(true);
    setSteps([]);
    setSummary('');
    setCharts([]);
    setTokenUsage(0);
    setElapsed(0);
    setStatus('running');
    setCurrentRunId(null);
    setConfidence('');

    try {
      const resp = await agentApi.run(task, datasetId || undefined, undefined, domain || undefined);
      const id: string = resp.data.run_id;
      setCurrentRunId(id);
      openStream(id);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to start agent';
      toast.error(msg);
      setStatus('failed');
      setRunning(false);
    }
  }, [task, domain, datasetId, openStream]);

  const stopRun = () => {
    esRef.current?.close();
    setRunning(false);
    setStatus('failed');
  };

  const deleteMemory = async (id: string) => {
    try {
      await agentApi.deleteMemory(id);
      setMemories(prev => prev.filter(m => m.id !== id));
      toast.success('Memory deleted');
    } catch {
      toast.error('Failed to delete memory');
    }
  };

  const submitCorrection = async () => {
    if (!correctionText.trim()) return;
    try {
      await agentApi.saveCorrection(correctionText.trim());
      toast.success('Correction saved as memory');
      setCorrectionText('');
      setShowCorrectionInput(false);
      agentApi.getMemories().then(r => setMemories(r.data || [])).catch(() => {});
    } catch {
      toast.error('Failed to save correction');
    }
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  return (
    <AppLayout>
      <div className="flex h-full gap-0 overflow-hidden">

        {/* ╔══════════════════════════════╗
            ║  LEFT COLUMN — 250px         ║
            ║  Past Analyses + Memories    ║
            ╚══════════════════════════════╝ */}
        <div className="w-[250px] flex-shrink-0 flex flex-col border-r border-white/5 overflow-hidden">
          {/* Header */}
          <div className="px-4 py-4 border-b border-white/5">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-white">AI Agent</h1>
                <p className="text-[10px] text-slate-500">Autonomous analyst</p>
              </div>
            </div>
          </div>

          {/* Past Runs */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            <div>
              <div className="flex items-center gap-1.5 mb-2 px-1">
                <History className="w-3 h-3 text-slate-500" />
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Past Analyses</span>
              </div>
              {pastRuns.length === 0 ? (
                <p className="text-[11px] text-slate-600 px-1">No runs yet</p>
              ) : (
                <div className="space-y-1">
                  {pastRuns.slice(0, 10).map(run => (
                    <button
                      key={run.id}
                      onClick={() => {
                        setTask(run.task);
                        setDomain(run.domain || '');
                      }}
                      className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-white/5 transition-colors group"
                    >
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <div className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', {
                          'bg-emerald-400': run.status === 'completed',
                          'bg-indigo-400': run.status === 'running',
                          'bg-red-400': run.status === 'failed',
                        })} />
                        <span className="text-[10px] text-slate-500 truncate">{run.domain || 'general'}</span>
                      </div>
                      <p className="text-[11px] text-slate-300 leading-snug line-clamp-2 group-hover:text-white transition-colors">
                        {run.task}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Memories */}
            <div>
              <div className="flex items-center justify-between mb-2 px-1">
                <div className="flex items-center gap-1.5">
                  <Brain className="w-3 h-3 text-indigo-400" />
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Memory</span>
                </div>
                <button
                  onClick={() => setShowCorrectionInput(v => !v)}
                  className="text-slate-600 hover:text-indigo-400 transition-colors"
                  title="Add correction"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>

              <AnimatePresence>
                {showCorrectionInput && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden mb-2"
                  >
                    <div className="bg-white/5 rounded-lg p-2 border border-white/10 space-y-1.5">
                      <textarea
                        value={correctionText}
                        onChange={e => setCorrectionText(e.target.value)}
                        placeholder="e.g. Always use percentage format for revenue metrics"
                        className="w-full bg-transparent text-[11px] text-slate-300 placeholder-slate-600 resize-none focus:outline-none leading-relaxed"
                        rows={2}
                      />
                      <div className="flex gap-1">
                        <button
                          onClick={submitCorrection}
                          className="flex-1 text-[10px] py-1 bg-indigo-600/40 hover:bg-indigo-600/60 text-indigo-300 rounded transition-colors"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setShowCorrectionInput(false)}
                          className="px-2 text-[10px] py-1 bg-white/5 hover:bg-white/10 text-slate-400 rounded transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {memories.length === 0 ? (
                <p className="text-[11px] text-slate-600 px-1">No memories yet</p>
              ) : (
                <div className="space-y-1">
                  {memories.slice(0, 8).map(mem => (
                    <div
                      key={mem.id}
                      className={cn(
                        'px-2 py-1.5 rounded-lg border group flex items-start gap-1.5',
                        MEMORY_TYPE_COLORS[mem.memory_type] || 'bg-slate-500/10 text-slate-300 border-slate-500/20'
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-[9px] uppercase tracking-wider opacity-60 truncate">{mem.memory_type}</p>
                        <p className="text-[11px] font-medium leading-snug truncate">{mem.key}</p>
                        <p className="text-[10px] opacity-70 leading-snug line-clamp-1">{mem.value}</p>
                      </div>
                      <button
                        onClick={() => deleteMemory(mem.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 hover:text-red-400"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ╔══════════════════════════════════════════╗
            ║  CENTER COLUMN — flex-1                  ║
            ║  Task input + Live step stream           ║
            ╚══════════════════════════════════════════╝ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top bar */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-white/5 flex-shrink-0">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-semibold text-white">Analysis Stream</span>
            <div className="ml-auto flex items-center gap-4 text-xs">
              {running && (
                <span className="flex items-center gap-1.5 text-amber-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running
                </span>
              )}
              {status === 'completed' && (
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Complete
                </span>
              )}
              {status === 'failed' && (
                <span className="flex items-center gap-1.5 text-red-400">
                  <AlertCircle className="w-3.5 h-3.5" /> Failed
                </span>
              )}
              <span className="flex items-center gap-1 text-slate-500">
                <Clock className="w-3.5 h-3.5" /> {formatTime(elapsed)}
              </span>
              <span className="flex items-center gap-1 text-slate-500">
                <Coins className="w-3.5 h-3.5" /> {tokenUsage.toLocaleString()}
              </span>
            </div>
          </div>

          {/* Task input area */}
          <div className="px-5 py-4 border-b border-white/5 flex-shrink-0 space-y-3">
            {/* Suggested prompts */}
            {!running && steps.length === 0 && (
              <div className="flex flex-wrap gap-1.5">
                {SUGGESTED_PROMPTS.map(p => (
                  <button
                    key={p}
                    onClick={() => setTask(p)}
                    className="text-[11px] px-2.5 py-1 rounded-full bg-white/5 hover:bg-indigo-500/15 border border-white/8 hover:border-indigo-500/30 text-slate-400 hover:text-indigo-300 transition-all"
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
            <textarea
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 resize-none focus:outline-none focus:border-indigo-500/50 transition-all"
              rows={2}
              placeholder="Describe your analysis task… e.g. Analyse revenue by region, find the top 5 customers, and build a summary report."
              value={task}
              onChange={e => setTask(e.target.value)}
              disabled={running}
            />
            {/* Agent tier selector */}
            <div className="flex gap-2">
              {AGENT_TIERS.map(tier => {
                const Icon = tier.icon;
                const isActive = agentTier === tier.key;
                return (
                  <button
                    key={tier.key}
                    onClick={() => setAgentTier(tier.key)}
                    disabled={running}
                    title={tier.desc}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] font-medium transition-all flex-1 justify-center',
                      isActive ? tier.color : 'text-slate-500 border-white/8 hover:border-white/15 hover:text-slate-400',
                    )}
                  >
                    <Icon className="w-3 h-3" />
                    {tier.label}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-2">
              <select
                className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500/40 transition-all"
                value={domain}
                onChange={e => setDomain(e.target.value)}
                disabled={running}
              >
                {DOMAINS.map(d => (
                  <option key={d} value={d} className="bg-slate-800 text-slate-200">{d || '— domain —'}</option>
                ))}
              </select>

              <select
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500/40 transition-all"
                value={datasetId}
                onChange={e => setDatasetId(e.target.value)}
                disabled={running}
              >
                <option value="" className="bg-slate-800 text-slate-200">— no dataset —</option>
                {datasets.filter(d => d.status === 'ready').map(d => (
                  <option key={d.id} value={d.id} className="bg-slate-800 text-slate-200">{d.name}</option>
                ))}
              </select>

              {!running ? (
                <motion.button
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors"
                  onClick={startRun}
                  disabled={!task.trim()}
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                >
                  <Play className="w-3.5 h-3.5" /> Run Agent
                </motion.button>
              ) : (
                <button
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded-lg text-xs font-medium transition-colors"
                  onClick={stopRun}
                >
                  <Square className="w-3.5 h-3.5" /> Stop
                </button>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {running && (
            <div className="px-5 pt-3 flex-shrink-0">
              <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1.5">
                <span className="flex items-center gap-1.5"><TrendingUp className="w-3 h-3 text-indigo-400" /> Step {steps.length} / 12</span>
                <span>{Math.round((steps.length / 12) * 100)}% complete</span>
              </div>
              <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                  animate={{ width: `${Math.min((steps.length / 12) * 100, 95)}%` }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
              </div>
            </div>
          )}

          {/* Steps stream */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
            {steps.length === 0 && !running && (
              <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
                <Bot className="w-14 h-14 opacity-15" />
                <p className="text-sm">Enter a task and click Run Agent</p>
                <p className="text-xs text-slate-700">The agent&apos;s reasoning steps will stream here in real time</p>
              </div>
            )}
            {running && steps.length === 0 && (
              <div className="flex items-center gap-3 text-slate-400 py-4">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                <span className="text-sm">Agent initialising…</span>
              </div>
            )}
            {steps.map((step, i) => (
              <StepCard key={i} step={step} />
            ))}
            <div ref={stepsEndRef} />
          </div>
        </div>

        {/* ╔══════════════════════════════╗
            ║  RIGHT COLUMN — 350px        ║
            ║  Charts + Report             ║
            ╚══════════════════════════════╝ */}
        <div className="w-[340px] flex-shrink-0 flex flex-col border-l border-white/5 overflow-hidden">
          <div className="px-4 py-3 border-b border-white/5 flex-shrink-0 flex items-center gap-2">
            <FileText className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-semibold text-white">Report &amp; Charts</span>
            <div className="ml-auto flex items-center gap-2">
              {confidence && (
                <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize', CONFIDENCE_STYLES[confidence] || 'text-slate-400 bg-slate-500/10')}>
                  {confidence} confidence
                </span>
              )}
              {status === 'completed' && (
                <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                  Done
                </span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {/* Charts */}
            {(charts.length > 0 || steps.some(s => s.figures.length > 0)) ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <BarChart2 className="w-3.5 h-3.5 text-violet-400" />
                  <span className="text-xs font-semibold text-slate-300">Charts</span>
                </div>
                <div className="space-y-3">
                  {charts.map((c, i) => (
                    <div key={i}>
                      <p className="text-[11px] text-slate-500 mb-1.5">{c.title}</p>
                      <img
                        src={`data:image/png;base64,${c.base64}`}
                        alt={c.title}
                        className="rounded-xl w-full border border-white/10"
                      />
                    </div>
                  ))}
                  {steps.flatMap(s => s.figures).map((fig, i) => (
                    <img
                      key={`sf-${i}`}
                      src={`data:image/png;base64,${fig}`}
                      alt={`Figure ${i + 1}`}
                      className="rounded-xl w-full border border-white/10"
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {/* Report / Summary */}
            {summary ? (() => {
              const structured = tryParseStructured(summary);
              if (structured) {
                return (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <FileText className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-xs font-semibold text-slate-300">Analysis Report</span>
                      {currentRunId && (
                        <a
                          href={`${API_BASE}/api/agent/runs/${currentRunId}/pdf?token=${encodeURIComponent(getAuthToken())}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-auto flex items-center gap-1 text-[10px] px-2 py-1 bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/30 rounded-lg transition-colors"
                        >
                          <FileText className="w-3 h-3" /> Download PDF
                        </a>
                      )}
                    </div>

                    {/* Executive Summary — teal/blue box with quote icon */}
                    <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-3">
                      <div className="flex items-center gap-1.5 mb-2">
                        <span className="text-2xl leading-none text-teal-500/40 font-serif select-none">&ldquo;</span>
                        <p className="text-[10px] text-teal-400 font-semibold uppercase tracking-wider">Executive Summary</p>
                      </div>
                      <p className="text-xs text-slate-200 leading-relaxed">{structured.executive_summary}</p>
                    </div>

                    {/* Key Findings — numbered cards */}
                    {structured.key_findings?.length > 0 && (
                      <div>
                        <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">Key Findings</p>
                        <div className="space-y-1.5">
                          {structured.key_findings.map((f, i) => (
                            <div key={i} className="flex gap-2 rounded-lg border border-white/5 bg-white/3 px-3 py-2">
                              <span className="w-4 h-4 rounded-full bg-indigo-500/20 text-indigo-300 text-[9px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{i + 1}</span>
                              <p className="text-[11px] text-slate-300 leading-relaxed">{f}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Root Causes */}
                    {structured.root_causes?.length > 0 && (
                      <div>
                        <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">Root Causes</p>
                        <div className="space-y-1">
                          {structured.root_causes.map((c, i) => (
                            <p key={i} className="text-[11px] text-slate-400 leading-relaxed pl-2 border-l border-amber-500/30">
                              {c}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Recommendations — priority-badged cards */}
                    {structured.recommendations?.length > 0 && (
                      <div>
                        <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">Recommendations</p>
                        <div className="space-y-2">
                          {structured.recommendations.map((rec, i) => (
                            <div key={i} className={cn(
                              'rounded-lg border px-3 py-2 space-y-1',
                              rec.priority === 'high'   ? 'border-red-500/30 bg-red-500/5'
                              : rec.priority === 'medium' ? 'border-yellow-500/30 bg-yellow-500/5'
                              : 'border-green-500/30 bg-green-500/5'
                            )}>
                              <div className="flex items-center gap-2">
                                <span className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase', PRIORITY_STYLES[rec.priority] || PRIORITY_STYLES.low)}>
                                  {rec.priority}
                                </span>
                                <p className="text-[11px] text-slate-200 font-medium leading-snug flex-1">{rec.action}</p>
                              </div>
                              {rec.expected_impact && (
                                <p className="text-[10px] text-emerald-400 pl-8">{rec.expected_impact}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Risks — red warning cards */}
                    {structured.risks?.length > 0 && (
                      <div>
                        <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-2">Risks</p>
                        <div className="space-y-1.5">
                          {structured.risks.map((r, i) => (
                            <div key={i} className="flex gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                              <AlertCircle className="w-3 h-3 text-red-400 flex-shrink-0 mt-0.5" />
                              <p className="text-[11px] text-red-300 leading-relaxed">{r}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Data quality notes */}
                    {structured.data_quality_notes && (
                      <div className="rounded-lg border border-slate-500/20 bg-slate-500/5 px-3 py-2">
                        <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-1">Data Quality Notes</p>
                        <p className="text-[11px] text-slate-400 leading-relaxed">{structured.data_quality_notes}</p>
                      </div>
                    )}
                  </div>
                );
              }

              // Fallback: plain markdown
              return (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-xs font-semibold text-slate-300">Analysis Report</span>
                    {currentRunId && (
                      <a
                        href={`${API_BASE}/api/agent/runs/${currentRunId}/pdf?token=${encodeURIComponent(getAuthToken())}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-auto flex items-center gap-1 text-[10px] px-2 py-1 bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/30 rounded-lg transition-colors"
                      >
                        <FileText className="w-3 h-3" /> Download PDF
                      </a>
                    )}
                  </div>
                  <div className="prose prose-xs prose-invert max-w-none text-slate-300 leading-relaxed">
                    <ReactMarkdown>{summary}</ReactMarkdown>
                  </div>
                </div>
              );
            })() : null}

            {/* Empty state */}
            {!summary && charts.length === 0 && !steps.some(s => s.figures.length > 0) && (
              <div className="flex flex-col items-center justify-center h-full text-slate-700 gap-3 py-16">
                <FileText className="w-12 h-12 opacity-15" />
                <p className="text-xs text-center text-slate-600 leading-relaxed">
                  Charts and the final report<br />will appear here as the agent works
                </p>
              </div>
            )}
          </div>
        </div>

      </div>
    </AppLayout>
  );
}

// ── Wrap with Suspense for useSearchParams ────────────────────────────────────

export default function AgentPage() {
  return (
    <Suspense fallback={
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      </AppLayout>
    }>
      <AgentPageInner />
    </Suspense>
  );
}
