/**
 * ProductPanel — right-side draft document view.
 *
 * Renders the position description as an OF-8 form with:
 *   - DocumentHeader: coversheet grid (title, series, grade, org hierarchy, etc.)
 *   - DraftSection (per element): collapsible toolbar with QA report, revision
 *     feedback, inline editing, lock/unlock, and approve controls
 *   - ExportBar: accept-all + download buttons
 *
 * Word count targets mirror backend `drafting_sections.py` and can be overridden
 * per-section via click-to-edit (persisted in localStorage).
 *
 * Status dots use a spinner for `needs_revision` during active drafting (when
 * the agent is still processing) to avoid confusing transient QA failures.
 */
import { useState, useCallback, useMemo, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Lock, Unlock, RefreshCw, Pencil, Send, X, Check,
  ChevronDown, CircleCheck, CircleX, AlertTriangle, Info, MessageSquare,
  Loader2,
} from "lucide-react"
import { useDraftStore } from "@/stores/draftStore"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ExportBar } from "./ExportBar"
import { cn } from "@/lib/utils"
import type { DraftElementSummary, QACheckSummary, ElementAction } from "@/types/api"

// Default target word counts — mirrors backend TARGET_WORD_COUNTS in drafting_sections.py
const DEFAULT_TARGET_WORD_COUNTS: Record<string, number> = {
  introduction: 240,
  background: 400,
  duties_overview: 300,
  major_duties: 300,
  factor_1_knowledge: 270,
  factor_2_supervisory_controls: 270,
  factor_3_guidelines: 260,
  factor_4_complexity: 250,
  factor_5_scope_effect: 260,
  factor_6_7_contacts: 260,
  factor_8_physical_demands: 80,
  factor_9_work_environment: 60,
  other_significant_factors: 260,
  supervisory_factor_1_program_scope: 260,
  supervisory_factor_2_organizational_setting: 260,
  supervisory_factor_3_authority: 260,
  supervisory_factor_4_contacts: 260,
  supervisory_factor_5_work_directed: 260,
  supervisory_factor_6_other_conditions: 260,
}

const LS_WORD_COUNT_OVERRIDES = "pd3r_word_count_targets"

function getWordCountTargets(): Record<string, number> {
  try {
    const raw = localStorage.getItem(LS_WORD_COUNT_OVERRIDES)
    if (raw) {
      const parsed = JSON.parse(raw)
      return { ...DEFAULT_TARGET_WORD_COUNTS, ...parsed }
    }
  } catch { /* ignore */ }
  return { ...DEFAULT_TARGET_WORD_COUNTS }
}

