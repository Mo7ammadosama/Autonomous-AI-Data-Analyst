'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BookOpen, Plus, Search, Play, Trash2, FileText, Code2, Database,
  Brain, BarChart2, ChevronRight, Clock, Sparkles, Download, Share2,
  CheckCircle2, AlertCircle, Loader2, X, ArrowUp, ArrowDown,
  MoreHorizontal, Tag
} from 'lucide-react';
import AppLayout from '@/components/layout/AppLayout';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const authHeaders = () => ({
  Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
  'Content-Type': 'application/json',
});

// ── Types ────────────────────────────────────────────────────────────────────
type CellType = 'markdown' | 'data' | 'ai_prompt' | 'code' | 'chart';

interface Cell {
  id: string;
  cell_type: CellType;
  position: number;
  content: string;
  output?: string | null;
  output_type?: string | null;
  is_executed: boolean;
  figures?: string[];
}

interface Notebook {
  id: string;
  title: string;
  description?: string;
  domain?: string;
  template_name?: string;
  created_at: string;
  updated_at: string;
  cells: Cell[];
}

interface Template {
  id: string;
  name: string;
  domain: string;
  description: string;
  run_count: number;
  cell_count: number;
}

// ── Constants ─────────────────────────────────────────────────────────────
const DOMAINS = ['All', 'Finance', 'Sales', 'Marketing', 'Operations', 'Healthcare', 'HR'];

const CELL_ICONS: Record<CellType, React.ElementType> = {
  markdown:  FileText,
  data:      Database,
  ai_prompt: Brain,
  code:      Code2,
  chart:     BarChart2,
};

const CELL_COLORS: Record<CellType, string> = {
  markdown:  'from-slate-500 to-slate-600',
  data:      'from-violet-500 to-purple-600',
  ai_prompt: 'from-indigo-500 to-blue-600',
  code:      'from-cyan-500 to-teal-600',
  chart:     'from-emerald-500 to-green-600',
};

