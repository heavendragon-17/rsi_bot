import React, { useEffect, useRef } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

export const LookbackInput: React.FC = () => {
  const { lookbackValue, setLookbackValue, lookbackUnit, setLookbackUnit } =
    useBacktestStore();
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut 'L' to focus input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key.toLowerCase() === "l" &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        e.target instanceof HTMLElement &&
        e.target.tagName !== "INPUT"
      ) {
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
    <div className="flex flex-col gap-1.5 mb-2">
      <div
        className={cn(
          "flex items-center bg-input/40 backdrop-blur-md border border-border-main rounded-lg px-2.5 py-1.5 transition-all duration-300",
          "focus-within:ring-1 focus-within:ring-accent-main/50 focus-within:border-accent-main focus-within:bg-input/60",
          "hover:border-white/20 hover:bg-input/50"
        )}
      >
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mr-3">
          Last
        </span>

        <input
          ref={inputRef}
          type="number"
          min="1"
          value={lookbackValue}
          onChange={handleChange}
          className="w-full bg-transparent border-none text-xs font-bold text-text-primary focus:outline-none p-0 appearance-none text-right placeholder-text-muted/50"
          placeholder="0"
        />

        <div className="w-[1px] h-4 bg-border-main mx-3 shrink-0" />

        <div className="relative shrink-0">
          <select
            value={lookbackUnit}
            onChange={(e) => setLookbackUnit(e.target.value as any)}
            className="bg-transparent border-none pr-5 text-[10px] font-bold text-text-muted uppercase tracking-wider focus:outline-none cursor-pointer appearance-none hover:text-text-primary transition-colors"
          >
            <option value="bars">Bars</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
            <option value="weeks">Weeks</option>
            <option value="months">Months</option>
          </select>
          <div className="absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none text-text-muted/50">
            <svg
              width="8"
              height="5"
              viewBox="0 0 10 6"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M1 1L5 5L9 1"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
};