function saveWordCountTarget(sectionName: string, target: number) {
  try {
    const raw = localStorage.getItem(LS_WORD_COUNT_OVERRIDES)
    const overrides = raw ? JSON.parse(raw) : {}
    overrides[sectionName] = target
    localStorage.setItem(LS_WORD_COUNT_OVERRIDES, JSON.stringify(overrides))
  } catch { /* ignore */ }
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

/** All draft sections in document order, mirroring backend DRAFT_ELEMENT_NAMES. */
const CORE_SECTIONS = [
  { name: "introduction", display: "Introduction" },
  { name: "background", display: "Background" },
  { name: "major_duties", display: "Major Duties and Responsibilities" },
  { name: "factor_1_knowledge", display: "Factor 1: Knowledge Required" },
  { name: "factor_2_supervisory_controls", display: "Factor 2: Supervisory Controls" },
  { name: "factor_3_guidelines", display: "Factor 3: Guidelines" },
  { name: "factor_4_complexity", display: "Factor 4: Complexity" },
  { name: "factor_5_scope_effect", display: "Factor 5: Scope and Effect" },
  { name: "factor_6_7_contacts", display: "Factor 6/7: Personal Contacts and Purpose of Contacts" },
  { name: "factor_8_physical_demands", display: "Factor 8: Physical Demands" },
  { name: "factor_9_work_environment", display: "Factor 9: Work Environment" },
  { name: "other_significant_factors", display: "Other Significant Factors" },
]

const SUPERVISORY_SECTIONS = [
  { name: "supervisory_factor_1_program_scope", display: "Supervisory Factor 1: Program Scope and Effect" },
  { name: "supervisory_factor_2_organizational_setting", display: "Supervisory Factor 2: Organizational Setting" },
  { name: "supervisory_factor_3_authority", display: "Supervisory Factor 3: Supervisory and Managerial Authority" },
  { name: "supervisory_factor_4_contacts", display: "Supervisory Factor 4: Personal Contacts" },
  { name: "supervisory_factor_5_work_directed", display: "Supervisory Factor 5: Difficulty of Work Directed" },
  { name: "supervisory_factor_6_other_conditions", display: "Supervisory Factor 6: Other Conditions" },
]

export function ProductPanel() {
  const elements = useDraftStore((s) => s.elements)
  const state = useSessionStore((s) => s.state)
  const pendingOverrides = useSessionStore((s) => s.pendingFieldOverrides)
  // Merge pending overrides so the document header reflects edits immediately
  const vals = { ...(state?.interview_data_values ?? {}), ...pendingOverrides }
  const isSupervisor = state?.is_supervisor

  // Build a lookup for draft content by element name
  const contentMap = new Map(elements.map((el) => [el.name, el]))

  const sections = isSupervisor
    ? [...CORE_SECTIONS, ...SUPERVISORY_SECTIONS]
    : CORE_SECTIONS

  const wordCountTargets = useMemo(() => getWordCountTargets(), [])

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-6 max-w-3xl mx-auto">
          {/* Document header */}
          <DocumentHeader vals={vals} isSupervisor={isSupervisor} />

          <Separator className="my-4" />

          {/* Draft sections */}
          {sections.map((sec) => {
            const el = contentMap.get(sec.name)
            return (
              <DraftSection
                key={sec.name}
                sectionName={sec.name}
                displayName={sec.display}
                element={el}
                targetWordCount={wordCountTargets[sec.name] ?? 0}
              />
            )
          })}
        </div>
      </ScrollArea>
      <ExportBar />
    </div>
  )
}

