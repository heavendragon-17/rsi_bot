import React from "react";
import { usePineStore } from "../../stores/pineStore";
import { ArrowRight, Code } from "lucide-react";

export const PasteZone: React.FC = () => {
  const { rawCode, setRawCode, parseCode } = usePineStore();

  return (
    <div className="flex flex-col h-full bg-bg-surface border border-border-main rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-border-main bg-bg-elevated/30 flex justify-between items-center">
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Code size={16} className="text-accent-main" />
            Paste Pine Script
        </h2>
        <span className="text-xs text-text-muted">TradingView v4/v5 supported</span>
      </div>
      
      <div className="flex-1 relative">
        <textarea
            value={rawCode}
            onChange={(e) => setRawCode(e.target.value)}
            placeholder="// Paste your TradingView Pine Script here...
//@version=5
indicator('My Strategy', overlay=true)
length = input.int(14, 'Length')
..."
            className="w-full h-full p-4 bg-transparent resize-none font-mono text-xs leading-relaxed text-text-primary placeholder:text-text-muted/40 focus:outline-none custom-scrollbar"
            spellCheck={false}
        />
      </div>

      <div className="p-4 border-t border-border-main bg-bg-surface flex justify-between items-center">
          <p className="text-xs text-text-secondary">
              💡 Tip: Copy the FULL script from TradingView's "Pine Editor" tab.
          </p>
          <button 
            onClick={parseCode}
            disabled={!rawCode.trim()}
            className="px-4 py-2 bg-accent-main hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg flex items-center gap-2 transition-colors"
          >
              Parse Script <ArrowRight size={16} />
          </button>
      </div>
    </div>
  );
};
