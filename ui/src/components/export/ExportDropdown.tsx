import React, { useState } from "react";
import { Download, FileText, Table, Image, Code, Package } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Button } from "../ui/button";
import { useExportStore } from "../../stores/exportStore";
import { ExportConfigModal } from "./ExportConfigModal";
import { ExportFormat } from "../../stores/exportStore";

export const ExportDropdown: React.FC = () => {
  const { setExporting } = useExportStore();
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat | null>(null);

  const handleExportClick = (format: ExportFormat) => {
    setSelectedFormat(format);
    setShowConfigModal(true);
  };

  const exportOptions = [
    {
      format: "pdf" as ExportFormat,
      icon: FileText,
      label: "Full Report (PDF)",
      description: "Complete dashboard with charts",
    },
    {
      format: "csv" as ExportFormat,
      icon: Table,
      label: "Trades Only (CSV)",
      description: "All trades with annotations",
    },
    {
      format: "png" as ExportFormat,
      icon: Image,
      label: "Charts (PNG)",
      description: "Equity curve + drawdown",
    },
    {
      format: "json" as ExportFormat,
      icon: Code,
      label: "Raw Data (JSON)",
      description: "Full backtest data for analysis",
    },
  ];

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="flex items-center gap-2 text-xs font-medium"
          >
            <Download size={14} />
            Export
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          {exportOptions.map((option) => {
            const Icon = option.icon;
            return (
              <DropdownMenuItem
                key={option.format}
                onClick={() => handleExportClick(option.format)}
                className="flex flex-col items-start gap-1 py-3 cursor-pointer"
              >
                <div className="flex items-center gap-2 w-full">
                  <Icon size={16} className="text-accent-main" />
                  <span className="font-medium">{option.label}</span>
                </div>
                <span className="text-xs text-text-muted ml-6">
                  {option.description}
                </span>
              </DropdownMenuItem>
            );
          })}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => handleExportClick("zip")}
            className="flex flex-col items-start gap-1 py-3 cursor-pointer"
          >
            <div className="flex items-center gap-2 w-full">
              <Package size={16} className="text-accent-main" />
              <span className="font-medium">Export All (ZIP)</span>
            </div>
            <span className="text-xs text-text-muted ml-6">
              PDF + CSV + PNG + JSON
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {showConfigModal && selectedFormat && (
        <ExportConfigModal
          format={selectedFormat}
          onClose={() => {
            setShowConfigModal(false);
            setSelectedFormat(null);
          }}
        />
      )}
    </>
  );
};
