/**
 * sessionStore — primary application state (Zustand).
 *
 * Manages session lifecycle (create, resume, restart, reset), phase tracking,
 * field overrides (optimistic updates persisted via REST PATCH), and WebSocket
 * send function registration. Auto-generates chat titles from position metadata.
 *
 * Field override flow:
 *   1. User edits a field → setFieldOverride() stores it locally + PATCHes backend
 *   2. Overrides are merged into interview_data_values for immediate UI display
 *   3. consumeFieldOverrides() returns them for inclusion in WS messages
 *   4. updateState() clears overrides once the backend confirms the values
 */
import { create } from "zustand"
import { toast } from "sonner"
import type { Phase, SessionState, AgentActivity } from "@/types/api"
import * as api from "@/api/client"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"

const SESSION_KEY = "pd3r-session-id"

type WsSendFn = (content: string, fieldOverrides?: Record<string, unknown>) => boolean

interface SessionStore {
  sessionId: string | null
  phase: Phase
  state: SessionState | null
  isConnected: boolean
  isLoading: boolean
  error: string | null
  pendingFieldOverrides: Record<string, unknown>
  /** WebSocket send function, set by ChatPanel for use by other components. */
  wsSend: WsSendFn | null
  /** Raw WebSocket reference for structured messages (element_action protocol). */
  wsRef: WebSocket | null
  /** Current agent activity (cleared on "done"). */
  agentActivity: { activity: AgentActivity; element?: string; detail?: string } | null
  /** Auto-generated or user-edited chat title */
  chatTitle: string | null
  /** True after user downloads the final document */
  downloaded: boolean

  createSession: () => Promise<string>
  updateState: (state: Partial<SessionState>) => void
  setPhase: (phase: Phase) => void
  setConnected: (connected: boolean) => void
  setFieldOverride: (field: string, value: unknown) => void
  consumeFieldOverrides: () => Record<string, unknown> | null
  setWsSend: (fn: WsSendFn | null) => void
  setWsRef: (ws: WebSocket | null) => void
  setAgentActivity: (activity: { activity: AgentActivity; element?: string; detail?: string } | null) => void
  setChatTitle: (title: string) => void
  setDownloaded: (v: boolean) => void
  resumeSession: (id: string) => Promise<boolean>
  stopSession: () => Promise<void>
  restartSession: () => Promise<void>
  reset: () => Promise<void>
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  sessionId: null,
  phase: "init",
  state: null,
  isConnected: false,
  isLoading: false,
  error: null,
  pendingFieldOverrides: {},
  wsSend: null,
  wsRef: null,
  agentActivity: null,
  chatTitle: null,
  downloaded: false,

