'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Terminal, Send, ThumbsUp, ThumbsDown, Clock, Database,
  Table, BarChart2, RefreshCw, ChevronDown, Code2, Sparkles
} from 'lucide-react';
import { toast } from 'sonner';
import dynamic from 'next/dynamic';
import { nl2sqlApi, datasetsApi } from '@/lib/api';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Dataset {
  id: string;
  name: string;
  status: string;
  row_count?: number;
  column_count?: number;
}

interface QueryResult {
  query_id: string;
  question: string;
  sql: string;
  data: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  chart?: Record<string, unknown>;
  error?: string;
  execution_time_ms: number;
}

interface HistoryItem {
  id: string;
  question: string;
  sql: string;
  row_count: number;
  execution_time_ms: number;
  success: boolean;
  feedback?: number;
  created_at: string;
}

const EXAMPLE_QUESTIONS = [
  'Show the top 10 rows by highest value',
  'What is the average of each numeric column?',
  'Count the number of unique values in each column',
  'Show rows where any value is null',
  'What are the 5 most common values in the first text column?',
  'Compare the sum vs count for numeric columns',
];

export default function NL2SQLPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showSQL, setShowSQL] = useState(false);
  const [activeTab, setActiveTab] = useState<'table' | 'chart'>('table');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadDatasets();
  }, []);

  useEffect(() => {
    if (selectedDataset) loadHistory();
  }, [selectedDataset]);

  async function loadDatasets() {
    try {
      const res = await datasetsApi.list();
      const ready = res.data.filter((d: Dataset) => d.status === 'ready');
      setDatasets(ready);
      if (ready.length > 0) setSelectedDataset(ready[0].id);
    } catch {
      toast.error('Failed to load datasets');
    }
  }

  async function loadHistory() {
    try {
      const res = await nl2sqlApi.history(selectedDataset, 10);
      setHistory(res.data);
    } catch { /* silent */ }
  }

  async function runQuery(e?: React.FormEvent) {
    e?.preventDefault();
    if (!question.trim()) return toast.error('Please enter a question');
    if (!selectedDataset) return toast.error('Please select a dataset');

    setLoading(true);
    setResult(null);
    try {
      const res = await nl2sqlApi.query(selectedDataset, question);
      setResult(res.data);
      if (res.data.error) {
        toast.error(`Query error: ${res.data.error}`);
      } else {
        toast.success(`Returned ${res.data.row_count} rows in ${res.data.execution_time_ms}ms`);
        setActiveTab(res.data.chart ? 'chart' : 'table');
      }
      await loadHistory();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Query failed');
    } finally {
      setLoading(false);
    }
  }

  async function submitFeedback(positive: boolean) {
    if (!result) return;
    try {
      await nl2sqlApi.feedback(result.query_id, positive ? 1 : -1);
      toast.success(positive ? 'Thanks for the positive feedback!' : 'Thanks — we\'ll improve this');
      setResult(r => r ? { ...r, feedbackGiven: true } as any : r);
    } catch { /* silent */ }
  }

  function applyExample(q: string) {
    setQuestion(q);
    inputRef.current?.focus();
  }

  function applyHistoryItem(item: HistoryItem) {
    setQuestion(item.question);
    setShowHistory(false);
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <PageHeader
          title="SQL Query Builder"
          description="Ask questions in plain English — get SQL queries executed instantly against your data"
          icon={<Terminal className="w-5 h-5 text-violet-400" />}
        />

        {/* Dataset selector + query form */}
        <div className="glass rounded-2xl p-5 space-y-4">
          {/* Dataset picker */}
          <div className="flex items-center gap-3">
            <Database className="w-4 h-4 text-slate-400 flex-shrink-0" />
            <select
              value={selectedDataset}
              onChange={e => setSelectedDataset(e.target.value)}
              className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Select a dataset…</option>
              {datasets.map(d => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.row_count?.toLocaleString()} rows · {d.column_count} cols)
                </option>
              ))}
            </select>
            {history.length > 0 && (
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-2 rounded-xl hover:bg-white/5 transition-colors"
              >
                <Clock className="w-3.5 h-3.5" />
                History
                <ChevronDown className={`w-3 h-3 transition-transform ${showHistory ? 'rotate-180' : ''}`} />
              </button>
            )}
          </div>

          {/* History dropdown */}
          <AnimatePresence>
            {showHistory && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="bg-black/20 rounded-xl border border-white/5 divide-y divide-white/5">
                  {history.map(item => (
                    <button
                      key={item.id}
                      onClick={() => applyHistoryItem(item)}
                      className="w-full text-left px-4 py-2.5 hover:bg-white/5 transition-colors group"
                    >
                      <p className="text-sm text-slate-200 group-hover:text-white truncate">{item.question}</p>
                      <p className="text-xs text-slate-600 mt-0.5">
                        {item.row_count} rows · {item.execution_time_ms}ms · {new Date(item.created_at).toLocaleDateString()}
                        {item.feedback === 1 && <span className="ml-2 text-emerald-500">👍</span>}
                        {item.feedback === -1 && <span className="ml-2 text-red-500">👎</span>}
                      </p>
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Question input */}
          <form onSubmit={runQuery} className="space-y-3">
            <div className="relative">
              <textarea
                ref={inputRef}
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runQuery(); } }}
                placeholder="Ask a question about your data… e.g. &quot;Show the top 5 products by total sales&quot;"
                rows={3}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
              />
              <button
                type="submit"
                disabled={loading || !question.trim() || !selectedDataset}
                className="absolute right-3 bottom-3 p-2 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </form>

          {/* Example questions */}
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map(q => (
              <button
                key={q}
                onClick={() => applyExample(q)}
                className="text-xs px-3 py-1.5 rounded-full bg-white/5 text-slate-400 hover:text-white hover:bg-white/10 transition-colors border border-white/5"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="glass rounded-2xl p-8 text-center"
            >
              <div className="flex items-center justify-center gap-3 text-slate-400">
                <RefreshCw className="w-5 h-5 animate-spin" />
                <span className="text-sm">Generating SQL and executing query…</span>
              </div>
            </motion.div>
          )}

          {result && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              {/* SQL card */}
              <div className="glass rounded-2xl overflow-hidden">
                <button
                  onClick={() => setShowSQL(!showSQL)}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Code2 className="w-4 h-4 text-violet-400" />
                    <span className="text-sm font-medium text-white">Generated SQL</span>
                    <span className="text-xs text-slate-500">{result.execution_time_ms}ms</span>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${showSQL ? 'rotate-180' : ''}`} />
                </button>
                <AnimatePresence>
                  {showSQL && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: 'auto' }}
                      exit={{ height: 0 }}
                      className="overflow-hidden border-t border-white/5"
                    >
                      <pre className="px-5 py-4 text-xs text-violet-300 font-mono bg-black/30 overflow-x-auto">
                        {result.sql}
                      </pre>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Error display */}
              {result.error && (
                <div className="glass rounded-xl p-4 border border-red-500/20 bg-red-500/5">
                  <p className="text-sm text-red-400 font-medium">Query Error</p>
                  <p className="text-xs text-red-400/70 mt-1">{result.error}</p>
                </div>
              )}

              {/* Results tabs */}
              {!result.error && result.row_count > 0 && (
                <div className="glass rounded-2xl overflow-hidden">
                  {/* Tab header */}
                  <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
                    <div className="flex items-center gap-1">
                      {(['table', 'chart'] as const).map(tab => (
                        result.chart || tab === 'table' ? (
                          <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              activeTab === tab
                                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                                : 'text-slate-400 hover:text-white'
                            }`}
                          >
                            {tab === 'table' ? <Table className="w-3.5 h-3.5" /> : <BarChart2 className="w-3.5 h-3.5" />}
                            {tab === 'table' ? `Table (${result.row_count} rows)` : 'Chart'}
                          </button>
                        ) : null
                      ))}
                    </div>
                    {/* Feedback */}
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-500 mr-1">Was this helpful?</span>
                      <button onClick={() => submitFeedback(true)} className="p-1.5 rounded-lg text-slate-500 hover:text-emerald-400 hover:bg-emerald-400/10 transition-colors">
                        <ThumbsUp className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => submitFeedback(false)} className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                        <ThumbsDown className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Table view */}
                  {activeTab === 'table' && (
                    <div className="overflow-x-auto max-h-96 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-black/40 backdrop-blur-sm">
                          <tr>
                            {result.columns.map(col => (
                              <th key={col} className="text-left px-4 py-2.5 text-slate-400 font-medium border-b border-white/5 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.data.map((row, i) => (
                            <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                              {result.columns.map(col => (
                                <td key={col} className="px-4 py-2 text-slate-300 whitespace-nowrap max-w-xs truncate">
                                  {row[col] === null ? (
                                    <span className="text-slate-600 italic">null</span>
                                  ) : String(row[col])}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Chart view */}
                  {activeTab === 'chart' && result.chart && (
                    <div className="p-4">
                      <Plot
                        data={(result.chart as any).data || []}
                        layout={{
                          ...(result.chart as any).layout,
                          paper_bgcolor: 'transparent',
                          plot_bgcolor: 'transparent',
                          font: { color: '#94a3b8', size: 11 },
                          margin: { t: 40, r: 20, b: 40, l: 50 },
                          height: 320,
                        }}
                        config={{ displayModeBar: false, responsive: true }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Empty result */}
              {!result.error && result.row_count === 0 && (
                <div className="glass rounded-xl p-6 text-center">
                  <p className="text-sm text-slate-400">Query returned no results</p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Empty state */}
        {!result && !loading && (
          <div className="glass rounded-2xl p-10 text-center">
            <Sparkles className="w-10 h-10 text-violet-500/50 mx-auto mb-3" />
            <p className="text-slate-400 text-sm font-medium">Ask anything about your data</p>
            <p className="text-slate-600 text-xs mt-1 max-w-sm mx-auto">
              Type a question in plain English above. The AI will generate and execute the SQL query for you.
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
