import { useState, useRef, useEffect } from "react"
import { Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useSessionStore } from "@/stores/sessionStore"
import { SettingsDialog } from "./SettingsDialog"

export function Header() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const reset = useSessionStore((s) => s.reset)
  const chatTitle = useSessionStore((s) => s.chatTitle)
  const setChatTitle = useSessionStore((s) => s.setChatTitle)

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const startEdit = () => {
    setDraft(chatTitle ?? "")
    setEditing(true)
  }

  const commitEdit = () => {
    const trimmed = draft.trim()
    if (trimmed) setChatTitle(trimmed)
    setEditing(false)
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-primary text-primary-foreground px-4">
      <div className="flex items-center gap-3">
        <img
          src="/va-logo-white.png"
          alt="U.S. Department of Veterans Affairs"
          className="h-9"
        />
        <div className="hidden sm:block border-l border-primary-foreground/20 pl-3 leading-tight">
          <span className="text-sm font-semibold tracking-tight">PD3r</span>
          <span className="text-xs opacity-70 ml-1.5">Position Description Writer</span>
        </div>
      </div>

      {/* Editable chat title — centered */}
      {chatTitle && !editing && (
        <button
          onClick={startEdit}
          className="hidden md:flex items-center gap-1.5 text-sm text-primary-foreground/80 hover:text-primary-foreground transition-colors max-w-[40%] truncate"
          title="Click to rename"
        >
          <span className="truncate">{chatTitle}</span>
          <Pencil className="h-3 w-3 shrink-0 opacity-50" />
        </button>
      )}
      {editing && (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit()
            if (e.key === "Escape") setEditing(false)
          }}
          className="bg-primary-foreground/10 text-primary-foreground text-sm rounded px-2 py-1 outline-none border border-primary-foreground/30 w-64 max-w-[40%]"
        />
      )}

      <div className="flex items-center gap-3">
        <SettingsDialog />
        {sessionId && (
          <Button
            variant="outline"
            size="sm"
            className="border-primary-foreground/40 bg-transparent text-primary-foreground hover:bg-primary-foreground/15"
            onClick={reset}
          >
            New Session
          </Button>
        )}
      </div>
    </header>
  )
}
