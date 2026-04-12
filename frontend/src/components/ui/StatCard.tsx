'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  iconColor?: string;
  trend?: { value: number; label: string };
  delay?: number;
  className?: string;
}

export default function StatCard({ title, value, subtitle, icon: Icon, iconColor = 'text-indigo-400', trend, delay = 0, className }: StatCardProps) {
  return (
    <motion.div
      className={cn('glass rounded-xl p-5 border border-white/5 card-hover', className)}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className={cn('p-2 rounded-lg bg-white/5', iconColor.replace('text-', 'bg-').replace('-400', '-400/10'))}>
          <Icon className={cn('w-4 h-4', iconColor)} />
        </div>
        {trend && (
          <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', trend.value >= 0 ? 'text-emerald-400 bg-emerald-400/10' : 'text-red-400 bg-red-400/10')}>
            {trend.value >= 0 ? '+' : ''}{trend.value}% {trend.label}
          </span>
        )}
      </div>
      <div className="text-2xl font-display font-bold text-white mb-0.5">{value}</div>
      <div className="text-sm font-medium text-slate-300">{title}</div>
      {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
    </motion.div>
  );
}
