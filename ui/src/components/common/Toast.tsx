import React from 'react';
import { useUIStore } from '../../stores/useUIStore';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/utils';

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useUIStore();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "flex items-center gap-3 min-w-[300px] p-4 rounded-lg shadow-lg border animate-slide-up",
            {
              "bg-surface border-success/20 text-success": toast.type === 'success',
              "bg-surface border-danger/20 text-danger": toast.type === 'error',
              "bg-surface border-warning/20 text-warning": toast.type === 'warning',
              "bg-surface border-info/20 text-info": toast.type === 'info',
            }
          )}
        >
          {toast.type === 'success' && <CheckCircle size={20} />}
          {toast.type === 'error' && <AlertCircle size={20} />}
          {toast.type === 'warning' && <AlertTriangle size={20} />}
          {toast.type === 'info' && <Info size={20} />}

          <p className="flex-1 text-sm font-medium text-text">{toast.message}</p>

          <button
            onClick={() => removeToast(toast.id)}
            className="text-text-muted hover:text-text transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
};
