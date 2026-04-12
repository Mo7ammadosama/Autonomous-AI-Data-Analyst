'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Database, Plus, Trash2, TestTube2, RefreshCw, Table2,
  CheckCircle2, XCircle, Play, Upload, Server, Lock,
  ChevronRight, Zap, Globe, FileSpreadsheet, Cloud,
  MessageSquare, Mail, Webhook, ArrowRight, X, Check,
  AlertCircle, Loader2
} from 'lucide-react';
import { toast } from 'sonner';
import AppLayout from '@/components/layout/AppLayout';
import api from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Connection {
  id: string;
  name: string;
  connection_type: string;
  host?: string;
  port?: number;
  database: string;
  username?: string;
  schema_name?: string;
  is_active: boolean;
  last_synced?: string;
  created_at: string;
}

// ── Connector catalog ─────────────────────────────────────────────────────────

type ConnectorCategory = 'all' | 'databases' | 'warehouses' | 'cloud' | 'apis' | 'spreadsheets';

interface ConnectorDef {
  key: string;
  name: string;
  description: string;
  category: ConnectorCategory;
  emoji: string;
  color: string;
  difficulty: 'Easy' | 'Medium' | 'Advanced';
  available: boolean;
}

const CONNECTORS: ConnectorDef[] = [
  { key: 'postgresql', name: 'PostgreSQL',   description: 'Open-source relational database',          category: 'databases',    emoji: '🐘', color: 'border-blue-500/30 bg-blue-500/5',     difficulty: 'Easy',     available: true },
  { key: 'mysql',      name: 'MySQL',         description: 'World\'s most popular open-source DB',     category: 'databases',    emoji: '🐬', color: 'border-orange-500/30 bg-orange-500/5', difficulty: 'Easy',     available: true },
  { key: 'sqlite',     name: 'SQLite',        description: 'Lightweight file-based database',          category: 'databases',    emoji: '📁', color: 'border-slate-500/30 bg-slate-500/5',  difficulty: 'Easy',     available: true },
  { key: 'sqlserver',  name: 'SQL Server',    description: 'Microsoft enterprise database',            category: 'databases',    emoji: '🪟', color: 'border-blue-400/30 bg-blue-400/5',    difficulty: 'Medium',   available: false },
  { key: 'mongodb',    name: 'MongoDB',       description: 'NoSQL document database',                  category: 'databases',    emoji: '🍃', color: 'border-emerald-500/30 bg-emerald-500/5', difficulty: 'Medium', available: false },
  { key: 'bigquery',   name: 'BigQuery',      description: 'Google Cloud serverless data warehouse',   category: 'warehouses',   emoji: '🔵', color: 'border-blue-400/30 bg-blue-400/5',    difficulty: 'Advanced', available: false },
  { key: 'snowflake',  name: 'Snowflake',     description: 'Cloud data platform',                      category: 'warehouses',   emoji: '❄️', color: 'border-cyan-500/30 bg-cyan-500/5',    difficulty: 'Advanced', available: false },
  { key: 'databricks', name: 'Databricks',    description: 'Unified analytics platform',               category: 'warehouses',   emoji: '⚡', color: 'border-red-500/30 bg-red-500/5',      difficulty: 'Advanced', available: false },
  { key: 'redshift',   name: 'Redshift',      description: 'AWS cloud data warehouse',                 category: 'warehouses',   emoji: '🔴', color: 'border-red-400/30 bg-red-400/5',      difficulty: 'Advanced', available: false },
  { key: 's3',         name: 'AWS S3',        description: 'Amazon object storage',                    category: 'cloud',        emoji: '🪣', color: 'border-amber-500/30 bg-amber-500/5',  difficulty: 'Medium',   available: false },
  { key: 'gsheets',    name: 'Google Sheets', description: 'Real-time spreadsheet collaboration',      category: 'spreadsheets', emoji: '📊', color: 'border-emerald-400/30 bg-emerald-400/5', difficulty: 'Easy', available: false },
  { key: 'excel',      name: 'Excel Online',  description: 'Microsoft 365 spreadsheets',               category: 'spreadsheets', emoji: '📗', color: 'border-green-500/30 bg-green-500/5',  difficulty: 'Easy',     available: false },
  { key: 'rest',       name: 'REST API',      description: 'Connect any HTTP/REST endpoint',           category: 'apis',         emoji: '🌐', color: 'border-violet-500/30 bg-violet-500/5', difficulty: 'Medium',  available: false },
  { key: 'webhook',    name: 'Webhook',       description: 'Receive real-time data pushes',            category: 'apis',         emoji: '🔗', color: 'border-indigo-500/30 bg-indigo-500/5', difficulty: 'Medium',  available: false },
];

