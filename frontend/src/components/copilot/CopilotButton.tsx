'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X } from 'lucide-react';
import dynamic from 'next/dynamic';

const CopilotPanel = dynamic(() => import('./CopilotPanel'), { ssr: false });

/**
 * Floating AI Copilot button — rendered in AppLayout so it's available everywhere.
 * Opens the sliding CopilotPanel when clicked.
 */
export default function CopilotButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Overlay */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
          />
        )}
      </AnimatePresence>

      {/* Sliding panel */}
      <AnimatePresence>
        {open && <CopilotPanel key="panel" onClose={() => setOpen(false)} />}
      </AnimatePresence>

      {/* Floating button */}
      <motion.button
        onClick={() => setOpen((v) => !v)}
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.94 }}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3
                   bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-2xl
                   shadow-xl shadow-indigo-900/50 font-medium text-sm
                   ring-2 ring-indigo-400/30 ring-offset-2 ring-offset-transparent
                   hover:ring-indigo-400/60 transition-all duration-200"
      >
        {open ? (
          <X className="w-4 h-4" />
        ) : (
          <Sparkles className="w-4 h-4" />
        )}
        <span>{open ? 'Close' : 'Ask DataMind'}</span>
      </motion.button>
    </>
  );
}
