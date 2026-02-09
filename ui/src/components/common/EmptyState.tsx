import React from 'react';
import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  action
}) => {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center bg-surface/30 rounded-xl border border-dashed border-border">
      <div className="p-4 rounded-full bg-surface mb-4">
        <Icon size={32} className="text-text-muted" />
      </div>
      <h3 className="text-lg font-medium text-text mb-2">{title}</h3>
      <p className="text-text-muted max-w-sm mb-6">{description}</p>
      {action}
    </div>
  );
};
