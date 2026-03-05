/**
 * PhaseAccordion — left-sidebar workflow stepper.
 *
 * Renders one accordion item per workflow phase (init → interview → requirements
 * → drafting → review → complete). Each item shows a phase-appropriate icon
 * (spinner, check, circle) and expands to reveal phase-specific detail:
 *   - init: editable org hierarchy + mission text
 *   - interview: InterviewFieldList (collected/pending fields)
 *   - requirements: FES evaluation score grid
 *   - drafting: element progress grid with status dots
 *   - review: approval progress counter
 *   - complete: download button
 *
 * The currently-active phase auto-expands when the phase changes.
 */
import { useState, useEffect, useCallback } from "react"
import { CheckCircle, Circle, Loader2, Download, ChevronUp, ChevronDown, Plus, X, PencilLine } from "lucide-react"
import { useSessionStore } from "@/stores/sessionStore"
import { useDraftStore } from "@/stores/draftStore"
import { exportDocument } from "@/api/client"
import { buildFilename } from "@/hooks/useExport"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { PHASE_ORDER, PHASE_LABELS, STATUS_COLORS } from "@/lib/constants"
import { cn } from "@/lib/utils"
import type { Phase, FESEvaluationSummary, ElementStatus } from "@/types/api"
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion"
import { InterviewFieldList } from "./InterviewFieldList"

/** Workflow stepper showing all phases with expandable detail panels. */
export function PhaseAccordion() {
  const phase = useSessionStore((s) => s.phase)
  const sessionId = useSessionStore((s) => s.sessionId)
  const state = useSessionStore((s) => s.state)
  const currentIndex = PHASE_ORDER.indexOf(phase)

  // Auto-expand the current phase (including init so users can review org/mission)
  const [expanded, setExpanded] = useState<string>(phase)

  // When the phase changes, auto-expand the new current phase
  useEffect(() => {
    setExpanded(phase)
  }, [phase])

  return (
    <div>
      <Accordion type="single" collapsible value={expanded} onValueChange={(v) => setExpanded(v)}>
        {PHASE_ORDER.map((p, i) => {
          // init is always "done" once the session exists
          const initDone = p === "init" && !!sessionId
          const isPast = i < currentIndex || initDone
          const isCurrent = p === phase && !initDone
          const isFuture = i > currentIndex && !initDone

          return (
            <AccordionItem key={p} value={p}>
              <AccordionTrigger
                className={cn(
                  "py-1.5 text-xs",
                  isFuture && "opacity-40",
                )}
                disabled={isFuture}
              >
                <PhaseIcon phase={p} isPast={isPast} isCurrent={isCurrent} />
                <span className={cn(isCurrent && "font-semibold")}>
                  {PHASE_LABELS[p]}
                </span>
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground">
                <PhaseDetail phase={p} isPast={isPast} isCurrent={isCurrent} state={state} />
              </AccordionContent>
            </AccordionItem>
          )
        })}
      </Accordion>
    </div>
  )
}

/** Phase status icon: green check (past), spinner (current), grey circle (future). */
function PhaseIcon({
  phase,
  isPast,
  isCurrent,
}: {
  phase: Phase
  isPast: boolean
  isCurrent: boolean
}) {
  const elements = useDraftStore((s) => s.elements)
  const downloaded = useSessionStore((s) => s.downloaded)

  // Review: spinner until all approved, then green check
  if (phase === "review" && isCurrent) {
    const allApproved = elements.length > 0 && elements.every((el) => el.status === "approved" || el.locked)
    if (allApproved) return <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
    return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin shrink-0" />
  }

  // Complete: green check only after download
  if (phase === "complete" && (isCurrent || isPast)) {
    if (downloaded) return <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
    return <Circle className="h-3.5 w-3.5 text-blue-500 shrink-0" />
  }

  if (isPast) return <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
  if (isCurrent) return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin shrink-0" />
  return <Circle className="h-3.5 w-3.5 text-muted-foreground/30 shrink-0" />
}

