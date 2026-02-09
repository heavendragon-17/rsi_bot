import { create } from 'zustand';
import { ThemeDetails } from '../types/pywebview';

interface UIState {
    theme: ThemeDetails | null;
    activeTab: 'dashboard' | 'backtest' | 'settings';
    sidebarOpen: boolean;

    setTheme: (theme: ThemeDetails) => void;
    setActiveTab: (tab: 'dashboard' | 'backtest' | 'settings') => void;
    toggleSidebar: () => void;
    initTheme: () => Promise<void>;
}

export const useUIStore = create<UIState>((set) => ({
    theme: null,
    activeTab: 'dashboard',
    sidebarOpen: true,

    setTheme: (theme) => {
        set({ theme });
        if (theme.css_variables) {
            const root = document.documentElement;
            Object.entries(theme.css_variables).forEach(([key, val]) => {
                root.style.setProperty(key, val);
            });
            if (theme.is_dark) {
                root.classList.add('dark');
            } else {
                root.classList.remove('dark');
            }
        }
    },

    setActiveTab: (tab) => set({ activeTab: tab }),
    toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

    initTheme: async () => {
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_active_theme();
                if (res.success) {
                    set((state) => {
                        state.setTheme(res.data);
                        return { theme: res.data };
                    });
                }
            }
        } catch (err) {
            console.error(err);
        }
    }
}));
