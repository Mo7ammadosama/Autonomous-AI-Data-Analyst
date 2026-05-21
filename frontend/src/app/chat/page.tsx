'use client';

import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare, Send, Database, Sparkles, Bot, User, Code2, Plus, Trash2,
  Copy, Check, ThumbsUp, ThumbsDown, Download, LayoutDashboard, ChevronDown,
  BarChart2, Zap, Brain, TrendingUp, Table, Hash, X, RefreshCw, FileText
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import AppLayout from '@/components/layout/AppLayout';
import ChartGrid from '@/components/charts/ChartGrid';
import { chatApi, datasetsApi, chatExtApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

// ── Types ──────────────────────────────────────────────────────

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  charts?: any[];
  code?: string;
  insights?: any[];
  created_at?: string;
  thinking?: boolean;
  streaming?: boolean;
  feedback?: 'up' | 'down' | null;
  error?: boolean;
}

interface Dataset {
  id: string;
  name: string;
  row_count?: number;
  column_count?: number;
  file_type?: string;
  status?: string;
}

interface Session {
  id: string;
  title?: string;
  created_at?: string;
  dataset_id?: string;
}

// ── Constants ──────────────────────────────────────────────────

const SUGGESTIONS = [
  { icon: BarChart2, text: 'Show me the distribution of numeric columns', label: 'Explore' },
  { icon: TrendingUp, text: 'Analyze trends and patterns over time', label: 'Trends' },
  { icon: Brain, text: 'Find correlations between variables', label: 'Correlate' },
  { icon: Zap, text: 'Detect outliers and anomalies', label: 'Anomalies' },
  { icon: Table, text: 'Give me a statistical summary of this dataset', label: 'Profile' },
  { icon: TrendingUp, text: 'What are the top 10 records by key metric?', label: 'Top-N' },
];

// ── Utility Helpers ────────────────────────────────────────────

