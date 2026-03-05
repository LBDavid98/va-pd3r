/**
 * InterviewFieldList — displays collected/pending interview fields in the
 * PhaseAccordion's interview section.
 *
 * Each field shows a check (collected) or circle (pending) icon, with
 * click-to-edit for scalar values and a ListFieldEditor for array fields
 * (e.g., organization_hierarchy). Edits are dispatched as field overrides
 * via sessionStore, which PATCHes the backend immediately.
 *
 * Supervisory fields are dimmed/disabled when position is non-supervisory.
 */
import { useState, useCallback } from "react"
import { CheckCircle, Circle, PencilLine, ChevronUp, ChevronDown, Plus, X } from "lucide-react"
import { useSessionStore } from "@/stores/sessionStore"
import { BASE_FIELDS, SUPERVISORY_FIELDS, type FieldMeta } from "@/lib/fieldMeta"
import { cn } from "@/lib/utils"

/** Field checklist with inline editing. Shows base fields + conditional supervisory fields. */
export function InterviewFieldList() {
  const state = useSessionStore((s) => s.state)
  const pendingOverrides = useSessionStore((s) => s.pendingFieldOverrides)
  // Merge pending overrides on top of backend values so edits are visible immediately
  const values = { ...(state?.interview_data_values ?? {}), ...pendingOverrides }
  // Derive supervisor status from merged values (respects pending overrides + backend state)
  const isSupervisor = values.is_supervisor != null
    ? isTruthy(values.is_supervisor)
    : state?.is_supervisor ?? null

  const collected = state?.collected_fields?.length ?? 0
  const missing = state?.missing_fields?.length ?? 0
  const total = collected + missing

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
        <span>Fields</span>
        <span>{collected}/{total || "..."}</span>
      </div>
      {BASE_FIELDS.map((f) => (
        <FieldRow key={f.key} field={f} value={values[f.key]} disabled={false} />
      ))}
      {SUPERVISORY_FIELDS.map((f) => (
        <FieldRow
          key={f.key}
          field={f}
          value={values[f.key]}
          disabled={isSupervisor !== true}
        />
      ))}
    </div>
  )
}

