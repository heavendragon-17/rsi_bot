import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Lightbulb } from "lucide-react";

interface ContextFactDisplayProps {
  fact: string;
}

export const ContextFactDisplay: React.FC<ContextFactDisplayProps> = ({ fact }) => {
  return (
    <div className="flex items-start gap-3 p-3 bg-bg-elevated/30 rounded-lg border border-border-main/50">
      <Lightbulb className="text-warning shrink-0 mt-0.5" size={16} />
      <AnimatePresence mode="wait">
        <motion.p
          key={fact}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.3 }}
          className="text-sm text-text-secondary italic"
        >
          "{fact}"
        </motion.p>
      </AnimatePresence>
    </div>
  );
};
