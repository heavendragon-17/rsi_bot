import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";
import { motion, AnimatePresence } from "motion/react";

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  headerAction?: React.ReactNode;
  className?: string;
  onToggle?: (isOpen: boolean) => void;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  children,
  defaultOpen = true,
  headerAction,
  className,
  onToggle,
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const handleToggle = () => {
    const newState = !isOpen;
    setIsOpen(newState);
    onToggle?.(newState);
  };

  return (
    <div className={cn("border-b border-border-main/50 last:border-0", className)}>
      <div 
        className="flex items-center justify-between py-3 px-4 cursor-pointer hover:bg-white/5 transition-colors group"
        onClick={handleToggle}
      >
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary group-hover:text-accent-main transition-colors">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {title}
        </div>
        {headerAction && (
          <div onClick={(e) => e.stopPropagation()}>
            {headerAction}
          </div>
        )}
      </div>
      
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-0">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};