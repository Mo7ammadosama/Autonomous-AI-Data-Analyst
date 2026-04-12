'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { sharingApi } from '@/lib/api';
import { Brain, Eye, Calendar, BarChart2, AlertCircle } from 'lucide-react';
import ChartGrid from '@/components/charts/ChartGrid';

interface SharedDashboard {
  id: string;
  name: string;
  description: string | null;
  charts: unknown[];
  layout: Record<string, unknown>;
  view_count: number;
  created_at: string;
}

export default function SharedDashboardPage() {
  const params = useParams();
  const token = params.token as string;
  const [dashboard, setDashboard] = useState<SharedDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await sharingApi.getPublic(token);
        setDashboard(res.data);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string }; status?: number } });
        if (msg.response?.status === 410) {
          setError('This share link has expired.');
        } else if (msg.response?.status === 404) {
          setError('Share link not found or has been revoked.');
        } else {
          setError('Failed to load shared dashboard.');
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center mx-auto animate-pulse">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <p className="text-slate-400 text-sm">Loading dashboard…</p>
        </div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-center space-y-4 max-w-sm">
          <AlertCircle className="w-10 h-10 text-red-400 mx-auto" />
          <h1 className="text-lg font-semibold text-white">Dashboard Unavailable</h1>
          <p className="text-slate-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      {/* Header */}
      <header className="border-b border-white/5 px-6 py-4 flex items-center gap-4">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0">
          <Brain className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-white truncate">{dashboard.name}</h1>
          {dashboard.description && <p className="text-xs text-slate-500 truncate">{dashboard.description}</p>}
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500 flex-shrink-0">
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" />
            {dashboard.view_count} views
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {new Date(dashboard.created_at).toLocaleDateString()}
          </span>
          <span className="flex items-center gap-1 text-indigo-400">
            <BarChart2 className="w-3 h-3" />
            DataMind
          </span>
        </div>
      </header>

      {/* Charts */}
      <main className="p-6">
        {dashboard.charts && dashboard.charts.length > 0 ? (
          <ChartGrid charts={dashboard.charts as unknown[]} />
        ) : (
          <div className="text-center py-20 text-slate-500">No charts in this dashboard.</div>
        )}
      </main>
    </div>
  );
}
