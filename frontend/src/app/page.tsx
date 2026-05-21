'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence, useScroll, useTransform } from 'framer-motion';
import {
  Brain, BarChart3, Sparkles, ArrowRight, Lock, Mail, User, Zap, Database,
  TrendingUp, Check, X, ChevronRight, Shield, Clock, DollarSign,
  Bot, Search, FileText, Bell, Server, Code2, Layers, Play,
  Star, Building2, Users, Target, Activity
} from 'lucide-react';
import { useAuthStore } from '@/lib/store';

// ── Floating data particle component ────────────────────────────────────────
function DataParticle({ x, y, delay }: { x: number; y: number; delay: number }) {
  return (
    <motion.div
      className="absolute w-1 h-1 rounded-full bg-indigo-400/30"
      style={{ left: `${x}%`, top: `${y}%` }}
      animate={{ y: [0, -30, 0], opacity: [0.3, 0.8, 0.3] }}
      transition={{ duration: 4 + delay, repeat: Infinity, delay }}
    />
  );
}

// ── Comparison table data ─────────────────────────────────────────────────
const comparisonRows = [
  { feature: 'Multi-LLM simultaneous routing',   dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'AutoML model training',             dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'Root Cause Analysis',               dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'What-If Scenario Engine',           dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'Domain Templates (4 industries)',   dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'Proactive Anomaly Detection',       dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'Persistent Agent Memory',           dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'Native Arabic Support',             dm: true,  julius: false, gpt: false, gemini: false },
  { feature: 'File size limit',                   dm: 'Unlimited', julius: '32GB', gpt: '512MB', gemini: '50MB' },
];

// ── Feature cards ─────────────────────────────────────────────────────────
const features = [
  {
    icon: Bot,
    title: 'Autonomous AI Agent',
    desc: 'ReAct loop with 15 tools and persistent memory. Replaces a full analyst.',
    color: 'from-indigo-500 to-violet-600',
    glow: 'group-hover:shadow-indigo-500/25',
  },
  {
    icon: Code2,
    title: 'Natural Language SQL',
    desc: 'English or Arabic → instant SQL with SELECT-safe execution.',
    color: 'from-violet-500 to-purple-600',
    glow: 'group-hover:shadow-violet-500/25',
  },
  {
    icon: Brain,
    title: 'AutoML Pipeline',
    desc: 'Train predictive models without writing a single line of code.',
    color: 'from-cyan-500 to-blue-600',
    glow: 'group-hover:shadow-cyan-500/25',
  },
  {
    icon: Zap,
    title: 'Proactive Intelligence',
    desc: 'Anomalies detected and flagged before you even ask the question.',
    color: 'from-amber-500 to-orange-600',
    glow: 'group-hover:shadow-amber-500/25',
  },
  {
    icon: Layers,
    title: 'Domain Templates',
    desc: '20+ pre-built Finance, Healthcare, Retail, and HR analyses.',
    color: 'from-emerald-500 to-teal-600',
    glow: 'group-hover:shadow-emerald-500/25',
  },
  {
    icon: Server,
    title: 'Multi-Source Connectors',
    desc: 'PostgreSQL, BigQuery, Snowflake, S3, and REST APIs.',
    color: 'from-rose-500 to-pink-600',
    glow: 'group-hover:shadow-rose-500/25',
  },
  {
    icon: FileText,
    title: 'Executive PDF Reports',
    desc: 'Board-ready, McKinsey-style reports generated in seconds.',
    color: 'from-indigo-500 to-cyan-600',
    glow: 'group-hover:shadow-indigo-500/25',
  },
  {
    icon: Bell,
    title: 'Real-Time Alerts',
    desc: 'Slack, Email, and Teams threshold monitoring around the clock.',
    color: 'from-violet-500 to-indigo-600',
    glow: 'group-hover:shadow-violet-500/25',
  },
];

