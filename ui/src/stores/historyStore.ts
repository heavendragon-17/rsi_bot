import { create } from "zustand";
import { toast } from "sonner";
import { fetchHistory, deleteRun as apiDeleteRun } from "../api";
import type { HistoryFilters } from "../api";

// ---------------------------------------------------------------------------
// HistoryRun — display type used by HistoryRow/HistoryTable
// Mapped from API RunSummary at fetch time.
// ---------------------------------------------------------------------------

export interface HistoryRun {
  id: number;
  runNumber: number;
  timestamp: string;
  strategyName: string;
  strategyVersion: string;
  symbol: string;
  isBatch: boolean;

  parameters: {
    timeframe?: string;
    capital?: number;
    leverage?: number;
    [key: string]: unknown;
  };

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
  // Table data (server-paged)
  runs: HistoryRun[];
  selectedRunIds: Set<number>;
  isLoading: boolean;

  // Server-side pagination
  currentPage: number;
  itemsPerPage: number;
  totalPages: number;
  totalCount: number;

  // Filters (sent to server)
  filters: Filters;

  // Compare Modal
  compareModalOpen: boolean;
  compareRuns: [HistoryRun, HistoryRun] | null;

  // Restore Modal
  restoreModalOpen: boolean;
  runToRestore: HistoryRun | null;

  // API-backed actions
  fetchRuns: (overrides?: Partial<HistoryFilters>) => Promise<void>;
  deleteRuns: (ids: number[]) => Promise<void>;

  // Local UI actions (kept)
  toggleRunSelection: (id: number) => void;
  clearSelection: () => void;
  compareSelected: () => void;
  closeCompareModal: () => void;
  loadRun: (id: number) => void;
  confirmRestore: () => void;
  cancelRestore: () => void;
  setFilter: (key: keyof Filters, value: unknown) => void;
  setPage: (page: number) => void;

  // Shims for HistoryTable backward-compat (server already paginates/filters)
  getPaginatedRuns: () => HistoryRun[];
  getFilteredRuns: () => HistoryRun[];
  getTotalPages: () => number;
}

// ---------------------------------------------------------------------------
// Helper: map API RunSummary -> HistoryRun display type
// ---------------------------------------------------------------------------

function mapToHistoryRun(r: {
  id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  created_at: string;
  initial_capital: string;
  leverage: number;
  net_profit: string | null;
  net_profit_pct: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  total_trades: number | null;
}): HistoryRun {
  return {
    id: r.id,
    runNumber: r.id,
    timestamp: r.created_at,
    strategyName: r.strategy_name,
    strategyVersion: "v1.0",
    symbol: r.symbol,
    isBatch: false,
    parameters: {
      timeframe: r.timeframe,
      capital: parseFloat(r.initial_capital) || 0,
      leverage: r.leverage,
    },
    netPnL: r.net_profit !== null ? parseFloat(r.net_profit) : 0,
    netPnLPct: r.net_profit_pct ?? 0,
    winRate: r.win_rate ?? 0,
    profitFactor: r.profit_factor ?? 0,
    maxDrawdownPct: r.max_drawdown_pct ?? 0,
    sharpeRatio: r.sharpe_ratio ?? 0,
    tradeCount: r.total_trades ?? 0,
  };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useHistoryStore = create<HistoryState>()((set, get) => ({
  runs: [],
  selectedRunIds: new Set(),
  isLoading: false,

  currentPage: 1,
  itemsPerPage: 20,
  totalPages: 0,
  totalCount: 0,

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

  // -- API-backed --

  fetchRuns: async (overrides = {}) => {
    set({ isLoading: true });
    try {
      const { currentPage, itemsPerPage, filters: f } = get();
      const response = await fetchHistory({
        page: currentPage,
        limit: itemsPerPage,
        strategy: f.strategy ?? undefined,
        symbol: f.symbol ?? undefined,
        profitable_only: f.profitableOnly || undefined,
        date_range: f.dateRange !== "all" ? f.dateRange : undefined,
        search: f.searchQuery || undefined,
        ...overrides,
      });
      set({
        runs: response.runs.map(mapToHistoryRun),
        totalPages: response.pages,
        totalCount: response.total,
        isLoading: false,
      });
    } catch {
      set({ isLoading: false });
      toast.error("Failed to load history");
    }
  },

  deleteRuns: async (ids) => {
    try {
      for (const id of ids) {
        await apiDeleteRun(id);
      }
      const selectedRunIds = new Set(
        Array.from(get().selectedRunIds).filter((id) => !ids.includes(id)),
      );
      set({ selectedRunIds });
      await get().fetchRuns();
    } catch {
      toast.error("Failed to delete run(s)");
    }
  },

  // -- Local UI --

  toggleRunSelection: (id) => {
    const selectedRunIds = new Set(get().selectedRunIds);
    if (selectedRunIds.has(id)) {
      selectedRunIds.delete(id);
    } else {
      if (selectedRunIds.size >= 2) {
        const firstId = Array.from(selectedRunIds)[0];
        selectedRunIds.delete(firstId);
      }
      selectedRunIds.add(id);
    }
    set({ selectedRunIds });
  },

  clearSelection: () => set({ selectedRunIds: new Set() }),

  compareSelected: () => {
    const { selectedRunIds, runs } = get();
    if (selectedRunIds.size === 2) {
      const selected = Array.from(selectedRunIds)
        .map((id) => runs.find((r) => r.id === id))
        .filter((r): r is HistoryRun => r !== undefined);
      if (selected.length === 2) {
        selected.sort((a, b) => a.runNumber - b.runNumber);
        set({ compareModalOpen: true, compareRuns: [selected[0], selected[1]] });
      }
    }
  },

  closeCompareModal: () => set({ compareModalOpen: false, compareRuns: null }),

  loadRun: (id) => {
    const run = get().runs.find((r) => r.id === id);
    if (run) set({ restoreModalOpen: true, runToRestore: run });
  },

  confirmRestore: () => set({ restoreModalOpen: false, runToRestore: null }),
  cancelRestore: () => set({ restoreModalOpen: false, runToRestore: null }),

  setFilter: (key, value) => {
    set((state) => ({
      filters: { ...state.filters, [key]: value },
      currentPage: 1,
    }));
  },

  setPage: (page) => set({ currentPage: page }),

  // -- Backward-compat shims (server already paginates/filters) --
  getPaginatedRuns: () => get().runs,
  getFilteredRuns: () => get().runs,
  getTotalPages: () => get().totalPages,
}));
