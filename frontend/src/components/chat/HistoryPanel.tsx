/**
 * HistoryPanel — slide-over panel showing past chat sessions.
 *
 * Two views:
 *   1. SessionListView: lists all saved sessions with delete + download buttons
 *   2. TranscriptView: shows full message transcript for a selected session,
 *      with resume + download actions
 *
 * Sessions are persisted to localStorage via historyStore (max 20 sessions,
 * 200 messages each). When the backend session has expired, download falls
 * back to a client-side markdown export from stored draft elements.
 */
import { useState, useCallback } from "react"
import { ArrowLeft, ChevronDown, ChevronRight, Download, Play, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { exportDocument } from "@/api/client"
import { buildFilename } from "@/hooks/useExport"
import { useHistoryStore, type SessionSummary } from "@/stores/historyStore"
import { useSessionStore } from "@/stores/sessionStore"
import type { DraftElementSummary } from "@/types/api"

function formatDate(ts: number): string {
  return new Date(ts).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function SessionListView() {
  const sessions = useHistoryStore((s) => s.sessions)
  const removeSession = useHistoryStore((s) => s.removeSession)
  const clearAll = useHistoryStore((s) => s.clearAll)
  const setSelectedSessionId = useHistoryStore((s) => s.setSelectedSessionId)
  const setOpen = useHistoryStore((s) => s.setOpen)

  return (
    <>
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">Chat History</h2>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground"
            onClick={clearAll}
          >
            Clear All
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setOpen(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className="flex items-start gap-2 border-b px-4 py-3 hover:bg-muted/50 cursor-pointer"
            onClick={() => setSelectedSessionId(s.session_id)}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{s.display_name}</p>
              <p className="text-xs text-muted-foreground">
                {formatDate(s.updated_at)} &middot; {s.message_count} messages
              </p>
            </div>
            {(s.phase === "complete" || s.phase === "review") && (
              <DownloadDocxButton sessionId={s.session_id} title={s.display_name} draftElements={s.draft_elements} />
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation()
                removeSession(s.session_id)
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
      </div>
    </>
  )
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-200 text-gray-700",
  draft: "bg-yellow-100 text-yellow-800",
  drafted: "bg-yellow-100 text-yellow-800",
  qa_passed: "bg-green-100 text-green-800",
  approved: "bg-green-200 text-green-900",
  locked: "bg-blue-100 text-blue-800",
  needs_revision: "bg-red-100 text-red-800",
}

/** Collapsible snapshot of session state: phase, collected fields, draft element statuses. */
function SessionStateSummary({ session }: { session: SessionSummary }) {
  const [expanded, setExpanded] = useState(false)
  const { state, draft_elements } = session
  if (!state && (!draft_elements || draft_elements.length === 0)) return null

  return (
    <div className="mx-4 mt-3 rounded-lg border bg-muted/30 text-sm">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:bg-muted/50"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        Session Snapshot
        {state && (
          <span className="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase">
            {state.phase}
          </span>
        )}
      </button>
      {expanded && (
        <div className="space-y-2 border-t px-3 py-2">
          {state && (
            <>
              {state.position_title && (
                <p className="text-xs">
                  <span className="font-medium">Title:</span> {state.position_title}
                </p>
              )}
              <p className="text-xs">
                <span className="font-medium">Fields collected:</span>{" "}
                {state.collected_fields.length} of{" "}
                {state.collected_fields.length + state.missing_fields.length}
              </p>
              {state.collected_fields.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {state.collected_fields.map((f) => (
                    <span
                      key={f}
                      className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] text-green-800"
                    >
                      {f.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
          {draft_elements && draft_elements.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1">Draft Elements</p>
              <div className="space-y-0.5">
                {draft_elements.map((el) => (
                  <div key={el.name} className="flex items-center gap-2 text-xs">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] ${STATUS_COLORS[el.status] ?? "bg-gray-100 text-gray-600"}`}
                    >
                      {el.status}
                    </span>
                    <span className="truncate">{el.display_name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function buildMarkdownFallback(elements: DraftElementSummary[]): string {
  const lines: string[] = ["# Position Description\n"]
  for (const el of elements) {
    if (!el.content) continue
    lines.push(`## ${el.display_name}\n`)
    lines.push(el.content)
    lines.push("")
  }
  return lines.join("\n")
}

/** Download button: tries server .docx export, falls back to client-side markdown if session expired. */
function DownloadDocxButton({ sessionId, title, draftElements }: { sessionId: string; title?: string; draftElements?: DraftElementSummary[] }) {
  const [busy, setBusy] = useState(false)
  const handleDownload = useCallback(async () => {
    setBusy(true)
    try {
      const blob = await exportDocument(sessionId, "word")
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = buildFilename(title ?? null, ".docx")
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      // Backend session gone — fall back to markdown from stored elements
      if (draftElements && draftElements.length > 0) {
        const md = buildMarkdownFallback(draftElements)
        const blob = new Blob([md], { type: "text/markdown" })
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = buildFilename(title ?? null, ".md")
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        toast.info("Downloaded as Markdown", { description: "Server session expired — .docx unavailable." })
      } else {
        toast.error("Download unavailable", { description: "Session expired and no draft content saved." })
      }
    } finally {
      setBusy(false)
    }
  }, [sessionId, title, draftElements])

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-primary"
      onClick={(e) => { e.stopPropagation(); handleDownload() }}
      disabled={busy}
      title="Download .docx"
    >
      <Download className="h-3.5 w-3.5" />
    </Button>
  )
}

/** Full message transcript view with resume + download actions. */
function TranscriptView({ session }: { session: SessionSummary }) {
  const setSelectedSessionId = useHistoryStore((s) => s.setSelectedSessionId)
  const setOpen = useHistoryStore((s) => s.setOpen)
  const resumeSession = useSessionStore((s) => s.resumeSession)
  const currentSessionId = useSessionStore((s) => s.sessionId)
  const canDownload = session.phase === "complete" || session.phase === "review"
  const canResume = session.phase !== "complete" && session.session_id !== currentSessionId

  const handleResume = useCallback(async () => {
    const ok = await resumeSession(session.session_id)
    if (ok) {
      setSelectedSessionId(null)
      setOpen(false)
    }
  }, [session.session_id, resumeSession, setSelectedSessionId, setOpen])

  return (
    <>
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setSelectedSessionId(null)}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold truncate">{session.display_name}</p>
          <p className="text-xs text-muted-foreground">{formatDate(session.created_at)}</p>
        </div>
        {canResume && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={handleResume}
          >
            <Play className="h-3 w-3" />
            Resume
          </Button>
        )}
        {canDownload && <DownloadDocxButton sessionId={session.session_id} title={session.display_name} draftElements={session.draft_elements} />}
      </div>
      <SessionStateSummary session={session} />
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {session.messages.map((msg) => (
          <div
            key={msg.id}
            className={`text-sm ${
              msg.role === "user"
                ? "ml-8 rounded-lg bg-primary/10 px-3 py-2"
                : "mr-8 rounded-lg bg-muted px-3 py-2"
            }`}
          >
            <span className="text-xs font-medium text-muted-foreground block mb-0.5">
              {msg.role === "user" ? "You" : "Pete"}
            </span>
            {msg.content}
          </div>
        ))}
        {session.messages.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No messages recorded.</p>
        )}
      </div>
    </>
  )
}

export function HistoryPanel() {
  const isOpen = useHistoryStore((s) => s.isOpen)
  const selectedSessionId = useHistoryStore((s) => s.selectedSessionId)
  const sessions = useHistoryStore((s) => s.sessions)

  if (!isOpen) return null

  const selectedSession = selectedSessionId
    ? sessions.find((s) => s.session_id === selectedSessionId)
    : null

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-96 flex-col border-l bg-background shadow-xl animate-in slide-in-from-right duration-200">
      {selectedSession ? (
        <TranscriptView session={selectedSession} />
      ) : (
        <SessionListView />
      )}
    </div>
  )
}