const CATEGORIES: { key: ConnectorCategory; label: string }[] = [
  { key: 'all',         label: 'All'          },
  { key: 'databases',   label: 'Databases'    },
  { key: 'warehouses',  label: 'Data Warehouses' },
  { key: 'cloud',       label: 'Cloud Storage' },
  { key: 'spreadsheets',label: 'Spreadsheets' },
  { key: 'apis',        label: 'APIs'         },
];

const TYPE_DEFAULTS: Record<string, { port: number; placeholder: string }> = {
  postgresql: { port: 5432, placeholder: 'your_database' },
  mysql:      { port: 3306, placeholder: 'your_database' },
  sqlite:     { port: 0,    placeholder: '/path/to/file.db' },
};

const DIFFICULTY_COLORS: Record<string, string> = {
  Easy:     'text-emerald-400 bg-emerald-500/10',
  Medium:   'text-amber-400 bg-amber-500/10',
  Advanced: 'text-red-400 bg-red-500/10',
};

// ── Wizard state ──────────────────────────────────────────────────────────────

type WizardStep = 'credentials' | 'testing' | 'preview' | 'done';

// ── Main component ────────────────────────────────────────────────────────────

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<ConnectorCategory>('all');

  // wizard
  const [wizard, setWizard] = useState<ConnectorDef | null>(null);
  const [wizardStep, setWizardStep] = useState<WizardStep>('credentials');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '', host: '', port: 5432, database: '',
    username: '', password: '', schema_name: '',
  });

  // active connection panels
  const [expanded, setExpanded] = useState<string | null>(null);
  const [tables, setTables] = useState<Record<string, string[]>>({});
  const [testingConn, setTestingConn] = useState<string | null>(null);
  const [queryMode, setQueryMode] = useState<string | null>(null);
  const [sql, setSql] = useState('SELECT * FROM your_table LIMIT 100');
  const [queryResult, setQueryResult] = useState<any>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('/api/connections/');
      setConnections(res.data);
    } catch { toast.error('Failed to load connections'); }
    finally { setLoading(false); }
  }

  // ── Wizard actions ──

  function openWizard(connector: ConnectorDef) {
    if (!connector.available) { toast.info(`${connector.name} connector coming soon!`); return; }
    setWizard(connector);
    setWizardStep('credentials');
    setTestResult(null);
    setCreatedId(null);
    setForm({ name: `My ${connector.name}`, host: 'localhost', port: TYPE_DEFAULTS[connector.key]?.port || 0, database: '', username: '', password: '', schema_name: '' });
  }

  async function wizardCreate() {
    if (!form.name || !form.database) { toast.error('Name and database are required'); return; }
    setWizardStep('testing');
    setTesting(true);
    try {
      const res = await api.post('/api/connections/', {
        name: form.name,
        connection_type: wizard!.key,
        host: form.host || undefined,
        port: form.port || undefined,
        database: form.database,
        username: form.username || undefined,
        password: form.password || undefined,
        schema_name: form.schema_name || undefined,
      });
      const id = res.data.id;
      setCreatedId(id);
      // test it
      const testRes = await api.post(`/api/connections/${id}/test`);
      setTestResult({ success: testRes.data.success, message: testRes.data.version || testRes.data.message || '' });
      setWizardStep('preview');
      await load();
    } catch (err: any) {
      setTestResult({ success: false, message: err.response?.data?.detail || 'Connection failed' });
      setWizardStep('preview');
    } finally { setTesting(false); }
  }

  function closeWizard() { setWizard(null); setWizardStep('credentials'); setTestResult(null); }

  // ── Active connection actions ──

  async function testConn(id: string) {
    setTestingConn(id);
    try {
      const res = await api.post(`/api/connections/${id}/test`);
      if (res.data.success) toast.success(`Connected! ${res.data.version || ''}`);
      else toast.error(`Failed: ${res.data.message}`);
      await load();
    } catch { toast.error('Test failed'); }
    finally { setTestingConn(null); }
  }

  async function loadTables(id: string) {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    if (tables[id]) return;
    try {
      const res = await api.get(`/api/connections/${id}/tables`);
      setTables(prev => ({ ...prev, [id]: res.data.tables }));
    } catch { toast.error('Failed to load tables'); }
  }

  async function runQuery(id: string) {
    if (!sql.trim()) return toast.error('Enter a SQL query');
    setQueryLoading(true); setQueryResult(null);
    try {
      const res = await api.post(`/api/connections/${id}/query`, { sql, max_rows: 500 });
      setQueryResult(res.data);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Query failed');
    } finally { setQueryLoading(false); }
  }

  async function importDataset(id: string) {
    if (!sql.trim()) return toast.error('Enter a SQL query');
    const name = prompt('Dataset name for import:');
    if (!name) return;
    try {
      const res = await api.post(`/api/connections/${id}/import`, { sql, dataset_name: name });
      toast.success(`Imported ${res.data.row_count} rows as "${name}"`);
      setQueryMode(null);
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Import failed'); }
  }

  async function deleteConn(id: string) {
    if (!confirm('Delete this connection?')) return;
    try {
      await api.delete(`/api/connections/${id}`);
      setConnections(prev => prev.filter(c => c.id !== id));
      toast.success('Connection deleted');
    } catch { toast.error('Failed to delete'); }
  }

  const visibleConnectors = category === 'all' ? CONNECTORS : CONNECTORS.filter(c => c.category === category);
  const connectedKeys = new Set(connections.map(c => c.connection_type));

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-10">

        {/* ── Header ── */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Server className="w-6 h-6 text-cyan-400" />
              Data Connectors & Integrations
            </h1>
            <p className="text-slate-400 mt-1">Connect your data sources for instant AI analysis. No exports needed.</p>
          </div>
        </div>

        {/* ── Active Connections ── */}
        {loading ? (
          <div className="space-y-3">{[1, 2].map(i => <div key={i} className="glass rounded-xl h-20 animate-pulse" />)}</div>
        ) : connections.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Connected Sources ({connections.length})
            </h2>
            <div className="space-y-3">
              {connections.map(conn => {
                const def = CONNECTORS.find(c => c.key === conn.connection_type);
                return (
                  <motion.div key={conn.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass rounded-xl overflow-hidden">
                    <div className="p-4 flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl border flex items-center justify-center text-xl flex-shrink-0 ${def?.color || 'border-white/10 bg-white/5'}`}>
                        {def?.emoji || '🗄️'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-white">{conn.name}</p>
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Active</span>
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {conn.connection_type}{conn.host ? ` · ${conn.host}:${conn.port}` : ''} · {conn.database}
                          {conn.last_synced && ` · Tested ${new Date(conn.last_synced).toLocaleDateString()}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={() => testConn(conn.id)} disabled={testingConn === conn.id} title="Test" className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-400/10 transition-colors disabled:opacity-40">
                          {testingConn === conn.id ? <RefreshCw className="w-4 h-4 animate-spin" /> : <TestTube2 className="w-4 h-4" />}
                        </button>
                        <button onClick={() => loadTables(conn.id)} title="Browse tables" className="p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-cyan-400/10 transition-colors">
                          <Table2 className="w-4 h-4" />
                        </button>
                        <button onClick={() => setQueryMode(queryMode === conn.id ? null : conn.id)} title="Run query" className="p-2 rounded-lg text-slate-400 hover:text-violet-400 hover:bg-violet-400/10 transition-colors">
                          <Play className="w-4 h-4" />
                        </button>
                        <button onClick={() => deleteConn(conn.id)} title="Delete" className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    <AnimatePresence>
                      {expanded === conn.id && (
                        <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                          className="overflow-hidden border-t border-white/5 bg-black/20 px-4 py-3">
                          <p className="text-xs text-slate-500 mb-2 font-medium">Tables ({tables[conn.id]?.length ?? '…'})</p>
                          <div className="flex flex-wrap gap-2">
                            {(tables[conn.id] || []).map(t => (
                              <span key={t} className="text-xs px-2 py-1 rounded-lg bg-white/5 text-slate-300 border border-white/5">{t}</span>
                            ))}
                            {!tables[conn.id] && <span className="text-xs text-slate-500">Loading…</span>}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <AnimatePresence>
                      {queryMode === conn.id && (
                        <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                          className="overflow-hidden border-t border-white/5 bg-black/20 p-4 space-y-3">
                          <p className="text-xs text-slate-500 font-medium">SQL Query</p>
                          <textarea value={sql} onChange={e => setSql(e.target.value)} rows={3}
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-violet-300 focus:outline-none focus:border-indigo-500 resize-none" />
                          <div className="flex items-center gap-2">
                            <button onClick={() => runQuery(conn.id)} disabled={queryLoading}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-500 hover:bg-violet-600 text-white text-xs font-medium transition-colors disabled:opacity-40">
                              {queryLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Run Query
                            </button>
                            <button onClick={() => importDataset(conn.id)}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium transition-colors">
                              <Upload className="w-3 h-3" /> Import as Dataset
                            </button>
                          </div>
                          {queryResult && (
                            <div className="overflow-x-auto max-h-64 overflow-y-auto rounded-xl border border-white/5">
                              <table className="w-full text-xs">
                                <thead className="sticky top-0 bg-black/60">
                                  <tr>{queryResult.columns.map((c: string) => (
                                    <th key={c} className="text-left px-3 py-2 text-slate-400 whitespace-nowrap border-b border-white/5">{c}</th>
                                  ))}</tr>
                                </thead>
                                <tbody>
                                  {queryResult.rows.slice(0, 50).map((row: any, i: number) => (
                                    <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                                      {queryResult.columns.map((c: string) => (
                                        <td key={c} className="px-3 py-1.5 text-slate-300 whitespace-nowrap">{String(row[c] ?? '')}</td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <p className="text-xs text-slate-500 px-3 py-2">{queryResult.row_count} total rows</p>
                            </div>
                          )}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Add Connector Section ── */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">Add Connector</h2>
            <div className="flex gap-1 bg-white/5 rounded-xl p-1">
              {CATEGORIES.map(cat => (
                <button
                  key={cat.key}
                  onClick={() => setCategory(cat.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    category === cat.key
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {visibleConnectors.map(connector => (
              <motion.button
                key={connector.key}
                onClick={() => openWizard(connector)}
                className={`text-left p-4 rounded-2xl border glass transition-all group relative ${connector.color} ${
                  connector.available ? 'hover:border-opacity-60 cursor-pointer' : 'opacity-60 cursor-not-allowed'
                }`}
                whileHover={connector.available ? { scale: 1.01 } : {}}
                whileTap={connector.available ? { scale: 0.99 } : {}}
              >
                {connectedKeys.has(connector.key) && (
                  <div className="absolute top-3 right-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  </div>
                )}
                {!connector.available && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-500/20 text-slate-400 border border-slate-500/20">Soon</span>
                  </div>
                )}
                <div className="text-2xl mb-2">{connector.emoji}</div>
                <div className="font-semibold text-white text-sm mb-0.5">{connector.name}</div>
                <div className="text-xs text-slate-400 mb-3 leading-snug">{connector.description}</div>
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${DIFFICULTY_COLORS[connector.difficulty]}`}>
                    {connector.difficulty}
                  </span>
                  {connector.available && (
                    <ChevronRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-white transition-colors" />
                  )}
                </div>
              </motion.button>
            ))}
          </div>
        </div>

        {/* ── Integrations ── */}
        <div>
          <h2 className="text-sm font-semibold text-white mb-4">Integrations</h2>
          <div className="grid grid-cols-4 gap-4">
            {[
              { icon: MessageSquare, name: 'Slack',           desc: 'Send insights to your Slack workspace',        color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
              { icon: Globe,         name: 'Microsoft Teams', desc: 'Get AI analysis updates in Teams channels',    color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/20'    },
              { icon: Mail,          name: 'Email',           desc: 'Schedule automated reports to stakeholders',   color: 'text-violet-400',  bg: 'bg-violet-500/10 border-violet-500/20' },
              { icon: Webhook,       name: 'Webhook',         desc: 'Connect to any system via webhooks',           color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20'  },
            ].map(item => {
              const Icon = item.icon;
              return (
                <div key={item.name} className={`glass rounded-2xl p-4 border ${item.bg} cursor-pointer hover:opacity-90 transition-opacity`}>
                  <div className={`w-8 h-8 rounded-xl ${item.bg} border flex items-center justify-center mb-3`}>
                    <Icon className={`w-4 h-4 ${item.color}`} />
                  </div>
                  <div className="font-medium text-white text-sm mb-1">{item.name}</div>
                  <div className="text-[11px] text-slate-400 leading-snug mb-3">{item.desc}</div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-500/20 text-slate-400 border border-slate-500/20">Coming Soon</span>
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* ── Connection Wizard Modal ── */}
      <AnimatePresence>
        {wizard && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={e => { if (e.target === e.currentTarget) closeWizard(); }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass rounded-2xl w-full max-w-lg border border-white/10 overflow-hidden"
            >
              {/* Wizard header */}
              <div className={`px-6 py-4 border-b border-white/5 flex items-center gap-3 ${wizard.color}`}>
                <span className="text-2xl">{wizard.emoji}</span>
                <div className="flex-1">
                  <h2 className="text-base font-bold text-white">Connect {wizard.name}</h2>
                  <p className="text-xs text-slate-400">{wizard.description}</p>
                </div>
                <button onClick={closeWizard} className="text-slate-400 hover:text-white transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Step indicator */}
              <div className="px-6 pt-4 flex items-center gap-2">
                {(['credentials', 'testing', 'preview'] as WizardStep[]).map((step, i) => {
                  const stepLabels: Record<WizardStep, string> = { credentials: 'Credentials', testing: 'Testing', preview: 'Preview', done: 'Done' };
                  const isDone = wizardStep === 'preview' && i < 2;
                  const isCurrent = wizardStep === step;
                  return (
                    <div key={step} className="flex items-center gap-2 flex-1">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
                        isDone ? 'bg-emerald-500 text-white' : isCurrent ? 'bg-indigo-500 text-white' : 'bg-white/10 text-slate-500'
                      }`}>
                        {isDone ? <Check className="w-3 h-3" /> : i + 1}
                      </div>
                      <span className={`text-xs ${isCurrent ? 'text-white' : 'text-slate-500'}`}>{stepLabels[step]}</span>
                      {i < 2 && <div className="flex-1 h-px bg-white/10" />}
                    </div>
                  );
                })}
              </div>

              {/* Wizard body */}
              <div className="px-6 py-5">
                {wizardStep === 'credentials' && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="col-span-2">
                        <label className="text-xs text-slate-400 mb-1 block">Connection Name *</label>
                        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                      </div>
                      {wizard.key !== 'sqlite' && (
                        <>
                          <div>
                            <label className="text-xs text-slate-400 mb-1 block">Host</label>
                            <input value={form.host} onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
                              placeholder="localhost"
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                          </div>
                          <div>
                            <label className="text-xs text-slate-400 mb-1 block">Port</label>
                            <input type="number" value={form.port} onChange={e => setForm(f => ({ ...f, port: parseInt(e.target.value) || 0 }))}
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
                          </div>
                        </>
                      )}
                      <div className={wizard.key !== 'sqlite' ? '' : 'col-span-2'}>
                        <label className="text-xs text-slate-400 mb-1 block">{wizard.key === 'sqlite' ? 'File Path *' : 'Database *'}</label>
                        <input value={form.database} onChange={e => setForm(f => ({ ...f, database: e.target.value }))}
                          placeholder={TYPE_DEFAULTS[wizard.key]?.placeholder || 'database_name'}
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                      </div>
                      {wizard.key !== 'sqlite' && (
                        <>
                          <div>
                            <label className="text-xs text-slate-400 mb-1 block">Username</label>
                            <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                              placeholder="db_user"
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                          </div>
                          <div>
                            <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1"><Lock className="w-3 h-3" /> Password</label>
                            <input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                              placeholder="••••••••"
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
                          </div>
                        </>
                      )}
                    </div>
                    <button onClick={wizardCreate}
                      className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors">
                      Test & Connect <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                )}

                {wizardStep === 'testing' && (
                  <div className="py-8 flex flex-col items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center">
                      <Loader2 className="w-7 h-7 text-indigo-400 animate-spin" />
                    </div>
                    <div className="text-center">
                      <p className="text-white font-medium">Connecting to {wizard.name}…</p>
                      <p className="text-xs text-slate-400 mt-1">Saving credentials and testing connection</p>
                    </div>
                  </div>
                )}

                {wizardStep === 'preview' && testResult && (
                  <div className="space-y-4">
                    {/* Result banner */}
                    <div className={`rounded-xl p-4 border flex items-start gap-3 ${
                      testResult.success
                        ? 'bg-emerald-500/10 border-emerald-500/30'
                        : 'bg-red-500/10 border-red-500/30'
                    }`}>
                      {testResult.success
                        ? <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                        : <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                      }
                      <div>
                        <p className={`text-sm font-semibold ${testResult.success ? 'text-emerald-300' : 'text-red-300'}`}>
                          {testResult.success ? 'Connection Successful!' : 'Connection Failed'}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">{testResult.message || (testResult.success ? 'Database is reachable and credentials verified.' : 'Check your credentials and try again.')}</p>
                      </div>
                    </div>

                    {testResult.success ? (
                      <div className="space-y-3">
                        <p className="text-xs text-slate-400">Your connection is ready. You can now import data or query it directly from the agent.</p>
                        <div className="flex gap-2">
                          <button
                            onClick={closeWizard}
                            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium transition-colors text-sm"
                          >
                            <Check className="w-4 h-4" /> Done
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <button onClick={() => setWizardStep('credentials')} className="flex-1 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white text-sm font-medium transition-colors">
                          Edit Credentials
                        </button>
                        <button onClick={closeWizard} className="py-2.5 px-4 rounded-xl text-slate-400 hover:text-white text-sm transition-colors">
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AppLayout>
  );
}
