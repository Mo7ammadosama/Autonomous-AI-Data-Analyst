'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Sparkles, ArrowRight, BarChart2, TrendingUp, Database,
  Users, ChevronDown, Loader2, ArrowUpRight, Copy, Check, Download,
  Hash, Table, Code2, X, History, ChevronRight, Zap, Brain
} from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { toast } from 'sonner';
import AppLayout from '@/components/layout/AppLayout';
import ChartGrid from '@/components/charts/ChartGrid';
import { apiClient } from '@/lib/api';
import { cn } from '@/lib/utils';

// ── Types ──────────────────────────────────────────────────────

interface ExploreResult {
  id: string;
  question: string;
  answer: string;
  sql?: string;
  data?: Record<string, any>[];
  totalRows?: number;
  chart?: any;
  confidence?: number;
  suggestions?: string[];
  dataset_name?: string;
  elapsed?: number;
  timestamp: Date;
}

interface Dataset {
  id: string;
  name: string;
  row_count?: number;
  column_count?: number;
  status?: string;
}

// ── Constants ──────────────────────────────────────────────────

const STARTER_QUESTIONS = [
  { q: "What are my top performing metrics this month?", icon: TrendingUp, tag: "KPIs" },
  { q: "Show me revenue trends over time", icon: BarChart2, tag: "Trends" },
  { q: "Which customer segments have the highest churn?", icon: Users, tag: "Segments" },
  { q: "What is the average order value by region?", icon: Hash, tag: "Aggregates" },
  { q: "Which products are selling the most?", icon: Zap, tag: "Top-N" },
  { q: "Detect any unusual patterns or anomalies", icon: Brain, tag: "Anomalies" },
];

const FOLLOW_UP_TEMPLATES = [
  "Break this down by category",
  "Compare this to the overall average",
  "Show the trend over the last 30 days",
  "Which segment drives this the most?",
  "Filter to the top 20% only",
];

// ── SQL Copy Button ────────────────────────────────────────────

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#1e1e2e] rounded-t-lg border border-white/10 border-b-0">
        <div className="flex items-center gap-2">
          <Code2 className="w-3.5 h-3.5 text-green-400" />
          <span className="text-xs text-slate-400">Generated SQL</span>
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-white transition-colors"
        >
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language="sql"
        style={oneDark}
        customStyle={{ margin: 0, background: '#13131f', fontSize: '12px', padding: '12px 16px', borderRadius: '0 0 8px 8px', border: '1px solid rgba(255,255,255,0.1)' }}
      >
        {sql}
      </SyntaxHighlighter>
    </div>
  );
}

// ── Data Table ─────────────────────────────────────────────────

