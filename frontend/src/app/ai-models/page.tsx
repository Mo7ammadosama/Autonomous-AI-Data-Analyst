'use client';

import { useState, useEffect } from 'react';
import AppLayout from '@/components/layout/AppLayout';
import { Sparkles, CheckCircle2, XCircle, Zap, DollarSign, RefreshCw, Play } from 'lucide-react';
import { toast } from 'sonner';
import { aiModelsApi } from '@/lib/api';

interface ModelStatus {
  key: string;
  name: string;
  provider: string;
  model_id: string;
  cost_per_1k_tokens: number;
  max_context: number;
  strengths: string[];
  api_key_configured: boolean;
  circuit_breaker_open: boolean;
  healthy: boolean;
}

interface UsageSummary {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  by_model: Record<string, { calls: number; tokens: number; cost_usd: number; provider: string }>;
}

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  anthropic: 'bg-orange-500/10 text-orange-300 border-orange-500/20',
  google: 'bg-blue-500/10 text-blue-300 border-blue-500/20',
  ollama: 'bg-purple-500/10 text-purple-300 border-purple-500/20',
};

export default function AIModelsPage() {
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [testModelKey, setTestModelKey] = useState('');
  const [testPrompt, setTestPrompt] = useState('Explain what a neural network is in one sentence.');
  const [testResult, setTestResult] = useState<{ response: string; latency_ms: number; success: boolean } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [modelsRes, usageRes] = await Promise.all([
        aiModelsApi.list(),
        aiModelsApi.usage(30),
      ]);
      setModels(modelsRes.data.models || []);
      setUsage(usageRes.data);
    } catch (e) {
      toast.error('Failed to load AI models data');
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    if (!testModelKey) { toast.error('Select a model first'); return; }
    if (!testPrompt.trim()) { toast.error('Enter a test prompt'); return; }
    setTesting(true);
    setTestResult(null);
    try {
      const res = await aiModelsApi.testModel(testModelKey, testPrompt);
      setTestResult(res.data);
      if (!res.data.success) toast.warning('Model responded with an error');
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const healthyCount = models.filter(m => m.healthy).length;

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-indigo-400" />
              AI Models
            </h1>
            <p className="text-slate-400 mt-1">Multi-model AI engine — intelligent routing across OpenAI, Anthropic Claude, and Google Gemini</p>
          </div>
          <button onClick={fetchData} className="flex items-center gap-2 px-4 py-2 rounded-xl glass glass-hover text-slate-300 text-sm">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="glass rounded-2xl p-5">
            <div className="text-slate-400 text-sm mb-1">Healthy Models</div>
            <div className="text-2xl font-bold text-white">{healthyCount} / {models.length}</div>
          </div>
          <div className="glass rounded-2xl p-5">
            <div className="text-slate-400 text-sm mb-1">Total API Calls (30d)</div>
            <div className="text-2xl font-bold text-white">{usage?.total_calls?.toLocaleString() || '0'}</div>
          </div>
          <div className="glass rounded-2xl p-5">
            <div className="text-slate-400 text-sm mb-1">Estimated Cost (30d)</div>
            <div className="text-2xl font-bold text-emerald-400">${usage?.total_cost_usd?.toFixed(4) || '0.0000'}</div>
          </div>
        </div>

        {/* Model Grid */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Available Models</h2>
          {loading ? (
            <div className="grid grid-cols-2 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="glass rounded-2xl p-5 h-40 animate-pulse" />)}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {models.map(model => (
                <div key={model.key} className={`glass rounded-2xl p-5 border ${model.healthy ? 'border-white/5' : 'border-red-500/20'}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-white">{model.name}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">{model.model_id}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${PROVIDER_COLORS[model.provider] || 'bg-slate-700 text-slate-300'}`}>
                        {model.provider}
                      </span>
                      {model.healthy
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        : <XCircle className="w-4 h-4 text-red-400" />
                      }
                    </div>
                  </div>
                  <div className="flex gap-4 text-xs text-slate-400 mb-3">
                    <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />${model.cost_per_1k_tokens}/1k tokens</span>
                    <span className="flex items-center gap-1"><Zap className="w-3 h-3" />{(model.max_context / 1000).toFixed(0)}k ctx</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {model.strengths.map(s => (
                      <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300">{s}</span>
                    ))}
                  </div>
                  {!model.api_key_configured && (
                    <p className="text-xs text-amber-400 mt-2">⚠ API key not configured</p>
                  )}
                  {model.circuit_breaker_open && (
                    <p className="text-xs text-red-400 mt-2">⛔ Circuit breaker open (cooling down)</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Model Tester */}
        <div className="glass rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Play className="w-5 h-5 text-indigo-400" />
            Test a Model
          </h2>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Select Model</label>
              <select
                value={testModelKey}
                onChange={e => setTestModelKey(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">— Choose a model —</option>
                {models.map(m => (
                  <option key={m.key} value={m.key} disabled={!m.api_key_configured}>
                    {m.name} ({m.provider}){!m.api_key_configured ? ' — key not configured' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Test Prompt</label>
              <textarea
                value={testPrompt}
                onChange={e => setTestPrompt(e.target.value)}
                rows={3}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none"
              />
            </div>
            <button
              onClick={handleTest}
              disabled={testing || !testModelKey}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {testing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {testing ? 'Testing…' : 'Run Test'}
            </button>
            {testResult && (
              <div className={`rounded-xl p-4 text-sm ${testResult.success ? 'bg-emerald-500/5 border border-emerald-500/20' : 'bg-red-500/5 border border-red-500/20'}`}>
                <div className="flex justify-between text-xs text-slate-400 mb-2">
                  <span>{testResult.success ? '✓ Success' : '✗ Failed'}</span>
                  <span>{testResult.latency_ms}ms</span>
                </div>
                <p className="text-slate-200 whitespace-pre-wrap">{testResult.response}</p>
              </div>
            )}
          </div>
        </div>

        {/* Usage by Model */}
        {usage && Object.keys(usage.by_model).length > 0 && (
          <div className="glass rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Usage by Model (Last 30 Days)</h2>
            <div className="space-y-3">
              {Object.entries(usage.by_model).map(([model, stats]) => (
                <div key={model} className="flex items-center gap-4 text-sm">
                  <span className="text-slate-200 w-32 truncate font-medium">{model}</span>
                  <span className="text-slate-400">{stats.calls} calls</span>
                  <span className="text-slate-400">{stats.tokens.toLocaleString()} tokens</span>
                  <span className="text-emerald-400 ml-auto">${stats.cost_usd.toFixed(5)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
