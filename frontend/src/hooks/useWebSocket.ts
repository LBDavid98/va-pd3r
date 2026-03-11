import { useEffect, useRef, useCallback } from "react"
import { toast } from "sonner"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"
import type { WSIncoming, WSAgentMessage, WSElementUpdate, WSActivityUpdate, Phase, ChatMessageType } from "@/types/api"

const PING_INTERVAL = 30_000
const RECONNECT_BASE = 1_000
const RECONNECT_MAX = 16_000
const TYPING_TIMEOUT = 90_000 // Safety: clear typing indicator after 90s of no response

/**
 * Classify agent messages to reduce chat noise during drafting/review.
 *
 * The ProductPanel and status tracker show element status, QA results,
 * and provide approve/reject buttons.  Chat should only contain
 * conversational messages — not operational status updates.
 */
function classifyAgentMessage(content: string): { action: "show" | "system" | "suppress"; replacement?: string } {
  // Draft content leaked into chat (long content with markdown delimiters)
  if (content.includes("\n---\n") && content.length > 500) {
    return { action: "suppress" }
  }

  // Operational messages that duplicate what the panel/tracker already shows
  if (content.startsWith("Moving to:") || content.startsWith("Moving to ")) {
    return { action: "suppress" }
  }
  if (content.includes("(queued for QA)")) {
    return { action: "suppress" }
  }

  // Generic prompts redundant with ProductPanel buttons
  if (content === "Do you approve this section?" || content === "What would you like to do next?") {
    return { action: "suppress" }
  }
  if (content === "Do you approve this section, or provide feedback for changes?") {
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
  const setAgentActivity = useSessionStore((s) => s.setAgentActivity)
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
          case "activity_update": {
            const data = msg.data as unknown as WSActivityUpdate
            setAgentActivity({ activity: data.activity, element: data.element, detail: data.detail })
            break
          }
          case "done": {
            // Single source of truth: backend signals processing complete.
            // This is the ONLY place typing gets turned off during normal flow.
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
            setTyping(false)
            setAgentActivity(null)
            break
          }
          case "stopped": {
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
            setTyping(false)
            setAgentActivity(null)
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
