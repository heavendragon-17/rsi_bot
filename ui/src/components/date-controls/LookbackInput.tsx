import React, { useEffect, useRef } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

export const LookbackInput: React.FC = () => {
  const { lookbackValue, setLookbackValue, lookbackUnit, setLookbackUnit } = useBacktestStore();
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut 'L' to focus input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'l' && !e.ctrlKey && !e.metaKey && !e.altKey && e.target instanceof HTMLElement && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value);
    if (!isNaN(val) && val > 0) {
      setLookbackValue(val);
    } else if (e.target.value === "") {
        // Allow temporary empty state while typing, handled by UI not crashing but store expects number.
        // Zustand persist might be unhappy with NaN, but `parseInt` returns NaN.
        // We'll just not update if invalid for now or handle string in store if we wanted perfect controlled input.
        // For now, strict update:
    }
  };

  return (
    <div className="flex items-center gap-2 mb-2">
      <div className="flex items-center gap-2 bg-input/50 border border-border-main rounded-md px-2 py-1 focus-within:ring-1 focus-within:ring-accent-main/50 focus-within:border-accent-main transition-colors w-full">
         <span className="text-[10px] font-medium text-text-muted whitespace-nowrap">Last</span>
         <input
            ref={inputRef}
            type="number"
            min="1"
            value={lookbackValue}
            onChange={handleChange}
            className="w-full bg-transparent border-none text-sm font-medium text-text-primary focus:outline-none p-0 appearance-none text-right"
         />
      </div>
      
      <div className="relative min-w-[80px]">
        <select
            value={lookbackUnit}
            onChange={(e) => setLookbackUnit(e.target.value as any)}
            className="w-full bg-input/50 border border-border-main rounded-md px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50 cursor-pointer appearance-none"
        >
            <option value="bars">Bars</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
            <option value="weeks">Weeks</option>
            <option value="months">Months</option>
        </select>
        {/* Simple arrow override could go here but default select arrow is often fine for internal tools, though design requested dropdown icon. */}
        <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-text-muted">
            <svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
        </div>
      </div>
    </div>
  );
};
