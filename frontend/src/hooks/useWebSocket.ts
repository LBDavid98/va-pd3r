import { useEffect, useRef, useCallback } from "react"
import { toast } from "sonner"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"
import type { WSIncoming, WSAgentMessage, WSElementUpdate, Phase, ChatMessageType } from "@/types/api"

const PING_INTERVAL = 30_000
const RECONNECT_BASE = 1_000
const RECONNECT_MAX = 16_000

/**
 * Classify agent messages to reduce chat noise.
 * Covers requirements, drafting, and review phases.
 * Returns: "show" (normal bubble), "system" (condensed notification), or "suppress" (hide).
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

  // --- Drafting preamble ---
  if (lower.includes("ready to start writing") || lower.includes("position description consists of")) {
    return { action: "suppress" }
  }
  if (lower.includes("let's start with") || lower.includes("let\u2019s start with")) {
    return { action: "suppress" }
  }
  if (lower.includes("draft each section") || lower.includes("sections total")) {
    return { action: "suppress" }
  }

  // --- "Generated draft for X (queued for QA)." ---
  if (lower.includes("generated draft for") || lower.includes("queued for qa")) {
    return { action: "suppress" }
  }

  // --- QA review results ---
  if (lower.includes("qa review") && lower.includes("requirements passed")) {
    return { action: "suppress" }
  }
  if (lower.includes("passed qa") || (lower.includes("qa") && lower.includes("confidence"))) {
    return { action: "suppress" }
  }
  if (lower.includes("this section passed") && lower.includes("approve")) {
    return { action: "suppress" }
  }

  // --- Section approval prompts ---
  // "**Introduction** ✅ Passed QA Review\n\nReview the section in the draft panel..."
  // Condense to a short system message so the user knows a section is ready
  if (lower.includes("review the section in the draft panel") || lower.includes("review in the draft panel")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} ready for review` }
  }
  if ((lower.includes("passed qa review") || lower.includes("requires human review")) && lower.includes("approve")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} ready for review` }
  }

  // --- Section approval confirmations ---
  // "Great! Introduction approved!", "All set! Major Duties approved!"
  if (lower.includes("approved!") || lower.includes("approved.")) {
    return { action: "suppress" }
  }

  // --- "Moving to next section: X" / "Moving to: X" ---
  if (/^moving to(?: next section)?[:\s]/i.test(trimmed)) {
    return { action: "suppress" }
  }

  // --- Draft content echoed in chat ---
  if (lower.includes("review it in the draft panel") || lower.includes("review in the panel")) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} drafted` }
  }
  if (lower.includes("let me know what you think")) {
    const match = content.match(/let me know what you think[:\s]*(.+)/i)
    const section = match?.[1]?.trim()
    return { action: "system", replacement: section ? `${section} drafted` : "New section drafted" }
  }
  // Emoji-prefixed content echo
  if (/^(📝|✅|✓)\s/.test(trimmed)) {
    return { action: "suppress" }
  }
  // Full draft content leak (contains --- delimiters)
  if (content.includes("\n---\n") && content.length > 500) {
    const match = content.match(/\*\*(.+?)\*\*/)
    const section = match?.[1] ?? "Section"
    return { action: "system", replacement: `${section} drafted` }
  }

  // --- Short filler / "X drafted" standalone ---
  if (/^\w[\w\s:]+drafted\.?$/i.test(trimmed) && trimmed.length < 60) {
    return { action: "suppress" }
  }

  return { action: "show" }
}

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const pingRef = useRef<ReturnType<typeof setInterval>>(null)
  const retryRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>(null)
  // Track which session this socket belongs to so stale events are ignored
  const activeSessionRef = useRef<string | null>(null)

  const setConnected = useSessionStore((s) => s.setConnected)
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
            const data = msg.data as unknown as WSAgentMessage
            if (data.content) {
              setTyping(false)

              // After interview, filter verbose agent messages
              const currentPhase = data.phase ?? useSessionStore.getState().state?.phase
              if (currentPhase === "requirements" || currentPhase === "drafting" || currentPhase === "review") {
                const { action, replacement } = classifyAgentMessage(data.content)
                if (action === "suppress") {
                  // Don't add to chat at all
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
            if (data.phase === "drafting" || data.phase === "review") {
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
          case "stopped": {
            setTyping(false)
            addMessage("agent", "Processing stopped.", "system")
            if (msg.data && Object.keys(msg.data).length > 0) {
              updateState(msg.data as Parameters<typeof updateState>[0])
            }
            break
          }
          case "error": {
            if (activeSessionRef.current !== sessionId) break
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