/** Renders phase-specific content inside the accordion (fields, FES grid, progress, etc). */
function PhaseDetail({
  phase,
  isPast,
  isCurrent,
  state,
}: {
  phase: Phase
  isPast: boolean
  isCurrent: boolean
  state: ReturnType<typeof useSessionStore.getState>["state"]
}) {
  switch (phase) {
    case "init":
      return <InitPhaseContent />

    case "interview":
      if (isCurrent || isPast) return <InterviewFieldList />
      return <span>Collecting position information</span>

    case "requirements": {
      const fes = state?.fes_evaluation
      return (
        <div className="space-y-2">
          {isPast && (
            <span className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-green-500" /> Requirements confirmed</span>
          )}
          {isCurrent && !isPast && (
            <span>Reviewing collected requirements...</span>
          )}
          {!isPast && !isCurrent && (
            <span>Confirm requirements before drafting</span>
          )}
          {fes && <FESScoreGrid fes={fes} />}
        </div>
      )
    }

    case "drafting": {
      if (!isPast && !isCurrent) return <span>Generate position description elements</span>
      return <DraftingProgress />
    }

    case "review":
      if (!isPast && !isCurrent) return <span>Review and approve each section</span>
      return <ReviewProgress />

    case "complete":
      if (isCurrent || isPast) return <CompletePhaseContent />
      return <span>Download document</span>

    default:
      return null
  }
}

