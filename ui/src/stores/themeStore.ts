import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Theme {
  id: string;
  name: string;
  isDarkMode: boolean;
  variables: Record<string, string>;
  contrastValidated: boolean;
  createdAt: string;
}

export interface ThemeState {
  // Current theme
  currentTheme: Theme | null;
  isLoading: boolean;

  // All available themes
  themes: Theme[];

  // Performance mode
  performanceMode: boolean;

  // Actions
  setTheme: (theme: Theme) => void;
  fetchThemes: () => Promise<void>;
  togglePerformanceMode: () => void;
  applyTheme: (theme: Theme) => void;
}

// Pre-built themes matching requirements
const DEFAULT_THEMES: Theme[] = [
  {
    id: "cyberpunk-neon",
    name: "Cyberpunk Neon",
    isDarkMode: true,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#0A0E27",
      "bg-secondary": "#151932",
      "bg-surface": "rgba(21, 25, 50, 0.6)",
      "bg-elevated": "#1F2347",
      "text-primary": "#F8FAFC",
      "text-secondary": "#E879F9",
      "text-muted": "#A78BFA",
      "accent-color": "#F472B6",
      "accent-hover": "#EC4899",
      "success": "#22C55E",
      "success-light": "#064E3B",
      "danger": "#EF4444",
      "danger-light": "#7F1D1D",
      "warning": "#F59E0B",
      "border-color": "#4C1D95",
      "glow": "0 0 15px rgba(244, 114, 182, 0.5)",
    },
  },
  {
    id: "beach-paradise",
    name: "Beach Paradise",
    isDarkMode: false,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#FFF9F5",
      "bg-secondary": "#FFFFFF",
      "bg-surface": "rgba(255, 255, 255, 0.7)",
      "bg-elevated": "#FEF3C7",
      "text-primary": "#1E293B",
      "text-secondary": "#0E7490",
      "text-muted": "#94A3B8",
      "accent-color": "#0891B2",
      "accent-hover": "#0E7490",
      "success": "#059669",
      "success-light": "#D1FAE5",
      "danger": "#DC2626",
      "danger-light": "#FEE2E2",
      "warning": "#D97706",
      "border-color": "#CBD5E1",
      "glow": "0 0 10px rgba(8, 145, 178, 0.3)",
    },
  },
  {
    id: "midnight-ocean",
    name: "Midnight Ocean",
    isDarkMode: true,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#0C1B2E",
      "bg-secondary": "#1A2F47",
      "bg-surface": "rgba(26, 47, 71, 0.6)",
      "bg-elevated": "#243B53",
      "text-primary": "#E0F2FE",
      "text-secondary": "#7DD3FC",
      "text-muted": "#64748B",
      "accent-color": "#06B6D4",
      "accent-hover": "#0891B2",
      "success": "#10B981",
      "success-light": "#064E3B",
      "danger": "#EF4444",
      "danger-light": "#7F1D1D",
      "warning": "#F59E0B",
      "border-color": "#334155",
      "glow": "0 0 12px rgba(6, 182, 212, 0.4)",
    },
  },
  {
    id: "forest-grove",
    name: "Forest Grove",
    isDarkMode: false,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#FAFDF7",
      "bg-secondary": "#FFFFFF",
      "bg-surface": "rgba(255, 255, 255, 0.7)",
      "bg-elevated": "#F0FDF4",
      "text-primary": "#14532D",
      "text-secondary": "#15803D",
      "text-muted": "#78716C",
      "accent-color": "#16A34A",
      "accent-hover": "#15803D",
      "success": "#16A34A",
      "success-light": "#DCFCE7",
      "danger": "#DC2626",
      "danger-light": "#FEE2E2",
      "warning": "#D97706",
      "border-color": "#D4D4D8",
      "glow": "0 0 10px rgba(22, 163, 74, 0.3)",
    },
  },
  {
    id: "deep-space",
    name: "Deep Space",
    isDarkMode: true,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#000000",
      "bg-secondary": "#0A0A0A",
      "bg-surface": "rgba(10, 10, 10, 0.6)",
      "bg-elevated": "#1A1A1A",
      "text-primary": "#FFFFFF",
      "text-secondary": "#A3A3A3",
      "text-muted": "#737373",
      "accent-color": "#8B5CF6",
      "accent-hover": "#7C3AED",
      "success": "#22C55E",
      "success-light": "#064E3B",
      "danger": "#EF4444",
      "danger-light": "#7F1D1D",
      "warning": "#F59E0B",
      "border-color": "#262626",
      "glow": "0 0 15px rgba(139, 92, 246, 0.5)",
    },
  },
  {
    id: "noir",
    name: "Noir",
    isDarkMode: true,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#18181B",
      "bg-secondary": "#27272A",
      "bg-surface": "rgba(39, 39, 42, 0.6)",
      "bg-elevated": "#3F3F46",
      "text-primary": "#FAFAFA",
      "text-secondary": "#D4D4D8",
      "text-muted": "#71717A",
      "accent-color": "#FAFAFA",
      "accent-hover": "#E4E4E7",
      "success": "#22C55E",
      "success-light": "#064E3B",
      "danger": "#EF4444",
      "danger-light": "#7F1D1D",
      "warning": "#F59E0B",
      "border-color": "#52525B",
      "glow": "0 0 10px rgba(250, 250, 250, 0.3)",
    },
  },
  {
    id: "paper",
    name: "Paper",
    isDarkMode: false,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#FAFAF9",
      "bg-secondary": "#FFFFFF",
      "bg-surface": "rgba(255, 255, 255, 0.7)",
      "bg-elevated": "#F5F5F4",
      "text-primary": "#1C1917",
      "text-secondary": "#57534E",
      "text-muted": "#A8A29E",
      "accent-color": "#0F172A",
      "accent-hover": "#334155",
      "success": "#16A34A",
      "success-light": "#DCFCE7",
      "danger": "#DC2626",
      "danger-light": "#FEE2E2",
      "warning": "#D97706",
      "border-color": "#E7E5E4",
      "glow": "0 0 8px rgba(15, 23, 42, 0.2)",
    },
  },
  {
    id: "sepia",
    name: "Sepia",
    isDarkMode: false,
    contrastValidated: true,
    createdAt: new Date().toISOString(),
    variables: {
      "bg-primary": "#F5F1E8",
      "bg-secondary": "#FFFEF9",
      "bg-surface": "rgba(255, 254, 249, 0.7)",
      "bg-elevated": "#EAE4D5",
      "text-primary": "#3E2723",
      "text-secondary": "#6D4C41",
      "text-muted": "#A1887F",
      "accent-color": "#8D6E63",
      "accent-hover": "#6D4C41",
      "success": "#558B2F",
      "success-light": "#DCEDC8",
      "danger": "#C62828",
      "danger-light": "#FFCDD2",
      "warning": "#EF6C00",
      "border-color": "#D7CCC8",
      "glow": "0 0 10px rgba(141, 110, 99, 0.3)",
    },
  },
];

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      currentTheme: null,
      isLoading: false,
      themes: [],
      performanceMode: false,

      fetchThemes: async () => {
        set({ isLoading: true });
        // Simulate database fetch
        await new Promise((resolve) => setTimeout(resolve, 100));
        set({ themes: DEFAULT_THEMES, isLoading: false });

        // If no theme is set, apply the first one (Cyberpunk Neon)
        if (!get().currentTheme) {
          get().applyTheme(DEFAULT_THEMES[0]);
        }
      },

      applyTheme: (theme: Theme) => {
        const root = document.documentElement;

        // Apply CSS variables to :root
        Object.entries(theme.variables).forEach(([key, value]) => {
          root.style.setProperty(`--${key}`, value);
        });

        // Also update shadcn-compatible variables for consistency
        const vars = theme.variables;

        // Map theme variables to shadcn base variables
        if (vars["bg-primary"]) root.style.setProperty("--background", vars["bg-primary"]);
        if (vars["text-primary"]) root.style.setProperty("--foreground", vars["text-primary"]);
        if (vars["bg-secondary"]) root.style.setProperty("--card", vars["bg-secondary"]);
        if (vars["text-primary"]) root.style.setProperty("--card-foreground", vars["text-primary"]);
        if (vars["bg-secondary"]) root.style.setProperty("--popover", vars["bg-secondary"]);
        if (vars["text-primary"]) root.style.setProperty("--popover-foreground", vars["text-primary"]);
        if (vars["text-primary"]) root.style.setProperty("--primary", vars["text-primary"]);
        if (vars["bg-primary"]) root.style.setProperty("--primary-foreground", vars["bg-primary"]);
        if (vars["bg-elevated"]) root.style.setProperty("--secondary", vars["bg-elevated"]);
        if (vars["text-primary"]) root.style.setProperty("--secondary-foreground", vars["text-primary"]);
        if (vars["bg-elevated"]) root.style.setProperty("--muted", vars["bg-elevated"]);
        if (vars["text-muted"]) root.style.setProperty("--muted-foreground", vars["text-muted"]);
        if (vars["accent-color"]) root.style.setProperty("--accent", vars["accent-color"]);
        if (vars["text-primary"]) root.style.setProperty("--accent-foreground", vars["text-primary"]);
        if (vars["danger"]) root.style.setProperty("--destructive", vars["danger"]);
        if (vars["text-primary"]) root.style.setProperty("--destructive-foreground", vars["text-primary"]);
        if (vars["border-color"]) root.style.setProperty("--border", vars["border-color"]);
        if (vars["border-color"]) root.style.setProperty("--input", vars["border-color"]);
        if (vars["accent-color"]) root.style.setProperty("--ring", vars["accent-color"]);

        // Apply dark mode class
        if (theme.isDarkMode) {
          root.classList.add("dark");
        } else {
          root.classList.remove("dark");
        }

        set({ currentTheme: theme });
      },

      setTheme: (theme: Theme) => {
        get().applyTheme(theme);
      },

      togglePerformanceMode: () => {
        const newMode = !get().performanceMode;
        set({ performanceMode: newMode });

        const root = document.documentElement;
        if (newMode) {
          root.classList.add("performance-mode");
        } else {
          root.classList.remove("performance-mode");
        }
      },
    }),
    {
      name: "theme-settings",
      partialize: (state) => ({
        currentTheme: state.currentTheme,
        performanceMode: state.performanceMode,
      }),
      onRehydrateStorage: () => (state) => {
        // After hydration, reapply the theme from localStorage
        if (state?.currentTheme) {
          state.applyTheme(state.currentTheme);
        }
        // Reapply performance mode
        if (state?.performanceMode) {
          document.documentElement.classList.add("performance-mode");
        }
      },
    }
  )
);
