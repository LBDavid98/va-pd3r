import { useCallback, useEffect } from "react"
import { useChatStore } from "@/stores/chatStore"
import { useSessionStore } from "@/stores/sessionStore"
import { useWebSocket } from "@/hooks/useWebSocket"
import { getAutoFillResponse } from "@/utils/autoFillScript"
import * as api from "@/api/client"
import { MessageList } from "./MessageList"
import { ChatInput } from "./ChatInput"

const HUNG_CHECK_INTERVAL = 10_000

export function ChatPanel() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const phase = useSessionStore((s) => s.phase)
  const sessionState = useSessionStore((s) => s.state)
  const isConnected = useSessionStore((s) => s.isConnected)
  const addMessage = useChatStore((s) => s.addMessage)
  const setTyping = useChatStore((s) => s.setTyping)
  const isTyping = useChatStore((s) => s.isTyping)
  const isHung = useChatStore((s) => s.isHung)
  const checkHung = useChatStore((s) => s.checkHung)
  const updateState = useSessionStore((s) => s.updateState)
  const consumeFieldOverrides = useSessionStore((s) => s.consumeFieldOverrides)
  const stopSession = useSessionStore((s) => s.stopSession)
  const setWsSend = useSessionStore((s) => s.setWsSend)
  const { sendMessage: wsSend } = useWebSocket(sessionId)

  // Register WS send function so other panels (ProductPanel) can use it
  useEffect(() => {
    setWsSend(wsSend)
    return () => setWsSend(null)
  }, [wsSend, setWsSend])

  // Periodic hung check
  useEffect(() => {
    const id = setInterval(checkHung, HUNG_CHECK_INTERVAL)
    return () => clearInterval(id)
  }, [checkHung])

  const handleSend = useCallback(
    async (content: string) => {
      if (!sessionId) return
      addMessage("user", content)

      // Field overrides are persisted via PATCH /fields on each edit.
      // Consume returns overrides to include in the WS message as a safety net,
      // but keep a snapshot so the UI still shows them until the backend confirms.
      const overrides = consumeFieldOverrides()

      // Try WebSocket first, fall back to REST
      const sent = wsSend(content, overrides ?? undefined)
      if (!sent) {
        setTyping(true)
        try {
          const res = await api.sendMessage(sessionId, content)
          for (const msg of res.messages) {
            addMessage("agent", msg.content)
          }
          updateState(res.session_state)
        } catch (e) {
          addMessage("agent", `Error: ${e instanceof Error ? e.message : "Unknown error"}`)
        } finally {
          setTyping(false)
        }
      }
    },
    [sessionId, addMessage, wsSend, setTyping, updateState, consumeFieldOverrides],
  )

  const handleAutoSend = useCallback(() => {
    const content = getAutoFillResponse(sessionState, phase)
    if (content) {
      handleSend(content)
    }
  }, [sessionState, phase, handleSend])

  return (
    <div className="flex h-full flex-col">
      <MessageList />
      {isHung && (
        <div className="mx-3 mb-2 rounded-md border border-yellow-400/60 bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
          The agent seems to be taking a long time. Hit Stop to cancel and send a new message.
        </div>
      )}
      <ChatInput
        onSend={handleSend}
        onAutoSend={handleAutoSend}
        onStop={stopSession}
        isTyping={isTyping}
        disabled={!sessionId || !isConnected}
      />
    </div>
  )
}
