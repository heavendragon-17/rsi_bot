import React, { useRef, useEffect, useState } from "react";
import { Calendar as CalendarIcon, AlertCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import { isValid, parse, format } from "date-fns";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Calendar } from "../ui/calendar";

interface DateTextInputProps {
  label: string;
  value: string;
  onChange: (date: string) => void;
  shortcut?: string;
}

export const DateTextInput: React.FC<DateTextInputProps> = ({
  label,
  value,
  onChange,
  shortcut,
}) => {
  const textInputRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  // Validation
  const parsedDate =
    value && value.length === 10
      ? parse(value, "dd-MM-yyyy", new Date())
      : undefined;
  const isDateValid = !value || (value.length === 10 && isValid(parsedDate));

  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
  };

  const handleDatePick = (date: Date | undefined) => {
    console.log("Date picked:", date);
    if (date) {
      const formatted = format(date, "dd-MM-yyyy");
      console.log("Calling onChange with:", formatted);
      onChange(formatted);
      setIsOpen(false);
    }
  };

  // Shortcut handling
  useEffect(() => {
    if (!shortcut) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key.toLowerCase() === shortcut.toLowerCase() &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        e.target instanceof HTMLElement &&
        e.target.tagName !== "INPUT"
      ) {
        e.preventDefault();
        textInputRef.current?.focus();
        textInputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcut]);

  const parsedDateFromInput =
    value && value.length === 10 && isValid(parsedDate)
      ? parsedDate
      : undefined;

  return (
    <div
      className="flex flex-col gap-1.5 flex-1 cursor-text"
      onClick={() => textInputRef.current?.focus()}
    >
      <div className="flex justify-between items-center">
        <label className="text-[10px] font-medium text-text-secondary uppercase tracking-wider">
          {label}
        </label>
        {!isDateValid && (
          <span className="text-[10px] text-danger flex items-center gap-1">
            <AlertCircle size={8} />
            Invalid
          </span>
        )}
      </div>

      <div
        className={cn(
          "relative flex items-center bg-input/50 border border-border-main rounded-md px-2 py-1.5 focus-within:ring-1 focus-within:ring-accent-main/50 focus-within:border-accent-main transition-colors",
          !isDateValid &&
            "border-danger focus-within:border-danger focus-within:ring-danger/20",
          isOpen && "ring-1 ring-accent-main/50 border-accent-main"
        )}
      >
        <input
          ref={textInputRef}
          type="text"
          value={value ?? ""}
          onChange={handleTextChange}
          placeholder="DD-MM-YYYY"
          className="w-full bg-transparent border-none text-xs font-mono text-text-primary focus:outline-none p-0"
          maxLength={10}
        />

        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="text-text-muted hover:text-text-primary transition-colors ml-2 flex items-center justify-center p-1 rounded-sm focus:outline-none focus:ring-1 focus:ring-accent-main/50"
              tabIndex={-1}
            >
              <CalendarIcon size={14} />
            </button>
          </PopoverTrigger>
          <PopoverContent
            className="w-auto p-0 border-border-main bg-bg-surface backdrop-blur-xl shadow-xl"
            align="end"
            style={{ width: "280px" }}
            onInteractOutside={(e) => {
              const target = e.target as HTMLElement;
              // Prevent closing if the element was removed from the DOM
              if (!document.contains(target)) {
                e.preventDefault();
              }
            }}
            onFocusOutside={(e) => {
              // Prevent closing when clicking the native year/month select dropdowns
              e.preventDefault();
            }}
          >
            <Calendar
              mode="single"
              selected={parsedDateFromInput}
              onSelect={handleDatePick}
              initialFocus
              className="bg-transparent"
            />
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
};
