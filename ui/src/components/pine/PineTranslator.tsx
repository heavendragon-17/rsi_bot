import React from "react";
import { usePineStore } from "../../stores/pineStore";
import { PasteZone } from "./PasteZone";
import { ParsedResults } from "./ParsedResults";
import { IndicatorLibrary } from "./IndicatorLibrary";
import { ArrowLeft, CheckCircle } from "lucide-react";

export const PineTranslator: React.FC = () => {
  const { step, reset } = usePineStore();

  if (step === "save") {
      return (
          <div className="h-full w-full flex flex-col p-6 space-y-6 max-w-5xl mx-auto">
             <div className="bg-success/10 border border-success/30 rounded-xl p-8 flex flex-col items-center text-center space-y-4 shadow-sm">
                 <div className="w-16 h-16 bg-success rounded-full flex items-center justify-center text-white shadow-lg shadow-success/30">
                     <CheckCircle size={32} />
                 </div>
                 <h2 className="text-2xl font-bold text-text-primary">Indicator Saved Successfully</h2>
                 <p className="text-text-secondary max-w-md">
                     Your custom indicator is now available in your library and can be selected in the Strategy Settings panel.
                 </p>
                 <div className="flex gap-4 pt-4">
                     <button 
                        onClick={reset}
                        className="px-6 py-2.5 bg-bg-surface border border-border-main hover:bg-bg-elevated text-text-primary font-medium rounded-lg transition-colors shadow-sm"
                     >
                         Import Another
                     </button>
                 </div>
             </div>
             
             <div className="flex-1 min-h-0">
                 <IndicatorLibrary />
             </div>
          </div>
      );
  }

  return (
    <div className="h-full w-full flex flex-col p-6 max-w-[1600px] mx-auto space-y-6">
        {/* Header Navigation if needed */}
        {step === "verify" && (
            <div className="flex items-center gap-2">
                <button 
                    onClick={() => usePineStore.setState({ step: "paste" })}
                    className="flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
                >
                    <ArrowLeft size={16} /> Back to Paste
                </button>
            </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-0 pb-6">
            {/* Left Main Panel */}
            <div className="lg:col-span-8 h-full flex flex-col min-h-0">
                 {step === "paste" ? <PasteZone /> : <ParsedResults />}
            </div>

            {/* Right Sidebar - Library */}
            <div className="lg:col-span-4 h-full min-h-0 hidden lg:block">
                 <IndicatorLibrary />
            </div>
        </div>
    </div>
  );
};