// ── Pricing tiers ─────────────────────────────────────────────────────────
const pricingTiers = [
  {
    name: 'Starter',
    price: '$99',
    period: '/mo',
    tagline: 'Replaces 1 analyst',
    savings: 'Save $120K/year',
    features: ['5 datasets', '50 AI analyses/mo', 'PDF reports', 'CSV & Excel export', 'Email alerts'],
    cta: 'Start Free Trial',
    highlight: false,
  },
  {
    name: 'Professional',
    price: '$299',
    period: '/mo',
    tagline: 'Replaces 2–3 analysts',
    savings: 'Save $360K/year',
    features: ['Unlimited datasets', '500 AI analyses/mo', 'AutoML + Forecasting', 'Slack & Teams alerts', 'Custom dashboards', 'NL2SQL + Root Cause'],
    cta: 'Start Free Trial',
    highlight: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    tagline: 'Full data team replacement',
    savings: 'Custom ROI analysis',
    features: ['Unlimited everything', 'Dedicated AI instance', 'SSO + RBAC', 'SLA 99.99%', 'White-label', 'Onboarding + training'],
    cta: 'Contact Sales',
    highlight: false,
  },
];

// ── Agent step animation data ─────────────────────────────────────────────
const demoSteps = [
  { num: 1, action: 'get_dataset_info',   badge: 'DATA',    color: 'bg-blue-500/20 text-blue-400',   text: '50K rows · 12 months · 5 regions' },
  { num: 2, action: 'execute_python',     badge: 'PYTHON',  color: 'bg-violet-500/20 text-violet-400', text: 'YoY growth per region computed' },
  { num: 3, action: 'auto_visualize',     badge: 'CHART',   color: 'bg-cyan-500/20 text-cyan-400',   text: 'Revenue trend line chart rendered' },
  { num: 4, action: 'root_cause',         badge: 'ANALYSIS',color: 'bg-orange-500/20 text-orange-400', text: 'Region B: -23% driver identified' },
  { num: 5, action: 'generate_action_plan', badge: 'PLAN',  color: 'bg-emerald-500/20 text-emerald-400', text: '30-60-90 day roadmap generated' },
  { num: 6, action: 'final_answer',       badge: 'REPORT',  color: 'bg-indigo-500/20 text-indigo-400', text: 'CEO Briefing + Risk Matrix ready' },
];

