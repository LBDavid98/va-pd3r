import { Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useHistoryStore } from "@/stores/historyStore"

export function HistoryButton() {
  const sessions = useHistoryStore((s) => s.sessions)
  const isOpen = useHistoryStore((s) => s.isOpen)
  const setOpen = useHistoryStore((s) => s.setOpen)

  if (sessions.length === 0) return null

  return (
    <Button
      size="sm"
      className="fixed bottom-6 right-6 z-40 bg-primary/80 backdrop-blur-sm hover:bg-primary/90 shadow-lg"
      onClick={() => setOpen(!isOpen)}
    >
      <Clock className="mr-1.5 h-3.5 w-3.5" />
      History ({sessions.length})
    </Button>
  )
}
