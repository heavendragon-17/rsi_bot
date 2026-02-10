import { create } from "zustand";
import { persist } from "zustand/middleware";

export type TradeTag = "star" | "review" | "learning" | "idea" | "lucky" | "unlucky";

export interface TradeAnnotation {
  tradeId: number;
  note: string;
  tags: TradeTag[];
  createdAt: string;
  updatedAt: string;
}

export type ExportFormat = "pdf" | "csv" | "png" | "json" | "zip";

export interface ExportConfig {
  fileName: string;
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
  theme: "current" | "light" | "dark";
}

export interface ExportState {
  // Export progress
  isExporting: boolean;
  exportFormat: ExportFormat | null;
  exportProgress: number;

  // Export config
  exportConfig: ExportConfig;

  // Annotations
  annotations: Record<number, TradeAnnotation>; // tradeId -> annotation
  editingTradeId: number | null;

  // Filters
  tagFilters: TradeTag[];
  showOnlyWithNotes: boolean;

  // Bulk selection
  selectedTradeIds: Set<number>;

  // Actions
  setExporting: (isExporting: boolean, format?: ExportFormat) => void;
  setExportProgress: (progress: number) => void;
  updateExportConfig: (config: Partial<ExportConfig>) => void;
  
  // Annotation actions
  addAnnotation: (tradeId: number, note: string, tags: TradeTag[]) => void;
  updateAnnotation: (tradeId: number, note: string, tags: TradeTag[]) => void;
  deleteAnnotation: (tradeId: number) => void;
  setEditingTrade: (tradeId: number | null) => void;
  
  // Filter actions
  toggleTagFilter: (tag: TradeTag) => void;
  clearTagFilters: () => void;
  setShowOnlyWithNotes: (show: boolean) => void;
  
  // Bulk actions
  toggleTradeSelection: (tradeId: number) => void;
  selectAllTrades: (tradeIds: number[]) => void;
  clearSelection: () => void;
  bulkAddTag: (tag: TradeTag) => void;
  bulkRemoveTag: (tag: TradeTag) => void;
}

export const useExportStore = create<ExportState>()(
  persist(
    (set, get) => ({
      // Initial state
      isExporting: false,
      exportFormat: null,
      exportProgress: 0,

      exportConfig: {
        fileName: "backtest_report",
        includeSections: {
          heroStats: true,
          equityCurve: true,
          drawdownChart: true,
          tradeList: true,
          parameterSettings: false,
          monthlyBreakdown: false,
        },
        pageSize: "a4",
        orientation: "portrait",
        theme: "current",
      },

      annotations: {},
      editingTradeId: null,

      tagFilters: [],
      showOnlyWithNotes: false,

      selectedTradeIds: new Set(),

      // Export actions
      setExporting: (isExporting, format) =>
        set({
          isExporting,
          exportFormat: format || null,
          exportProgress: isExporting ? 0 : 100,
        }),

      setExportProgress: (progress) => set({ exportProgress: progress }),

      updateExportConfig: (config) =>
        set((state) => ({
          exportConfig: { ...state.exportConfig, ...config },
        })),

      // Annotation actions
      addAnnotation: (tradeId, note, tags) =>
        set((state) => ({
          annotations: {
            ...state.annotations,
            [tradeId]: {
              tradeId,
              note,
              tags,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
          },
          editingTradeId: null,
        })),

      updateAnnotation: (tradeId, note, tags) =>
        set((state) => ({
          annotations: {
            ...state.annotations,
            [tradeId]: {
              ...state.annotations[tradeId],
              note,
              tags,
              updatedAt: new Date().toISOString(),
            },
          },
          editingTradeId: null,
        })),

      deleteAnnotation: (tradeId) =>
        set((state) => {
          const newAnnotations = { ...state.annotations };
          delete newAnnotations[tradeId];
          return { annotations: newAnnotations };
        }),

      setEditingTrade: (tradeId) => set({ editingTradeId: tradeId }),

      // Filter actions
      toggleTagFilter: (tag) =>
        set((state) => {
          const filters = state.tagFilters.includes(tag)
            ? state.tagFilters.filter((t) => t !== tag)
            : [...state.tagFilters, tag];
          return { tagFilters: filters };
        }),

      clearTagFilters: () => set({ tagFilters: [], showOnlyWithNotes: false }),

      setShowOnlyWithNotes: (show) => set({ showOnlyWithNotes: show }),

      // Bulk actions
      toggleTradeSelection: (tradeId) =>
        set((state) => {
          const newSelection = new Set(state.selectedTradeIds);
          if (newSelection.has(tradeId)) {
            newSelection.delete(tradeId);
          } else {
            newSelection.add(tradeId);
          }
          return { selectedTradeIds: newSelection };
        }),

      selectAllTrades: (tradeIds) =>
        set({ selectedTradeIds: new Set(tradeIds) }),

      clearSelection: () => set({ selectedTradeIds: new Set() }),

      bulkAddTag: (tag) =>
        set((state) => {
          const newAnnotations = { ...state.annotations };
          state.selectedTradeIds.forEach((tradeId) => {
            if (newAnnotations[tradeId]) {
              // Add tag if not already present
              if (!newAnnotations[tradeId].tags.includes(tag)) {
                newAnnotations[tradeId] = {
                  ...newAnnotations[tradeId],
                  tags: [...newAnnotations[tradeId].tags, tag],
                  updatedAt: new Date().toISOString(),
                };
              }
            } else {
              // Create new annotation with just the tag
              newAnnotations[tradeId] = {
                tradeId,
                note: "",
                tags: [tag],
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              };
            }
          });
          return { annotations: newAnnotations };
        }),

      bulkRemoveTag: (tag) =>
        set((state) => {
          const newAnnotations = { ...state.annotations };
          state.selectedTradeIds.forEach((tradeId) => {
            if (newAnnotations[tradeId]) {
              newAnnotations[tradeId] = {
                ...newAnnotations[tradeId],
                tags: newAnnotations[tradeId].tags.filter((t) => t !== tag),
                updatedAt: new Date().toISOString(),
              };
            }
          });
          return { annotations: newAnnotations };
        }),
    }),
    {
      name: "export-storage",
      partialize: (state) => ({
        annotations: state.annotations,
        exportConfig: state.exportConfig,
      }),
    }
  )
);
