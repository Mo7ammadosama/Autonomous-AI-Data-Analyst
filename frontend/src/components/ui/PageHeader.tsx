'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  description?: string;  // alias for subtitle
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export default function PageHeader({ title, subtitle, description, icon, action, className }: PageHeaderProps) {
  const subtext = subtitle || description;
  return (
    <motion.div
      className={cn('flex items-center justify-between mb-6', className)}
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-center gap-3">
        {icon && (
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center">
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-xl font-display font-bold text-white">{title}</h1>
          {subtext && <p className="text-sm text-slate-500 mt-0.5">{subtext}</p>}
        </div>
      </div>
      {action && <div>{action}</div>}
    </motion.div>
  );
}