/** A single draft section with collapsible toolbar: QA report, notes, and controls. */
function DraftSection({
  sectionName,
  displayName,
  element,
  targetWordCount,
}: {
  sectionName: string
  displayName: string
  element: DraftElementSummary | undefined
  targetWordCount: number
}) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState("")
  const [editingTarget, setEditingTarget] = useState(false)
  const [targetDraft, setTargetDraft] = useState("")
  const [currentTarget, setCurrentTarget] = useState(targetWordCount)
  const [pendingAction, setPendingAction] = useState<ElementAction | null>(null)
  const wsRef = useSessionStore((s) => s.wsRef)
  const phase = useSessionStore((s) => s.phase)
  const isTyping = useChatStore((s) => s.isTyping)
  const addMessage = useChatStore((s) => s.addMessage)
  const setTyping = useChatStore((s) => s.setTyping)
  const updateElement = useDraftStore((s) => s.updateElement)

  const hasContent = element?.content && element.content.length > 0
  const isLocked = element?.locked ?? false
  const isEdited = element?.edited ?? false
  const notes = element?.notes ?? ""
  const qaReview = element?.qa_review ?? null
  const actualWords = hasContent ? countWords(element!.content!) : 0

  // Clear pending action when element status changes (backend confirmed)
  const prevStatusRef = useRef(element?.status)
  useEffect(() => {
    if (element?.status !== prevStatusRef.current) {
      prevStatusRef.current = element?.status
      setPendingAction(null)
    }
  }, [element?.status])

  /** Send a structured element action over WebSocket (bypasses LLM classification). */
  const sendElementAction = useCallback(
    (action: ElementAction, feedback?: string) => {
      if (!wsRef) return
      setPendingAction(action)
      const data: Record<string, unknown> = { element: sectionName, action }
      if (feedback) data.feedback = feedback
      wsRef.send(JSON.stringify({ type: "element_action", data }))
      setTyping(true)
    },
    [wsRef, sectionName, setTyping],
  )

  /** Send a free-text message to the agent (for chat-based interactions). */
  const sendAgentMessage = useCallback(
    (content: string) => {
      addMessage("user", content)
      if (wsRef) {
        wsRef.send(JSON.stringify({ type: "user_message", data: { content } }))
        setTyping(true)
      }
    },
    [wsRef, addMessage, setTyping],
  )

  // --- Lock ---
  const handleLock = useCallback(() => {
    updateElement(sectionName, { locked: !isLocked })
  }, [sectionName, isLocked, updateElement])

  // --- Inline edit ---
  const startEdit = useCallback(() => {
    if (!hasContent) return
    setEditDraft(element!.content!)
    setEditing(true)
    setExpanded(true)
  }, [hasContent, element])

  const saveEdit = useCallback(() => {
    updateElement(sectionName, {
      content: editDraft,
      locked: true,
      edited: true,
    })
    setEditing(false)
  }, [sectionName, editDraft, updateElement])

  const cancelEdit = useCallback(() => {
    setEditing(false)
    setEditDraft("")
  }, [])

  // --- Regenerate (sends structured action with feedback) ---
  const handleRegenerate = useCallback(() => {
    if (isLocked) return
    updateElement(sectionName, { edited: false })
    sendElementAction("regenerate", notes.trim() || undefined)
  }, [isLocked, notes, sectionName, sendElementAction, updateElement])

  const saveTarget = useCallback(() => {
    const num = parseInt(targetDraft, 10)
    if (!isNaN(num) && num > 0) {
      setCurrentTarget(num)
      saveWordCountTarget(sectionName, num)
    }
    setEditingTarget(false)
  }, [targetDraft, sectionName])

  // Word count color
  const wordCountColor = (() => {
    if (!hasContent || currentTarget === 0) return "text-muted-foreground"
    const ratio = actualWords / currentTarget
    if (ratio >= 0.8 && ratio <= 1.2) return "text-green-600"
    if (ratio > 1.5 || ratio < 0.5) return "text-red-500"
    return "text-amber-600"
  })()

  // Determine a small status dot for the header.
  // During active drafting, "needs_revision" is transient (auto-rewrite pending),
  // so show a spinner instead of a static amber dot. In review phase, amber is
  // meaningful because the user must act.
  const isAgentProcessing = phase === "drafting" && isTyping
  const statusDot = (() => {
    if (!element) return null
    // During active drafting, "drafted" means QA is running and "needs_revision"
    // means an auto-rewrite is pending — show spinners for both.
    if ((element.status === "drafted" || element.status === "needs_revision") && isAgentProcessing) {
      const color = element.status === "drafted" ? "text-blue-400" : "text-amber-400"
      return <Loader2 className={`h-3 w-3 animate-spin ${color} shrink-0`} />
    }
    switch (element.status) {
      case "approved": return <span className="h-2 w-2 rounded-full bg-green-500 shrink-0" />
      case "qa_passed": return <span className="h-2 w-2 rounded-full bg-green-400 shrink-0" />
      case "drafted": return <span className="h-2 w-2 rounded-full bg-blue-400 shrink-0" />
      case "needs_revision": return <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0" />
      case "pending": return <span className="h-2 w-2 rounded-full bg-gray-300 shrink-0" />
      default: return null
    }
  })()

  return (
    <section className="mb-6 group">
      {/* ── Header row: status dot, title, word count, lock, chevron ── */}
      <div className="flex items-center gap-2 mb-2">
        {statusDot}
        <h2 className="text-base font-semibold flex-1 min-w-0 truncate">{displayName}</h2>

        {/* Word count */}
        {currentTarget > 0 && (
          <span className="flex items-center gap-0.5 text-[10px] tabular-nums shrink-0">
            {hasContent && <span className={wordCountColor}>{actualWords}</span>}
            {hasContent && <span className="text-muted-foreground">/</span>}
            {editingTarget ? (
              <input
                className="w-10 rounded border px-1 py-0 text-[10px] bg-background text-center"
                value={targetDraft}
                onChange={(e) => setTargetDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveTarget()
                  if (e.key === "Escape") setEditingTarget(false)
                }}
                onBlur={saveTarget}
                autoFocus
              />
            ) : (
              <span
                className="text-muted-foreground cursor-pointer hover:underline"
                onClick={() => { setTargetDraft(String(currentTarget)); setEditingTarget(true) }}
                title="Click to edit target"
              >
                {currentTarget}w
              </span>
            )}
          </span>
        )}

        {/* Approve button — visible when content exists and not yet approved/locked */}
        {hasContent && !editing && !isLocked && element?.status !== "approved" && (
          <TooltipProvider delayDuration={300}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-green-600 hover:text-green-700 hover:bg-green-50"
                  disabled={pendingAction === "approve" || isTyping}
                  onClick={() => sendElementAction("approve")}
                >
                  {pendingAction === "approve"
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <CircleCheck className="h-4 w-4" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">Approve &amp; lock section</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Lock button — always visible when content exists */}
        {hasContent && !editing && (
          <TooltipProvider delayDuration={300}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={handleLock}>
                  {isLocked
                    ? <Lock className="h-3.5 w-3.5 text-amber-600" />
                    : <Unlock className="h-3.5 w-3.5 text-muted-foreground" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {isLocked ? "Unlock section" : "Lock section"}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Chevron toggle */}
        {hasContent && !editing && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="h-7 w-7 flex items-center justify-center rounded-md hover:bg-accent shrink-0 transition-colors"
          >
            <ChevronDown className={cn(
              "h-4 w-4 text-muted-foreground transition-transform duration-200",
              expanded && "rotate-180",
            )} />
          </button>
        )}
      </div>

      {/* ── Collapsible panel ── */}
      {expanded && hasContent && !editing && (
        <div className="mb-3 rounded-md border border-border bg-muted/30 text-sm overflow-hidden">
          {/* QA Report */}
          {qaReview && qaReview.passes !== undefined && (
            <div className="px-3 py-2">
              <div className="flex items-center gap-2 mb-1.5">
                {qaReview.passes
                  ? <CircleCheck className="h-3.5 w-3.5 text-green-600 shrink-0" />
                  : <CircleX className="h-3.5 w-3.5 text-red-500 shrink-0" />}
                <span className={cn("text-xs font-medium", qaReview.passes ? "text-green-700" : "text-red-600")}>
                  QA {qaReview.passes ? "Passed" : "Failed"}
                </span>
                <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">
                  {qaReview.passed_count ?? 0}/{(qaReview.passed_count ?? 0) + (qaReview.failed_count ?? 0)} checks
                </span>
              </div>
              {qaReview.overall_feedback && (
                <p className="text-[11px] text-muted-foreground mb-1.5 leading-snug">{qaReview.overall_feedback}</p>
              )}
              {(qaReview.checks ?? []).length > 0 && (
                <div className="space-y-0.5">
                  {(qaReview.checks ?? []).map((c, i) => (
                    <QACheckRow key={i} check={c} />
                  ))}
                </div>
              )}
            </div>
          )}

          {qaReview && <Separator />}

          {/* Feedback + Controls */}
          <div className="px-3 py-2 space-y-2">
            {/* Feedback textarea — persisted, auto-grows, used on regeneration */}
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <MessageSquare className="h-3 w-3 text-muted-foreground" />
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Revision Feedback</span>
              </div>
              <Textarea
                value={notes}
                onChange={(e) => updateElement(sectionName, { notes: e.target.value })}
                placeholder="Describe what to change on next regeneration..."
                className="text-xs min-h-[36px] bg-background resize-y"
                rows={1}
                onInput={(e) => {
                  const ta = e.currentTarget
                  ta.style.height = "auto"
                  ta.style.height = ta.scrollHeight + "px"
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    handleRegenerate()
                  }
                }}
              />
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2">
              {!isLocked && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="h-7 gap-1.5 text-xs"
                  onClick={handleRegenerate}
                >
                  <RefreshCw className="h-3 w-3" />
                  Regenerate
                </Button>
              )}
              <TooltipProvider delayDuration={300}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs" onClick={startEdit}>
                      <Pencil className={cn("h-3 w-3", isEdited ? "text-blue-600" : "text-muted-foreground")} />
                      {isEdited ? "Edit (hand-edited)" : "Edit"}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">Edit content in place</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              {!isLocked && <span className="text-[10px] text-muted-foreground ml-auto">Cmd+Enter to regenerate</span>}
            </div>
            {isLocked && (
              <p className="text-[11px] text-amber-600 flex items-center gap-1">
                <Lock className="h-3 w-3" />
                {isEdited ? "Locked (hand-edited) — unlock to regenerate" : "Locked — unlock to regenerate"}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Inline edit mode ── */}
      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={editDraft}
            onChange={(e) => setEditDraft(e.target.value)}
            className="text-sm min-h-[200px] font-mono"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveEdit() }
              if (e.key === "Escape") cancelEdit()
            }}
          />
          <div className="flex items-center gap-2">
            <Button size="sm" className="h-7 text-xs gap-1" onClick={saveEdit}>
              <Check className="h-3 w-3" /> Save & Lock
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={cancelEdit}>
              Cancel
            </Button>
            <span className="text-[10px] text-muted-foreground ml-auto">Cmd+Enter to save, Esc to cancel</span>
          </div>
        </div>
      ) : hasContent ? (
        <div className="prose prose-sm max-w-none dark:prose-invert text-sm [&>p+p]:mt-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {element!.content!}
          </ReactMarkdown>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground/50 italic">
          {"{ Draft not yet generated }"}
        </p>
      )}
    </section>
  )
}

