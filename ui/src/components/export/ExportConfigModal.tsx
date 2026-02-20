import React, { useState } from "react";
import { X, FileText } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Checkbox } from "../ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { useExportStore, ExportFormat } from "../../stores/exportStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { useResultsStore } from "../../stores/resultsStore";
import { ExportProgress } from "./ExportProgress";
import {
  exportToCSV,
  exportToJSON,
  exportChartToPNG,
  exportToPDF,
  exportToZIP,
  ExportData,
} from "../../lib/export-utils";
import { toast } from "sonner";

interface ExportConfigModalProps {
  format: ExportFormat;
  onClose: () => void;
}

export const ExportConfigModal: React.FC<ExportConfigModalProps> = ({
  format,
  onClose,
}) => {
  const { exportConfig, updateExportConfig, annotations, setExporting, setExportProgress } =
    useExportStore();
  const { strategy, symbol, timeframe } = useBacktestStore();
  const resultsStore = useResultsStore();

  const [localConfig, setLocalConfig] = useState(exportConfig);
  const [isExporting, setIsExportingLocal] = useState(false);

  const formatLabels: Record<ExportFormat, string> = {
    pdf: "Full Report (PDF)",
    csv: "Trades Only (CSV)",
    png: "Charts (PNG)",
    json: "Raw Data (JSON)",
    zip: "Export All (ZIP)",
  };

  const handleGenerate = async () => {
    setIsExportingLocal(true);
    setExporting(true, format);

    const exportData: ExportData = {
      strategy,
      symbol,
      timeframe,
      netProfit: resultsStore.netProfit,
      netProfitPct: resultsStore.netProfitPct,
      winRate: resultsStore.winRate,
      profitFactor: resultsStore.profitFactor,
      maxDrawdownPct: resultsStore.maxDrawdownPct,
      sharpeRatio: resultsStore.sharpeRatio,
      trades: resultsStore.trades,
      annotations,
    };

    try {
      switch (format) {
        case "csv":
          exportToCSV(resultsStore.trades, annotations, localConfig.fileName);
          toast.success("CSV exported successfully!");
          break;

        case "json":
          exportToJSON(exportData, localConfig.fileName);
          toast.success("JSON exported successfully!");
          break;

        case "png":
          await exportChartToPNG("equity-chart", `${localConfig.fileName}_equity`);
          await exportChartToPNG("drawdown-chart", `${localConfig.fileName}_drawdown`);
          toast.success("Charts exported successfully!");
          break;

        case "pdf":
          await exportToPDF(
            exportData,
            {
              includeSections: localConfig.includeSections,
              pageSize: localConfig.pageSize,
              orientation: localConfig.orientation,
            },
            localConfig.fileName,
            (progress) => setExportProgress(progress)
          );
          toast.success("PDF exported successfully!");
          break;

        case "zip":
          await exportToZIP(
            exportData,
            localConfig,
            localConfig.fileName,
            (progress) => setExportProgress(progress)
          );
          toast.success("ZIP archive exported successfully!");
          break;
      }

      // Save config for next time
      updateExportConfig(localConfig);

      // Close modal after a brief delay
      setTimeout(() => {
        onClose();
      }, 500);
    } catch (error) {
      console.error("Export failed:", error);
      toast.error("Export failed. Please try again.");
    } finally {
      setIsExportingLocal(false);
      setExporting(false);
    }
  };

  const showSectionOptions = format === "pdf" || format === "zip";

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl bg-bg-surface border-border-main">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <FileText size={20} className="text-accent-main" />
              EXPORT: {formatLabels[format]}
            </span>
          </DialogTitle>
        </DialogHeader>

        {isExporting ? (
          <ExportProgress format={format} />
        ) : (
          <div className="space-y-6 py-4">
            {/* File Name */}
            <div className="space-y-2">
              <Label className="text-sm font-medium text-text-primary">
                FILE NAME
              </Label>
              <Input
                value={localConfig.fileName}
                onChange={(e) =>
                  setLocalConfig({ ...localConfig, fileName: e.target.value })
                }
                placeholder="backtest_report"
                className="bg-bg-elevated border-border-main"
              />
            </div>

            {/* Include Sections (PDF/ZIP only) */}
            {showSectionOptions && (
              <div className="space-y-2">
                <Label className="text-sm font-medium text-text-primary">
                  INCLUDE SECTIONS
                </Label>
                <div className="space-y-3 p-4 border border-border-main rounded-lg bg-bg-elevated">
                  {[
                    { key: "heroStats", label: "Hero Statistics" },
                    { key: "equityCurve", label: "Equity Curve" },
                    { key: "drawdownChart", label: "Drawdown Chart" },
                    { key: "tradeList", label: "Trade List (with annotations)" },
                    { key: "parameterSettings", label: "Parameter Settings" },
                    { key: "monthlyBreakdown", label: "Monthly Breakdown" },
                  ].map((section) => (
                    <div key={section.key} className="flex items-center gap-2">
                      <Checkbox
                        id={section.key}
                        checked={
                          localConfig.includeSections[
                            section.key as keyof typeof localConfig.includeSections
                          ]
                        }
                        onCheckedChange={(checked) =>
                          setLocalConfig({
                            ...localConfig,
                            includeSections: {
                              ...localConfig.includeSections,
                              [section.key]: checked,
                            },
                          })
                        }
                      />
                      <Label
                        htmlFor={section.key}
                        className="text-sm text-text-secondary cursor-pointer"
                      >
                        {section.label}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Page Size & Orientation (PDF only) */}
            {format === "pdf" && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium text-text-primary">
                    PAGE SIZE
                  </Label>
                  <Select
                    value={localConfig.pageSize}
                    onValueChange={(value: "a4" | "letter") =>
                      setLocalConfig({ ...localConfig, pageSize: value })
                    }
                  >
                    <SelectTrigger className="bg-bg-elevated border-border-main">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="a4">A4</SelectItem>
                      <SelectItem value="letter">Letter</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="text-sm font-medium text-text-primary">
                    ORIENTATION
                  </Label>
                  <Select
                    value={localConfig.orientation}
                    onValueChange={(value: "portrait" | "landscape") =>
                      setLocalConfig({ ...localConfig, orientation: value })
                    }
                  >
                    <SelectTrigger className="bg-bg-elevated border-border-main">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="portrait">Portrait</SelectItem>
                      <SelectItem value="landscape">Landscape</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button onClick={handleGenerate} className="gap-2">
                Generate {formatLabels[format].split(" ")[0]}
                <FileText size={16} />
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
