import React, { useRef, useEffect } from "react";
import { Calendar as CalendarIcon, AlertCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import { isValid, parseISO } from "date-fns";

interface DateTextInputProps {
  label: string;
  value: string;
  onChange: (date: string) => void;
  shortcut?: string;
}

export const DateTextInput: React.FC<DateTextInputProps> = ({ label, value, onChange, shortcut }) => {
  const dateInputRef = useRef<HTMLInputElement>(null);
  const textInputRef = useRef<HTMLInputElement>(null);

  // Validation
  const isDateValid = !value || (value.length === 10 && isValid(parseISO(value)));
  
  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
  };

  const handleDateIconClick = () => {
    try {
        dateInputRef.current?.showPicker();
    } catch (e) {
        dateInputRef.current?.click();
    }
  };

  const handleDatePick = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.value) {
          onChange(e.target.value);
      }
  };

  // Shortcut handling
  useEffect(() => {
    if (!shortcut) return;
    const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key.toLowerCase() === shortcut.toLowerCase() && !e.ctrlKey && !e.metaKey && !e.altKey && e.target instanceof HTMLElement && e.target.tagName !== 'INPUT') {
            e.preventDefault();
            textInputRef.current?.focus();
            textInputRef.current?.select();
        }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcut]);

  return (
    <div className="flex flex-col gap-1.5 flex-1">
      <div className="flex justify-between items-center">
        <label className="text-[10px] font-medium text-text-secondary uppercase tracking-wider">{label}</label>
        {!isDateValid && (
             <span className="text-[10px] text-danger flex items-center gap-1">
                <AlertCircle size={8} />
                Invalid
             </span>
        )}
      </div>
      
      <div className={cn(
        "relative flex items-center bg-input/50 border border-border-main rounded-md px-2 py-1.5 focus-within:ring-1 focus-within:ring-accent-main/50 focus-within:border-accent-main transition-colors",
        !isDateValid && "border-danger focus-within:border-danger focus-within:ring-danger/20"
      )}>
        <input
          ref={textInputRef}
          type="text"
          value={value ?? ''}
          onChange={handleTextChange}
          placeholder="YYYY-MM-DD"
          className="w-full bg-transparent border-none text-xs font-mono text-text-primary focus:outline-none p-0"
          maxLength={10}
        />
        
        <button 
            onClick={handleDateIconClick}
            className="text-text-muted hover:text-text-primary transition-colors ml-2"
            tabIndex={-1}
        >
            <CalendarIcon size={14} />
        </button>

        {/* Hidden Native Date Input for Picker */}
        <input
            ref={dateInputRef}
            type="date"
            value={value ?? ''}
            onChange={handleDatePick}
            className="absolute opacity-0 w-0 h-0 bottom-0 left-0 -z-10"
            tabIndex={-1}
        />
      </div>
    </div>
  );
};