function formatTime(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diff = (now.getTime() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

function exportChatMarkdown(messages: Message[], sessionTitle?: string) {
  const lines = [`# Chat Export: ${sessionTitle || 'DataMind Session'}`, ''];
  messages.forEach(m => {
    lines.push(`**${m.role === 'user' ? 'You' : 'DataMind AI'}** (${formatTime(m.created_at)})`);
    lines.push('');
    lines.push(m.content);
    if (m.code) {
      lines.push('');
      lines.push('```python');
      lines.push(m.code);
      lines.push('```');
    }
    lines.push('');
    lines.push('---');
    lines.push('');
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `datamind-chat-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Code Block Component ───────────────────────────────────────

function CodeBlock({ code, language = 'python' }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="rounded-xl overflow-hidden border border-white/10 my-2">
      <div className="flex items-center justify-between px-4 py-2 bg-[#1e1e2e] border-b border-white/10">
        <div className="flex items-center gap-2">
          <Code2 className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-xs text-slate-400 font-mono">{language}</span>
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{ margin: 0, background: '#13131f', fontSize: '12px', padding: '16px' }}
        showLineNumbers
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

// ── Message Copy Button ────────────────────────────────────────

function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className={cn('p-1 rounded-md text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all', className)}
      title="Copy message"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// ── Typewriter Hook ────────────────────────────────────────────

function useTypewriter(text: string, active: boolean, speed = 8) {
  const [displayed, setDisplayed] = useState('');
  const idx = useRef(0);

  useEffect(() => {
    if (!active) { setDisplayed(text); return; }
    idx.current = 0;
    setDisplayed('');
    const interval = setInterval(() => {
      if (idx.current >= text.length) { clearInterval(interval); return; }
      // Advance by `speed` chars per tick for fast but visible effect
      idx.current = Math.min(idx.current + speed, text.length);
      setDisplayed(text.slice(0, idx.current));
    }, 16);
    return () => clearInterval(interval);
  }, [text, active, speed]);

  return displayed;
}

// ── Message Bubble ─────────────────────────────────────────────

function MessageBubble({
  msg,
  animate,
  onFeedback,
}: {
  msg: Message;
  animate: boolean;
  onFeedback?: (id: string, v: 'up' | 'down') => void;
}) {
  const displayed = useTypewriter(msg.content, animate && !msg.thinking && msg.role === 'assistant');

  return (
    <motion.div
      className={cn('flex gap-3 group', msg.role === 'user' ? 'flex-row-reverse' : '')}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      {/* Avatar */}
      <div className={cn(
        'w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 shadow-lg',
        msg.role === 'user'
          ? 'bg-indigo-600 shadow-indigo-500/25'
          : 'bg-gradient-to-br from-violet-600 to-indigo-700 shadow-violet-500/25'
      )}>
        {msg.role === 'user'
          ? <User className="w-4 h-4 text-white" />
          : <Bot className="w-4 h-4 text-white" />}
      </div>

      {/* Content */}
      <div className={cn('max-w-[75%] space-y-2', msg.role === 'user' ? 'items-end flex flex-col' : '')}>
        {/* Bubble */}
        <div className={cn(
          'px-4 py-3 rounded-2xl text-sm leading-relaxed relative',
          msg.role === 'user'
            ? 'bg-indigo-600 text-white rounded-tr-sm shadow-lg shadow-indigo-500/20'
            : msg.error
              ? 'bg-red-900/30 border border-red-500/30 text-red-200 rounded-tl-sm'
              : 'bg-white/5 border border-white/8 text-slate-200 rounded-tl-sm backdrop-blur-sm'
        )}>
          {msg.thinking ? (
            <div className="flex items-center gap-1.5 py-0.5">
              {[0, 0.15, 0.3].map((d, i) => (
                <div key={i} className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: `${d}s` }} />
              ))}
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '');
                    const inline = !match;
                    if (inline) {
                      return (
                        <code className="bg-white/10 px-1.5 py-0.5 rounded text-indigo-300 font-mono text-xs" {...props}>
                          {children}
                        </code>
                      );
                    }
                    return <CodeBlock code={String(children).trim()} language={match[1]} />;
                  },
                  table({ children }: any) {
                    return (
                      <div className="overflow-x-auto rounded-lg border border-white/10 my-2">
                        <table className="w-full text-xs">{children}</table>
                      </div>
                    );
                  },
                  th({ children }: any) {
                    return <th className="px-3 py-2 text-left text-slate-400 font-medium bg-white/5 border-b border-white/10">{children}</th>;
                  },
                  td({ children }: any) {
                    return <td className="px-3 py-2 text-slate-300 border-b border-white/5">{children}</td>;
                  },
                }}
              >
                {displayed || (animate && msg.role === 'assistant' ? '' : msg.content)}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Standalone code block from backend */}
        {msg.code && !msg.content.includes('```') && (
          <CodeBlock code={msg.code} language="python" />
        )}

        {/* Charts */}
        {msg.charts && msg.charts.length > 0 && (
          <div className="w-full">
            <ChartGrid charts={msg.charts} columns={msg.charts.length > 1 ? 2 : 1} chartHeight={260} />
          </div>
        )}

        {/* Insights pills */}
        {msg.insights && msg.insights.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {msg.insights.slice(0, 4).map((ins: any, i: number) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-indigo-900/40 border border-indigo-500/20 text-indigo-300">
                {typeof ins === 'string' ? ins : ins.text || JSON.stringify(ins)}
              </span>
            ))}
          </div>
        )}

        {/* Actions (assistant only) */}
        {msg.role === 'assistant' && !msg.thinking && (
          <div className={cn(
            'flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity',
          )}>
            <CopyButton text={msg.content} />
            <button
              onClick={() => onFeedback?.(msg.id, 'up')}
              className={cn(
                'p-1 rounded-md transition-all',
                msg.feedback === 'up'
                  ? 'text-green-400 bg-green-400/10'
                  : 'text-slate-500 hover:text-green-400 hover:bg-green-400/10'
              )}
              title="Helpful"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onFeedback?.(msg.id, 'down')}
              className={cn(
                'p-1 rounded-md transition-all',
                msg.feedback === 'down'
                  ? 'text-red-400 bg-red-400/10'
                  : 'text-slate-500 hover:text-red-400 hover:bg-red-400/10'
              )}
              title="Not helpful"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
            {msg.created_at && (
              <span className="text-xs text-slate-600 ml-1">{formatTime(msg.created_at)}</span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── Dataset Info Card ──────────────────────────────────────────

function DatasetCard({ dataset }: { dataset: Dataset }) {
  return (
    <div className="mx-3 mb-2 p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/20">
      <div className="flex items-center gap-2 mb-2">
        <Database className="w-3.5 h-3.5 text-indigo-400" />
        <span className="text-xs font-medium text-indigo-300 truncate">{dataset.name}</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {dataset.row_count != null && (
          <div className="text-center">
            <div className="text-sm font-bold text-white">{dataset.row_count.toLocaleString()}</div>
            <div className="text-xs text-slate-500">rows</div>
          </div>
        )}
        {dataset.column_count != null && (
          <div className="text-center">
            <div className="text-sm font-bold text-white">{dataset.column_count}</div>
            <div className="text-xs text-slate-500">columns</div>
          </div>
        )}
      </div>
      {dataset.file_type && (
        <div className="mt-1.5 text-center">
          <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-slate-500 uppercase tracking-wide">
            {dataset.file_type}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────

function ChatPageInner() {
  const searchParams = useSearchParams();
  const datasetIdParam = searchParams.get('dataset');

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(datasetIdParam || '');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<string | null>(null);
  const [currentSessionTitle, setCurrentSessionTitle] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [lastAnimatedId, setLastAnimatedId] = useState<string | null>(null);
  const [showDatasetMenu, setShowDatasetMenu] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const selectedDataset = datasets.find(d => d.id === selectedDatasetId) || null;

  // Load datasets + sessions
  useEffect(() => {
    datasetsApi.list().then(res => {
      const ds: Dataset[] = Array.isArray(res.data) ? res.data : res.data?.datasets || [];
      const ready = ds.filter(d => d.status === 'ready' || d.status === undefined);
      setDatasets(ready);
      if (!selectedDatasetId && ready[0]) setSelectedDatasetId(ready[0].id);
    }).catch(() => {});
    chatApi.listSessions().then(res => setSessions(res.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }, [input]);

  const loadSession = async (session: Session) => {
    setCurrentSession(session.id);
    setCurrentSessionTitle(session.title || 'Chat session');
    const res = await chatApi.getMessages(session.id);
    setMessages(res.data || []);
  };

  const newSession = () => {
    setCurrentSession(null);
    setCurrentSessionTitle('');
    setMessages([]);
  };

  const deleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await chatApi.deleteSession(id);
      setSessions(s => s.filter(s => s.id !== id));
      if (currentSession === id) newSession();
    } catch {
      toast.error('Failed to delete session');
    }
  };

  const handleFeedback = (msgId: string, value: 'up' | 'down') => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, feedback: m.feedback === value ? null : value } : m
    ));
    toast.success(value === 'up' ? 'Thanks for the feedback!' : 'Got it, we\'ll improve.');
  };

  const sendMessage = useCallback(async (text?: string) => {
    const msg = text ?? input;
    if (!msg.trim() || sending) return;
    if (!text) setInput('');
    setSending(true);

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
    };
    const thinkingMsg: Message = {
      id: 'thinking',
      role: 'assistant',
      content: '',
      thinking: true,
    };
    setMessages(prev => [...prev, userMsg, thinkingMsg]);

    try {
      const res = await chatApi.sendMessage(msg, currentSession || undefined, selectedDatasetId || undefined);
      const data = res.data;

      if (!currentSession) {
        setCurrentSession(data.session_id);
        setCurrentSessionTitle(data.title || msg.slice(0, 40));
        chatApi.listSessions().then(r => setSessions(r.data || [])).catch(() => {});
      }

      const assistantId = data.message_id || `ai-${Date.now()}`;
      setLastAnimatedId(assistantId);
      setMessages(prev => [
        ...prev.filter(m => m.id !== 'thinking'),
        {
          id: assistantId,
          role: 'assistant',
          content: data.content || '',
          charts: data.charts || [],
          code: data.code || '',
          insights: data.insights || [],
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err: any) {
      const errId = `err-${Date.now()}`;
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || '';
      const isAiKeyMissing =
        status === 402 ||
        (status === 400 && /credit|api.?key|quota|billing/i.test(detail));
      const errorContent = isAiKeyMissing
        ? 'AI features require an API key. Set ANTHROPIC_API_KEY in your backend .env file.'
        : detail || 'Something went wrong. Please try again.';
      setMessages(prev => [
        ...prev.filter(m => m.id !== 'thinking'),
        {
          id: errId,
          role: 'assistant',
          content: errorContent,
          error: true,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, currentSession, selectedDatasetId]);

  const handleConvertToDashboard = async () => {
    if (!currentSession) { toast.error('Start a conversation first'); return; }
    try {
      toast.loading('Converting to dashboard…');
      await chatExtApi.convertToDashboard(currentSession);
      toast.success('Dashboard created! Check your Dashboards page.');
    } catch {
      toast.error('Failed to convert. Try after more messages.');
    }
  };

  const handleExport = () => {
    if (messages.length === 0) { toast.error('Nothing to export yet'); return; }
    exportChatMarkdown(messages, currentSessionTitle);
    toast.success('Chat exported as Markdown');
  };

  return (
    <AppLayout>
      <div className="flex h-screen overflow-hidden">

        {/* ── Sidebar ──────────────────────────────────────────── */}
        <div className="w-60 flex-shrink-0 border-r border-white/5 flex flex-col bg-black/20 backdrop-blur-sm">

          {/* New Chat */}
          <div className="p-3 border-b border-white/5">
            <button
              onClick={newSession}
              className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-sm font-medium transition-colors border border-indigo-500/20"
            >
              <Plus className="w-4 h-4" /> New Chat
            </button>
          </div>

          {/* Dataset picker */}
          <div className="px-3 py-2.5 border-b border-white/5">
            <label className="text-xs text-slate-500 font-medium mb-1.5 block">Active Dataset</label>
            <div className="relative">
              <button
                onClick={() => setShowDatasetMenu(v => !v)}
                className="w-full flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-2.5 py-2 text-xs text-slate-300 hover:bg-white/8 transition-colors"
              >
                <Database className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
                <span className="flex-1 truncate text-left">{selectedDataset?.name || 'No dataset'}</span>
                <ChevronDown className="w-3 h-3 text-slate-500" />
              </button>
              <AnimatePresence>
                {showDatasetMenu && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1a2e] border border-white/10 rounded-xl shadow-xl overflow-hidden max-h-48 overflow-y-auto"
                  >
                    <button
                      onClick={() => { setSelectedDatasetId(''); setShowDatasetMenu(false); }}
                      className="w-full px-3 py-2 text-xs text-left text-slate-400 hover:bg-white/5 transition-colors"
                    >
                      No dataset
                    </button>
                    {datasets.map(d => (
                      <button
                        key={d.id}
                        onClick={() => { setSelectedDatasetId(d.id); setShowDatasetMenu(false); }}
                        className={cn(
                          'w-full px-3 py-2 text-xs text-left transition-colors flex items-center gap-2',
                          selectedDatasetId === d.id
                            ? 'bg-indigo-600/20 text-indigo-300'
                            : 'text-slate-300 hover:bg-white/5'
                        )}
                      >
                        <Database className="w-3 h-3 flex-shrink-0" />
                        <span className="truncate">{d.name}</span>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Dataset info card */}
          {selectedDataset && (
            <div className="pt-2">
              <DatasetCard dataset={selectedDataset} />
            </div>
          )}

          {/* Session list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {sessions.length === 0 && (
              <p className="text-xs text-slate-600 text-center py-4 px-2">No conversations yet. Start chatting!</p>
            )}
            {sessions.map(s => (
              <div
                key={s.id}
                onClick={() => loadSession(s)}
                className={cn(
                  'flex items-start gap-2 px-2.5 py-2.5 rounded-lg cursor-pointer text-xs transition-all group',
                  currentSession === s.id
                    ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                )}
              >
                <MessageSquare className="w-3 h-3 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="truncate leading-tight">{s.title || 'New chat'}</p>
                  {s.created_at && (
                    <p className="text-slate-600 text-[10px] mt-0.5">{formatTime(s.created_at)}</p>
                  )}
                </div>
                <button
                  onClick={e => deleteSession(s.id, e)}
                  className="opacity-0 group-hover:opacity-100 flex-shrink-0 text-slate-600 hover:text-red-400 transition-all mt-0.5"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>

          {/* Sidebar footer actions */}
          <div className="p-3 border-t border-white/5 space-y-1.5">
            <button
              onClick={handleExport}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> Export chat (.md)
            </button>
            <button
              onClick={handleConvertToDashboard}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-400 hover:text-violet-300 hover:bg-violet-900/20 transition-colors"
            >
              <LayoutDashboard className="w-3.5 h-3.5" /> Convert to Dashboard
            </button>
          </div>
        </div>

        {/* ── Main Chat Area ────────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Top bar */}
          <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-violet-500/20">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">
                  {currentSessionTitle || 'DataMind AI Analyst'}
                </h2>
                <p className="text-xs text-slate-500">
                  {selectedDataset
                    ? `Analyzing: ${selectedDataset.name} · ${selectedDataset.row_count?.toLocaleString() || '?'} rows`
                    : 'Select a dataset to unlock data analysis'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Model badge */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10">
                <Brain className="w-3 h-3 text-indigo-400" />
                <span className="text-xs text-slate-400">GPT-4o-mini</span>
              </div>

              {messages.length > 0 && (
                <>
                  <button
                    onClick={handleExport}
                    className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                    title="Export chat"
                  >
                    <FileText className="w-4 h-4" />
                  </button>
                  <button
                    onClick={newSession}
                    className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                    title="New session"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
            {messages.length === 0 && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto text-center"
              >
                <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center mb-6 shadow-xl shadow-indigo-500/10">
                  <Bot className="w-10 h-10 text-indigo-400" />
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">
                  {selectedDataset ? `Analyzing ${selectedDataset.name}` : 'Ask me anything'}
                </h3>
                <p className="text-slate-500 text-sm mb-8 max-w-sm">
                  {selectedDataset
                    ? `I have access to your ${selectedDataset.row_count?.toLocaleString() || ''} row dataset. Ask anything — I'll generate charts, stats, and insights.`
                    : 'Select a dataset from the sidebar to start AI-powered data analysis, or ask general data science questions.'}
                </p>

                <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
                  {SUGGESTIONS.map(({ icon: Icon, text, label }) => (
                    <button
                      key={text}
                      onClick={() => sendMessage(text)}
                      className="group flex items-start gap-3 p-3.5 glass rounded-xl border border-white/5 hover:border-indigo-500/30 hover:bg-indigo-950/20 text-left transition-all"
                    >
                      <div className="w-7 h-7 rounded-lg bg-indigo-900/40 flex items-center justify-center flex-shrink-0 group-hover:bg-indigo-600/30 transition-colors">
                        <Icon className="w-3.5 h-3.5 text-indigo-400" />
                      </div>
                      <div>
                        <p className="text-xs font-medium text-indigo-400 mb-0.5">{label}</p>
                        <p className="text-xs text-slate-400 leading-snug">{text}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {messages.map((msg, i) => (
              <MessageBubble
                key={msg.id || i}
                msg={msg}
                animate={msg.id === lastAnimatedId}
                onFeedback={handleFeedback}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="p-4 border-t border-white/5 bg-black/10">
            {!selectedDataset && (
              <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-900/20 border border-amber-500/20 text-amber-300 text-xs">
                <Database className="w-3.5 h-3.5 flex-shrink-0" />
                No dataset selected — analysis capabilities are limited
              </div>
            )}

            <div className="flex gap-3 items-end">
              <div className="flex-1 relative">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage(undefined);
                    }
                  }}
                  placeholder={selectedDataset
                    ? `Ask about ${selectedDataset.name}… (Enter to send, Shift+Enter for newline)`
                    : 'Ask a data science question… (Enter to send)'}
                  rows={1}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-600 resize-none focus:outline-none focus:border-indigo-500/50 transition-all pr-4 leading-relaxed"
                  style={{ minHeight: '46px', maxHeight: '140px' }}
                />
              </div>

              <motion.button
                onClick={() => sendMessage(undefined)}
                disabled={!input.trim() || sending}
                className={cn(
                  'p-3 rounded-xl transition-all flex-shrink-0 shadow-lg',
                  input.trim() && !sending
                    ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-500/25 hover:shadow-indigo-500/40'
                    : 'bg-white/5 text-slate-600 cursor-not-allowed shadow-none'
                )}
                whileHover={input.trim() && !sending ? { scale: 1.05 } : {}}
                whileTap={input.trim() && !sending ? { scale: 0.95 } : {}}
              >
                {sending ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </motion.button>
            </div>

            <div className="flex items-center justify-between mt-2 px-1">
              <p className="text-[11px] text-slate-600">
                Powered by GPT-4o-mini · Context: {messages.filter(m => !m.thinking).length} messages
              </p>
              {input.length > 0 && (
                <p className={cn('text-[11px]', input.length > 800 ? 'text-amber-400' : 'text-slate-600')}>
                  {input.length} chars
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  );
}
