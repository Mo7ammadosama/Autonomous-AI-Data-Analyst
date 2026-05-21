'use client';

import { useState, useEffect } from 'react';
import { webhooksApi } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';
import AppLayout from '@/components/layout/AppLayout';
import { Webhook, Plus, Trash2, Play, CheckCircle, XCircle, AlertCircle, RefreshCw, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';

interface WebhookItem {
  id: string;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  failure_count: number;
  last_triggered_at: string | null;
  created_at: string;
}

const ALL_EVENTS = ['alert.triggered', 'report.sent', 'dataset.uploaded', 'insight.ready', 'pipeline.complete'];

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({});
  const [form, setForm] = useState({ name: '', url: '', events: [] as string[], secret: '' });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await webhooksApi.list();
      setWebhooks(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!form.name || !form.url || form.events.length === 0) return;
    setSaving(true);
    try {
      await webhooksApi.create({ name: form.name, url: form.url, events: form.events, secret: form.secret || undefined });
      setForm({ name: '', url: '', events: [], secret: '' });
      setShowCreate(false);
      load();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this webhook?')) return;
    await webhooksApi.delete(id);
    load();
  };

  const handleToggle = async (wh: WebhookItem) => {
    await webhooksApi.update(wh.id, { is_active: !wh.is_active });
    load();
  };

  const handleTest = async (id: string) => {
    try {
      const res = await webhooksApi.test(id);
      setTestResults((prev) => ({ ...prev, [id]: res.data }));
      setTimeout(() => setTestResults((prev) => { const n = { ...prev }; delete n[id]; return n; }), 5000);
    } catch (e) {
      console.error(e);
    }
  };

  const toggleEvent = (ev: string) => {
    setForm((f) => ({
      ...f,
      events: f.events.includes(ev) ? f.events.filter((e) => e !== ev) : [...f.events, ev],
    }));
  };

  return (
    <AppLayout>
    <div className="p-6 space-y-6 max-w-5xl">
      <PageHeader
        title="Webhooks"
        description="Receive HTTP callbacks when platform events occur"
        icon={<Webhook className="w-6 h-6" />}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-2 text-sm">
            <Plus className="w-4 h-4" /> Add Webhook
          </button>
        }
      />

      {/* Create form */}
      {showCreate && (
        <div className="glass rounded-xl p-6 border border-indigo-500/20 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200">New Webhook</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Name</label>
              <input
                className="input w-full"
                placeholder="My webhook"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">URL</label>
              <input
                className="input w-full"
                placeholder="https://example.com/hook"
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-2">Events</label>
            <div className="flex flex-wrap gap-2">
              {ALL_EVENTS.map((ev) => (
                <button
                  key={ev}
                  onClick={() => toggleEvent(ev)}
                  className={cn(
                    'text-xs px-3 py-1 rounded-full border transition-all',
                    form.events.includes(ev)
                      ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                      : 'border-white/10 text-slate-400 hover:border-white/20'
                  )}
                >
                  {ev}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Secret (optional)</label>
            <input
              className="input w-full font-mono text-sm"
              placeholder="Auto-generated if blank"
              value={form.secret}
              onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
            />
          </div>
          <div className="flex gap-3">
            <button onClick={handleCreate} disabled={saving} className="btn-primary text-sm">
              {saving ? 'Creating…' : 'Create Webhook'}
            </button>
            <button onClick={() => setShowCreate(false)} className="btn-ghost text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Webhooks list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="glass rounded-xl p-4 h-20 animate-pulse" />)}
        </div>
      ) : webhooks.length === 0 ? (
        <div className="glass rounded-xl p-12 text-center">
          <Webhook className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No webhooks configured yet.</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm mt-4">Add your first webhook</button>
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map((wh) => (
            <div key={wh.id} className="glass rounded-xl p-4 border border-white/5">
              <div className="flex items-start gap-4">
                <div className={cn('mt-0.5 w-2 h-2 rounded-full flex-shrink-0', wh.is_active ? 'bg-emerald-400' : 'bg-slate-600')} style={{ marginTop: 6 }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-200">{wh.name}</span>
                    {wh.failure_count > 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-400">
                        {wh.failure_count} failures
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <a href={wh.url} target="_blank" rel="noreferrer" className="text-xs text-slate-500 hover:text-indigo-400 transition-colors truncate max-w-xs">
                      {wh.url}
                    </a>
                    <ExternalLink className="w-3 h-3 text-slate-600 flex-shrink-0" />
                  </div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {wh.events.map((ev) => (
                      <span key={ev} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400">{ev}</span>
                    ))}
                  </div>
                  {wh.last_triggered_at && (
                    <p className="text-xs text-slate-600 mt-1">
                      Last triggered {formatDistanceToNow(new Date(wh.last_triggered_at), { addSuffix: true })}
                    </p>
                  )}
                  {testResults[wh.id] && (
                    <div className={cn('mt-2 text-xs flex items-center gap-1', testResults[wh.id].success ? 'text-emerald-400' : 'text-red-400')}>
                      {testResults[wh.id].success ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      {testResults[wh.id].message}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button onClick={() => handleTest(wh.id)} title="Send test" className="btn-ghost p-1.5 text-slate-400 hover:text-indigo-400">
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => handleToggle(wh)} title={wh.is_active ? 'Disable' : 'Enable'} className="btn-ghost p-1.5 text-slate-400 hover:text-amber-400">
                    {wh.is_active ? <AlertCircle className="w-3.5 h-3.5" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  </button>
                  <button onClick={() => handleDelete(wh.id)} title="Delete" className="btn-ghost p-1.5 text-slate-400 hover:text-red-400">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    </AppLayout>
  );
}
