'use client';

import { useState, useEffect, useRef } from 'react';
import { Bell, X, CheckCheck } from 'lucide-react';
import { notificationsApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import Link from 'next/link';

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

const typeColors: Record<string, string> = {
  alert: 'bg-red-500/10 text-red-400',
  insight: 'bg-indigo-500/10 text-indigo-400',
  report: 'bg-emerald-500/10 text-emerald-400',
  info: 'bg-slate-500/10 text-slate-400',
};

export default function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Poll unread count every 2 minutes (was 30s — reduced network noise)
  useEffect(() => {
    const fetchCount = async () => {
      try {
        const res = await notificationsApi.count();
        setUnread(res.data.unread);
      } catch {}
    };
    fetchCount();
    const interval = setInterval(fetchCount, 120_000);
    return () => clearInterval(interval);
  }, []);

  // Load notifications when opened
  useEffect(() => {
    if (!open) return;
    const load = async () => {
      setLoading(true);
      try {
        const res = await notificationsApi.list(false, 20);
        setNotifications(res.data);
      } catch {}
      finally { setLoading(false); }
    };
    load();
  }, [open]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markAllRead = async () => {
    await notificationsApi.markRead();
    setUnread(0);
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const deleteNotif = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await notificationsApi.delete(id);
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative p-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-all"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-indigo-500 text-[10px] font-bold text-white flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 glass rounded-xl border border-white/10 shadow-2xl z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
            <span className="text-sm font-semibold text-slate-200">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
                <CheckCheck className="w-3 h-3" /> Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <div className="p-4 space-y-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-10 bg-white/5 rounded-lg animate-pulse" />)}
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-10 text-center text-xs text-slate-500">No notifications yet</div>
            ) : (
              notifications.map((n) => {
                const colorClass = typeColors[n.type] || typeColors.info;
                const inner = (
                  <div
                    key={n.id}
                    className={cn(
                      'flex items-start gap-3 px-4 py-3 hover:bg-white/3 transition-colors group',
                      !n.is_read && 'bg-indigo-500/5'
                    )}
                  >
                    <div className={cn('w-2 h-2 rounded-full mt-1.5 flex-shrink-0', !n.is_read ? 'bg-indigo-400' : 'bg-transparent')} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-slate-200 leading-tight">{n.title}</p>
                      {n.message && <p className="text-[11px] text-slate-500 mt-0.5 truncate">{n.message}</p>}
                      <p className="text-[10px] text-slate-600 mt-0.5">
                        {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                      </p>
                    </div>
                    <button
                      onClick={(e) => deleteNotif(n.id, e)}
                      className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-slate-400 transition-all flex-shrink-0"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                );
                return n.link ? <Link key={n.id} href={n.link} onClick={() => setOpen(false)}>{inner}</Link> : <div key={n.id}>{inner}</div>;
              })
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-white/5 px-4 py-2.5">
            <Link
              href="/activity"
              onClick={() => setOpen(false)}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              View activity log →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
