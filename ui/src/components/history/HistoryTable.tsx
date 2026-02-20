import React from "react";
import { useHistoryStore } from "../../stores/historyStore";
import { HistoryRow } from "./HistoryRow";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "../ui/pagination";
import { Checkbox } from "../ui/checkbox";

export const HistoryTable: React.FC = () => {
  const {
    getPaginatedRuns,
    getFilteredRuns,
    getTotalPages,
    currentPage,
    setPage,
    itemsPerPage,
    selectedRunIds,
    toggleRunSelection,
    clearSelection,
  } = useHistoryStore();

  const paginatedRuns = getPaginatedRuns();
  const filteredRuns = getFilteredRuns();
  const totalPages = getTotalPages();

  const startIndex = (currentPage - 1) * itemsPerPage + 1;
  const endIndex = Math.min(currentPage * itemsPerPage, filteredRuns.length);

  // Check if all visible runs are selected
  const allVisibleSelected =
    paginatedRuns.length > 0 &&
    paginatedRuns.every((run) => selectedRunIds.has(run.id));

  const handleSelectAll = () => {
    if (allVisibleSelected) {
      clearSelection();
    } else {
      paginatedRuns.forEach((run) => {
        if (!selectedRunIds.has(run.id)) {
          toggleRunSelection(run.id);
        }
      });
    }
  };

  // Generate page numbers to display
  const generatePageNumbers = () => {
    const pages: (number | "ellipsis")[] = [];
    const maxVisiblePages = 5;

    if (totalPages <= maxVisiblePages) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Always show first page
      pages.push(1);

      if (currentPage > 3) {
        pages.push("ellipsis");
      }

      // Show pages around current page
      const start = Math.max(2, currentPage - 1);
      const end = Math.min(totalPages - 1, currentPage + 1);

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (currentPage < totalPages - 2) {
        pages.push("ellipsis");
      }

      // Always show last page
      pages.push(totalPages);
    }

    return pages;
  };

  if (filteredRuns.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 rounded-full bg-bg-elevated flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">📜</span>
          </div>
          <h3 className="text-lg font-medium text-text-primary mb-2">No runs found</h3>
          <p className="text-sm text-text-muted">
            Try adjusting your filters or run a backtest to see results here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-bg-secondary border-b border-border-main/50 z-10">
            <tr>
              <th className="w-12 px-4 py-3 text-left">
                <Checkbox
                  checked={allVisibleSelected}
                  onCheckedChange={handleSelectAll}
                  className="border-border-main"
                />
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Run #
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Date/Time
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Strategy
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Net PnL
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Win Rate
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-main/30">
            {paginatedRuns.map((run) => (
              <HistoryRow key={run.id} run={run} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="px-6 py-4 border-t border-border-main/50 bg-bg-surface/30 flex items-center justify-between">
        <div className="text-sm text-text-muted">
          Showing {startIndex}-{endIndex} of {filteredRuns.length} runs
        </div>

        {totalPages > 1 && (
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => currentPage > 1 && setPage(currentPage - 1)}
                  className={
                    currentPage === 1
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer hover:bg-bg-elevated"
                  }
                />
              </PaginationItem>

              {generatePageNumbers().map((page, index) =>
                page === "ellipsis" ? (
                  <PaginationItem key={`ellipsis-${index}`}>
                    <PaginationEllipsis />
                  </PaginationItem>
                ) : (
                  <PaginationItem key={page}>
                    <PaginationLink
                      onClick={() => setPage(page)}
                      isActive={currentPage === page}
                      className="cursor-pointer"
                    >
                      {page}
                    </PaginationLink>
                  </PaginationItem>
                )
              )}

              <PaginationItem>
                <PaginationNext
                  onClick={() => currentPage < totalPages && setPage(currentPage + 1)}
                  className={
                    currentPage === totalPages
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer hover:bg-bg-elevated"
                  }
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        )}
      </div>
    </div>
  );
};
