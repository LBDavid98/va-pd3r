import { useEffect, useRef } from "react"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Header } from "@/components/layout/Header"
import { AppShell } from "@/components/layout/AppShell"
import { HistoryButton } from "@/components/chat/HistoryButton"
import { HistoryPanel } from "@/components/chat/HistoryPanel"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"
import { useHistoryStore } from "@/stores/historyStore"
import { syncConfigToBackend, getDefaultOrgList, getMissionText } from "@/components/layout/SettingsDialog"

export default function App() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const phase = useSessionStore((s) => s.phase)
  const sessionState = useSessionStore((s) => s.state)
  const addMessage = useChatStore((s) => s.addMessage)
  const messages = useChatStore((s) => s.messages)
  const clearChat = useChatStore((s) => s.clear)
  const draftElements = useDraftStore((s) => s.elements)
  const clearDraft = useDraftStore((s) => s.clear)
  const saveSession = useHistoryStore((s) => s.saveSession)
  const updateSession = useHistoryStore((s) => s.updateSession)
  const initRef = useRef(false)

  // Create session on mount (or when reset clears sessionId)
  useEffect(() => {
    if (sessionId) return

    // Guard against StrictMode double-fire
    if (initRef.current) return
    initRef.current = true

    clearChat()
    clearDraft()

    const controller = new AbortController()

    async function init() {
      try {
        await syncConfigToBackend()

        // Try restoring an existing session from sessionStorage
        const savedId = sessionStorage.getItem("pd3r-session-id")
        if (savedId) {
          const resumed = await useSessionStore.getState().resumeSession(savedId)
          if (resumed) return
        }

        const res = await fetch("/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
        })
        if (!res.ok) throw new Error(`API ${res.status}`)
        const data = await res.json()

        sessionStorage.setItem("pd3r-session-id", data.session_id)
        useSessionStore.setState({
          sessionId: data.session_id,
          phase: data.phase,
          isLoading: false,
        })

        // Seed the default org hierarchy as a pending field override
        const defaultOrg = getDefaultOrgList()
        if (defaultOrg.length > 0) {
          useSessionStore.getState().setFieldOverride("organization_hierarchy", defaultOrg)
        }

        // Seed mission text if configured
        const mission = getMissionText()
        if (mission) {
          useSessionStore.getState().setFieldOverride("mission_text", mission)
        }

        if (data.message && data.message !== "Session created") {
          addMessage("agent", data.message)
        }

        // Save to history
        saveSession({
          session_id: data.session_id,
          display_name: `New Position ${new Date().toLocaleString()}`,
          created_at: Date.now(),
          updated_at: Date.now(),
          message_count: 0,
          phase: data.phase,
          messages: [],
        })
      } catch (e) {
        if (controller.signal.aborted) return
        useSessionStore.setState({
          error: e instanceof Error ? e.message : "Failed to create session",
          isLoading: false,
        })
      }
    }

    init()
    return () => {
      controller.abort()
    }
  }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Allow re-init when session is reset (New Session button)
  useEffect(() => {
    if (!sessionId) {
      initRef.current = false
    }
  }, [sessionId])

  // Sync messages and display name to history when they change
  useEffect(() => {
    if (!sessionId) return
    const title = sessionState?.position_title
    const grade = sessionState?.interview_data_values?.grade as string | undefined
    const series = sessionState?.interview_data_values?.series as string | undefined

    let displayName: string | undefined
    if (title) {
      const parts = ["GS"]
      if (grade) parts[0] = `GS-${grade}`
      if (series) parts[0] += `-${series}`
      displayName = `${parts[0]} ${title}`
    }

    updateSession(sessionId, {
      message_count: messages.length,
      messages,
      phase,
      ...(displayName ? { display_name: displayName } : {}),
      ...(sessionState ? { state: sessionState } : {}),
      ...(draftElements.length > 0 ? { draft_elements: draftElements } : {}),
    })
  }, [sessionId, messages, phase, sessionState, draftElements, updateSession])

  return (
    <TooltipProvider>
      <div className="flex h-screen flex-col">
        <Header />
        <AppShell />
        <footer className="flex items-center justify-between border-t bg-muted/50 px-4 py-1.5 text-[11px] text-muted-foreground">
          <span>VHA Digital Health Office</span>
          <span>
            Built by David Hook (David.Hook2@va.gov)
          </span>
        </footer>
      </div>
      <HistoryButton />
      <HistoryPanel />
      <Toaster />
    </TooltipProvider>
  )
}