function DataTable({ data, totalRows }: { data: Record<string, any>[]; totalRows?: number }) {
  if (!data.length) return null;
  const cols = Object.keys(data[0]);

  const exportCsv = () => {
    const header = cols.join(',');
    const rows = data.map(row => cols.map(c => JSON.stringify(row[c] ?? '')).join(','));
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `datamind-result-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Exported as CSV');
  };

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Table className="w-3.5 h-3.5 text-indigo-400" />
          <span>
            Showing {data.length} row{data.length !== 1 ? 's' : ''}
            {totalRows && totalRows > data.length ? ` of ${totalRows.toLocaleString()} total` : ''}
          </span>
        </div>
        <button
          onClick={exportCsv}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-300 transition-colors"
        >
          <Download className="w-3 h-3" /> CSV
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-white/5 border-b border-white/10">
              {cols.map(col => (
                <th key={col} className="px-4 py-2.5 text-left text-slate-400 font-medium whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className={cn('border-b border-white/5 transition-colors hover:bg-white/3', i % 2 === 0 ? '' : 'bg-white/2')}>
                {cols.map(col => (
                  <td key={col} className="px-4 py-2 text-slate-300 whitespace-nowrap max-w-xs truncate">
                    {row[col] == null ? <span className="text-slate-600 italic">null</span> : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Result Card ────────────────────────────────────────────────

function ResultCard({
  result,
  onFollowUp,
}: {
  result: ExploreResult;
  onFollowUp: (q: string) => void;
}) {
  const [showSql, setShowSql] = useState(false);
  const [showChart, setShowChart] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="bg-white/4 border border-white/10 rounded-2xl overflow-hidden shadow-xl"
    >
      {/* Question header */}
      <div className="px-6 py-4 border-b border-white/8 bg-white/2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <Users className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-white font-medium">{result.question}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {result.dataset_name && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/40 border border-indigo-500/20 text-indigo-400">
                {result.dataset_name}
              </span>
            )}
            {result.elapsed != null && (
              <span className="text-xs text-slate-600">{result.elapsed.toFixed(2)}s</span>
            )}
          </div>
        </div>
      </div>

      {/* Answer body */}
      <div className="px-6 py-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center">
            <Sparkles className="w-3 h-3 text-white" />
          </div>
          <span className="text-sm font-medium text-indigo-300">DataMind AI</span>
          {result.confidence != null && (
            <div className="flex items-center gap-1.5 ml-auto">
              <div className="h-1.5 w-20 bg-white/10 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                  style={{ width: `${Math.round(result.confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs text-slate-500">{Math.round(result.confidence * 100)}% confidence</span>
            </div>
          )}
        </div>

        <p className="text-sm text-slate-200 leading-relaxed mb-4">{result.answer}</p>

        {/* Chart */}
        {result.chart && (
          <div className="mb-4">
            <button
              onClick={() => setShowChart(v => !v)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 mb-2 transition-colors"
            >
              <BarChart2 className="w-3.5 h-3.5" />
              {showChart ? 'Hide chart' : 'Show chart'}
              <ChevronDown className={cn('w-3 h-3 transition-transform', showChart ? 'rotate-180' : '')} />
            </button>
            <AnimatePresence>
              {showChart && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <ChartGrid charts={[result.chart]} columns={1} chartHeight={280} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Data table */}
        {result.data && result.data.length > 0 && (
          <DataTable data={result.data} totalRows={result.totalRows} />
        )}

        {/* SQL */}
        {result.sql && (
          <div className="mt-3">
            <button
              onClick={() => setShowSql(v => !v)}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              {showSql ? 'Hide' : 'View'} generated SQL
              <ChevronDown className={cn('w-3 h-3 transition-transform', showSql ? 'rotate-180' : '')} />
            </button>
            <AnimatePresence>
              {showSql && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                  <SqlBlock sql={result.sql} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Follow-up suggestions */}
        {result.suggestions && result.suggestions.length > 0 && (
          <div className="mt-5 pt-4 border-t border-white/8">
            <p className="text-xs text-slate-500 mb-2.5">Dig deeper:</p>
            <div className="flex flex-wrap gap-2">
              {result.suggestions.map(s => (
                <button
                  key={s}
                  onClick={() => onFollowUp(s)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-900/30 border border-indigo-500/20 text-sm text-indigo-300 hover:bg-indigo-900/50 transition-colors"
                >
                  <ArrowUpRight className="w-3 h-3" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── Main Page ──────────────────────────────────────────────────

export default function ExplorePage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ExploreResult[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [showDatasetPicker, setShowDatasetPicker] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiClient.get('/api/datasets').then(res => {
      const ds: Dataset[] = Array.isArray(res.data) ? res.data : res.data?.datasets || [];
      const ready = ds.filter(d => d.status === 'ready' || !d.status);
      setDatasets(ready);
      if (ready.length > 0) setSelectedDataset(ready[0].id);
    }).catch(() => {});
  }, []);

  const selectedDatasetObj = datasets.find(d => d.id === selectedDataset);

  const generateSuggestions = (q: string): string[] => {
    const base = [
      `Break down by the most relevant category`,
      `Compare to the overall average`,
      `Show the trend over time`,
    ];
    if (q.toLowerCase().includes('revenue') || q.toLowerCase().includes('sales')) {
      return [`Revenue by region`, `Month-over-month growth`, `Top 5 products by revenue`];
    }
    if (q.toLowerCase().includes('customer') || q.toLowerCase().includes('user')) {
      return [`Segment by acquisition channel`, `Retention rate analysis`, `Lifetime value distribution`];
    }
    return base;
  };

  const askQuestion = useCallback(async (q: string) => {
    if (!q.trim()) return;
    if (!selectedDataset) {
      toast.error('Please select a dataset first');
      setShowDatasetPicker(true);
      return;
    }

    setLoading(true);
    setQuestion('');
    setHistory(h => [q, ...h.filter(x => x !== q)].slice(0, 20));
    setHistoryIdx(-1);

    const startTime = Date.now();
    try {
      const res = await apiClient.post(`/api/nl2sql/${selectedDataset}/query`, { question: q });
      const data = res.data;
      const elapsed = (Date.now() - startTime) / 1000;

      const result: ExploreResult = {
        id: `result-${Date.now()}`,
        question: q,
        answer: data.error
          ? `Could not generate an answer: ${data.error}. Try rephrasing your question.`
          : data.data?.length
            ? `Found ${data.data.length} result${data.data.length !== 1 ? 's' : ''} matching your query.`
            : `Query executed successfully. No matching rows found.`,
        sql: data.sql,
        data: (data.data || []).slice(0, 15),
        totalRows: data.data?.length,
        chart: data.chart,
        confidence: data.thinking_trace?.confidence,
        dataset_name: selectedDatasetObj?.name,
        elapsed,
        suggestions: generateSuggestions(q),
        timestamp: new Date(),
      };

      setResults(prev => [result, ...prev]);

      // Scroll to top of results
      setTimeout(() => {
        document.getElementById('results-top')?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to answer question');
    } finally {
      setLoading(false);
    }
  }, [selectedDataset, selectedDatasetObj]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      askQuestion(question);
    } else if (e.key === 'ArrowUp' && history.length > 0) {
      e.preventDefault();
      const idx = Math.min(historyIdx + 1, history.length - 1);
      setHistoryIdx(idx);
      setQuestion(history[idx]);
    } else if (e.key === 'ArrowDown' && historyIdx > -1) {
      e.preventDefault();
      const idx = historyIdx - 1;
      setHistoryIdx(idx);
      setQuestion(idx >= 0 ? history[idx] : '');
    }
  };

  const clearResults = () => {
    setResults([]);
    toast.success('Results cleared');
  };

  return (
    <AppLayout>
      <div className="min-h-screen">

        {/* ── Hero / Search Header ────────────────────────────── */}
        <div className="pt-12 pb-6 px-6 text-center border-b border-white/5 bg-gradient-to-b from-indigo-950/20 to-transparent">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-900/40 border border-indigo-500/30 text-indigo-300 text-xs mb-5"
          >
            <Sparkles className="w-3.5 h-3.5" />
            NL2SQL — Plain English Data Queries
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="text-3xl font-bold text-white mb-2"
          >
            What do you want to know?
          </motion.h1>
          <p className="text-slate-500 text-sm mb-6">
            Ask any question — DataMind converts it to SQL and returns results instantly
          </p>

          {/* Dataset selector */}
          <div className="flex justify-center mb-5">
            <div className="relative">
              <button
                onClick={() => setShowDatasetPicker(v => !v)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-gray-300 hover:bg-white/8 transition-colors"
              >
                <Database className="w-4 h-4 text-indigo-400" />
                {selectedDatasetObj
                  ? <>
                      <span>{selectedDatasetObj.name}</span>
                      {selectedDatasetObj.row_count && (
                        <span className="text-xs text-slate-500">· {selectedDatasetObj.row_count.toLocaleString()} rows</span>
                      )}
                    </>
                  : 'Select a dataset'}
                <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
              </button>

              <AnimatePresence>
                {showDatasetPicker && datasets.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    className="absolute z-50 top-full left-0 mt-1 w-64 bg-[#1a1a2e] border border-white/10 rounded-xl shadow-2xl overflow-hidden"
                  >
                    {datasets.map(ds => (
                      <button
                        key={ds.id}
                        onClick={() => { setSelectedDataset(ds.id); setShowDatasetPicker(false); }}
                        className={cn(
                          'w-full px-4 py-3 text-sm text-left transition-colors flex items-center justify-between',
                          selectedDataset === ds.id
                            ? 'bg-indigo-600/20 text-indigo-300'
                            : 'text-slate-300 hover:bg-white/5'
                        )}
                      >
                        <span className="truncate">{ds.name}</span>
                        {ds.row_count && (
                          <span className="text-xs text-slate-500 ml-2 flex-shrink-0">
                            {ds.row_count.toLocaleString()} rows
                          </span>
                        )}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Search bar */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 }}
            className="max-w-2xl mx-auto"
          >
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-500 pointer-events-none" />
                <input
                  ref={inputRef}
                  type="text"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. What drove revenue growth last quarter?"
                  className="w-full pl-11 pr-4 py-3.5 bg-white/5 border border-white/15 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 text-sm transition-colors"
                  autoFocus
                />
                {question && (
                  <button
                    onClick={() => setQuestion('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <button
                onClick={() => askQuestion(question)}
                disabled={loading || !question.trim()}
                className="px-5 py-3.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-white text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-indigo-500/20"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                Ask
              </button>
            </div>
            <p className="text-xs text-slate-600 mt-2">↑ / ↓ arrows to navigate question history</p>
          </motion.div>

          {/* Starter questions */}
          {results.length === 0 && !loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="mt-6 grid grid-cols-3 gap-2 max-w-2xl mx-auto"
            >
              {STARTER_QUESTIONS.map(({ q, icon: Icon, tag }) => (
                <button
                  key={q}
                  onClick={() => askQuestion(q)}
                  className="group flex items-start gap-2.5 p-3 rounded-xl bg-white/4 border border-white/8 hover:border-indigo-500/30 hover:bg-indigo-950/20 text-left transition-all text-xs"
                >
                  <div className="w-6 h-6 rounded-lg bg-indigo-900/40 flex items-center justify-center flex-shrink-0 group-hover:bg-indigo-600/30 transition-colors">
                    <Icon className="w-3 h-3 text-indigo-400" />
                  </div>
                  <div>
                    <span className="text-indigo-400 font-medium block mb-0.5">{tag}</span>
                    <span className="text-slate-400 leading-snug">{q}</span>
                  </div>
                </button>
              ))}
            </motion.div>
          )}
        </div>

        {/* ── Results ──────────────────────────────────────────── */}
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
          <div id="results-top" />

          {/* Results header */}
          {results.length > 0 && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <History className="w-4 h-4" />
                <span>{results.length} result{results.length !== 1 ? 's' : ''}</span>
              </div>
              <button
                onClick={clearResults}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-red-400 transition-colors"
              >
                <X className="w-3.5 h-3.5" /> Clear all
              </button>
            </div>
          )}

          {/* Loading skeleton */}
          <AnimatePresence>
            {loading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="bg-white/4 border border-white/10 rounded-2xl p-6"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center">
                    <Loader2 className="w-3.5 h-3.5 text-white animate-spin" />
                  </div>
                  <span className="text-sm text-slate-300">Translating to SQL and executing…</span>
                </div>
                <div className="space-y-2">
                  {[90, 75, 60].map((w, i) => (
                    <div key={i} className="h-3 bg-white/8 rounded-full animate-pulse" style={{ width: `${w}%` }} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Result cards */}
          <AnimatePresence mode="popLayout">
            {results.map(result => (
              <ResultCard
                key={result.id}
                result={result}
                onFollowUp={q => { setQuestion(q); inputRef.current?.focus(); askQuestion(q); }}
              />
            ))}
          </AnimatePresence>

          {/* Follow-up templates when results exist */}
          {results.length > 0 && !loading && (
            <div className="pt-2">
              <p className="text-xs text-slate-600 mb-2">Quick follow-ups:</p>
              <div className="flex flex-wrap gap-2">
                {FOLLOW_UP_TEMPLATES.map(t => (
                  <button
                    key={t}
                    onClick={() => { setQuestion(t); inputRef.current?.focus(); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-slate-400 hover:text-slate-200 hover:bg-white/8 transition-colors"
                  >
                    <ChevronRight className="w-3 h-3" /> {t}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
