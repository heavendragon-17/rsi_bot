import React from "react";
import { motion } from "motion/react";
import { cn } from "../../lib/utils";

interface AnimatedProgressBarProps {
  progress: number; // 0-100
  className?: string;
  colorClass?: string;
}

export const AnimatedProgressBar: React.FC<AnimatedProgressBarProps> = ({ 
    progress, 
    className,
    colorClass = "bg-accent-main"
}) => {
  return (
    <div className={cn("relative w-full h-2 bg-bg-elevated rounded-full overflow-hidden", className)}>
      <motion.div 
        className={cn("h-full rounded-full relative", colorClass)}
        initial={{ width: 0 }}
        animate={{ width: `${progress}%` }}
        transition={{ type: "spring", stiffness: 50, damping: 20 }}
      >
        {/* Shimmer Effect */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer" 
             style={{ backgroundSize: '200% 100%' }} 
        />
      </motion.div>
    </div>
  );
};
