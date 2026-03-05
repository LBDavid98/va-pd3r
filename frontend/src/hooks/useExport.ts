import { useCallback, useState } from "react"
import { exportDocument } from "@/api/client"
import { useSessionStore } from "@/stores/sessionStore"

/** Turn a chat title like "GS-13 2210 IT Specialist [Mar 4]" into a safe filename slug. */
export function buildFilename(title: string | null, ext: string): string {
  if (!title) return `position_description${ext}`
  const slug = title
    .replace(/\[.*?\]/g, "")     // strip date brackets
    .trim()
    .replace(/[^a-zA-Z0-9\-_ ]+/g, "") // remove special chars
    .replace(/\s+/g, "_")        // spaces → underscores
    .replace(/_+$/, "")          // trailing underscores
  return slug ? `${slug}${ext}` : `position_description${ext}`
}

export function useExport() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const chatTitle = useSessionStore((s) => s.chatTitle)
  const [isExporting, setIsExporting] = useState(false)

  const download = useCallback(
    async (format: "markdown" | "word") => {
      if (!sessionId) return
      setIsExporting(true)
      try {
        const blob = await exportDocument(sessionId, format)
        const ext = format === "markdown" ? ".md" : ".docx"
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = buildFilename(chatTitle, ext)
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
      } finally {
        setIsExporting(false)
      }
    },
    [sessionId, chatTitle],
  )

  return { download, isExporting }
}
