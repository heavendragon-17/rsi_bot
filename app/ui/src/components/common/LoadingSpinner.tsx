interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeClasses = {
  sm: 'w-4 h-4 border-2',
  md: 'w-8 h-8 border-3',
  lg: 'w-12 h-12 border-4',
};

export function LoadingSpinner({ size = 'md', className = '' }: LoadingSpinnerProps) {
  return (
    <div
      className={`
        ${sizeClasses[size]}
        border-[var(--color-primary)]
        border-t-transparent
        rounded-full
        animate-spin
        ${className}
      `}
    />
  );
}

interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({ message = 'Loading...' }: LoadingOverlayProps) {
  return (
    <div className="absolute inset-0 bg-[var(--color-bg)]/80 backdrop-blur-sm flex flex-col items-center justify-center z-40">
      <LoadingSpinner size="lg" />
      <p className="mt-4 text-[var(--color-text-muted)]">{message}</p>
    </div>
  );
}
