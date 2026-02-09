import { ReactNode } from 'react';
import { FileX, Database, Activity, Search } from 'lucide-react';

type EmptyStateVariant = 'no-data' | 'no-runs' | 'no-results' | 'no-search';

interface EmptyStateProps {
  variant: EmptyStateVariant;
  title?: string;
  description?: string;
  action?: ReactNode;
}

const defaults: Record<EmptyStateVariant, { icon: ReactNode; title: string; description: string }> = {
  'no-data': {
    icon: <FileX size={48} className="text-[var(--color-text-muted)]" />,
    title: 'No Data Files Found',
    description: 'Add CSV files to app/backtest/data/ to get started.',
  },
  'no-runs': {
    icon: <Database size={48} className="text-[var(--color-text-muted)]" />,
    title: 'No Runs Yet',
    description: 'Run your first backtest to see results here.',
  },
  'no-results': {
    icon: <Activity size={48} className="text-[var(--color-text-muted)]" />,
    title: 'No Results',
    description: 'Complete a backtest to view performance metrics.',
  },
  'no-search': {
    icon: <Search size={48} className="text-[var(--color-text-muted)]" />,
    title: 'No Matches',
    description: 'Try adjusting your search or filters.',
  },
};

export function EmptyState({ variant, title, description, action }: EmptyStateProps) {
  const config = defaults[variant];

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="mb-4 opacity-50">
        {config.icon}
      </div>
      <h3 className="text-lg font-semibold text-[var(--color-text)] mb-2">
        {title || config.title}
      </h3>
      <p className="text-sm text-[var(--color-text-muted)] max-w-sm mb-4">
        {description || config.description}
      </p>
      {action && (
        <div className="mt-2">
          {action}
        </div>
      )}
    </div>
  );
}
