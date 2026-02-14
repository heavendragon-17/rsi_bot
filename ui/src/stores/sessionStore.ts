import { create } from "zustand";

const API_BASE = "http://localhost:8765/api";

export interface Session {
  id: string;
  mode_type: string;
  strategy_id: number;
  created_at: string;
  last_accessed: string | null;
  status: string;
  notes: string | null;
}

interface SessionState {
  activeSessionId: string | null;
  sessions: Session[];
  isLoading: boolean;
  error: string | null;

  createSession: (modeType: string, configSnapshot: Record<string, unknown>) => Promise<string>;
  listSessions: () => Promise<void>;
  setActiveSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  activeSessionId: null,
  sessions: [],
  isLoading: false,
  error: null,

  createSession: async (modeType: string, configSnapshot: Record<string, unknown>) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode_type: modeType, config: configSnapshot }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const sessionId: string = data.id;
      set((state) => ({
        activeSessionId: sessionId,
        sessions: [data, ...state.sessions],
        isLoading: false,
      }));
      return sessionId;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, error: msg });
      throw e;
    }
  },

  listSessions: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const activeSessions: Session[] = (data.sessions || []).filter(
        (s: Session) => s.status === "active"
      );
      set({ sessions: activeSessions, isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, error: msg });
    }
  },

  setActiveSession: (id: string) => {
    set({ activeSessionId: id });
  },
}));
