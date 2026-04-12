'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, LayoutDashboard, Database, MessageSquare, BarChart2,
  Lightbulb, PanelsTopLeft, FileText, Settings, LogOut, ChevronDown,
  TrendingUp, Cpu, GitCompare, Bell, Terminal, Server, Calendar,
  Activity, BarChart3, Webhook, Sparkles, SearchCode,
  Bot, LayoutTemplate, BookOpen, Zap, Users, GitPullRequest, Sliders,
  ShieldCheck, Sun, Moon, Search, X
} from 'lucide-react';
import { useAuthStore, ThemeAccent, ColorMode } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import NotificationsBell from '@/components/ui/NotificationsBell';
import { useState, useMemo } from 'react';

const QUICK_THEMES: { id: ThemeAccent; color: string }[] = [
  { id: 'indigo',  color: '#6366f1' },
  { id: 'violet',  color: '#8b5cf6' },
  { id: 'emerald', color: '#10b981' },
  { id: 'cyan',    color: '#06b6d4' },
  { id: 'rose',    color: '#f43f5e' },
  { id: 'amber',   color: '#f59e0b' },
];

type NavItem = {
  href: string;
  icon: React.ElementType;
  label: string;
  section: string;
  badge?: string;
  hero?: boolean;
  hidden?: boolean;
  requiredRole?: 'analyst' | 'admin' | 'superadmin';
};

const navItems: NavItem[] = [
  // ── AI Analysis ──────────────────────────────────────────────────────
  { href: '/agent',            icon: Sparkles,      label: 'AI Agent',          section: 'ai',       badge: 'AI', hero: true },
  { href: '/chat',             icon: MessageSquare, label: 'Chat with Data',    section: 'ai',       badge: 'AI' },
  { href: '/autonomous',       icon: Cpu,           label: 'Auto Analyst',      section: 'ai',       badge: 'AI' },
  { href: '/notebooks',        icon: BookOpen,      label: 'Notebooks',         section: 'ai',       badge: 'NEW' },
  // ── Insights ─────────────────────────────────────────────────────────
  { href: '/proactive',        icon: Zap,           label: 'Intelligence Feed', section: 'insights', badge: 'AI' },
  { href: '/forecasting',      icon: TrendingUp,    label: 'Forecasting',       section: 'insights', badge: 'AI' },
  { href: '/root-cause',       icon: SearchCode,    label: 'Root Cause',        section: 'insights', badge: 'AI' },
  { href: '/scenarios',        icon: Sliders,       label: 'What-If',           section: 'insights', badge: 'NEW' },
  { href: '/automl',           icon: Bot,           label: 'AutoML',            section: 'insights', badge: 'NEW' },
  // ── Build ────────────────────────────────────────────────────────────
  { href: '/dashboards',       icon: PanelsTopLeft, label: 'Dashboards',        section: 'build' },
  { href: '/custom-reports',   icon: FileText,      label: 'Custom Reports',    section: 'build',    badge: 'NEW' },
  { href: '/templates',        icon: LayoutTemplate,label: 'Templates',         section: 'build' },
  { href: '/alerts',           icon: Bell,          label: 'Alerts',            section: 'build' },
  // ── Data ─────────────────────────────────────────────────────────────
  { href: '/datasets',         icon: Database,      label: 'Datasets',          section: 'data' },
  { href: '/connections',      icon: Server,        label: 'Connections',       section: 'data' },
  { href: '/catalog',          icon: BookOpen,      label: 'Data Catalog',      section: 'data' },
  { href: '/nl2sql',           icon: Terminal,      label: 'SQL Query',         section: 'data' },
  // ── Settings ─────────────────────────────────────────────────────────
  { href: '/settings',         icon: Settings,      label: 'Settings',          section: 'settings' },
  { href: '/ai-models',        icon: Sparkles,      label: 'AI Models',         section: 'settings', badge: 'NEW' },
  { href: '/metrics',          icon: BarChart3,     label: 'Platform Metrics',  section: 'settings' },
  { href: '/admin',            icon: ShieldCheck,   label: 'Admin Panel',       section: 'settings', badge: 'SA', requiredRole: 'superadmin' },
];

const sections: { key: string; label: string; icon: React.ElementType }[] = [
  { key: 'ai',       label: 'AI Analysis', icon: Sparkles },
  { key: 'insights', label: 'Insights',    icon: Lightbulb },
  { key: 'build',    label: 'Build',       icon: PanelsTopLeft },
  { key: 'data',     label: 'Data',        icon: Database },
  { key: 'settings', label: 'Settings',   icon: Settings },
];