export default function LandingPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [activeStep, setActiveStep] = useState(0);
  const [showAuth, setShowAuth] = useState(false);
  const { login, register, demoLogin, isLoading, isAuthenticated, initialize } = useAuthStore();
  const router = useRouter();

  useEffect(() => { initialize(); }, [initialize]);
  useEffect(() => { if (isAuthenticated) router.push('/dashboard'); }, [isAuthenticated, router]);

  // Animate demo steps
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStep(s => (s + 1) % demoSteps.length);
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(email, username, password);
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Authentication failed');
    }
  };

  const handleDemo = async () => {
    setError('');
    try {
      await demoLogin();
    } catch {
      setError('Demo login failed. Is the backend running?');
    }
  };

  return (
    <div className="min-h-screen bg-[#080b14] text-white overflow-x-hidden">
      {/* ── Ambient background ───────────────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-indigo-600/8 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 right-1/4 w-[500px] h-[500px] bg-violet-600/8 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 left-1/3 w-[400px] h-[400px] bg-cyan-600/5 rounded-full blur-[100px]" />
        {/* Grid overlay */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{ backgroundImage: 'linear-gradient(rgba(99,102,241,1) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,1) 1px, transparent 1px)', backgroundSize: '60px 60px' }} />
        {/* Floating particles — fixed positions to avoid SSR/client hydration mismatch */}
        {[
          [71.5, 76.1], [23.4, 45.2], [88.7, 12.3], [5.6, 67.8], [45.3, 32.1],
          [62.1, 89.4], [15.8, 23.7], [78.9, 54.6], [33.2, 11.5], [91.4, 78.3],
          [48.7, 43.9], [7.3, 88.2], [55.6, 65.7], [82.4, 27.6], [19.1, 95.3],
          [66.8, 8.4],  [39.5, 72.1], [93.2, 41.8], [12.7, 58.4], [74.6, 33.9],
        ].map(([x, y], i) => (
          <DataParticle key={i} x={x} y={y} delay={i * 0.3} />
        ))}
      </div>

      {/* ── Navigation ───────────────────────────────────────────────── */}
      <nav className="relative z-50 flex items-center justify-between px-8 py-5 border-b border-white/5 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <span className="text-lg font-bold bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">DataMind AI</span>
          <span className="hidden sm:block text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 font-medium">Enterprise</span>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => setShowAuth(true)} className="text-sm text-slate-400 hover:text-white transition-colors">Sign In</button>
          <button
            onClick={() => setShowAuth(true)}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-sm font-semibold hover:from-indigo-500 hover:to-violet-500 transition-all shadow-lg shadow-indigo-500/25"
          >
            Start Free Trial
          </button>
        </div>
      </nav>

      {/* ── Hero Section ─────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-7xl mx-auto px-8 pt-24 pb-20">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Left: Copy */}
          <div>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium mb-6">
                <Sparkles className="w-3.5 h-3.5" />
                The AI Data Team That Never Sleeps
              </div>
              <h1 className="text-5xl lg:text-6xl font-bold leading-[1.08] mb-6">
                <span className="text-white">Your AI Data</span>
                <br />
                <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent">Team.</span>
                <br />
                <span className="text-white">Available 24/7.</span>
              </h1>
              <p className="text-slate-400 text-lg leading-relaxed mb-8 max-w-xl">
                DataMind AI analyzes data, finds insights, builds dashboards, and delivers executive reports — autonomously.
                Replace weeks of analyst work with minutes.
              </p>
              <div className="flex flex-wrap gap-3 mb-10">
                <motion.button
                  onClick={() => setShowAuth(true)}
                  className="px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold hover:from-indigo-500 hover:to-violet-500 transition-all shadow-xl shadow-indigo-500/30 flex items-center gap-2"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  Start Free Trial
                  <ArrowRight className="w-4 h-4" />
                </motion.button>
                <motion.button
                  onClick={handleDemo}
                  className="px-6 py-3 rounded-xl border border-white/10 text-white font-semibold hover:bg-white/5 transition-all flex items-center gap-2"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Play className="w-4 h-4 text-indigo-400" />
                  Watch 2-Min Demo
                </motion.button>
              </div>
            </motion.div>

            {/* Social proof */}
            <motion.div
              className="flex flex-wrap gap-6"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
            >
              {[
                { val: '500K+', label: 'Analyses run' },
                { val: '89%',   label: 'Faster than manual' },
                { val: '3.2x',  label: 'ROI vs hiring' },
              ].map(({ val, label }) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="text-2xl font-bold bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">{val}</span>
                  <span className="text-sm text-slate-500">{label}</span>
                </div>
              ))}
            </motion.div>
          </div>

          {/* Right: Live Agent Demo Panel */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="relative"
          >
            <div className="relative rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-sm overflow-hidden shadow-2xl">
              {/* Panel header */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5 bg-white/[0.02]">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
                </div>
                <div className="flex-1 flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
                    <Brain className="w-2.5 h-2.5 text-white" />
                  </div>
                  <span className="text-xs text-slate-400 font-medium">DataMind Agent — Analyzing Q4_Sales.csv</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs text-emerald-400">Live</span>
                </div>
              </div>

              {/* Progress bar */}
              <div className="px-4 pt-3 pb-1">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                  <span>Iteration {activeStep + 1} / {demoSteps.length}</span>
                  <span>{Math.round(((activeStep + 1) / demoSteps.length) * 100)}%</span>
                </div>
                <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                    animate={{ width: `${((activeStep + 1) / demoSteps.length) * 100}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>

              {/* Steps */}
              <div className="p-4 space-y-2.5 min-h-[280px]">
                {demoSteps.map((step, i) => (
                  <motion.div
                    key={step.num}
                    className={`flex items-start gap-3 rounded-xl p-3 transition-all duration-300 ${
                      i === activeStep ? 'bg-white/[0.06] border border-white/10' :
                      i < activeStep ? 'opacity-60' : 'opacity-20'
                    }`}
                    animate={{ opacity: i <= activeStep ? (i === activeStep ? 1 : 0.6) : 0.2 }}
                  >
                    <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      i < activeStep ? 'bg-emerald-500/20 text-emerald-400' :
                      i === activeStep ? 'bg-indigo-500/20 text-indigo-400' : 'bg-white/5 text-slate-600'
                    }`}>
                      {i < activeStep ? '✓' : step.num}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <code className="text-xs font-mono text-slate-300">{step.action}</code>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${step.color}`}>{step.badge}</span>
                      </div>
                      <p className="text-xs text-slate-500 truncate">{step.text}</p>
                    </div>
                    {i === activeStep && (
                      <motion.div
                        className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0 mt-1"
                        animate={{ opacity: [1, 0.3, 1] }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                      />
                    )}
                  </motion.div>
                ))}
              </div>

              {/* Bottom result preview */}
              <div className="mx-4 mb-4 p-3 rounded-xl bg-gradient-to-r from-indigo-500/10 to-violet-500/10 border border-indigo-500/20">
                <p className="text-xs text-indigo-300 font-semibold mb-1">CEO Briefing Preview</p>
                <p className="text-xs text-slate-400 leading-relaxed">
                  &quot;Q4 revenue $4.2M, +8% YoY. Region B is your crisis — inaction = $1.8M annualized loss.&quot;
                </p>
              </div>
            </div>

            {/* Floating badges */}
            <motion.div
              className="absolute -right-4 top-8 px-3 py-1.5 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 text-xs font-semibold shadow-xl"
              animate={{ y: [0, -6, 0] }}
              transition={{ duration: 3, repeat: Infinity }}
            >
              89% faster
            </motion.div>
            <motion.div
              className="absolute -left-4 bottom-16 px-3 py-1.5 rounded-xl bg-violet-500/20 border border-violet-500/30 text-violet-400 text-xs font-semibold shadow-xl"
              animate={{ y: [0, 6, 0] }}
              transition={{ duration: 3.5, repeat: Infinity }}
            >
              Saves $450K/yr
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── Social Proof Bar ──────────────────────────────────────────── */}
      <section className="relative z-10 border-y border-white/5 bg-white/[0.02] py-6">
        <div className="max-w-7xl mx-auto px-8 flex flex-wrap justify-center gap-8">
          {[
            { icon: Users,    val: '500K+',  label: 'Analyses completed' },
            { icon: Building2, val: '1,200+', label: 'Enterprise clients' },
            { icon: Clock,    val: '89%',    label: 'Faster than manual' },
            { icon: DollarSign, val: '3.2x', label: 'Average ROI' },
            { icon: Star,     val: '4.9/5',  label: 'Customer rating' },
          ].map(({ icon: Icon, val, label }) => (
            <div key={label} className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                <Icon className="w-4 h-4 text-indigo-400" />
              </div>
              <div>
                <div className="text-lg font-bold text-white">{val}</div>
                <div className="text-xs text-slate-500">{label}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Comparison Table ──────────────────────────────────────────── */}
      <section className="relative z-10 max-w-7xl mx-auto px-8 py-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-medium mb-4">
            <Target className="w-3.5 h-3.5" />
            Competitive Analysis
          </div>
          <h2 className="text-3xl font-bold text-white mb-3">Why DataMind Wins</h2>
          <p className="text-slate-400">The only platform purpose-built for enterprise autonomous data analysis.</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="overflow-hidden rounded-2xl border border-white/10"
        >
          <table className="w-full">
            <thead>
              <tr className="bg-white/[0.04] border-b border-white/10">
                <th className="text-left px-6 py-4 text-sm font-semibold text-slate-300">Feature</th>
                <th className="px-6 py-4 text-center">
                  <div className="flex flex-col items-center gap-1">
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
                      <Brain className="w-4 h-4 text-white" />
                    </div>
                    <span className="text-sm font-bold text-white">DataMind</span>
                  </div>
                </th>
                <th className="px-4 py-4 text-center text-sm font-medium text-slate-500">Julius AI</th>
                <th className="px-4 py-4 text-center text-sm font-medium text-slate-500">ChatGPT</th>
                <th className="px-4 py-4 text-center text-sm font-medium text-slate-500">Gemini</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row, i) => (
                <tr key={row.feature} className={`border-b border-white/5 ${i % 2 === 0 ? 'bg-white/[0.01]' : ''}`}>
                  <td className="px-6 py-3.5 text-sm text-slate-300">{row.feature}</td>
                  <td className="px-6 py-3.5 text-center">
                    {typeof row.dm === 'boolean' ? (
                      row.dm
                        ? <Check className="w-5 h-5 text-emerald-400 mx-auto" />
                        : <X className="w-4 h-4 text-red-500/60 mx-auto" />
                    ) : (
                      <span className="text-sm font-semibold text-emerald-400">{row.dm}</span>
                    )}
                  </td>
                  {['julius', 'gpt', 'gemini'].map(k => {
                    const val = row[k as 'julius' | 'gpt' | 'gemini'];
                    return (
                      <td key={k} className="px-4 py-3.5 text-center">
                        {typeof val === 'boolean' ? (
                          val
                            ? <Check className="w-5 h-5 text-emerald-400 mx-auto" />
                            : <X className="w-4 h-4 text-slate-600 mx-auto" />
                        ) : (
                          <span className="text-sm text-slate-500">{val}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      </section>

      {/* ── Features Grid ─────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-7xl mx-auto px-8 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-medium mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            Platform Capabilities
          </div>
          <h2 className="text-3xl font-bold text-white mb-3">Everything Your Data Team Does, Automated</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">
            One platform replaces your entire data analytics stack. No integrations. No delays. No headcount.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className={`group relative rounded-2xl border border-white/8 bg-white/[0.03] p-5 hover:bg-white/[0.06] transition-all hover:border-white/15 hover:shadow-xl ${f.glow}`}
            >
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-4 shadow-lg`}>
                <f.icon className="w-5 h-5 text-white" />
              </div>
              <h3 className="font-semibold text-white mb-2 text-sm">{f.title}</h3>
              <p className="text-xs text-slate-500 leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Pricing ───────────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-7xl mx-auto px-8 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium mb-4">
            <DollarSign className="w-3.5 h-3.5" />
            ROI-Framed Pricing
          </div>
          <h2 className="text-3xl font-bold text-white mb-3">Replace Analysts, Not Budgets</h2>
          <p className="text-slate-400">Every tier pays for itself in the first month.</p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6">
          {pricingTiers.map((tier, i) => (
            <motion.div
              key={tier.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className={`relative rounded-2xl border p-6 flex flex-col ${
                tier.highlight
                  ? 'border-indigo-500/50 bg-gradient-to-b from-indigo-500/10 to-violet-500/10 shadow-xl shadow-indigo-500/10'
                  : 'border-white/10 bg-white/[0.03]'
              }`}
            >
              {tier.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white text-xs font-bold shadow-lg">
                  Most Popular
                </div>
              )}
              <div className="mb-4">
                <div className="text-sm font-semibold text-slate-400 mb-1">{tier.name}</div>
                <div className="flex items-end gap-1 mb-1">
                  <span className="text-4xl font-bold text-white">{tier.price}</span>
                  <span className="text-slate-500 mb-1">{tier.period}</span>
                </div>
                <div className="text-xs text-slate-500">{tier.tagline}</div>
                <div className="mt-2 inline-block px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-semibold border border-emerald-500/20">
                  {tier.savings}
                </div>
              </div>
              <ul className="space-y-2.5 flex-1 mb-6">
                {tier.features.map(feat => (
                  <li key={feat} className="flex items-center gap-2.5 text-sm text-slate-300">
                    <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    {feat}
                  </li>
                ))}
              </ul>
              <motion.button
                onClick={() => setShowAuth(true)}
                className={`w-full py-2.5 rounded-xl font-semibold text-sm transition-all ${
                  tier.highlight
                    ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500 shadow-lg shadow-indigo-500/25'
                    : 'border border-white/10 text-white hover:bg-white/5'
                }`}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {tier.cta}
              </motion.button>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-white/5 py-10">
        <div className="max-w-7xl mx-auto px-8 flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-semibold text-white">DataMind AI</span>
          </div>
          <div className="flex flex-wrap gap-4">
            {['SOC 2', 'GDPR', 'HIPAA', 'ISO 27001'].map(badge => (
              <div key={badge} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-xs text-slate-400">
                <Shield className="w-3 h-3 text-emerald-400" />
                {badge}
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-600">© 2025 DataMind AI. Enterprise data analytics.</p>
        </div>
      </footer>

      {/* ── Auth Modal ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showAuth && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={(e) => { if (e.target === e.currentTarget) setShowAuth(false); }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="w-full max-w-sm"
            >
              <div className="rounded-2xl border border-white/10 bg-[#0d1117] shadow-2xl overflow-hidden">
                {/* Modal top gradient line */}
                <div className="h-1 bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-500" />
                <div className="p-8">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                      <Brain className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-white">
                        {mode === 'login' ? 'Welcome back' : 'Create account'}
                      </h2>
                      <p className="text-xs text-slate-500">
                        {mode === 'login' ? 'Sign in to your workspace' : 'Start analyzing your data'}
                      </p>
                    </div>
                  </div>

                  {/* Demo button */}
                  <motion.button
                    onClick={handleDemo}
                    disabled={isLoading}
                    className="w-full mb-4 py-2.5 px-4 rounded-xl border border-indigo-500/40 bg-indigo-500/10 text-indigo-300 text-sm font-medium hover:bg-indigo-500/20 transition-all flex items-center justify-center gap-2"
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                  >
                    <Zap className="w-4 h-4" />
                    Try Demo — No signup required
                  </motion.button>

                  <div className="flex items-center gap-3 mb-4">
                    <div className="flex-1 h-px bg-white/5" />
                    <span className="text-xs text-slate-600">or continue with email</span>
                    <div className="flex-1 h-px bg-white/5" />
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                        <input
                          type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                          placeholder="you@company.com" required
                          className="w-full bg-white/5 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500/50 focus:outline-none transition-all"
                        />
                      </div>
                    </div>
                    <AnimatePresence>
                      {mode === 'register' && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                          <label className="block text-xs font-medium text-slate-400 mb-1.5">Username</label>
                          <div className="relative">
                            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                            <input
                              type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                              placeholder="analyst_pro" required
                              className="w-full bg-white/5 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500/50 focus:outline-none transition-all"
                            />
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Password</label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                        <input
                          type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                          placeholder="••••••••" required
                          className="w-full bg-white/5 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500/50 focus:outline-none transition-all"
                        />
                      </div>
                    </div>
                    {error && (
                      <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
                        {error}
                      </motion.p>
                    )}
                    <motion.button
                      type="submit" disabled={isLoading}
                      className="w-full py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold text-sm hover:from-indigo-500 hover:to-violet-500 transition-all flex items-center justify-center gap-2 disabled:opacity-50 shadow-lg shadow-indigo-500/25"
                      whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                    >
                      {isLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : (
                        <>{mode === 'login' ? 'Sign In' : 'Create Account'}<ArrowRight className="w-4 h-4" /></>
                      )}
                    </motion.button>
                  </form>
                  <p className="text-center text-sm text-slate-500 mt-4">
                    {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
                    <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }} className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors">
                      {mode === 'login' ? 'Sign up' : 'Sign in'}
                    </button>
                  </p>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
