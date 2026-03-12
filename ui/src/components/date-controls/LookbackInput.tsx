import React, { useEffect, useRef, useState } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { ChevronUp, ChevronDown } from "lucide-react";

export const LookbackInput: React.FC = () => {
  const { lookbackValue, setLookbackValue, lookbackUnit, setLookbackUnit } =
    useBacktestStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [inputVal, setInputVal] = useState(String(lookbackValue));

  useEffect(() => { setInputVal(String(lookbackValue)); }, [lookbackValue]);

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
    setInputVal(e.target.value);
    const val = parseInt(e.target.value);
    if (!isNaN(val) && val > 0) {
      setLookbackValue(val);
    }
  };

  const increment = () => {
    setLookbackValue((lookbackValue || 0) + 1);
  };

  const decrement = () => {
    if ((lookbackValue || 1) > 1) {
      setLookbackValue((lookbackValue || 1) - 1);
    }
  };

  return (
    <>
      <style>{`
        .custom-number-input::-webkit-outer-spin-button,
        .custom-number-input::-webkit-inner-spin-button {
          -webkit-appearance: none;
          margin: 0;
        }
        .custom-number-input {
          -moz-appearance: textfield;
        }
      `}</style>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex items-center h-8 bg-input/50 border border-border-main rounded-md px-2.5 focus-within:ring-1 focus-within:ring-accent-main/50 transition-colors flex-1 group min-w-0">
          <span className="text-xs font-medium text-text-muted shrink-0">
            Last
          </span>
          <input
            ref={inputRef}
            type="number"
            min="1"
            value={inputVal}
            onChange={handleChange}
            className="flex-1 min-w-0 w-full bg-transparent border-none text-sm font-medium text-text-primary focus:outline-none p-0 text-right pr-2 custom-number-input"
          />
          <div className="flex flex-col items-center justify-center shrink-0 border-l border-border-main/50 pl-1.5 ml-1">
            <button
              onClick={increment}
              className="text-text-muted hover:text-text-primary transition-colors focus:outline-none h-[12px] flex items-end justify-center"
              tabIndex={-1}
            >
              <ChevronUp size={12} strokeWidth={3} />
            </button>
            <button
              onClick={decrement}
              className="text-text-muted hover:text-text-primary transition-colors focus:outline-none h-[12px] flex items-start justify-center mt-0.5"
              tabIndex={-1}
            >
              <ChevronDown size={12} strokeWidth={3} />
            </button>
          </div>
        </div>

        <div className="w-[72px] shrink-0">
          <Select
            value={lookbackUnit || "bars"}
            onValueChange={(val) => setLookbackUnit(val as any)}
          >
            <SelectTrigger className="w-full h-8 bg-input/50 border-border-main rounded-md px-2 py-1 text-xs text-text-primary focus:ring-1 focus:ring-accent-main/50 data-[state=open]:bg-bg-elevated shadow-none transition-colors gap-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent
              align="end"
              className="min-w-[70px] border-border-main bg-bg-surface backdrop-blur-xl shadow-xl"
            >
              <SelectItem
                value="bars"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Bars
              </SelectItem>
              <SelectItem
                value="hours"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Hours
              </SelectItem>
              <SelectItem
                value="days"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Days
              </SelectItem>
              <SelectItem
                value="weeks"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Weeks
              </SelectItem>
              <SelectItem
                value="months"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Months
              </SelectItem>
              <SelectItem
                value="years"
                className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
              >
                Years
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </>
  );
};