const ROLE_ORDER: Record<string, number> = { viewer: 0, analyst: 1, admin: 2, superadmin: 3 };

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout, theme, setTheme, colorMode, setColorMode } = useAuthStore();
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  const userLevel = ROLE_ORDER[user?.role ?? 'viewer'] ?? 0;
  const visibleItems = navItems.filter(item => {
    if (!item.requiredRole) return true;
    return userLevel >= (ROLE_ORDER[item.requiredRole] ?? 0);
  });

  const filteredItems = useMemo(() => {
    if (!search.trim()) return visibleItems;
    const q = search.toLowerCase();
    return visibleItems.filter(i => i.label.toLowerCase().includes(q));
  }, [visibleItems, search]);

  const grouped = filteredItems.reduce<Record<string, NavItem[]>>((acc, item) => {
    if (!acc[item.section]) acc[item.section] = [];
    acc[item.section].push(item);
    return acc;
  }, {});

  const toggleSection = (key: string) => {
    setCollapsed(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const isSearching = search.trim().length > 0;

  return (
    <aside className="animate-sidebar w-[200px] flex-shrink-0 h-screen flex flex-col border-r border-white/5 bg-black/20 backdrop-blur-xl">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-white/5">
        <Link href="/dashboard" className="flex items-center gap-2.5 group mb-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-shadow flex-shrink-0">
            <Brain className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-display font-bold text-white text-sm leading-tight">DataMind AI</div>
            <div className="text-[10px] text-slate-500 leading-tight truncate">{user?.email?.split('@')[1] || 'Workspace'}</div>
          </div>
        </Link>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gradient-to-r from-indigo-500/20 to-violet-500/20 text-indigo-300 border border-indigo-500/20 font-semibold">Pro</span>
          <span className="text-[10px] text-slate-600">Your AI Data Team</span>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-white/5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search..."
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-7 pr-7 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 focus:bg-white/8 transition-all"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2">
              <X className="w-3 h-3 text-slate-500 hover:text-slate-300" />
            </button>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
        {isSearching ? (
          /* Flat search results */
          <div className="space-y-0.5">
            {filteredItems.length === 0 && (
              <p className="text-xs text-slate-600 px-3 py-2">No results</p>
            )}
            {filteredItems.map(item => (
              <NavLink key={item.href} item={item} pathname={pathname} />
            ))}
          </div>
        ) : (
          /* Grouped sections */
          sections.map(({ key, label }) => {
            const items = grouped[key];
            if (!items || items.length === 0) return null;
            const isCollapsed = collapsed[key] ?? false;
            return (
              <div key={key}>
                <button
                  onClick={() => toggleSection(key)}
                  className="w-full flex items-center justify-between px-2 py-1 mb-0.5 group"
                >
                  <span className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider group-hover:text-slate-400 transition-colors">
                    {label}
                  </span>
                  <ChevronDown className={cn(
                    'w-3 h-3 text-slate-600 group-hover:text-slate-400 transition-all',
                    isCollapsed && '-rotate-90'
                  )} />
                </button>
                <AnimatePresence initial={false}>
                  {!isCollapsed && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.18, ease: 'easeInOut' }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-0.5 pb-1">
                        {items.map(item => (
                          <NavLink key={item.href} item={item} pathname={pathname} />
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })
        )}
      </nav>

      {/* Quick theme picker + dark/light toggle */}
      <div className="px-4 py-2 flex items-center gap-1.5">
        {QUICK_THEMES.map(t => (
          <button
            key={t.id}
            onClick={() => setTheme(t.id)}
            title={t.id}
            className="w-3 h-3 rounded-full transition-all hover:scale-125"
            style={{
              background: t.color,
              outline: theme === t.id ? `2px solid ${t.color}` : 'none',
              outlineOffset: '2px',
            }}
          />
        ))}
        <button
          onClick={() => setColorMode(colorMode === 'dark' ? 'light' : 'dark')}
          title={colorMode === 'dark' ? 'Switch to Light' : 'Switch to Dark'}
          className="ml-auto w-5 h-5 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-200 hover:bg-white/10 transition-all"
        >
          {colorMode === 'dark' ? <Sun className="w-3 h-3" /> : <Moon className="w-3 h-3" />}
        </button>
      </div>

      {/* User profile */}
      <div className="px-2 pb-3 border-t border-white/5 pt-2">
        <div className="flex items-center gap-2 px-2 py-2 rounded-xl glass glass-hover">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user?.username?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-slate-200 truncate">{user?.username || 'User'}</div>
            <div className="text-[10px] text-slate-500 truncate">{user?.role}</div>
          </div>
          <NotificationsBell />
          <button onClick={handleLogout} className="text-slate-600 hover:text-red-400 transition-colors flex-shrink-0">
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
  return (
    <Link href={item.href}>
      <motion.div
        className={cn(
          'flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs transition-all group border',
          item.hero
            ? isActive
              ? 'bg-gradient-to-r from-indigo-600/40 to-violet-600/40 border-indigo-500/40 text-white font-semibold shadow-lg shadow-indigo-500/20'
              : 'bg-gradient-to-r from-indigo-500/10 to-violet-500/10 border-indigo-500/20 text-indigo-300 hover:from-indigo-500/20 hover:to-violet-500/20 hover:border-indigo-500/40 hover:text-white font-medium'
            : isActive
              ? 'nav-active border-transparent font-medium'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-white/5'
        )}
        whileHover={{ x: 1 }}
        whileTap={{ scale: 0.98 }}
      >
        <item.icon className={cn(
          'w-3.5 h-3.5 flex-shrink-0',
          item.hero
            ? isActive ? 'text-indigo-300' : 'text-indigo-400'
            : isActive ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-400'
        )} />
        <span className="flex-1 truncate">{item.label}</span>
        {item.badge && (
          <span className={cn(
            'text-[9px] font-bold px-1 py-0.5 rounded-full',
            item.badge === 'AI' ? 'bg-indigo-500/20 text-indigo-300'
            : item.badge === 'SA' ? 'bg-red-500/20 text-red-300'
            : 'bg-emerald-500/20 text-emerald-300'
          )}>
            {item.badge}
          </span>
        )}
      </motion.div>
    </Link>
  );
}
