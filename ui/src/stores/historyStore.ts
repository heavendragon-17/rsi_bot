import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface HistoryRun {
  id: number;
  runNumber: number;
  timestamp: string;
  strategyName: string;
  strategyVersion: string;
  symbol: string;
  isBatch: boolean;

  // Parameters snapshot
  parameters: {
    rsi_period?: number;
    ema_fast?: number;
    ema_slow?: number;
    tp1_rr?: number;
    tp2_rr?: number;
    sl_buffer_pct?: number;
    capital?: number;
    leverage?: number;
    riskPercent?: number;
    timeframe?: string;
    startDate?: string | null;
    endDate?: string | null;
    [key: string]: any;
  };

  // Results summary
  netPnL: number;
  netPnLPct: number;
  winRate: number;
  profitFactor: number;
  maxDrawdownPct: number;
  sharpeRatio: number;
  tradeCount: number;
}

interface Filters {
  strategy: string | null;
  symbol: string | null;
  dateRange: "today" | "7days" | "30days" | "all";
  profitableOnly: boolean;
  showBatchRuns: boolean;
  searchQuery: string;
}

export interface HistoryState {
  // Table
  runs: HistoryRun[];
  selectedRunIds: Set<number>;
  isLoading: boolean;

  // Pagination
  currentPage: number;
  itemsPerPage: number;

  // Filters
  filters: Filters;

  // Compare Modal
  compareModalOpen: boolean;
  compareRuns: [HistoryRun, HistoryRun] | null;

  // Restore Modal
  restoreModalOpen: boolean;
  runToRestore: HistoryRun | null;

  // Actions
  addRun: (run: Omit<HistoryRun, "id" | "runNumber" | "timestamp">) => void;
  toggleRunSelection: (id: number) => void;
  clearSelection: () => void;
  compareSelected: () => void;
  closeCompareModal: () => void;
  loadRun: (id: number) => void;
  confirmRestore: () => void;
  cancelRestore: () => void;
  deleteRuns: (ids: number[]) => void;
  clearAllHistory: () => void;
  setFilter: (key: keyof Filters, value: any) => void;
  setPage: (page: number) => void;
  getFilteredRuns: () => HistoryRun[];
  getPaginatedRuns: () => HistoryRun[];
  getTotalPages: () => number;
}

export const useHistoryStore = create<HistoryState>()(
  persist(
    (set, get) => ({
      runs: [],
      selectedRunIds: new Set(),
      isLoading: false,

      currentPage: 1,
      itemsPerPage: 20,

      filters: {
        strategy: null,
        symbol: null,
        dateRange: "all",
        profitableOnly: false,
        showBatchRuns: true,
        searchQuery: "",
      },

      compareModalOpen: false,
      compareRuns: null,

      restoreModalOpen: false,
      runToRestore: null,

      addRun: (runData) => {
        const runs = get().runs;
        const newRun: HistoryRun = {
          ...runData,
          id: runs.length > 0 ? Math.max(...runs.map((r) => r.id)) + 1 : 1,
          runNumber: runs.length > 0 ? Math.max(...runs.map((r) => r.runNumber)) + 1 : 1,
          timestamp: new Date().toISOString(),
        };
        set({ runs: [newRun, ...runs] });
      },

      toggleRunSelection: (id) => {
        const selectedRunIds = new Set(get().selectedRunIds);
        if (selectedRunIds.has(id)) {
          selectedRunIds.delete(id);
        } else {
          // Limit selection to 2 for comparison
          if (selectedRunIds.size >= 2) {
            // Remove the oldest selection
            const firstId = Array.from(selectedRunIds)[0];
            selectedRunIds.delete(firstId);
          }
          selectedRunIds.add(id);
        }
        set({ selectedRunIds });
      },

      clearSelection: () => {
        set({ selectedRunIds: new Set() });
      },

      compareSelected: () => {
        const { selectedRunIds, runs } = get();
        if (selectedRunIds.size === 2) {
          const selectedRuns = Array.from(selectedRunIds)
            .map((id) => runs.find((r) => r.id === id))
            .filter((r): r is HistoryRun => r !== undefined);

          if (selectedRuns.length === 2) {
            // Sort by run number (older first)
            selectedRuns.sort((a, b) => a.runNumber - b.runNumber);
            set({
              compareModalOpen: true,
              compareRuns: [selectedRuns[0], selectedRuns[1]],
            });
          }
        }
      },

      closeCompareModal: () => {
        set({ compareModalOpen: false, compareRuns: null });
      },

      loadRun: (id) => {
        const run = get().runs.find((r) => r.id === id);
        if (run) {
          set({ restoreModalOpen: true, runToRestore: run });
        }
      },

      confirmRestore: () => {
        // This will be handled by the component that needs to restore settings
        set({ restoreModalOpen: false, runToRestore: null });
      },

      cancelRestore: () => {
        set({ restoreModalOpen: false, runToRestore: null });
      },

      deleteRuns: (ids) => {
        const runs = get().runs.filter((r) => !ids.includes(r.id));
        const selectedRunIds = new Set(
          Array.from(get().selectedRunIds).filter((id) => !ids.includes(id))
        );
        set({ runs, selectedRunIds });
      },

      clearAllHistory: () => {
        set({ runs: [], selectedRunIds: new Set(), currentPage: 1 });
      },

      setFilter: (key, value) => {
        set((state) => ({
          filters: { ...state.filters, [key]: value },
          currentPage: 1, // Reset to first page when filtering
        }));
      },

      setPage: (page) => {
        set({ currentPage: page });
      },

      getFilteredRuns: () => {
        const { runs, filters } = get();
        let filtered = [...runs];

        // Filter by strategy
        if (filters.strategy) {
          filtered = filtered.filter((r) => r.strategyName === filters.strategy);
        }

        // Filter by symbol
        if (filters.symbol) {
          filtered = filtered.filter((r) => r.symbol === filters.symbol);
        }

        // Filter by date range
        if (filters.dateRange !== "all") {
          const now = new Date();
          const cutoff = new Date();

          if (filters.dateRange === "today") {
            cutoff.setHours(0, 0, 0, 0);
          } else if (filters.dateRange === "7days") {
            cutoff.setDate(now.getDate() - 7);
          } else if (filters.dateRange === "30days") {
            cutoff.setDate(now.getDate() - 30);
          }

          filtered = filtered.filter((r) => new Date(r.timestamp) >= cutoff);
        }

        // Filter profitable only
        if (filters.profitableOnly) {
          filtered = filtered.filter((r) => r.netPnL > 0);
        }

        // Filter batch runs
        if (!filters.showBatchRuns) {
          filtered = filtered.filter((r) => !r.isBatch);
        }

        // Search query
        if (filters.searchQuery) {
          const query = filters.searchQuery.toLowerCase();
          filtered = filtered.filter(
            (r) =>
              r.strategyName.toLowerCase().includes(query) ||
              r.symbol.toLowerCase().includes(query) ||
              r.runNumber.toString().includes(query)
          );
        }

        return filtered;
      },

      getPaginatedRuns: () => {
        const { currentPage, itemsPerPage } = get();
        const filtered = get().getFilteredRuns();
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        return filtered.slice(start, end);
      },

      getTotalPages: () => {
        const { itemsPerPage } = get();
        const filtered = get().getFilteredRuns();
        return Math.ceil(filtered.length / itemsPerPage);
      },
    }),
    {
      name: "run-history",
      partialize: (state) => ({
        runs: state.runs,
        filters: state.filters,
      }),
      // Restore Set from array during hydration
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.selectedRunIds = new Set();
        }
      },
    }
  )
);
