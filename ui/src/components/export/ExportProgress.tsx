import React from "react";
import { Loader2 } from "lucide-react";
import { Progress } from "../ui/progress";
import { useExportStore, ExportFormat } from "../../stores/exportStore";

interface ExportProgressProps {
  format: ExportFormat;
}

export const ExportProgress: React.FC<ExportProgressProps> = ({ format }) => {
  const { exportProgress } = useExportStore();

  const formatLabels: Record<ExportFormat, string> = {
    pdf: "PDF report",
    csv: "CSV file",
    png: "PNG charts",
    json: "JSON data",
    zip: "ZIP archive",
  };

  return (
    <div className="flex flex-col items-center justify-center py-12 space-y-6">
      <Loader2 size={48} className="text-accent-main animate-spin" />
      
      <div className="text-center space-y-2">
        <p className="text-lg font-medium text-text-primary">
          Generating {formatLabels[format]}...
        </p>
        <p className="text-sm text-text-muted">
          This may take a few moments
        </p>
      </div>

      <div className="w-full max-w-md space-y-2">
        <Progress value={exportProgress} className="h-2" />
        <p className="text-xs text-text-muted text-center">
          {exportProgress}% complete
        </p>
      </div>
    </div>
  );
};
