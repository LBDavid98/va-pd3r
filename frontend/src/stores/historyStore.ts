import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { ChatMessage, SessionState, DraftElementSummary } from "@/types/api"

const MAX_SESSIONS = 20
const MAX_MESSAGES_PER_SESSION = 200

export interface SessionSummary {
  session_id: string
  display_name: string
  created_at: number
  updated_at: number
  message_count: number
  phase: string
  messages: ChatMessage[]
  state?: SessionState
  draft_elements?: DraftElementSummary[]
}

interface HistoryStore {
  sessions: SessionSummary[]
  isOpen: boolean
  selectedSessionId: string | null

  saveSession: (session: SessionSummary) => void
  updateSession: (sessionId: string, updates: Partial<SessionSummary>) => void
  removeSession: (sessionId: string) => void
  clearAll: () => void
  setOpen: (open: boolean) => void
  setSelectedSessionId: (id: string | null) => void
}

export const useHistoryStore = create<HistoryStore>()(
  persist(
    (set) => ({
      sessions: [],
      isOpen: false,
      selectedSessionId: null,

      saveSession: (session) =>
        set((s) => {
          // Don't duplicate
          if (s.sessions.some((h) => h.session_id === session.session_id)) {
            return s
          }
          const updated = [session, ...s.sessions].slice(0, MAX_SESSIONS)
          return { sessions: updated }
        }),

      updateSession: (sessionId, updates) =>
        set((s) => ({
          sessions: s.sessions.map((h) => {
            if (h.session_id !== sessionId) return h
            const merged = { ...h, ...updates, updated_at: Date.now() }
            // Cap messages
            if (merged.messages.length > MAX_MESSAGES_PER_SESSION) {
              merged.messages = merged.messages.slice(-MAX_MESSAGES_PER_SESSION)
            }
            return merged
          }),
        })),

      removeSession: (sessionId) =>
        set((s) => ({
          sessions: s.sessions.filter((h) => h.session_id !== sessionId),
          selectedSessionId:
            s.selectedSessionId === sessionId ? null : s.selectedSessionId,
        })),

      clearAll: () => set({ sessions: [], selectedSessionId: null }),
      setOpen: (open) => set({ isOpen: open, selectedSessionId: null }),
      setSelectedSessionId: (id) => set({ selectedSessionId: id }),
    }),
    {
      name: "pd3r-history",
      partialize: (state) => ({
        sessions: state.sessions,
      }),
    },
  ),
)
