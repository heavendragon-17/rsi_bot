import React from "react";
import { usePineStore, SavedIndicator } from "../../stores/pineStore";
import { cn } from "../../lib/utils";
import { Edit2, Trash2, Plus, CheckCircle, AlertTriangle, XCircle, Code } from "lucide-react";

const IndicatorCard: React.FC<{ 
    indicator: SavedIndicator;
    onEdit: (id: string) => void;
    onDelete: (id: string) => void;
}> = ({ indicator, onEdit, onDelete }) => (
    <div className="group relative flex flex-col p-4 bg-bg-surface border border-border-main rounded-xl hover:border-accent-main/50 transition-colors shadow-sm">
        <div className="flex justify-between items-start mb-2">
            <h3 className="font-bold text-text-primary truncate pr-8">{indicator.name}</h3>
            <div className={cn(
                "w-2 h-2 rounded-full",
                indicator.status === "ready" ? "bg-success" : 
                indicator.status === "warning" ? "bg-warning" : "bg-danger"
            )} />
        </div>
        
        <div className="flex items-center gap-2 mb-4">
             <span className="text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded bg-bg-elevated text-text-secondary border border-border-main">
                 {indicator.type}
             </span>
             <span className="text-xs text-text-muted flex items-center gap-1">
                 <Code size={10} />
                 {indicator.parameters.length} Inputs
             </span>
        </div>

        <div className="mt-auto flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button 
                onClick={() => onEdit(indicator.id)}
                className="flex-1 py-1.5 text-xs font-medium bg-bg-elevated hover:bg-bg-secondary text-text-primary rounded border border-border-main flex items-center justify-center gap-1"
            >
                <Edit2 size={10} /> Edit
            </button>
            <button 
                onClick={() => onDelete(indicator.id)}
                className="w-8 py-1.5 bg-danger/10 hover:bg-danger/20 text-danger rounded border border-danger/20 flex items-center justify-center"
            >
                <Trash2 size={10} />
            </button>
        </div>
    </div>
);

export const IndicatorLibrary: React.FC = () => {
  const { savedIndicators, loadIndicatorForEdit, deleteIndicator, reset } = usePineStore();

  return (
    <div className="flex flex-col h-full bg-bg-surface border border-border-main rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-border-main bg-bg-elevated/30 flex justify-between items-center">
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            Your Indicators
            <span className="text-xs font-normal text-text-muted px-2 py-0.5 bg-bg-elevated rounded-full border border-border-main">
                {savedIndicators.length}
            </span>
        </h2>
        
        <button 
            onClick={() => reset()} // Reset ensures we go to Paste mode cleanly
            className="text-xs font-medium text-accent-main hover:text-accent-hover flex items-center gap-1"
        >
            <Plus size={12} /> Import New
        </button>
      </div>
      
      <div className="p-4 overflow-y-auto custom-scrollbar flex-1">
          {savedIndicators.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-text-muted text-sm space-y-2 opacity-60">
                  <Code size={40} />
                  <p>No custom indicators yet.</p>
              </div>
          ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {savedIndicators.map(ind => (
                      <IndicatorCard 
                        key={ind.id} 
                        indicator={ind} 
                        onEdit={loadIndicatorForEdit}
                        onDelete={deleteIndicator}
                      />
                  ))}
              </div>
          )}
      </div>
    </div>
  );
};
