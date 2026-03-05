import { useCallback } from "react"
import { Check, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useExport } from "@/hooks/useExport"
import { useSessionStore } from "@/stores/sessionStore"
import { useDraftStore } from "@/stores/draftStore"

export function ExportBar() {
  const phase = useSessionStore((s) => s.phase)
  const elements = useDraftStore((s) => s.elements)
  const updateElement = useDraftStore((s) => s.updateElement)
  const setDownloaded = useSessionStore((s) => s.setDownloaded)
  const { download, isExporting } = useExport()

  const handleAccept = useCallback(() => {
    for (const el of useDraftStore.getState().elements) {
      if (!el.locked) {
        updateElement(el.name, { locked: true, status: "approved" })
      }
    }
  }, [updateElement])

  const handleDownload = useCallback(async () => {
    await download("word")
    setDownloaded(true)
  }, [download, setDownloaded])

  const canShow = phase === "review" || phase === "complete" || phase === "drafting"
  if (!canShow) return null

  const allApproved =
    elements.length > 0 &&
    elements.every(
      (el) => el.status === "approved" || el.locked,
    )

  return (
    <div className="flex items-center justify-center border-t p-3">
      {allApproved ? (
        <Button size="sm" disabled={isExporting} onClick={handleDownload} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          {isExporting ? "Exporting..." : "Download"}
        </Button>
      ) : (
        <Button size="sm" onClick={handleAccept} className="gap-1.5">
          <Check className="h-3.5 w-3.5" />
          Accept Draft
        </Button>
      )}
    </div>
  )
}
