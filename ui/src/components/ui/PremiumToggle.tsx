"use client";

import * as React from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { motion } from "motion/react";
import { cn } from "../../lib/utils";

interface PremiumToggleProps
  extends React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root> {
  size?: "sm" | "md" | "lg";
}

const PremiumToggle = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  PremiumToggleProps
>(({ className, size = "md", ...props }, ref) => {
  const [internalChecked, setInternalChecked] = React.useState(
    props.defaultChecked || false
  );

  const isControlled = typeof props.checked !== "undefined";
  const checked = isControlled ? props.checked : internalChecked;

  const handleCheckedChange = (c: boolean) => {
    if (!isControlled) setInternalChecked(c);
    props.onCheckedChange?.(c);
  };

  const configs = {
    sm: { w: "w-12", h: "h-7", p: 3, thumbSize: 14 },
    md: { w: "w-16", h: "h-9", p: 6, thumbSize: 20 },
    lg: { w: "w-20", h: "h-11", p: 8, thumbSize: 24 },
  };
  const config = configs[size];

  // Padding numerical value for calculation
  const padding = config.p;

  return (
    <SwitchPrimitives.Root
      className={cn(
        "group peer relative inline-flex shrink-0 cursor-pointer items-center rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
        config.w,
        config.h,
        // Track Background:
        // Active: bg-accent (visible cyan/blue)
        // Inactive: bg-slate-700/50 (dark neutral)
        checked
          ? "bg-accent border-accent/20"
          : "bg-slate-700/50 border-white/10",
        className
      )}
      checked={checked}
      onCheckedChange={handleCheckedChange}
      ref={ref}
      {...props}
    >
      <motion.div
        className={cn(
          "pointer-events-none absolute block rounded-full bg-white shadow-lg ring-0"
        )}
        initial={false}
        animate={{
          // Reduce travel distance by adding extra padding to the right side calculation
          left: checked
            ? `calc(100% - ${config.thumbSize}px - ${padding + 4}px)`
            : `${padding}px`,
          width: config.thumbSize,
          height: config.thumbSize,
          // Distinct ON state: Scale up slightly when active
          scale: checked ? 1.1 : 0.9,
        }}
        // Override x to be 0 always since we control 'left'
        style={{ x: 0 }}
        transition={{
          type: "spring",
          stiffness: 500,
          damping: 30,
        }}
        whileTap={{
          scale: 1.0,
          width: config.thumbSize + 4, // Subtle stretch
        }}
      />
    </SwitchPrimitives.Root>
  );
});

PremiumToggle.displayName = SwitchPrimitives.Root.displayName;

export { PremiumToggle };
