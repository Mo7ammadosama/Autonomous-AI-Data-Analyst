'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  GitPullRequest, CheckCircle2, XCircle, Clock, User,
  ChevronDown, ChevronUp, Eye, MessageSquare
} from 'lucide-react';
import { toast } from 'sonner';
import AppLayout from '@/components/layout/AppLayout';
import PageHeader from '@/components/ui/PageHeader';
import { apiClient } from '@/lib/api';

interface DashboardPR {
  id: string;
  dashboard_id: string;
  proposed_by: string;
  title: string;
  description?: string;
  status: 'pending' | 'approved' | 'rejected';
  reviewed_by?: string;
  review_comment?: string;
  reviewed_at?: string;
  created_at: string;
  diff_summary?: any;
}

const STATUS_META = {
  pending:  { icon: Clock,        color: 'text-yellow-400', bg: 'bg-yellow-900/30', label: 'Pending Review' },
  approved: { icon: CheckCircle2, color: 'text-green-400',  bg: 'bg-green-900/30',  label: 'Approved' },
  rejected: { icon: XCircle,      color: 'text-red-400',    bg: 'bg-red-900/30',    label: 'Rejected' },
};

function PRCard({ pr, onApprove, onReject }: {
  pr: DashboardPR;
  onApprove: (id: string) => void;
  onReject: (id: string, comment: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  const meta = STATUS_META[pr.status];
  const Icon = meta.icon;

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      {/* Header */}
      <div
        className="p-4 flex items-start gap-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className={`p-2 rounded-lg flex-shrink-0 ${meta.bg}`}>
          <Icon className={`w-5 h-5 ${meta.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-white font-semibold">{pr.title}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${meta.bg} ${meta.color}`}>
              {meta.label}
            </span>
          </div>
          {pr.description && (
            <p className="text-sm text-gray-400 line-clamp-1">{pr.description}</p>
          )}
          <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <User className="w-3 h-3" />
              Proposed by {pr.proposed_by.slice(0, 8)}…
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(pr.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
        <button className="text-gray-500 flex-shrink-0">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-t border-white/10"
          >
            <div className="p-4 space-y-4">
              {/* Diff summary */}
              {pr.diff_summary && (
                <div>
                  <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Changes</p>
                  <pre className="text-xs bg-black/30 rounded-lg p-3 text-gray-300 overflow-x-auto">
                    {JSON.stringify(pr.diff_summary, null, 2)}
                  </pre>
                </div>
              )}

              {/* Review comment */}
              {pr.review_comment && (
                <div className="flex items-start gap-2">
                  <MessageSquare className="w-4 h-4 text-gray-400 mt-0.5" />
                  <p className="text-sm text-gray-300">{pr.review_comment}</p>
                </div>
              )}

              {/* Actions (only for pending) */}
              {pr.status === 'pending' && (
                <div className="flex gap-2">
                  <button
                    onClick={() => { onApprove(pr.id); setExpanded(false); }}
                    className="flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm text-white transition-colors"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => setShowRejectInput(!showRejectInput)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-red-900/50 hover:bg-red-900/70 border border-red-700 rounded-lg text-sm text-red-300 transition-colors"
                  >
                    <XCircle className="w-4 h-4" />
                    Reject
                  </button>
                  <a
                    href={`/dashboards/${pr.dashboard_id}`}
                    className="flex items-center gap-1.5 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-gray-300 transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                    View Dashboard
                  </a>
                </div>
              )}

              {showRejectInput && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="space-y-2"
                >
                  <textarea
                    value={rejectComment}
                    onChange={e => setRejectComment(e.target.value)}
                    placeholder="Reason for rejection (optional)"
                    className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-sm text-white placeholder-gray-500 resize-none"
                    rows={2}
                  />
                  <button
                    onClick={() => { onReject(pr.id, rejectComment); setExpanded(false); }}
                    className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded-lg text-sm text-white"
                  >
                    Confirm Rejection
                  </button>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function ReviewsPage() {
  const [prs, setPRs] = useState<DashboardPR[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('pending');

  const fetchPRs = async () => {
    setLoading(true);
    try {
      // Fetch PRs from all dashboards of the user
      const dashRes = await apiClient.get('/api/dashboards');
      const dashboards = Array.isArray(dashRes.data) ? dashRes.data : dashRes.data?.dashboards || [];
      const allPRs: DashboardPR[] = [];
      await Promise.all(
        dashboards.slice(0, 20).map(async (d: any) => {
          try {
            const res = await apiClient.get(`/api/dashboards/${d.id}/reviews`);
            const reviews = Array.isArray(res.data) ? res.data : res.data?.reviews || [];
            allPRs.push(...reviews);
          } catch { /* skip */ }
        })
      );
      allPRs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setPRs(allPRs);
    } catch {
      toast.error('Failed to load reviews');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPRs(); }, []);

  const handleApprove = async (prId: string) => {
    // Find dashboard_id for this PR
    const pr = prs.find(p => p.id === prId);
    if (!pr) return;
    try {
      await apiClient.post(`/api/dashboards/${pr.dashboard_id}/reviews/${prId}/approve`);
      toast.success('Dashboard change approved!');
      setPRs(prev => prev.map(p => p.id === prId ? { ...p, status: 'approved' } : p));
    } catch {
      toast.error('Failed to approve');
    }
  };

  const handleReject = async (prId: string, comment: string) => {
    const pr = prs.find(p => p.id === prId);
    if (!pr) return;
    try {
      await apiClient.post(`/api/dashboards/${pr.dashboard_id}/reviews/${prId}/reject`, { comment });
      toast.success('Review rejected');
      setPRs(prev => prev.map(p => p.id === prId ? { ...p, status: 'rejected', review_comment: comment } : p));
    } catch {
      toast.error('Failed to reject');
    }
  };

  const filtered = prs.filter(p => filter === 'all' || p.status === filter);
  const pendingCount = prs.filter(p => p.status === 'pending').length;

  return (
    <AppLayout>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <PageHeader
          title="PR Reviews"
          subtitle="Review proposed dashboard changes before publishing — Hex diff view style"
          icon={<GitPullRequest className="w-6 h-6 text-indigo-400" />}
        />

        {/* Filter tabs */}
        <div className="flex gap-1 p-1 bg-white/5 rounded-lg border border-white/10 w-fit">
          {(['pending', 'approved', 'rejected', 'all'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
                filter === f ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {f}
              {f === 'pending' && pendingCount > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-yellow-600 rounded-full">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* PR list */}
        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-20 rounded-xl bg-white/5 animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            <GitPullRequest className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No {filter === 'all' ? '' : filter} reviews found.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <AnimatePresence>
              {filtered.map(pr => (
                <motion.div key={pr.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <PRCard pr={pr} onApprove={handleApprove} onReject={handleReject} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
