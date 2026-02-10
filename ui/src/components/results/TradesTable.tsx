import React, { useState } from "react";
import { useResultsStore, Trade } from "../../stores/resultsStore";
import { useExportStore, TradeTag } from "../../stores/exportStore";
import { cn } from "../../lib/utils";
import { 
  ChevronDown, 
  ChevronUp, 
  Edit, 
  Tag as TagIcon, 
  Star, 
  AlertTriangle, 
  BookOpen, 
  Lightbulb, 
  Clover, 
  Skull,
  StickyNote
} from "lucide-react";
import { AddNoteModal, NotePopover, TagFilter, BulkActionsBar } from "../export";
import { Checkbox } from "../ui/checkbox";
import { Button } from "../ui/button";

export const TradesTable: React.FC = () => {
  const { filteredTrades, activeFilter } = useResultsStore();
  const { 
    annotations, 
    toggleTradeSelection, 
    selectedTradeIds, 
    tagFilters, 
    showOnlyWithNotes 
  } = useExportStore();
  
  const [sortField, setSortField] = useState<keyof Trade>("id");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [currentPage, setCurrentPage] = useState(1);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const itemsPerPage = 25;

  // Tag icon mapping
  const tagIcons: Record<TradeTag, any> = {
    star: Star,
    review: AlertTriangle,
    learning: BookOpen,
    idea: Lightbulb,
    lucky: Clover,
    unlucky: Skull,
  };

  const tagColors: Record<TradeTag, string> = {
    star: "text-yellow-400",
    review: "text-orange-400",
    learning: "text-blue-400",
    idea: "text-purple-400",
    lucky: "text-green-400",
    unlucky: "text-red-400",
  };

  // Apply tag filters to trades
  const tagFilteredTrades = filteredTrades.filter((trade) => {
    const annotation = annotations[trade.id];
    
    // Filter by notes
    if (showOnlyWithNotes && !annotation?.note) {
      return false;
    }
    
    // Filter by tags
    if (tagFilters.length > 0) {
      if (!annotation) return false;
      return tagFilters.some((tag) => annotation.tags.includes(tag));
    }
    
    return true;
  });

  // Sorting
  const sortedTrades = [...tagFilteredTrades].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    
    if (typeof aVal === "string" && typeof bVal === "string") {
      return sortDirection === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    // @ts-ignore
    return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
  });

  // Pagination
  const totalPages = Math.ceil(sortedTrades.length / itemsPerPage);
  const currentTrades = sortedTrades.slice(
    (currentPage - 1) * itemsPerPage, 
    currentPage * itemsPerPage
  );

  const handleHeaderClick = (field: keyof Trade) => {
    if (sortField === field) {
      setSortDirection(prev => prev === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const SortIcon = ({ field }: { field: keyof Trade }) => {
    if (sortField !== field) return <div className="w-3 h-3" />;
    return sortDirection === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  return (
    <>
      <div className="flex flex-col h-full border border-border-main rounded-xl bg-bg-surface overflow-hidden">
        {/* Tag Filter */}
        <TagFilter filteredCount={tagFilteredTrades.length} totalCount={filteredTrades.length} />

        {/* Bulk Actions Bar */}
        <BulkActionsBar />

        {/* Header Filter Badge */}
        {activeFilter && (
          <div className="px-4 py-2 bg-accent-main/5 border-b border-border-main flex items-center justify-between">
            <span className="text-xs text-accent-main font-medium">
              Viewing {filteredTrades.length} trades filtered by <span className="font-bold">{activeFilter}</span>
            </span>
          </div>
        )}

        <div className="overflow-auto flex-1 custom-scrollbar">
          <table className="w-full text-left border-collapse">
            <thead className="bg-bg-elevated sticky top-0 z-10 text-[10px] font-semibold text-text-secondary uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 w-10">
                  <Checkbox
                    checked={currentTrades.length > 0 && currentTrades.every(t => selectedTradeIds.has(t.id))}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        currentTrades.forEach(t => {
                          if (!selectedTradeIds.has(t.id)) {
                            toggleTradeSelection(t.id);
                          }
                        });
                      } else {
                        currentTrades.forEach(t => {
                          if (selectedTradeIds.has(t.id)) {
                            toggleTradeSelection(t.id);
                          }
                        });
                      }
                    }}
                  />
                </th>
                {[
                  { key: "id", label: "#", w: "w-10" },
                  { key: "entryTime", label: "Entry Time", w: "w-32" },
                  { key: "symbol", label: "Symbol", w: "w-20" },
                  { key: "side", label: "Side", w: "w-16" },
                  { key: "entryPrice", label: "Entry $", w: "w-24 text-right" },
                  { key: "exitPrice", label: "Exit $", w: "w-24 text-right" },
                  { key: "pnl", label: "PnL", w: "w-24 text-right" },
                  { key: "exitReason", label: "Exit Reason", w: "w-24" },
                  { key: "tags", label: "Tags", w: "w-20" },
                  { key: "notes", label: "Notes", w: "w-16" },
                  { key: "actions", label: "Actions", w: "w-24" },
                ].map(col => (
                  <th 
                    key={col.key}
                    onClick={() => {
                      if (col.key !== "tags" && col.key !== "notes" && col.key !== "actions") {
                        handleHeaderClick(col.key as keyof Trade);
                      }
                    }}
                    className={cn(
                      "px-4 py-3 select-none",
                      col.key !== "tags" && col.key !== "notes" && col.key !== "actions" && "cursor-pointer hover:bg-bg-elevated/80 transition-colors",
                      col.w
                    )}
                  >
                    <div className={cn("flex items-center gap-1", col.w.includes("right") && "justify-end")}>
                      {col.label}
                      {col.key !== "tags" && col.key !== "notes" && col.key !== "actions" && (
                        <SortIcon field={col.key as keyof Trade} />
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-sm font-mono text-text-primary divide-y divide-border-main/30">
              {currentTrades.map((trade) => {
                const isWin = trade.pnl >= 0;
                const annotation = annotations[trade.id];
                const isSelected = selectedTradeIds.has(trade.id);
                
                return (
                  <tr 
                    key={trade.id} 
                    className={cn(
                      "group hover:bg-bg-elevated/30 transition-colors",
                      isSelected && "bg-accent-main/10"
                    )}
                  >
                    <td className="px-4 py-2.5">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => toggleTradeSelection(trade.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td className="px-4 py-2.5 text-text-muted">{trade.id}</td>
                    <td className="px-4 py-2.5 text-xs text-text-secondary">{trade.entryTime}</td>
                    <td className="px-4 py-2.5 font-medium">{trade.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-bold border",
                        trade.side === "LONG" 
                          ? "bg-success/10 text-success border-success/20" 
                          : "bg-danger/10 text-danger border-danger/20"
                      )}>
                        {trade.side}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-text-secondary">
                      ${trade.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-2.5 text-right text-text-secondary">
                      ${trade.exitPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className={cn("px-4 py-2.5 text-right font-bold", isWin ? "text-success" : "text-danger")}>
                      {isWin ? "+" : ""}{trade.pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={cn(
                        "px-2 py-0.5 rounded-full text-[10px] font-medium border",
                        trade.exitReason.includes("SL") 
                          ? "border-danger/30 text-danger bg-danger/5"
                          : trade.exitReason === "MANUAL"
                          ? "border-text-muted text-text-muted"
                          : "border-success/30 text-success bg-success/5"
                      )}>
                        {trade.exitReason}
                      </span>
                    </td>
                    
                    {/* Tags Column */}
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1">
                        {annotation?.tags.slice(0, 3).map((tag) => {
                          const Icon = tagIcons[tag];
                          const color = tagColors[tag];
                          return (
                            <Icon key={tag} size={14} className={color} />
                          );
                        })}
                        {annotation && annotation.tags.length > 3 && (
                          <span className="text-xs text-text-muted">+{annotation.tags.length - 3}</span>
                        )}
                      </div>
                    </td>
                    
                    {/* Notes Column */}
                    <td className="px-4 py-2.5">
                      {annotation?.note && (
                        <NotePopover
                          annotation={annotation}
                          onEdit={() => setEditingTrade(trade)}
                          onClose={() => {}}
                        >
                          <button className="text-accent-main hover:text-accent-main/80 transition-colors">
                            <StickyNote size={14} />
                          </button>
                        </NotePopover>
                      )}
                    </td>
                    
                    {/* Actions Column */}
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTrade(trade);
                          }}
                        >
                          <Edit size={14} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex items-center justify-between px-4 py-3 bg-bg-elevated border-t border-border-main text-xs text-text-secondary">
          <span>
            Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, sortedTrades.length)} of {sortedTrades.length} trades
          </span>
          <div className="flex gap-2">
            <button 
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(p => p - 1)}
              className="px-2 py-1 rounded border border-border-main hover:bg-bg-surface disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Prev
            </button>
            <span className="flex items-center px-2">{currentPage} / {totalPages}</span>
            <button 
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(p => p + 1)}
              className="px-2 py-1 rounded border border-border-main hover:bg-bg-surface disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Add/Edit Note Modal */}
      {editingTrade && (
        <AddNoteModal
          trade={editingTrade}
          onClose={() => setEditingTrade(null)}
        />
      )}
    </>
  );
};
