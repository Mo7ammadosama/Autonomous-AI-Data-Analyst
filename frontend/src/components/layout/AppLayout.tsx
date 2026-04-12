'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Toaster } from 'sonner';
import Sidebar from '@/components/layout/SidebarClient';
import CopilotButton from '@/components/copilot/CopilotButton';
import { useAuthStore } from '@/lib/store';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, initialize, isLoading, theme, colorMode } = useAuthStore();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  // Apply saved theme and color mode on mount
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (colorMode === 'light') {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    } else {
      document.documentElement.classList.remove('light');
      document.documentElement.classList.add('dark');
    }
  }, [colorMode]);

  // initialize is synchronous (reads localStorage) — run immediately
  useEffect(() => {
    initialize();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Only redirect after initialize has had a chance to restore auth state
    if (!isLoading && !isAuthenticated) router.push('/');
  }, [isAuthenticated, isLoading, router]);

  // Suppress hydration mismatch: server has no localStorage, client may be authenticated.
  // Return null on both until client has mounted, ensuring SSR HTML matches initial client render.
  if (!mounted) return null;

  // Redirect unauthenticated users (isAuthenticated is pre-loaded from localStorage)
  if (!isAuthenticated && !isLoading) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto bg-transparent">
        {children}
      </main>
      {/* Global AI Copilot — available on every page */}
      <CopilotButton />
      {/* Global toast notifications */}
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1a1a2e',
            border: '1px solid rgba(255,255,255,0.08)',
            color: '#e2e8f0',
            fontFamily: 'inherit',
            fontSize: '13px',
          },
        }}
        richColors
      />
    </div>
  );
}
