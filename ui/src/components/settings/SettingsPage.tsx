import React from "react";
import { ArrowLeft } from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";
import { ThemeSettings } from "../theme/ThemeSettings";
import { cn } from "../../lib/utils";

export const SettingsPage: React.FC = () => {
  const { setMode } = useBacktestStore();

  return (
    <div className="flex flex-col bg-bg-surface animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-bg-surface/80 backdrop-blur-xl border-b border-border-main/50 px-4 sm:px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setMode("single")}
            className="p-2 rounded-xl hover:bg-bg-elevated text-text-secondary hover:text-text-primary transition-all active:scale-95"
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-xl font-bold text-text-primary tracking-tight">Settings</h1>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-12 pb-12">
        <div className="space-y-16">
          <section>
            <div className="flex items-center gap-3 mb-8">
              <div className="w-1 h-6 bg-accent-main rounded-full" />
              <h2 className="text-xl font-bold text-text-primary tracking-tight">Appearance</h2>
            </div>
            
            <div className="bg-bg-elevated/30 rounded-[2rem] border border-border-main/50 p-8 sm:p-12 shadow-sm">
                <ThemeSettings />
            </div>
          </section>

          {/* You can add more sections here like Account, API Keys, etc. */}
          
          <section className="pt-8 border-t border-border-main/50 opacity-60">
             <p className="text-xs text-text-muted text-center italic">
                RSI Bot v1.2.4 • Strategy Command Terminal
             </p>
          </section>
        </div>
      </div>
    </div>
  );
};