/** Single field row: status icon + label + editable value. Click to edit, Enter to save. */
function FieldRow({
  field,
  value,
  disabled,
}: {
  field: FieldMeta
  value: unknown
  disabled: boolean
}) {
  const setFieldOverride = useSessionStore((s) => s.setFieldOverride)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")

  const hasValue = value !== undefined && value !== null
  const isList = field.fieldType === "list"
  const displayValue = hasValue ? formatValue(value) : "Pending"

  const startEdit = useCallback(() => {
    if (!hasValue || disabled) return
    if (isList) {
      setEditing(true)
      return
    }
    setDraft(typeof value === "string" ? value : JSON.stringify(value))
    setEditing(true)
  }, [hasValue, disabled, value, isList])

  const save = useCallback(() => {
    setFieldOverride(field.key, draft)
    setEditing(false)
  }, [field.key, draft, setFieldOverride])

  const cancel = useCallback(() => {
    setEditing(false)
  }, [])

  return (
    <div
      className={cn(
        "flex items-start gap-1.5 py-0.5 px-0.5 rounded text-xs group",
        disabled && "opacity-40 pointer-events-none",
      )}
    >
      {hasValue ? (
        <CheckCircle className="h-3.5 w-3.5 text-green-500 mt-0.5 shrink-0" />
      ) : (
        <Circle className="h-3.5 w-3.5 text-muted-foreground/40 mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <span className="text-muted-foreground">{field.label}</span>
        {editing && isList ? (
          <ListFieldEditor
            fieldKey={field.key}
            items={toStringArray(value)}
            onClose={() => setEditing(false)}
          />
        ) : editing ? (
          <div className="flex items-center gap-1 mt-0.5">
            <input
              className="flex-1 rounded border px-1.5 py-0.5 text-xs bg-background"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") save()
                if (e.key === "Escape") cancel()
              }}
              autoFocus
            />
            <button onClick={save} className="text-green-600 text-xs font-medium">
              Save
            </button>
            <button onClick={cancel} className="text-muted-foreground text-xs">
              Cancel
            </button>
          </div>
        ) : (
          <div
            className={cn(
              "truncate",
              hasValue ? "text-foreground cursor-pointer hover:underline" : "text-muted-foreground/60 italic",
            )}
            onClick={startEdit}
            title={hasValue ? String(displayValue) : undefined}
          >
            {displayValue}
            {hasValue && (
              <PencilLine className="inline ml-1 h-3 w-3 opacity-0 group-hover:opacity-60" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** Inline editor for list-type fields with reorder + add + remove. */
function ListFieldEditor({
  fieldKey,
  items: initialItems,
  onClose,
}: {
  fieldKey: string
  items: string[]
  onClose: () => void
}) {
  const setFieldOverride = useSessionStore((s) => s.setFieldOverride)
  const [items, setItems] = useState<string[]>([...initialItems])
  const [adding, setAdding] = useState("")

  const move = useCallback((from: number, dir: -1 | 1) => {
    setItems((prev) => {
      const to = from + dir
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      ;[next[from], next[to]] = [next[to], next[from]]
      return next
    })
  }, [])

  const remove = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const addItem = useCallback(() => {
    const trimmed = adding.trim()
    if (!trimmed) return
    setItems((prev) => [...prev, trimmed])
    setAdding("")
  }, [adding])

  const save = useCallback(() => {
    setFieldOverride(fieldKey, items)
    onClose()
  }, [fieldKey, items, setFieldOverride, onClose])

  return (
    <div className="mt-1 space-y-1 rounded border bg-background p-1.5">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-0.5 text-xs">
          <div className="flex flex-col">
            <button
              className="text-muted-foreground hover:text-foreground disabled:opacity-20"
              disabled={i === 0}
              onClick={() => move(i, -1)}
            >
              <ChevronUp className="h-3 w-3" />
            </button>
            <button
              className="text-muted-foreground hover:text-foreground disabled:opacity-20"
              disabled={i === items.length - 1}
              onClick={() => move(i, 1)}
            >
              <ChevronDown className="h-3 w-3" />
            </button>
          </div>
          <span className="flex-1 truncate">{item}</span>
          <button
            className="text-muted-foreground hover:text-destructive shrink-0"
            onClick={() => remove(i)}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}

      <div className="flex items-center gap-1 pt-0.5">
        <input
          className="flex-1 rounded border px-1.5 py-0.5 text-xs bg-background"
          placeholder="Add item..."
          value={adding}
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") addItem()
            if (e.key === "Escape") onClose()
          }}
        />
        <button
          className="text-primary hover:text-primary/80 shrink-0"
          onClick={addItem}
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex justify-end gap-1 pt-0.5">
        <button onClick={save} className="text-green-600 text-xs font-medium">
          Save
        </button>
        <button onClick={onClose} className="text-muted-foreground text-xs">
          Cancel
        </button>
      </div>
    </div>
  )
}

function toStringArray(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String)
  if (typeof v === "string") return v.split(",").map((s) => s.trim()).filter(Boolean)
  return []
}

function isTruthy(v: unknown): boolean {
  if (typeof v === "boolean") return v
  if (typeof v === "string") return ["yes", "true", "1"].includes(v.toLowerCase())
  return Boolean(v)
}

function formatValue(v: unknown): string {
  if (typeof v === "string") return v
  if (typeof v === "boolean") return v ? "Yes" : "No"
  if (typeof v === "number") return String(v)
  if (Array.isArray(v)) return v.join(", ")
  if (typeof v === "object" && v !== null) {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${val}`)
      .join("; ")
  }
  return String(v)
}
