import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import Papa from "papaparse";
import JSZip from "jszip";
import { Trade } from "../stores/resultsStore";
import { TradeAnnotation } from "../stores/exportStore";

export interface ExportData {
  strategy: string;
  symbol: string;
  timeframe: string;
  netProfit: number;
  netProfitPct: number;
  winRate: number;
  profitFactor: number;
  maxDrawdownPct: number;
  sharpeRatio: number;
  trades: Trade[];
  annotations: Record<number, TradeAnnotation>;
}

/**
 * Export trades to CSV with annotations
 */
export function exportToCSV(
  trades: Trade[],
  annotations: Record<number, TradeAnnotation>,
  fileName: string
): void {
  const data = trades.map((trade) => {
    const annotation = annotations[trade.id];
    return {
      ID: trade.id,
      "Entry Time": trade.entryTime,
      "Exit Time": trade.exitTime,
      Symbol: trade.symbol,
      Side: trade.side,
      "Entry Price": trade.entryPrice.toFixed(4),
      "Exit Price": trade.exitPrice.toFixed(4),
      Size: trade.size,
      PnL: trade.pnl.toFixed(2),
      "PnL %": trade.pnlPct.toFixed(2),
      "Exit Reason": trade.exitReason,
      Fees: trade.fees.toFixed(2),
      Tags: annotation?.tags.join(", ") || "",
      Notes: annotation?.note || "",
    };
  });

  const csv = Papa.unparse(data);
  downloadFile(csv, `${fileName}.csv`, "text/csv");
}

/**
 * Export to JSON
 */
export function exportToJSON(data: ExportData, fileName: string): void {
  const json = JSON.stringify(data, null, 2);
  downloadFile(json, `${fileName}.json`, "application/json");
}

/**
 * Export chart as PNG
 */