  createSession: async () => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.createSession()
      localStorage.setItem(SESSION_KEY, res.session_id)
      set({
        sessionId: res.session_id,
        phase: res.phase as Phase,
        isLoading: false,
      })
      return res.session_id
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to create session"
      set({ error: msg, isLoading: false })
      throw e
    }
  },

  updateState: (partial) => {
    const current = get().state
    const updated = current
      ? { ...current, ...partial }
      : (partial as SessionState)

    // Clear any pending overrides that the backend state now confirms
    const confirmed = updated.interview_data_values ?? {}
    const pending = get().pendingFieldOverrides
    const remaining: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(pending)) {
      if (!(k in confirmed)) remaining[k] = v
    }

    // Auto-generate chat title when key fields are first available
    const vals = updated.interview_data_values ?? {}
    const title = get().chatTitle
    const autoTitle =
      !title && vals.position_title
        ? _buildChatTitle(vals)
        : undefined

    set({
      state: updated,
      phase: (partial.phase as Phase) ?? get().phase,
      pendingFieldOverrides: remaining,
      ...(autoTitle ? { chatTitle: autoTitle } : {}),
    })
  },

  setPhase: (phase) => set({ phase }),
  setConnected: (connected) => set({ isConnected: connected }),

  setFieldOverride: (field, value) => {
    set((s) => ({
      pendingFieldOverrides: { ...s.pendingFieldOverrides, [field]: value },
    }))
    // Persist to backend checkpoint immediately (fire-and-forget)
    const sessionId = get().sessionId
    if (sessionId) {
      api.patchFields(sessionId, { [field]: value }).catch((err) => {
        console.error("Failed to persist field override:", err)
      })
    }
  },

  consumeFieldOverrides: () => {
    const overrides = get().pendingFieldOverrides
    if (Object.keys(overrides).length === 0) return null
    // Don't clear here — overrides stay visible until backend confirms them
    // in updateState(). Return a snapshot to include in the WS message.
    return { ...overrides }
  },

  setWsSend: (fn) => set({ wsSend: fn }),
  setWsRef: (ws) => set({ wsRef: ws }),
  setAgentActivity: (activity) => set({ agentActivity: activity }),

  setChatTitle: (title) => set({ chatTitle: title }),
  setDownloaded: (v) => set({ downloaded: v }),

  resumeSession: async (id: string) => {
    try {
      const state = await api.getSession(id)
      localStorage.setItem(SESSION_KEY, id)
      set({
        sessionId: id,
        phase: state.phase,
        state,
        isLoading: false,
        error: null,
        pendingFieldOverrides: {},
      })

      // Replay chat messages from history store
      const { useHistoryStore } = await import("@/stores/historyStore")
      const historySession = useHistoryStore.getState().sessions.find((s) => s.session_id === id)
      if (historySession?.messages?.length) {
        useChatStore.getState().clear()
        for (const msg of historySession.messages) {
          useChatStore.getState().addMessage(msg.role, msg.content, msg.type)
        }
      }

      // Fetch draft if in drafting/review/complete
      if (state.phase === "drafting" || state.phase === "review" || state.phase === "complete") {
        useDraftStore.getState().fetchDraft(id)
      }

      // Auto-generate chat title
      const vals = state.interview_data_values ?? {}
      if (vals.position_title) {
        set({ chatTitle: _buildChatTitle(vals) })
      }

      return true
    } catch {
      localStorage.removeItem(SESSION_KEY)
      toast.error("Session no longer available on server")
      return false
    }
  },

  stopSession: async () => {
    const { sessionId } = get()
    if (!sessionId) return
    try {
      await api.stopSession(sessionId)
    } catch {
      // Ignore errors — stop is best-effort
    }
    useChatStore.getState().setTyping(false)
  },

  restartSession: async () => {
    const { sessionId } = get()
    if (!sessionId) return
    try {
      const res = await api.restartSession(sessionId)
      useChatStore.getState().clear()
      useDraftStore.getState().clear()
      set({
        phase: res.phase as Phase,
        state: null,
        error: null,
        pendingFieldOverrides: {},
        chatTitle: null,
        downloaded: false,
      })
      if (res.message && res.message !== "Session created") {
        useChatStore.getState().addMessage("agent", res.message)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to restart session"
      set({ error: msg })
    }
  },

  reset: async () => {
    const { sessionId } = get()
    localStorage.removeItem(SESSION_KEY)
    if (sessionId) {
      try {
        await api.deleteSession(sessionId)
      } catch {
        // Ignore delete errors on reset
      }
    }
    set({
      sessionId: null,
      phase: "init",
      state: null,
      isConnected: false,
      isLoading: false,
      error: null,
      pendingFieldOverrides: {},
      chatTitle: null,
      downloaded: false,
    })
  },
}))

/** Build a chat title like "GS-13 2210 IT Specialist [Mar 4]" */
function _buildChatTitle(vals: Record<string, unknown>): string {
  const parts: string[] = []
  const grade = vals.grade as string | undefined
  const series = vals.series as string | undefined
  if (grade) parts.push(`GS-${String(grade).replace(/^GS-?/i, "")}`)
  if (series) parts.push(String(series))
  parts.push(String(vals.position_title))
  const d = new Date()
  const month = d.toLocaleString("en-US", { month: "short" })
  parts.push(`[${month} ${d.getDate()}]`)
  return parts.join(" ")
}
