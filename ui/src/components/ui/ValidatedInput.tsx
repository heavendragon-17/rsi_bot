import React, { useState, useEffect } from "react";
import { cn } from "../../lib/utils";
import { validateParam } from "../../lib/validation";
import { AlertCircle } from "lucide-react";

interface ValidatedInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  paramKey: string;
  label: string;
  value: string;
  onChangeValue: (value: string) => void;
  suffix?: string;
  disabled?: boolean;
}

export const ValidatedInput: React.FC<ValidatedInputProps> = ({
  paramKey,
  label,
  value,
  onChangeValue,
  suffix,
  className,
  disabled,
  ...props
}) => {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const result = validateParam(paramKey, value);
    setError(result.error);
  }, [value, paramKey]);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex justify-between items-center">
        <label className="text-xs font-medium text-text-secondary">{label}</label>
        {error && (
          <span className="text-[10px] text-danger flex items-center gap-1">
            <AlertCircle size={10} />
            {error}
          </span>
        )}
      </div>
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => onChangeValue(e.target.value)}
          disabled={disabled}
          className={cn(
            "w-full bg-input/50 border border-border-main rounded-md px-3 py-2 text-sm text-text-primary transition-colors focus:outline-none focus:ring-1 focus:ring-accent-main/50",
            error && "border-danger focus:ring-danger/20",
            disabled && "cursor-not-allowed opacity-70",
            suffix && "pr-8"
          )}
          {...props}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-text-muted">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
};
