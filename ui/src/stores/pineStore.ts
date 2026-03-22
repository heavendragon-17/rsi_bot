import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ParsedIndicator, parsePineScript, PineParameter, ParseError, ParseWarning } from "../lib/pine-parser";

export interface SavedIndicator {
  id: string;
  name: string;
  type: "oscillator" | "overlay";
  parameters: PineParameter[];
  rawCode: string;
  createdAt: string;
  status: "ready" | "warning" | "error";
}

interface PineStoreState {
  step: "paste" | "verify" | "save";

  // Input
  rawCode: string;

  // Parsed Data
  parsedIndicator: ParsedIndicator | null;
  parameterOverrides: Record<string, any>;

  // Library
  savedIndicators: SavedIndicator[];

  // Actions
  setRawCode: (code: string) => void;
  parseCode: () => void;
  updateParameterOverride: (paramId: string, value: any) => void;
  saveIndicator: () => void;
  deleteIndicator: (id: string) => void;
  reset: () => void;
  loadIndicatorForEdit: (id: string) => void;
}

export const usePineStore = create<PineStoreState>()(
  persist(
    (set, get) => ({
      step: "paste",
      rawCode: "",
      parsedIndicator: null,
      parameterOverrides: {},
      savedIndicators: [
          // Pre-populate with a demo indicator
          {
              id: "demo-rsi",
              name: "Classic RSI",
              type: "oscillator",
              parameters: [
                  { id: "p1", name: "Length", variableName: "len", type: "int", defaultValue: 14, pineSource: "input(14)" },
                  { id: "p2", name: "Source", variableName: "src", type: "source", defaultValue: "close", pineSource: "input(close)" }
              ],
              rawCode: "// Demo RSI\nindicator('Classic RSI')",
              createdAt: new Date().toISOString(),
              status: "ready"
          }
      ],

      setRawCode: (code) => set({ rawCode: code }),

      parseCode: () => {
        const { rawCode } = get();
        if (!rawCode.trim()) return;

        const result = parsePineScript(rawCode);

        // Initialize overrides with defaults
        const overrides: Record<string, any> = {};
        result.parameters.forEach(p => {
            overrides[p.id] = p.defaultValue;
        });

        set({
            parsedIndicator: result,
            parameterOverrides: overrides,
            step: "verify"
        });
      },

      updateParameterOverride: (paramId, value) => set(state => ({
          parameterOverrides: { ...state.parameterOverrides, [paramId]: value }
      })),

      saveIndicator: () => {
          const { parsedIndicator, rawCode, parameterOverrides, savedIndicators } = get();
          if (!parsedIndicator) return;

          // Merge overrides into parameters for storage
          const finalParams = parsedIndicator.parameters.map(p => ({
              ...p,
              defaultValue: parameterOverrides[p.id] ?? p.defaultValue
          }));

          const newIndicator: SavedIndicator = {
              id: Date.now().toString(),
              name: parsedIndicator.name,
              type: parsedIndicator.type,
              parameters: finalParams,
              rawCode: rawCode,
              createdAt: new Date().toISOString(),
              status: parsedIndicator.errors.length > 0 ? "error" : parsedIndicator.warnings.length > 0 ? "warning" : "ready"
          };

          set({
              savedIndicators: [newIndicator, ...savedIndicators],
              step: "save" // Move to success view
          });
      },

      deleteIndicator: (id) => set(state => ({
          savedIndicators: state.savedIndicators.filter(i => i.id !== id)
      })),

      reset: () => set({
          step: "paste",
          rawCode: "",
          parsedIndicator: null,
          parameterOverrides: {}
      }),

      loadIndicatorForEdit: (id) => {
          const item = get().savedIndicators.find(i => i.id === id);
          if (item) {
              set({
                  step: "paste",
                  rawCode: item.rawCode
              });
              // Ideally trigger parse immediately?
              // get().parseCode();
              // Let's let user see code first.
          }
      }
    }),
    {
      name: "pine-script-store",
    }
  )
);
