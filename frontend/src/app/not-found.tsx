import Link from 'next/link';
import { Home, Search } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="text-center">
        <div className="text-8xl font-display font-bold gradient-text mb-4">404</div>
        <h2 className="text-xl font-display font-bold text-white mb-2">Page not found</h2>
        <p className="text-slate-500 text-sm mb-8">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="flex gap-3 justify-center">
          <Link href="/dashboard">
            <button className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition-colors">
              <Home className="w-4 h-4" /> Go to Dashboard
            </button>
          </Link>
          <Link href="/datasets">
            <button className="flex items-center gap-2 px-4 py-2.5 glass border border-white/10 text-slate-300 hover:text-white rounded-xl text-sm font-medium transition-colors">
              <Search className="w-4 h-4" /> Browse Datasets
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
}