const CELL_LABELS: Record<CellType, string> = {
  markdown:  'Markdown',
  data:      'Data',
  ai_prompt: 'AI Prompt',
  code:      'Python',
  chart:     'Chart',
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── API helpers ──────────────────────────────────────────────────────────────
async function apiFetch(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  if (!res.ok) throw new Error(await res.text());
  if (res.status === 204) return null;
  return res.json();
}

// ── Cell editor component ─────────────────────────────────────────────────
function CellEditor({
  cell,
  index,
  total,
  onUpdate,
  onDelete,
  onMove,
  onRun,
  isRunning,
}: {
  cell: Cell;
  index: number;
  total: number;
  onUpdate: (id: string, content: string) => void;
  onDelete: (id: string) => void;
  onMove: (id: string, dir: 'up' | 'down') => void;
  onRun: (id: string) => void;
  isRunning: boolean;
}) {
  const Icon = CELL_ICONS[cell.cell_type];
  const colorClass = CELL_COLORS[cell.cell_type];
  const label = CELL_LABELS[cell.cell_type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="group rounded-2xl border border-white/8 bg-white/[0.03] overflow-hidden hover:border-white/15 transition-all"
    >
      {/* Cell header */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 bg-white/[0.02]">
        <div className={`w-6 h-6 rounded-lg bg-gradient-to-br ${colorClass} flex items-center justify-center flex-shrink-0`}>
          <Icon className="w-3.5 h-3.5 text-white" />
        </div>
        <span className="text-xs font-semibold text-slate-400">{label}</span>
        <div className="flex-1" />
        {/* Controls */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onMove(cell.id, 'up')}
            disabled={index === 0}
            className="w-6 h-6 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-200 hover:bg-white/10 disabled:opacity-30 transition-all"
          >
            <ArrowUp className="w-3 h-3" />
          </button>
          <button
            onClick={() => onMove(cell.id, 'down')}
            disabled={index === total - 1}
            className="w-6 h-6 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-200 hover:bg-white/10 disabled:opacity-30 transition-all"
          >
            <ArrowDown className="w-3 h-3" />
          </button>
          <button
            onClick={() => onRun(cell.id)}
            disabled={isRunning || cell.cell_type === 'markdown'}
            className="w-6 h-6 rounded-lg flex items-center justify-center text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 disabled:opacity-30 transition-all"
          >
            {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          </button>
          <button
            onClick={() => onDelete(cell.id)}
            className="w-6 h-6 rounded-lg flex items-center justify-center text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Cell body */}
      <div className="p-4">
        <textarea
          value={cell.content}
          onChange={e => onUpdate(cell.id, e.target.value)}
          placeholder={
            cell.cell_type === 'markdown' ? '# Write markdown here...' :
            cell.cell_type === 'ai_prompt' ? 'Describe what you want the AI to analyze...' :
            cell.cell_type === 'code' ? '# Python code here\nimport pandas as pd' :
            cell.cell_type === 'data' ? 'Describe the dataset or select one...' :
            'Chart description...'
          }
          className="w-full bg-transparent text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none resize-none font-mono leading-relaxed min-h-[80px]"
          rows={Math.max(3, (cell.content?.split('\n').length || 1) + 1)}
        />

        {/* Output */}
        {cell.is_executed && cell.output && (
          <div className={cn(
            'mt-3 rounded-xl p-3 text-xs',
            cell.output_type === 'error'
              ? 'bg-red-500/10 border border-red-500/20 text-red-400'
              : 'bg-white/[0.03] border border-white/5 text-slate-400'
          )}>
            <div className="flex items-center gap-2 mb-2">
              {cell.output_type === 'error'
                ? <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                : <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              }
              <span className="font-semibold text-slate-500">Output</span>
            </div>
            <pre className="whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
              {typeof cell.output === 'string' ? cell.output.replace(/^"|"$/g, '') : String(cell.output)}
            </pre>
            {cell.figures && cell.figures.length > 0 && (
              <div className="mt-3 space-y-2">
                {cell.figures.map((fig, i) => (
                  <img key={i} src={`data:image/png;base64,${fig}`} alt={`Chart ${i + 1}`} className="rounded-xl w-full" />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────
export default function NotebooksPage() {
  const router = useRouter();
  const [view, setView] = useState<'gallery' | 'editor'>('gallery');
  const [activeTab, setActiveTab] = useState('All');
  const [search, setSearch] = useState('');
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [activeNotebook, setActiveNotebook] = useState<Notebook | null>(null);
  const [cells, setCells] = useState<Cell[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);
  const [runningCell, setRunningCell] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nbs, tmps] = await Promise.all([
        apiFetch('/api/notebooks'),
        apiFetch('/api/notebooks/templates'),
      ]);
      setNotebooks(nbs || []);
      setTemplates(tmps || []);
    } catch {
      toast.error('Failed to load notebooks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createNew = async () => {
    try {
      const nb = await apiFetch('/api/notebooks', {
        method: 'POST',
        body: JSON.stringify({
          title: 'Untitled Notebook',
          cells: [{ cell_type: 'markdown', content: '# New Analysis\nAdd cells below to start your analysis.', position: 0 }],
        }),
      });
      openNotebook(nb);
    } catch {
      toast.error('Failed to create notebook');
    }
  };

  const applyTemplate = async (templateId: string) => {
    try {
      const nb = await apiFetch(`/api/notebooks/templates/${templateId}/use`, { method: 'POST' });
      toast.success('Template loaded');
      openNotebook(nb);
    } catch {
      toast.error('Failed to load template');
    }
  };

  const openNotebook = (nb: Notebook) => {
    setActiveNotebook(nb);
    setCells(nb.cells || []);
    setView('editor');
  };

  const deleteNotebook = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiFetch(`/api/notebooks/${id}`, { method: 'DELETE' });
      setNotebooks(prev => prev.filter(n => n.id !== id));
      toast.success('Notebook deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const saveCells = async () => {
    if (!activeNotebook) return;
    try {
      await apiFetch(`/api/notebooks/${activeNotebook.id}/cells`, {
        method: 'POST',
        body: JSON.stringify({ cells: cells.map((c, i) => ({ ...c, position: i })) }),
      });
      toast.success('Saved');
    } catch {
      toast.error('Save failed');
    }
  };

  const addCell = (type: CellType) => {
    const newCell: Cell = {
      id: `temp-${Date.now()}`,
      cell_type: type,
      position: cells.length,
      content: '',
      is_executed: false,
    };
    setCells(prev => [...prev, newCell]);
  };

  const updateCell = (id: string, content: string) => {
    setCells(prev => prev.map(c => c.id === id ? { ...c, content } : c));
  };

  const deleteCell = (id: string) => {
    setCells(prev => prev.filter(c => c.id !== id));
  };

  const moveCell = (id: string, dir: 'up' | 'down') => {
    setCells(prev => {
      const idx = prev.findIndex(c => c.id === id);
      if (idx === -1) return prev;
      const next = [...prev];
      const swap = dir === 'up' ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= next.length) return prev;
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
  };

  const runAll = async () => {
    if (!activeNotebook) return;
    setRunningAll(true);
    try {
      await saveCells();
      const result = await apiFetch(`/api/notebooks/${activeNotebook.id}/run`, { method: 'POST' });
      // Update cell outputs
      if (result?.results) {
        setCells(prev => prev.map(cell => {
          const res = result.results.find((r: { cell_id: string; output?: string; output_type?: string; error?: string; figures?: string[] }) => r.cell_id === cell.id);
          if (!res) return cell;
          return {
            ...cell,
            output: res.error || res.output,
            output_type: res.output_type,
            is_executed: true,
            figures: res.figures,
          };
        }));
      }
      toast.success(`${result?.cells_executed || 0} cells executed`);
    } catch {
      toast.error('Run failed');
    } finally {
      setRunningAll(false);
    }
  };

  const filteredTemplates = templates.filter(t => {
    const matchDomain = activeTab === 'All' || t.domain.toLowerCase() === activeTab.toLowerCase();
    const matchSearch = !search || t.name.toLowerCase().includes(search.toLowerCase()) || t.description.toLowerCase().includes(search.toLowerCase());
    return matchDomain && matchSearch;
  });

  // ── Template Gallery view ──────────────────────────────────────────────
  if (view === 'gallery') {
    return (
      <AppLayout>
        <div className="max-w-7xl mx-auto px-6 py-8">
          {/* Header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
                  <BookOpen className="w-5 h-5 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Analysis Notebooks</h1>
              </div>
              <p className="text-slate-400 text-sm ml-12">Structured, repeatable analyses with AI-powered cells</p>
            </div>
            <motion.button
              onClick={createNew}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-sm font-semibold hover:from-indigo-500 hover:to-violet-500 transition-all shadow-lg shadow-indigo-500/25"
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            >
              <Plus className="w-4 h-4" />
              New Notebook
            </motion.button>
          </div>

          {/* My Notebooks */}
          {notebooks.length > 0 && (
            <div className="mb-10">
              <h2 className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-indigo-400" />
                My Notebooks
              </h2>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {notebooks.map(nb => (
                  <motion.div
                    key={nb.id}
                    onClick={() => openNotebook(nb)}
                    className="group relative rounded-2xl border border-white/8 bg-white/[0.03] p-5 hover:bg-white/[0.07] hover:border-white/15 transition-all cursor-pointer"
                    whileHover={{ y: -2 }}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center">
                        <BookOpen className="w-4.5 h-4.5 text-indigo-400" />
                      </div>
                      <button
                        onClick={(e) => deleteNotebook(nb.id, e)}
                        className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <h3 className="font-semibold text-white text-sm mb-1">{nb.title}</h3>
                    {nb.template_name && (
                      <div className="flex items-center gap-1.5 mb-2">
                        <Tag className="w-3 h-3 text-indigo-400" />
                        <span className="text-xs text-indigo-400">{nb.template_name}</span>
                      </div>
                    )}
                    <p className="text-xs text-slate-500">{nb.cells?.length || 0} cells · {formatDate(nb.updated_at)}</p>
                    <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Template Gallery */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-violet-400" />
                Analysis Templates
              </h2>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search templates..."
                  className="pl-9 pr-4 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/40 transition-all w-48"
                />
              </div>
            </div>

            {/* Domain tabs */}
            <div className="flex gap-1 mb-6 flex-wrap">
              {DOMAINS.map(d => (
                <button
                  key={d}
                  onClick={() => setActiveTab(d)}
                  className={cn(
                    'px-3 py-1.5 rounded-xl text-xs font-medium transition-all',
                    activeTab === d
                      ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-500/20'
                      : 'bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white border border-white/8'
                  )}
                >
                  {d}
                </button>
              ))}
            </div>

            {loading ? (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {[...Array(6)].map((_, i) => <div key={i} className="h-40 rounded-2xl bg-white/5 animate-pulse" />)}
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredTemplates.map((t, i) => (
                  <motion.div
                    key={t.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="group rounded-2xl border border-white/8 bg-white/[0.03] p-5 hover:bg-white/[0.07] hover:border-white/15 transition-all"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <span className={cn(
                          'text-[10px] px-2 py-0.5 rounded-full font-semibold border mb-2 inline-block',
                          t.domain === 'Finance'    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                          t.domain === 'Sales'      ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20' :
                          t.domain === 'Marketing'  ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' :
                          t.domain === 'Operations' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                          t.domain === 'HR'         ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                          'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                        )}>
                          {t.domain}
                        </span>
                      </div>
                      <div className="text-xs text-slate-600">{t.cell_count} cells</div>
                    </div>
                    <h3 className="font-semibold text-white text-sm mb-1.5">{t.name}</h3>
                    <p className="text-xs text-slate-500 leading-relaxed mb-4">{t.description}</p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-600">By DataMind · {t.run_count.toLocaleString()} runs</span>
                      <motion.button
                        onClick={() => applyTemplate(t.id)}
                        className="px-3 py-1.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold hover:bg-indigo-500/20 transition-all flex items-center gap-1.5"
                        whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                      >
                        <Play className="w-3 h-3" />
                        Use Template
                      </motion.button>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>
      </AppLayout>
    );
  }

  // ── Notebook Editor view ────────────────────────────────────────────────
  return (
    <AppLayout>
      <div className="flex flex-col h-screen overflow-hidden">
        {/* Editor toolbar */}
        <div className="flex items-center gap-3 px-6 py-3.5 border-b border-white/5 bg-white/[0.02] flex-shrink-0">
          <button
            onClick={() => { setView('gallery'); load(); }}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5" />
            Notebooks
          </button>
          <ChevronRight className="w-3 h-3 text-slate-600" />
          <span className="text-xs font-semibold text-white truncate max-w-[200px]">{activeNotebook?.title}</span>
          {activeNotebook?.template_name && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              {activeNotebook.template_name}
            </span>
          )}
          <div className="flex-1" />
          {/* Add cell buttons */}
          <div className="flex items-center gap-1">
            {(['markdown', 'data', 'ai_prompt', 'code', 'chart'] as CellType[]).map(type => {
              const Icon = CELL_ICONS[type];
              return (
                <button
                  key={type}
                  onClick={() => addCell(type)}
                  title={`Add ${CELL_LABELS[type]} cell`}
                  className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-white/8 border border-white/5 hover:border-white/15 transition-all"
                >
                  <Icon className="w-3 h-3" />
                  <span className="hidden sm:block">{CELL_LABELS[type]}</span>
                </button>
              );
            })}
          </div>
          <div className="w-px h-5 bg-white/10" />
          <button
            onClick={saveCells}
            className="px-3 py-1.5 rounded-xl text-xs text-slate-300 hover:text-white border border-white/10 hover:border-white/20 hover:bg-white/5 transition-all"
          >
            Save
          </button>
          <motion.button
            onClick={runAll}
            disabled={runningAll || cells.length === 0}
            className="flex items-center gap-2 px-4 py-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-xs font-semibold hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 transition-all shadow-lg shadow-indigo-500/20"
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          >
            {runningAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run All
          </motion.button>
        </div>

        {/* Editor content */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-6 py-6 space-y-3">
            {cells.length === 0 ? (
              <div className="text-center py-20 text-slate-500">
                <BookOpen className="w-10 h-10 mx-auto mb-3 text-slate-700" />
                <p className="text-sm">No cells yet. Add a cell above to start your analysis.</p>
              </div>
            ) : (
              <AnimatePresence>
                {cells.map((cell, i) => (
                  <CellEditor
                    key={cell.id}
                    cell={cell}
                    index={i}
                    total={cells.length}
                    onUpdate={updateCell}
                    onDelete={deleteCell}
                    onMove={moveCell}
                    onRun={(id) => {
                      setRunningCell(id);
                      setTimeout(() => setRunningCell(null), 2000);
                    }}
                    isRunning={runningCell === cell.id || runningAll}
                  />
                ))}
              </AnimatePresence>
            )}

            {/* Add cell bar */}
            <div className="flex items-center gap-2 pt-2">
              <div className="flex-1 h-px bg-white/5" />
              <span className="text-xs text-slate-600">Add cell</span>
              <div className="flex-1 h-px bg-white/5" />
            </div>
            <div className="flex gap-2 flex-wrap">
              {(['markdown', 'data', 'ai_prompt', 'code', 'chart'] as CellType[]).map(type => {
                const Icon = CELL_ICONS[type];
                const gradClass = CELL_COLORS[type];
                return (
                  <button
                    key={type}
                    onClick={() => addCell(type)}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl border border-white/8 bg-white/[0.03] text-xs text-slate-400 hover:text-white hover:bg-white/8 hover:border-white/15 transition-all"
                  >
                    <div className={`w-4 h-4 rounded bg-gradient-to-br ${gradClass} flex items-center justify-center`}>
                      <Icon className="w-2.5 h-2.5 text-white" />
                    </div>
                    {CELL_LABELS[type]}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
