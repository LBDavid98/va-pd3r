import { useEffect, useRef, useCallback } from "react"
import { toast } from "sonner"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"
import type { WSIncoming, WSAgentMessage, WSElementUpdate, Phase, ChatMessageType } from "@/types/api"

const PING_INTERVAL = 30_000
const RECONNECT_BASE = 1_000
const RECONNECT_MAX = 16_000
const TYPING_TIMEOUT = 90_000 // Safety: clear typing indicator after 90s of no response

/**
 * Classify agent messages to reduce chat noise during drafting.
 *
 * Returns:
 *   "show"     → normal chat bubble (user-facing content)
 *   "system"   → condensed notification (progress, approvals)
 *   "suppress" → hidden entirely (internal plumbing)
 *
 * Key principle: anything the user initiated (approve, regenerate) should
 * produce at least a system message so they know it worked.  Internal
 * pipeline messages (QA details, element transitions) can be suppressed.
 */
function classifyAgentMessage(content: string): { action: "show" | "system" | "suppress"; replacement?: string } {
  const lower = content.toLowerCase()
  const trimmed = content.trim()

  // --- FES evaluation (requirements phase) ---
  if (lower.includes("fes evaluation complete") || (lower.includes("total points") && lower.includes("factor"))) {
    return { action: "suppress" }
  }
  if (/^(primary|other) (significant )?factor (levels|ratings)/i.test(trimmed)) {
    return { action: "suppress" }
  }

  // --- Drafting preamble (internal setup) ---
  if (lower.includes("ready to start writing") || lower.includes("position description consists of")) {
    return { action: "suppress" }
  }
  if (lower.includes("let's start with") || lower.includes("let\u2019s start with")) {
    return { action: "suppress" }
  }
  if (lower.includes("draft each section") || lower.includes("sections total")) {
    return { action: "suppress" }
  }

  // --- Batch generation noise ---
  if (lower.includes("generated draft for") || lower.includes("queued for qa")) {
    return { action: "suppress" }
  }
  if (lower.includes("is ready for review")) {
    return { action: "suppress" }
  }

  // --- QA results (internal — QA detail shown in draft panel) ---
  if (lower.includes("qa review") && lower.includes("requirements passed")) {
    return { action: "suppress" }
  }
  if (lower.includes("this section passed") && lower.includes("approve")) {
    return { action: "suppress" }
  }

  // --- Section ready for review (QA passed → user needs to act) ---
  if (lower.includes("review the section in the draft panel") || lower.includes("review in the draft panel")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} ready for review` }
  }
  if ((lower.includes("passed qa review") || lower.includes("requires human review")) && (lower.includes("approve") || lower.includes("review"))) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} ready for review` }
  }

  // --- Section approval confirmations (user-initiated → system message) ---
  if (lower.includes("approved!") || lower.includes("approved.")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} approved` }
  }

  // --- "Moving to next section: X" / "Moving to: X" ---
  if (/moving to(?: next section)?[:\s]/i.test(lower)) {
    return { action: "suppress" }
  }

  // --- "Let me draft X" / "Let me revise X" (internal pipeline) ---
  if (/let me (draft|revise|rewrite)/i.test(lower)) {
    return { action: "suppress" }
  }

  // --- "Drafting X..." (next_prompt passthrough) ---
  if (/^drafting\s/i.test(trimmed) && trimmed.length < 80) {
    return { action: "suppress" }
  }

  // --- Revision acknowledgments (user-initiated → system message) ---
  if (lower.includes("needs revision") && lower.includes("rewriting automatically")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} being revised` }
  }

  // --- Draft content echoed in chat ---
  if (lower.includes("review it in the draft panel") || lower.includes("review in the panel")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} drafted` }
  }
  // Emoji-prefixed content echo
  if (/^(📝|✅|✓)\s/.test(trimmed)) {
    return { action: "suppress" }
  }
  // Full draft content leak (contains --- delimiters and is long)
  if (content.includes("\n---\n") && content.length > 500) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} drafted` }
  }

  // --- Short filler / "X drafted" standalone ---
  if (/^\w[\w\s:]+drafted\.?$/i.test(trimmed) && trimmed.length < 60) {
    return { action: "suppress" }
  }

  // --- "Running QA review..." / "Revising..." next_prompt passthroughs ---
  if (/^(running qa|revising|reviewing)/i.test(trimmed) && trimmed.length < 60) {
    return { action: "suppress" }
  }

  // --- "Do you approve this section?" interrupt prompt ---
  if (lower.includes("do you approve")) {
    return { action: "suppress" }
  }

  return { action: "show" }
}

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const pingRef = useRef<ReturnType<typeof setInterval>>(null)
  const retryRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>(null)
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout>>(null)
  // Track which session this socket belongs to so stale events are ignored
  const activeSessionRef = useRef<string | null>(null)

  const setConnected = useSessionStore((s) => s.setConnected)
  const setWsRef = useSessionStore((s) => s.setWsRef)
  const updateState = useSessionStore((s) => s.updateState)
  const addMessage = useChatStore((s) => s.addMessage)
  const setTyping = useChatStore((s) => s.setTyping)
  const updateElement = useDraftStore((s) => s.updateElement)
  const fetchDraft = useDraftStore((s) => s.fetchDraft)

  useEffect(() => {
    // Clean up any previous connection
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.close()
      wsRef.current = null
    }
    if (pingRef.current) {
      clearInterval(pingRef.current)
      pingRef.current = null
    }

    activeSessionRef.current = sessionId
    retryRef.current = 0

    if (!sessionId) {
      setConnected(false)
      return
    }

    function connect() {
      // Bail if session changed since this connect was scheduled
      if (activeSessionRef.current !== sessionId) return

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const host = window.location.host
      const ws = new WebSocket(`${protocol}//${host}/sessions/${sessionId}/stream`)

      ws.onopen = () => {
        if (activeSessionRef.current !== sessionId) {
          ws.close()
          return
        }
        setConnected(true)
        setWsRef(ws)
        retryRef.current = 0
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }))
          }
        }, PING_INTERVAL)
      }

      ws.onmessage = (event) => {
        // Ignore messages from stale sessions
        if (activeSessionRef.current !== sessionId) return

        const msg: WSIncoming = JSON.parse(event.data)

        switch (msg.type) {
          case "agent_message": {
            // Reset typing timeout — backend is alive and streaming
            if (typingTimeoutRef.current) {
              clearTimeout(typingTimeoutRef.current)
              typingTimeoutRef.current = setTimeout(() => {
                setTyping(false)
                addMessage("agent", "The response timed out. Please try sending your message again.", "system")
                toast.warning("Response timed out")
              }, TYPING_TIMEOUT)
            }
            const data = msg.data as unknown as WSAgentMessage
            if (data.content) {
              // After interview, filter verbose agent messages
              const currentPhase = data.phase ?? useSessionStore.getState().state?.phase
              if (currentPhase === "requirements" || currentPhase === "drafting" || currentPhase === "review") {
                const { action, replacement } = classifyAgentMessage(data.content)
                if (action === "suppress") {
                  // Don't add to chat — pipeline still running
                } else if (action === "system") {
                  addMessage("agent", replacement ?? data.content, "system")
                } else {
                  addMessage("agent", data.content)
                }
              } else {
                addMessage("agent", data.content)
              }
            }
            if (data.phase) {
              updateState({ phase: data.phase })
            }
            // Don't fetchDraft on every agent_message during streaming —
            // element_update WS messages handle real-time updates.
            // Only fetch on phase transitions to sync full state.
            if (data.phase && (data.phase === "drafting" || data.phase === "review" || data.phase === "complete")) {
              fetchDraft(sessionId)
            }
            break
          }
          case "state_update": {
            const prevPhase = useSessionStore.getState().phase
            updateState(msg.data as Record<string, unknown> as Parameters<typeof updateState>[0])
            const phase = msg.data.phase as Phase | undefined
            // Only show "Drafting all sections" on first transition into drafting
            if (phase === "drafting" && prevPhase !== "drafting") {
              addMessage("agent", "Drafting all sections now — this may take a minute.", "system")
            }
            if (phase === "drafting" || phase === "review" || phase === "complete") {
              fetchDraft(sessionId)
            }
            break
          }
          case "element_update": {
            const data = msg.data as unknown as WSElementUpdate
            updateElement(data.name, {
              status: data.status,
              content: data.content ?? undefined,
              ...(data.qa_review ? { qa_review: data.qa_review } : {}),
            })
            break
          }
          case "done": {
            // Single source of truth: backend signals processing complete.
            // This is the ONLY place typing gets turned off during normal flow.
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
            setTyping(false)
            break
          }
          case "stopped": {
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
            setTyping(false)
            addMessage("agent", "Processing stopped.", "system")
            if (msg.data && Object.keys(msg.data).length > 0) {
              updateState(msg.data as Parameters<typeof updateState>[0])
            }
            break
          }
          case "error": {
            if (activeSessionRef.current !== sessionId) break
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
            const errMsg = (msg.data as { message?: string }).message ?? "Unknown error"
            addMessage("agent", `Error: ${errMsg}`)
            toast.error("Something went wrong", { description: errMsg })
            setTyping(false)
            break
          }
          case "pong":
            break
        }
      }

      ws.onclose = () => {
        if (pingRef.current) clearInterval(pingRef.current)
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
        setTyping(false)
        setWsRef(null)

        // Don't reconnect if session changed
        if (activeSessionRef.current !== sessionId) return

        setConnected(false)
        toast.warning("Connection lost", { description: "Reconnecting..." })

        const delay = Math.min(RECONNECT_BASE * 2 ** retryRef.current, RECONNECT_MAX)
        retryRef.current += 1
        reconnectTimerRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        ws.close()
      }

      wsRef.current = ws
    }

    connect()

    return () => {
      activeSessionRef.current = null
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
      if (pingRef.current) clearInterval(pingRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.onerror = null
        wsRef.current.onmessage = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const sendMessage = useCallback(
    (content: string, fieldOverrides?: Record<string, unknown>) => {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        const data: Record<string, unknown> = { content }
        if (fieldOverrides && Object.keys(fieldOverrides).length > 0) {
          data.field_overrides = fieldOverrides
        }
        ws.send(JSON.stringify({ type: "user_message", data }))
        setTyping(true)
        // Safety timeout: if backend never sends "done", clear typing after 90s
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
        typingTimeoutRef.current = setTimeout(() => {
          setTyping(false)
          addMessage("agent", "The response timed out. Please try sending your message again.", "system")
          toast.warning("Response timed out")
        }, TYPING_TIMEOUT)
        return true
      }
      return false
    },
    [setTyping],
  )

  const sendStop = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }))
    }
  }, [])

  return { sendMessage, sendStop }
}
