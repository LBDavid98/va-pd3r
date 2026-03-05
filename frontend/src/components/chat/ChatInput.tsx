import { useState, useCallback, type KeyboardEvent, type MouseEvent } from "react"
import { Square } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface ChatInputProps {
  onSend: (content: string) => void
  onAutoSend?: () => void
  onStop?: () => void
  disabled?: boolean
  isTyping?: boolean
}

export function ChatInput({ onSend, onAutoSend, onStop, disabled, isTyping }: ChatInputProps) {
  const [value, setValue] = useState("")

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue("")
  }, [value, onSend])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        if (e.altKey && onAutoSend) {
          onAutoSend()
        } else {
          handleSend()
        }
      }
    },
    [handleSend, onAutoSend],
  )

  const handleSendClick = useCallback(
    (e: MouseEvent<HTMLButtonElement>) => {
      if (e.altKey && onAutoSend) {
        e.preventDefault()
        onAutoSend()
      } else {
        handleSend()
      }
    },
    [handleSend, onAutoSend],
  )

  return (
    <div className="border-t p-3 flex gap-2">
      <Textarea
        placeholder="Type a message... (Option+Send to auto-fill)"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        className="min-h-[40px] max-h-[120px] resize-none"
        rows={1}
      />
      {isTyping ? (
        <Button
          onClick={onStop}
          size="sm"
          variant="destructive"
          className="shrink-0 self-end"
          title="Stop processing"
        >
          <Square className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <Button
          onClick={handleSendClick}
          disabled={disabled}
          size="sm"
          className="shrink-0 self-end"
          title="Send (Option+click to auto-fill)"
        >
          Send
        </Button>
      )}
    </div>
  )
}
