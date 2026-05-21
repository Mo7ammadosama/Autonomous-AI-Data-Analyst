'use client';

import { useState, useEffect } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import {
  FileText, Plus, Trash2, Download, Sparkles, ChevronUp,
  ChevronDown, Loader2, CheckCircle2, AlertCircle, Edit3,
  Globe, GripVertical, Eye
} from 'lucide-react';
import { toast } from 'sonner';
import { datasetsApi, domainTemplatesApi, customReportsApi } from '@/lib/api';
import ReactMarkdown from 'react-markdown';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Dataset { id: string; name: string; status: string; }
interface TemplateSummary { domain: string; name: string; description: string; }

interface Section {
  id: string;
  type: string;
  title: string;
  content: Record<string, unknown> | null;
  order: number;
}

interface Report {
  id: string;
  name: string;
  domain: string | null;
  template_name: string | null;
  dataset_id: string | null;
  sections: Section[];
  generated_content: Record<string, { body: string }>;
  status: string;
  created_at: string;
}

const DOMAINS = ['finance', 'retail', 'healthcare', 'marketing', 'hr', 'operations'];
const SECTION_TYPES = ['text', 'metric_card', 'insight_list', 'chart', 'table'];

// ── Section type badge ─────────────────────────────────────────────────────────

function SectionTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    text: 'bg-indigo-500/10 text-indigo-300',
    chart: 'bg-violet-500/10 text-violet-300',
    table: 'bg-cyan-500/10 text-cyan-300',
    metric_card: 'bg-emerald-500/10 text-emerald-300',
    insight_list: 'bg-amber-500/10 text-amber-300',
  };
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${colors[type] || 'bg-slate-500/10 text-slate-400'}`}>
      {type}
    </span>
  );
}

// ── Section editor row ─────────────────────────────────────────────────────────

function SectionRow({
  section, idx, total, onMove, onDelete, onTitleChange, generatedContent
}: {
  section: Section;
  idx: number;
  total: number;
  onMove: (from: number, to: number) => void;
  onDelete: (id: string) => void;
  onTitleChange: (id: string, title: string) => void;
  generatedContent: string;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(section.title);

  const saveTitle = () => {
    onTitleChange(section.id, title);
    setEditing(false);
  };

  return (
    <div className="glass rounded-xl p-3 flex items-start gap-3 group">
      <GripVertical className="w-4 h-4 text-slate-600 mt-1 flex-shrink-0" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <SectionTypeBadge type={section.type} />
          {editing ? (
            <input
              className="flex-1 bg-transparent border-b border-indigo-500 text-sm text-white outline-none"
              value={title}
              onChange={e => setTitle(e.target.value)}
              onBlur={saveTitle}
              onKeyDown={e => e.key === 'Enter' && saveTitle()}
              autoFocus
            />
          ) : (
            <button
              className="text-sm text-slate-300 text-left hover:text-white flex items-center gap-1"
              onClick={() => setEditing(true)}
            >
              {section.title}
              <Edit3 className="w-3 h-3 opacity-0 group-hover:opacity-50 transition-opacity" />
            </button>
          )}
        </div>
        {generatedContent && (
          <div className="text-xs text-slate-500 line-clamp-2 mt-1">{generatedContent}</div>
        )}
      </div>

      <div className="flex flex-col gap-1 flex-shrink-0">
        <button
          className="p-1 text-slate-600 hover:text-slate-300 disabled:opacity-30 transition-colors"
          onClick={() => onMove(idx, idx - 1)}
          disabled={idx === 0}
        >
          <ChevronUp className="w-3 h-3" />
        </button>
        <button
          className="p-1 text-slate-600 hover:text-slate-300 disabled:opacity-30 transition-colors"
          onClick={() => onMove(idx, idx + 1)}
          disabled={idx === total - 1}
        >
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>

      <button
        className="p-1 text-slate-600 hover:text-red-400 transition-colors flex-shrink-0"
        onClick={() => onDelete(section.id)}
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CustomReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [activeReport, setActiveReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // New report form
  const [newName, setNewName] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [newTemplate, setNewTemplate] = useState('');
  const [newDataset, setNewDataset] = useState('');

  // Filtered templates for selected domain
  const domainTemplates = templates.filter(t => t.domain === newDomain);

  useEffect(() => {
    loadReports();
    datasetsApi.list().then(r => {
      setDatasets((r.data as { datasets?: Dataset[] }).datasets || r.data || []);
    }).catch(() => {});
    domainTemplatesApi.list().then(r => {
      setTemplates(r.data as TemplateSummary[] || []);
    }).catch(() => {});
  }, []);

  // Normalize a report so sections is always an array
  const normalizeReport = (r: any): Report => ({
    ...r,
    sections: Array.isArray(r.sections) ? r.sections : [],
    generated_content: r.generated_content || {},
  });

  const loadReports = async () => {
    try {
      const r = await customReportsApi.list();
      setReports((r.data as any[]).map(normalizeReport));
    } catch {
      toast.error('Failed to load reports');
    }
  };

  const createReport = async () => {
    if (newName.trim().length < 2) { toast.error('Report name must be at least 2 characters'); return; }
    setLoading(true);
    try {
      const r = await customReportsApi.create({
        name: newName,
        domain: newDomain || undefined,
        template_name: newTemplate || undefined,
        dataset_id: newDataset || undefined,
      });
      const rep = normalizeReport(r.data);
      setReports(prev => [rep, ...prev]);
      setActiveReport(rep);
      setNewName('');
      toast.success('Report created');
    } catch {
      toast.error('Failed to create report');
    } finally {
      setLoading(false);
    }
  };

  const deleteReport = async (id: string) => {
    if (!confirm('Delete this report?')) return;
    try {
      await customReportsApi.delete(id);
      setReports(prev => prev.filter(r => r.id !== id));
      if (activeReport?.id === id) setActiveReport(null);
      toast.success('Report deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const generateReport = async () => {
    if (!activeReport) return;
    setGenerating(true);
    try {
      const r = await customReportsApi.generate(activeReport.id);
      const updated = normalizeReport(r.data);
      setActiveReport(updated);
      setReports(prev => prev.map(rep => rep.id === updated.id ? updated : rep));
      toast.success('Report generated!');
    } catch {
      toast.error('Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const saveSection = async (sections: Section[]) => {
    if (!activeReport) return;
    try {
      const r = await customReportsApi.update(activeReport.id, { sections });
      setActiveReport(normalizeReport(r.data));
    } catch {
      toast.error('Failed to save sections');
    }
  };

  const addSection = async () => {
    if (!activeReport) return;
    const newSection: Section = {
      id: crypto.randomUUID(),
      type: 'text',
      title: `Section ${activeReport.sections.length + 1}`,
      content: null,
      order: activeReport.sections.length,
    };
    const updated = [...activeReport.sections, newSection];
    setActiveReport(prev => prev ? { ...prev, sections: updated } : null);
    await saveSection(updated);
  };

  const moveSection = async (from: number, to: number) => {
    if (!activeReport) return;
    if (to < 0 || to >= activeReport.sections.length) return;
    const sections = [...activeReport.sections];
    const [moved] = sections.splice(from, 1);
    sections.splice(to, 0, moved);
    const reordered = sections.map((s, i) => ({ ...s, order: i }));
    setActiveReport(prev => prev ? { ...prev, sections: reordered } : null);
    await saveSection(reordered);
  };

  const deleteSection = async (sectionId: string) => {
    if (!activeReport) return;
    const updated = activeReport.sections.filter(s => s.id !== sectionId);
    setActiveReport(prev => prev ? { ...prev, sections: updated } : null);
    await saveSection(updated);
  };

  const changeSectionTitle = async (sectionId: string, title: string) => {
    if (!activeReport) return;
    const updated = activeReport.sections.map(s => s.id === sectionId ? { ...s, title } : s);
    setActiveReport(prev => prev ? { ...prev, sections: updated } : null);
    await saveSection(updated);
  };

  const exportReport = async (fmt: 'html' | 'pdf' | 'json') => {
    if (!activeReport) return;
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : '';
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    try {
      const res = await fetch(
        `${API_BASE}/api/custom-reports/${activeReport.id}/export?fmt=${fmt}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) { toast.error('Export failed'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeReport.name}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Export failed');
    }
  };

  return (
    <AppLayout>
      <div className="flex h-full gap-4 p-6">

        {/* ── Left: reports list + create ───────────────────── */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4">
          {/* Create form */}
          <div className="glass rounded-2xl p-4 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-slate-300">New Report</h2>
            <input
              className="input-field text-sm"
              placeholder="Report name"
              value={newName}
              onChange={e => setNewName(e.target.value)}
            />
            <select
              className="input-field text-sm"
              value={newDomain}
              onChange={e => { setNewDomain(e.target.value); setNewTemplate(''); }}
            >
              <option value="">— domain —</option>
              {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            {domainTemplates.length > 0 && (
              <select
                className="input-field text-sm"
                value={newTemplate}
                onChange={e => setNewTemplate(e.target.value)}
              >
                <option value="">— template —</option>
                {domainTemplates.map(t => (
                  <option key={t.name} value={t.name}>{t.name.replace(/_/g, ' ')}</option>
                ))}
              </select>
            )}
            <select
              className="input-field text-sm"
              value={newDataset}
              onChange={e => setNewDataset(e.target.value)}
            >
              <option value="">— dataset —</option>
              {datasets.filter(d => d.status === 'ready').map(d => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <button
              className="btn-primary flex items-center justify-center gap-2 text-sm"
              onClick={createReport}
              disabled={loading || !newName.trim()}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Report
            </button>
          </div>

          {/* Reports list */}
          <div className="flex-1 overflow-y-auto space-y-2">
            {reports.map(r => (
              <div
                key={r.id}
                role="button"
                tabIndex={0}
                className={`w-full text-left glass rounded-xl p-3 border transition-all cursor-pointer ${activeReport?.id === r.id ? 'border-indigo-500/40' : 'border-transparent hover:border-white/10'}`}
                onClick={() => setActiveReport(normalizeReport(r))}
                onKeyDown={e => e.key === 'Enter' && setActiveReport(normalizeReport(r))}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">{r.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{r.domain || 'general'}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {r.status === 'ready' && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                    {r.status === 'generating' && <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />}
                    {r.status === 'failed' && <AlertCircle className="w-3 h-3 text-red-400" />}
                    <button
                      className="p-1 text-slate-600 hover:text-red-400 transition-colors"
                      onClick={e => { e.stopPropagation(); deleteReport(r.id); }}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {reports.length === 0 && (
              <p className="text-xs text-slate-600 text-center py-4">No reports yet</p>
            )}
          </div>
        </div>

        {/* ── Centre: Section editor ──────────────────────────── */}
        <div className="flex-1 flex flex-col glass rounded-2xl overflow-hidden">
          {!activeReport ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
              <FileText className="w-12 h-12 opacity-20" />
              <p className="text-sm">Select or create a report</p>
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <span className="text-sm font-semibold text-slate-300 flex-1 truncate">{activeReport.name}</span>
                <button
                  className="btn-ghost text-xs flex items-center gap-1 px-3 py-1.5"
                  onClick={addSection}
                >
                  <Plus className="w-3 h-3" /> Add Section
                </button>
                <button
                  className="btn-primary text-xs flex items-center gap-1 px-3 py-1.5"
                  onClick={generateReport}
                  disabled={generating}
                >
                  {generating
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Sparkles className="w-3 h-3" />}
                  Generate AI
                </button>
                <div className="flex items-center gap-1 ml-2">
                  <button
                    className="p-1.5 text-slate-500 hover:text-slate-200 hover:bg-white/5 rounded-lg transition-colors"
                    onClick={() => exportReport('html')}
                    title="Export HTML"
                  >
                    <Globe className="w-4 h-4" />
                  </button>
                  <button
                    className="p-1.5 text-slate-500 hover:text-slate-200 hover:bg-white/5 rounded-lg transition-colors"
                    onClick={() => exportReport('pdf')}
                    title="Export PDF"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Section list */}
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {activeReport.sections.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-600 gap-2">
                    <p className="text-sm">No sections yet. Add a section or generate from template.</p>
                  </div>
                )}
                {[...activeReport.sections]
                  .sort((a, b) => a.order - b.order)
                  .map((section, idx) => {
                    const genContent = activeReport.generated_content?.[section.id]?.body || '';
                    return (
                      <SectionRow
                        key={section.id}
                        section={section}
                        idx={idx}
                        total={activeReport.sections.length}
                        onMove={moveSection}
                        onDelete={deleteSection}
                        onTitleChange={changeSectionTitle}
                        generatedContent={genContent.slice(0, 120)}
                      />
                    );
                  })}
              </div>
            </>
          )}
        </div>

        {/* ── Right: Preview ──────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 glass rounded-2xl overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
            <Eye className="w-4 h-4 text-slate-400" />
            <span className="text-sm font-semibold text-slate-300">Preview</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {!activeReport && (
              <p className="text-xs text-slate-600 text-center py-8">No report selected</p>
            )}
            {activeReport && (
              <div className="space-y-4">
                <h3 className="text-base font-bold text-white">{activeReport.name}</h3>
                {activeReport.domain && (
                  <p className="text-xs text-slate-500">Domain: {activeReport.domain}</p>
                )}
                {[...activeReport.sections]
                  .sort((a, b) => a.order - b.order)
                  .map(section => {
                    const body = activeReport.generated_content?.[section.id]?.body;
                    return (
                      <div key={section.id}>
                        <h4 className="text-sm font-semibold text-indigo-400 mb-1">{section.title}</h4>
                        {body ? (
                          <div className="prose prose-sm prose-invert max-w-none text-slate-400 text-xs">
                            <ReactMarkdown>{body}</ReactMarkdown>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-600 italic">Not generated yet</p>
                        )}
                      </div>
                    );
                  })}
                {activeReport.status === 'ready' && activeReport.sections.length > 0 && (
                  <div className="flex gap-2 pt-2">
                    <button
                      className="flex-1 btn-ghost text-xs flex items-center justify-center gap-1"
                      onClick={() => exportReport('html')}
                    >
                      <Globe className="w-3 h-3" /> HTML
                    </button>
                    <button
                      className="flex-1 btn-ghost text-xs flex items-center justify-center gap-1"
                      onClick={() => exportReport('pdf')}
                    >
                      <Download className="w-3 h-3" /> PDF
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

      </div>
    </AppLayout>
  );
}
