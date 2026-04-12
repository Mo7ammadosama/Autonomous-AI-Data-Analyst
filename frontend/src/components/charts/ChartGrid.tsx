'use client';

import { motion } from 'framer-motion';
import Chart from './Chart';

interface ChartGridProps {
  charts: any[];
  columns?: 1 | 2 | 3;
  chartHeight?: number;
}

export default function ChartGrid({ charts, columns = 2, chartHeight = 280 }: ChartGridProps) {
  if (!charts?.length) return null;

  const gridClass = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 lg:grid-cols-2',
    3: 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3',
  }[columns];

  return (
    <div className={`grid ${gridClass} gap-4`}>
      {charts.map((chart, i) => (
        <motion.div
          key={chart.id || i}
          className="glass rounded-xl p-4 border border-white/5 card-hover"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08 }}
        >
          <Chart chart={chart} height={chartHeight} />
        </motion.div>
      ))}
    </div>
  );
}