export async function exportChartToPNG(
  elementId: string,
  fileName: string
): Promise<void> {
  const element = document.getElementById(elementId);
  if (!element) {
    console.error(`Element with id "${elementId}" not found`);
    return;
  }

  const canvas = await html2canvas(element, {
    backgroundColor: "#0a0e14",
    scale: 2,
  });

  canvas.toBlob((blob) => {
    if (blob) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${fileName}.png`;
      link.click();
      URL.revokeObjectURL(url);
    }
  });
}

/**
 * Export full report as PDF
 */
export async function exportToPDF(
  data: ExportData,
  config: {
    includeSections: {
      heroStats: boolean;
      equityCurve: boolean;
      drawdownChart: boolean;
      tradeList: boolean;
      parameterSettings: boolean;
      monthlyBreakdown: boolean;
    };
    pageSize: "a4" | "letter";
    orientation: "portrait" | "landscape";
  },
  fileName: string,
  onProgress?: (progress: number) => void
): Promise<void> {
  const pdf = new jsPDF({
    orientation: config.orientation,
    unit: "mm",
    format: config.pageSize,
  });

  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  let yPos = 20;

  // Title
  pdf.setFontSize(20);
  pdf.setTextColor(255, 255, 255);
  pdf.text(`${data.strategy} - ${data.symbol}`, 20, yPos);
  yPos += 10;

  pdf.setFontSize(12);
  pdf.setTextColor(180, 180, 180);
  pdf.text(`Timeframe: ${data.timeframe}`, 20, yPos);
  yPos += 15;

  onProgress?.(20);

  // Hero Stats
  if (config.includeSections.heroStats) {
    pdf.setFontSize(14);
    pdf.setTextColor(255, 255, 255);
    pdf.text("Performance Summary", 20, yPos);
    yPos += 8;

    pdf.setFontSize(10);
    pdf.setTextColor(200, 200, 200);
    
    const stats = [
      `Net Profit: $${data.netProfit.toFixed(2)} (${data.netProfitPct.toFixed(2)}%)`,
      `Win Rate: ${data.winRate.toFixed(2)}%`,
      `Profit Factor: ${data.profitFactor.toFixed(2)}`,
      `Max Drawdown: ${data.maxDrawdownPct.toFixed(2)}%`,
      `Sharpe Ratio: ${data.sharpeRatio.toFixed(2)}`,
      `Total Trades: ${data.trades.length}`,
    ];

    stats.forEach((stat) => {
      pdf.text(stat, 25, yPos);
      yPos += 6;
    });
    yPos += 10;
  }

  onProgress?.(40);

  // Charts (if sections enabled)
  if (config.includeSections.equityCurve) {
    try {
      const equityElement = document.getElementById("equity-chart");
      if (equityElement) {
        const canvas = await html2canvas(equityElement, { scale: 1 });
        const imgData = canvas.toDataURL("image/png");
        
        if (yPos + 80 > pageHeight) {
          pdf.addPage();
          yPos = 20;
        }
        
        pdf.text("Equity Curve", 20, yPos);
        yPos += 5;
        pdf.addImage(imgData, "PNG", 20, yPos, pageWidth - 40, 70);
        yPos += 80;
      }
    } catch (err) {
      console.error("Failed to capture equity chart:", err);
    }
  }

  onProgress?.(60);

  if (config.includeSections.drawdownChart) {
    try {
      const drawdownElement = document.getElementById("drawdown-chart");
      if (drawdownElement) {
        const canvas = await html2canvas(drawdownElement, { scale: 1 });
        const imgData = canvas.toDataURL("image/png");
        
        if (yPos + 80 > pageHeight) {
          pdf.addPage();
          yPos = 20;
        }
        
        pdf.text("Drawdown", 20, yPos);
        yPos += 5;
        pdf.addImage(imgData, "PNG", 20, yPos, pageWidth - 40, 70);
        yPos += 80;
      }
    } catch (err) {
      console.error("Failed to capture drawdown chart:", err);
    }
  }

  onProgress?.(80);

  // Trade List
  if (config.includeSections.tradeList) {
    if (yPos + 40 > pageHeight) {
      pdf.addPage();
      yPos = 20;
    }

    pdf.setFontSize(14);
    pdf.setTextColor(255, 255, 255);
    pdf.text("Trade List", 20, yPos);
    yPos += 8;

    pdf.setFontSize(8);
    pdf.setTextColor(200, 200, 200);

    // Table header
    const cols = ["#", "Entry", "Exit", "Side", "PnL", "Exit Reason", "Tags"];
    let xPos = 20;
    cols.forEach((col, i) => {
      pdf.text(col, xPos, yPos);
      xPos += i === 0 ? 10 : i < 3 ? 30 : 25;
    });
    yPos += 5;

    // Show first 50 trades
    const tradesToShow = data.trades.slice(0, 50);
    tradesToShow.forEach((trade) => {
      if (yPos > pageHeight - 15) {
        pdf.addPage();
        yPos = 20;
      }

      const annotation = data.annotations[trade.id];
      xPos = 20;
      
      pdf.text(String(trade.id), xPos, yPos);
      xPos += 10;
      pdf.text(trade.entryTime, xPos, yPos);
      xPos += 30;
      pdf.text(trade.exitTime, xPos, yPos);
      xPos += 30;
      pdf.text(trade.side, xPos, yPos);
      xPos += 25;
      
      const pnlColor = trade.pnl >= 0 ? [0, 255, 0] : [255, 0, 0];
      pdf.setTextColor(pnlColor[0], pnlColor[1], pnlColor[2]);
      pdf.text(`$${trade.pnl.toFixed(2)}`, xPos, yPos);
      pdf.setTextColor(200, 200, 200);
      xPos += 25;
      
      pdf.text(trade.exitReason, xPos, yPos);
      xPos += 25;
      pdf.text(annotation?.tags.join(", ") || "", xPos, yPos);
      
      yPos += 5;
    });

    if (data.trades.length > 50) {
      yPos += 3;
      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`... and ${data.trades.length - 50} more trades`, 20, yPos);
    }
  }

  onProgress?.(100);

  // Save PDF
  pdf.save(`${fileName}.pdf`);
}

/**
 * Export all formats as ZIP
 */
export async function exportToZIP(
  data: ExportData,
  config: any,
  fileName: string,
  onProgress?: (progress: number) => void
): Promise<void> {
  const zip = new JSZip();

  onProgress?.(10);

  // Add CSV
  const csvData = data.trades.map((trade) => {
    const annotation = data.annotations[trade.id];
    return {
      ID: trade.id,
      "Entry Time": trade.entryTime,
      "Exit Time": trade.exitTime,
      Symbol: trade.symbol,
      Side: trade.side,
      "Entry Price": trade.entryPrice.toFixed(4),
      "Exit Price": trade.exitPrice.toFixed(4),
      Size: trade.size,
      PnL: trade.pnl.toFixed(2),
      "PnL %": trade.pnlPct.toFixed(2),
      "Exit Reason": trade.exitReason,
      Fees: trade.fees.toFixed(2),
      Tags: annotation?.tags.join(", ") || "",
      Notes: annotation?.note || "",
    };
  });
  const csv = Papa.unparse(csvData);
  zip.file("trades.csv", csv);

  onProgress?.(30);

  // Add JSON
  const json = JSON.stringify(data, null, 2);
  zip.file("backtest_data.json", json);

  onProgress?.(50);

  // Add charts as PNG
  try {
    const equityElement = document.getElementById("equity-chart");
    if (equityElement) {
      const canvas = await html2canvas(equityElement, { scale: 2 });
      const blob = await new Promise<Blob>((resolve) =>
        canvas.toBlob((b) => resolve(b!))
      );
      zip.file("equity_curve.png", blob);
    }
  } catch (err) {
    console.error("Failed to capture equity chart:", err);
  }

  onProgress?.(70);

  try {
    const drawdownElement = document.getElementById("drawdown-chart");
    if (drawdownElement) {
      const canvas = await html2canvas(drawdownElement, { scale: 2 });
      const blob = await new Promise<Blob>((resolve) =>
        canvas.toBlob((b) => resolve(b!))
      );
      zip.file("drawdown.png", blob);
    }
  } catch (err) {
    console.error("Failed to capture drawdown chart:", err);
  }

  onProgress?.(90);

  // Generate ZIP
  const content = await zip.generateAsync({ type: "blob" });
  downloadFile(content, `${fileName}.zip`, "application/zip");

  onProgress?.(100);
}

/**
 * Helper to trigger file download
 */
function downloadFile(
  content: string | Blob,
  fileName: string,
  mimeType: string
): void {
  const blob =
    content instanceof Blob ? content : new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