/** A single QA check result row with severity icon and color coding. */
function QACheckRow({ check }: { check: QACheckSummary }) {
  const icon = check.passed
    ? <CircleCheck className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />
    : check.severity === "critical"
      ? <CircleX className="h-3 w-3 text-red-500 shrink-0 mt-0.5" />
      : check.severity === "warning"
        ? <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0 mt-0.5" />
        : <Info className="h-3 w-3 text-blue-400 shrink-0 mt-0.5" />

  return (
    <div className="flex items-start gap-1.5 py-0.5">
      {icon}
      <div className="min-w-0 flex-1">
        <span className={cn(
          "text-[11px] leading-snug",
          check.passed ? "text-muted-foreground" : "text-foreground",
        )}>
          {check.explanation}
        </span>
        {!check.passed && check.suggestion && (
          <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug italic">
            {check.suggestion}
          </p>
        )}
      </div>
    </div>
  )
}

/** OF-8 style Position Description coversheet header. */
function DocumentHeader({
  vals,
  isSupervisor,
}: {
  vals: Record<string, unknown>
  isSupervisor: boolean | null | undefined
}) {
  const orgHierarchy = Array.isArray(vals.organization_hierarchy)
    ? (vals.organization_hierarchy as string[])
    : []

  const supervisorLabel =
    isSupervisor === true
      ? "Supervisory"
      : isSupervisor === false
        ? "Non-Supervisory"
        : undefined

  // Derive FLSA: supervisory GS-positions are typically Exempt
  const flsaStatus =
    isSupervisor === true
      ? "Exempt"
      : isSupervisor === false
        ? "Nonexempt"
        : undefined

  // Derive position sensitivity from grade
  const gradeNum = vals.grade ? parseInt(String(vals.grade).replace(/\D/g, ""), 10) : NaN
  const positionSensitivity = !isNaN(gradeNum)
    ? gradeNum >= 13
      ? "Noncritical-Sensitive"
      : "Non-Sensitive"
    : undefined

  return (
    <div className="text-xs">
      {/* Form title bar */}
      <div className="bg-primary text-primary-foreground px-3 py-1.5 text-[11px] font-semibold tracking-widest uppercase text-center">
        Position Description — OF-8
      </div>

      {/* Grid coversheet */}
      <table className="w-full border-collapse border border-border text-xs">
        <tbody>
          {/* Row 1: Title + Classification */}
          <tr>
            <td className="border border-border p-2" colSpan={2}>
              <CellLabel>1. Position Title</CellLabel>
              <CellValue value={vals.position_title} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>2. Pay Plan</CellLabel>
              <CellValue value="GS" />
            </td>
            <td className="border border-border p-2">
              <CellLabel>3. Series</CellLabel>
              <CellValue value={vals.series} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>4. Grade</CellLabel>
              <CellValue value={vals.grade} />
            </td>
          </tr>

          {/* Row 2: Organization */}
          <tr>
            <td className="border border-border p-2" colSpan={5}>
              <CellLabel>5. Employing Department / Agency</CellLabel>
              <div className="mt-0.5 text-sm">
                {orgHierarchy.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-x-1">
                    {orgHierarchy.map((level, i) => (
                      <span key={i}>
                        {i > 0 && <span className="text-muted-foreground mx-0.5">/</span>}
                        <span className="font-medium">{level}</span>
                      </span>
                    ))}
                  </div>
                ) : (
                  <Placeholder text="Department / Agency / Office" />
                )}
              </div>
            </td>
          </tr>

          {/* Row 3: Reports To + Supervisory + FLSA */}
          <tr>
            <td className="border border-border p-2" colSpan={2}>
              <CellLabel>6. Reports To (Title)</CellLabel>
              <CellValue value={vals.reports_to} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>7. Supervisory Status</CellLabel>
              <CellValue value={supervisorLabel} />
            </td>
            <td className="border border-border p-2" colSpan={2}>
              <CellLabel>8. FLSA Status</CellLabel>
              <CellValue value={flsaStatus} />
            </td>
          </tr>

          {/* Row 4: Administrative fields */}
          <tr>
            <td className="border border-border p-2">
              <CellLabel>9. Position Sensitivity</CellLabel>
              <CellValue value={positionSensitivity} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>10. Competitive Level</CellLabel>
              <CellValue value={undefined} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>11. Position Number</CellLabel>
              <CellValue value={undefined} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>12. Classified By</CellLabel>
              <CellValue value={undefined} />
            </td>
            <td className="border border-border p-2">
              <CellLabel>13. Date</CellLabel>
              <CellValue value={new Date().toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" })} />
            </td>
          </tr>

          {/* Row 5: Supervisory details (conditional) */}
          {isSupervisor === true && (
            <tr>
              <td className="border border-border p-2" colSpan={3}>
                <CellLabel>Employees Supervised</CellLabel>
                <CellValue value={vals.supervised_employees ? formatDict(vals.supervised_employees) : undefined} />
              </td>
              <td className="border border-border p-2" colSpan={2}>
                <CellLabel>% Time Supervising</CellLabel>
                <CellValue value={vals.percent_supervising ? `${vals.percent_supervising}%` : undefined} />
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function CellLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-0.5">
      {children}
    </div>
  )
}

function CellValue({ value }: { value: unknown }) {
  const hasValue = value !== undefined && value !== null && value !== ""
  return (
    <div className={cn("text-sm", !hasValue && "text-muted-foreground/40 italic")}>
      {hasValue ? String(value) : "—"}
    </div>
  )
}

function Placeholder({ text }: { text: string }) {
  return <span className="text-muted-foreground/40 italic">{text}</span>
}

function formatDict(v: unknown): string {
  if (typeof v === "string") return v
  if (typeof v === "object" && v !== null && !Array.isArray(v)) {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${val}`)
      .join("; ")
  }
  return String(v)
}
