'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface ChartData {
  id?: string;
  type: string;
  title: string;
  data: any[];
  layout?: Record<string, any>;
}

interface ChartProps {
  chart: ChartData;
  className?: string;
  height?: number;
}

export default function Chart({ chart, className, height = 280 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !containerRef.current) return;

    let cancelled = false;

    const render = async () => {
      try {
        const Plotly = (await import('plotly.js')).default;
        if (cancelled || !containerRef.current) return;

        const defaultLayout = {
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: '#94a3b8', family: 'Space Grotesk, sans-serif', size: 11 },
          margin: { t: 40, b: 40, l: 50, r: 20 },
          xaxis: { gridcolor: 'rgba(255,255,255,0.05)', zerolinecolor: 'rgba(255,255,255,0.1)', ...(chart.layout?.xaxis || {}) },
          yaxis: { gridcolor: 'rgba(255,255,255,0.05)', zerolinecolor: 'rgba(255,255,255,0.1)', ...(chart.layout?.yaxis || {}) },
          legend: { bgcolor: 'rgba(0,0,0,0)', font: { color: '#94a3b8' } },
          colorway: ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'],
          title: chart.layout?.title ? {
            text: chart.layout.title,
            font: { color: '#e2e8f0', size: 13, family: 'Syne, sans-serif' },
            x: 0.02,
          } : undefined,
          ...chart.layout,
        };

        const config = {
          displayModeBar: false,
          responsive: true,
          staticPlot: false,
        };

        const data = Array.isArray(chart.data) ? chart.data : [chart.data];

        await Plotly.react(containerRef.current, data, defaultLayout, config);
      } catch (err) {
        console.error('Chart render error:', err);
      }
    };

    render();
    return () => { cancelled = true; };
  }, [mounted, chart]);

  return (
    <div className={cn('relative', className)}>
      {!mounted ? (
        <div className="w-full bg-white/3 rounded-xl shimmer" style={{ height }} />
      ) : (
        <div ref={containerRef} style={{ height, width: '100%' }} />
      )}
    </div>
  );
}
