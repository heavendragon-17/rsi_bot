import React from "react";
import { motion } from "motion/react";
import { cn } from "../../lib/utils";

export const TechnicalZenLoader: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <div className={cn("relative w-24 h-24 flex items-center justify-center", className)}>
      {/* Abstract Grid/Network Animation */}
      <svg width="100%" height="100%" viewBox="0 0 100 100" className="overflow-visible">
         <defs>
             <linearGradient id="grid-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                 <stop offset="0%" stopColor="var(--accent-main)" stopOpacity="0.1" />
                 <stop offset="50%" stopColor="var(--accent-main)" stopOpacity="0.5" />
                 <stop offset="100%" stopColor="var(--accent-main)" stopOpacity="0.1" />
             </linearGradient>
         </defs>

         {/* Rotating Rings */}
         <motion.circle 
            cx="50" cy="50" r="40" 
            stroke="var(--border-main)" strokeWidth="1" fill="none"
            animate={{ rotate: 360 }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            className="opacity-30"
         />
         <motion.circle 
            cx="50" cy="50" r="30" 
            stroke="var(--accent-main)" strokeWidth="1" fill="none"
            strokeDasharray="4 8"
            animate={{ rotate: -360 }}
            transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
            className="opacity-50"
         />
         
         {/* Inner Hex or Shape */}
         <motion.path
            d="M50 20 L76 35 L76 65 L50 80 L24 65 L24 35 Z"
            fill="url(#grid-grad)"
            stroke="var(--accent-main)"
            strokeWidth="0.5"
            initial={{ scale: 0.8, opacity: 0.5 }}
            animate={{ scale: [0.8, 1, 0.8], opacity: [0.5, 0.8, 0.5] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
         />
         
         {/* Scanning Line */}
         <motion.line
            x1="20" y1="20" x2="80" y2="20"
            stroke="var(--accent-main)"
            strokeWidth="2"
            strokeLinecap="round"
            initial={{ y1: 20, y2: 20, opacity: 0 }}
            animate={{ y1: 80, y2: 80, opacity: [0, 1, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
         />
      </svg>
    </div>
  );
};