/** Init phase detail: editable organization hierarchy and mission statement. */
function InitPhaseContent() {
  const state = useSessionStore((s) => s.state)
  const pendingOverrides = useSessionStore((s) => s.pendingFieldOverrides)
  const setFieldOverride = useSessionStore((s) => s.setFieldOverride)
  const values = { ...(state?.interview_data_values ?? {}), ...pendingOverrides }

  const orgList: string[] = Array.isArray(values.organization_hierarchy)
    ? values.organization_hierarchy.map(String)
    : []
  const missionText = typeof values.mission_text === "string" ? values.mission_text : ""

  const [editingOrg, setEditingOrg] = useState(false)
  const [editingMission, setEditingMission] = useState(false)
  const [orgDraft, setOrgDraft] = useState<string[]>([])
  const [orgAdding, setOrgAdding] = useState("")
  const [missionDraft, setMissionDraft] = useState("")

  const startEditOrg = useCallback(() => {
    setOrgDraft([...orgList])
    setEditingOrg(true)
  }, [orgList])

  const startEditMission = useCallback(() => {
    setMissionDraft(missionText)
    setEditingMission(true)
  }, [missionText])

  const moveOrg = useCallback((from: number, dir: -1 | 1) => {
    setOrgDraft((prev) => {
      const to = from + dir
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      ;[next[from], next[to]] = [next[to], next[from]]
      return next
    })
  }, [])

  const removeOrg = useCallback((index: number) => {
    setOrgDraft((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const addOrg = useCallback(() => {
    const trimmed = orgAdding.trim()
    if (!trimmed) return
    setOrgDraft((prev) => [...prev, trimmed])
    setOrgAdding("")
  }, [orgAdding])

  const saveOrg = useCallback(() => {
    setFieldOverride("organization_hierarchy", orgDraft)
    setEditingOrg(false)
  }, [orgDraft, setFieldOverride])

  const saveMission = useCallback(() => {
    setFieldOverride("mission_text", missionDraft)
    setEditingMission(false)
  }, [missionDraft, setFieldOverride])

  return (
    <div className="space-y-2">
      {/* Organization Hierarchy */}
      <div className="space-y-0.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Organization
          </span>
          {!editingOrg && orgList.length > 0 && (
            <button onClick={startEditOrg} className="text-muted-foreground hover:text-foreground">
              <PencilLine className="h-3 w-3" />
            </button>
          )}
        </div>
        {editingOrg ? (
          <div className="space-y-1 rounded border bg-background p-1.5">
            {orgDraft.map((item, i) => (
              <div key={i} className="flex items-center gap-0.5 text-xs">
                <div className="flex flex-col">
                  <button
                    className="text-muted-foreground hover:text-foreground disabled:opacity-20"
                    disabled={i === 0}
                    onClick={() => moveOrg(i, -1)}
                  >
                    <ChevronUp className="h-3 w-3" />
                  </button>
                  <button
                    className="text-muted-foreground hover:text-foreground disabled:opacity-20"
                    disabled={i === orgDraft.length - 1}
                    onClick={() => moveOrg(i, 1)}
                  >
                    <ChevronDown className="h-3 w-3" />
                  </button>
                </div>
                <span className="flex-1 truncate">{item}</span>
                <button
                  className="text-muted-foreground hover:text-destructive shrink-0"
                  onClick={() => removeOrg(i)}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            <div className="flex items-center gap-1 pt-0.5">
              <input
                className="flex-1 rounded border px-1.5 py-0.5 text-xs bg-background"
                placeholder="Add level..."
                value={orgAdding}
                onChange={(e) => setOrgAdding(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addOrg()
                  if (e.key === "Escape") setEditingOrg(false)
                }}
              />
              <button className="text-primary hover:text-primary/80 shrink-0" onClick={addOrg}>
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="flex justify-end gap-1 pt-0.5">
              <button onClick={saveOrg} className="text-green-600 text-xs font-medium">Save</button>
              <button onClick={() => setEditingOrg(false)} className="text-muted-foreground text-xs">Cancel</button>
            </div>
          </div>
        ) : (
          <div className="text-xs">
            {orgList.length > 0 ? (
              orgList.map((item, i) => (
                <div key={i} className="truncate text-foreground">
                  {"  ".repeat(i)}{i > 0 ? "› " : ""}{item}
                </div>
              ))
            ) : (
              <span className="text-muted-foreground/60 italic">Not set</span>
            )}
          </div>
        )}
      </div>

      {/* Mission Text */}
      <div className="space-y-0.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Mission
          </span>
          {!editingMission && missionText && (
            <button onClick={startEditMission} className="text-muted-foreground hover:text-foreground">
              <PencilLine className="h-3 w-3" />
            </button>
          )}
        </div>
        {editingMission ? (
          <div className="space-y-1 rounded border bg-background p-1.5">
            <textarea
              className="w-full min-h-[60px] rounded border px-1.5 py-1 text-xs bg-background resize-y"
              value={missionDraft}
              onChange={(e) => setMissionDraft(e.target.value)}
              autoFocus
            />
            <div className="flex justify-end gap-1">
              <button onClick={saveMission} className="text-green-600 text-xs font-medium">Save</button>
              <button onClick={() => setEditingMission(false)} className="text-muted-foreground text-xs">Cancel</button>
            </div>
          </div>
        ) : (
          <div
            className={cn(
              "text-xs",
              missionText ? "text-foreground cursor-pointer hover:underline" : "text-muted-foreground/60 italic",
            )}
            onClick={missionText ? startEditMission : undefined}
          >
            {missionText || "Not set"}
          </div>
        )}
      </div>
    </div>
  )
}

/** Short display names for the element grid. */
const ELEMENT_SHORT_NAMES: Record<string, string> = {
  introduction: "Intro",
  background: "Background",
  duties_overview: "Duties Overview",
  major_duties: "Major Duties",
  factor_1_knowledge: "F1 Knowledge",
  factor_2_supervisory_controls: "F2 Supv Controls",
  factor_3_guidelines: "F3 Guidelines",
  factor_4_complexity: "F4 Complexity",
  factor_5_scope_effect: "F5 Scope/Effect",
  factor_6_7_contacts: "F6/7 Contacts",
  factor_8_physical_demands: "F8 Physical",
  factor_9_work_environment: "F9 Work Env",
  other_significant_factors: "Other Factors",
  supervisory_factor_1_program_scope: "SF1 Program",
  supervisory_factor_2_organizational_setting: "SF2 Org Setting",
  supervisory_factor_3_authority: "SF3 Authority",
  supervisory_factor_4_contacts: "SF4 Contacts",
  supervisory_factor_5_work_directed: "SF5 Work Dir",
  supervisory_factor_6_other_conditions: "SF6 Other",
}

/** Status dot color classes. */
function statusDotClass(status: ElementStatus): string {
  switch (status) {
    case "approved": return "bg-green-500"
    case "qa_passed": return "bg-green-400"
    case "drafted": case "draft": return "bg-blue-400"
    case "needs_revision": return "bg-orange-400"
    case "pending": default: return "bg-muted-foreground/20"
  }
}

/** Drafting phase: progress bar + element grid with color-coded status dots. */
function DraftingProgress() {
  const elements = useDraftStore((s) => s.elements)
  const currentName = useSessionStore((s) => s.state?.current_element_name)

  if (elements.length === 0) {
    return <span>Preparing draft elements...</span>
  }

  const done = elements.filter((e) =>
    e.status === "approved" || e.status === "qa_passed",
  ).length
  const total = elements.length
  const pct = Math.round((done / total) * 100)

  return (
    <div className="space-y-1.5">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <Progress value={pct} className="h-1.5 flex-1" />
        <span className="text-[10px] tabular-nums text-muted-foreground shrink-0">
          {done}/{total}
        </span>
      </div>

      {/* Element grid */}
      <div className="grid grid-cols-2 gap-x-2 gap-y-px">
        {elements.map((el) => {
          const isActive = el.name === currentName
          const shortName = ELEMENT_SHORT_NAMES[el.name] ?? el.display_name
          const { label } = STATUS_COLORS[el.status] ?? { label: el.status }
          return (
            <div
              key={el.name}
              className={cn(
                "flex items-center gap-1 py-px text-[11px] rounded-sm px-0.5",
                isActive && "bg-blue-50 dark:bg-blue-950",
              )}
              title={`${el.display_name}: ${label}`}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(el.status))} />
              <span className={cn(
                "truncate",
                isActive ? "font-medium text-blue-700 dark:text-blue-300" : "text-muted-foreground",
              )}>
                {shortName}
              </span>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-2 gap-y-0 pt-0.5">
        {([
          ["bg-muted-foreground/20", "Pending"],
          ["bg-blue-400", "Drafted"],
          ["bg-orange-400", "Revising"],
          ["bg-green-400", "QA Passed"],
          ["bg-green-500", "Approved"],
        ] as const).map(([dot, lbl]) => (
          <span key={lbl} className="flex items-center gap-0.5 text-[9px] text-muted-foreground">
            <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
            {lbl}
          </span>
        ))}
      </div>
    </div>
  )
}

/** FES (Factor Evaluation System) score card showing primary + other factors with point totals. */
function FESScoreGrid({ fes }: { fes: FESEvaluationSummary }) {
  const primary = fes.factors.filter((f) => {
    const n = typeof f.factor_num === "string" ? parseInt(f.factor_num) : f.factor_num
    return n >= 1 && n <= 5
  })
  const other = fes.factors.filter((f) => {
    const n = typeof f.factor_num === "string" ? parseInt(f.factor_num) : f.factor_num
    return n >= 6 && n <= 9
  })

  return (
    <div className="space-y-1.5 rounded border bg-background p-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          FES Evaluation — {fes.grade}
        </span>
        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold">
          {fes.total_points} pts
        </span>
      </div>
      {primary.length > 0 && (
        <div>
          <p className="text-[10px] font-medium text-muted-foreground mb-0.5">Primary Factors</p>
          <div className="grid grid-cols-1 gap-px">
            {primary.map((f) => (
              <FESFactorRow key={String(f.factor_num)} factor={f} />
            ))}
          </div>
        </div>
      )}
      {other.length > 0 && (
        <div>
          <p className="text-[10px] font-medium text-muted-foreground mb-0.5">Other Factors</p>
          <div className="grid grid-cols-1 gap-px">
            {other.map((f) => (
              <FESFactorRow key={String(f.factor_num)} factor={f} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function FESFactorRow({ factor }: { factor: FESEvaluationSummary["factors"][number] }) {
  // Shorten factor name for compact display
  const shortName = factor.factor_name
    .replace(/^Factor \d+:\s*/, "")
    .replace("Knowledge Required by the Position", "Knowledge Required")
    .replace("Scope and Effect", "Scope & Effect")
    .replace("Personal Contacts", "Contacts")

  return (
    <div className="flex items-center gap-1 py-px text-[11px]">
      <span className="w-5 shrink-0 text-right font-mono text-muted-foreground">
        {factor.factor_num}
      </span>
      <span className="flex-1 truncate">{shortName}</span>
      <span className="shrink-0 font-mono text-muted-foreground">{factor.level_code}</span>
      <span className="w-8 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
        {factor.points}
      </span>
    </div>
  )
}

/** Review phase: shows count of approved/locked sections out of total. */
function ReviewProgress() {
  const elements = useDraftStore((s) => s.elements)

  if (elements.length === 0) return <span>Waiting for draft elements...</span>

  const approved = elements.filter((e) => e.status === "approved" || e.locked).length
  const total = elements.length
  const allDone = approved === total

  return (
    <div className="space-y-1">
      {allDone ? (
        <span className="flex items-center gap-1 text-green-600 font-medium">
          <CheckCircle className="h-3 w-3" /> All sections approved
        </span>
      ) : (
        <span>Approving sections ({approved}/{total})</span>
      )}
    </div>
  )
}

/** Complete phase: export/download button with progress tracking. */
function CompletePhaseContent() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const chatTitle = useSessionStore((s) => s.chatTitle)
  const downloaded = useSessionStore((s) => s.downloaded)
  const setDownloaded = useSessionStore((s) => s.setDownloaded)
  const [busy, setBusy] = useState(false)

  const handleExport = useCallback(async () => {
    if (!sessionId) return
    setBusy(true)
    try {
      const blob = await exportDocument(sessionId, "word")
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = buildFilename(chatTitle, ".docx")
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setDownloaded(true)
    } catch (e) {
      console.error("Export failed:", e)
    } finally {
      setBusy(false)
    }
  }, [sessionId, chatTitle, setDownloaded])

  return (
    <div className="space-y-1.5">
      {downloaded ? (
        <span className="flex items-center gap-1 text-green-600 font-medium">
          <CheckCircle className="h-3 w-3" /> Document downloaded
        </span>
      ) : (
        <span>Ready to download</span>
      )}
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs justify-start gap-1.5"
        disabled={busy}
        onClick={handleExport}
      >
        <Download className="h-3 w-3" />
        {busy ? "Exporting..." : "Download"}
      </Button>
    </div>
  )
}
