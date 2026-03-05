import { useState, useEffect, useCallback } from "react"
import { ChevronUp, ChevronDown, Plus, X, Settings, FlaskConical, Play } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useSessionStore } from "@/stores/sessionStore"
import { useChatStore } from "@/stores/chatStore"
import { useDraftStore } from "@/stores/draftStore"
import * as api from "@/api/client"
import { TEST_SCRIPTS, getActiveScriptId, setActiveScriptId } from "@/utils/autoFillScript"

const SEED_PHASES = [
  { id: "init", label: "Fresh Start", description: "Default — no pre-populated state" },
  { id: "interview", label: "Interview", description: "Mid-interview with some fields collected" },
  { id: "requirements", label: "Requirements", description: "All fields collected, ready to confirm" },
  { id: "drafting", label: "Drafting", description: "Confirmed, first draft section generating" },
  { id: "complete", label: "Complete", description: "All sections drafted, ready for export" },
] as const

const LS_KEY = "pd3r_api_key"
const LS_BASE_URL = "pd3r_base_url"
const LS_DEFAULT_ORG = "pd3r_default_org"
const LS_MISSION_TEXT = "pd3r_mission_text"

const DEFAULT_ORG_LIST = [
  "Department of Veterans Affairs",
  "Veterans Health Administration",
  "Digital Health Office",
]

export const DEFAULT_MISSION_TEXT =
  "Deliver modern, innovating, and user-centered digital health solutions " +
  "to create outstanding health care experiences for Veterans and their care teams."

/** Read the saved default org list (or return the built-in default). */
export function getDefaultOrgList(): string[] {
  try {
    const raw = localStorage.getItem(LS_DEFAULT_ORG)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch { /* ignore */ }
  return DEFAULT_ORG_LIST
}

/** Read the saved mission text (or return the built-in default). */
export function getMissionText(): string {
  return localStorage.getItem(LS_MISSION_TEXT) || DEFAULT_MISSION_TEXT
}

export function SettingsDialog() {
  const isConnected = useSessionStore((s) => s.isConnected)
  const [open, setOpen] = useState(false)

  // LLM tab state
  const [apiKey, setApiKey] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmStatus, setLlmStatus] = useState<"idle" | "saved" | "error">("idle")
  const [hasKey, setHasKey] = useState(false)

  // Organization tab state
  const [orgList, setOrgList] = useState<string[]>(DEFAULT_ORG_LIST)
  const [orgAdding, setOrgAdding] = useState("")
  const [missionText, setMissionText] = useState("")
  const [orgStatus, setOrgStatus] = useState<"idle" | "saved">("idle")

  // Testing tab state
  const [activeScript, setActiveScript] = useState(getActiveScriptId())
  const [seedPhase, setSeedPhase] = useState("init")
  const [seedLoading, setSeedLoading] = useState(false)
  const [seedStatus, setSeedStatus] = useState<"idle" | "ok" | "error">("idle")
  const [seedError, setSeedError] = useState("")

  // Load saved values from localStorage on mount
  useEffect(() => {
    setApiKey(localStorage.getItem(LS_KEY) ?? "")
    setBaseUrl(localStorage.getItem(LS_BASE_URL) ?? "")
    setOrgList(getDefaultOrgList())
    setMissionText(getMissionText())
    api.getConfig().then((cfg) => setHasKey(cfg.has_key)).catch(() => {})
  }, [])

  const moveOrg = useCallback((from: number, dir: -1 | 1) => {
    setOrgList((prev) => {
      const to = from + dir
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      ;[next[from], next[to]] = [next[to], next[from]]
      return next
    })
  }, [])

  const removeOrg = useCallback((index: number) => {
    setOrgList((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const addOrg = useCallback(() => {
    const trimmed = orgAdding.trim()
    if (!trimmed) return
    setOrgList((prev) => [...prev, trimmed])
    setOrgAdding("")
  }, [orgAdding])

  const handleSaveLlm = useCallback(async () => {
    if (!apiKey.trim()) return
    setLlmSaving(true)
    setLlmStatus("idle")
    try {
      await api.setConfig(apiKey.trim(), baseUrl.trim() || undefined)
      localStorage.setItem(LS_KEY, apiKey.trim())
      if (baseUrl.trim()) {
        localStorage.setItem(LS_BASE_URL, baseUrl.trim())
      } else {
        localStorage.removeItem(LS_BASE_URL)
      }
      setHasKey(true)
      setLlmStatus("saved")
      setTimeout(() => setLlmStatus("idle"), 2000)
    } catch {
      setLlmStatus("error")
    } finally {
      setLlmSaving(false)
    }
  }, [apiKey, baseUrl])

  const handleSeedSession = useCallback(async () => {
    if (seedPhase === "init") {
      // Fresh start — just reset the session normally
      useChatStore.getState().clear()
      useDraftStore.getState().clear()
      useSessionStore.setState({ sessionId: null, phase: "init", state: null })
      setOpen(false)
      return
    }
    setSeedLoading(true)
    setSeedStatus("idle")
    setSeedError("")
    try {
      const data = await api.createSeededSession(activeScript, seedPhase)
      // Reset stores and inject seeded session
      useChatStore.getState().clear()
      useDraftStore.getState().clear()
      useSessionStore.setState({
        sessionId: data.session_id,
        phase: data.phase as any,
        isLoading: false,
        state: null,
      })
      if (data.message && data.message !== "Session created") {
        useChatStore.getState().addMessage("agent", data.message)
      }
      setSeedStatus("ok")
      setOpen(false)
    } catch (e) {
      setSeedStatus("error")
      setSeedError(e instanceof Error ? e.message : "Failed to seed session")
    } finally {
      setSeedLoading(false)
    }
  }, [activeScript, seedPhase])

  const handleSaveOrg = useCallback(() => {
    localStorage.setItem(LS_DEFAULT_ORG, JSON.stringify(orgList))
    localStorage.setItem(LS_MISSION_TEXT, missionText)
    setOrgStatus("saved")
    setTimeout(() => setOrgStatus("idle"), 2000)
  }, [orgList, missionText])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5 text-primary-foreground hover:bg-primary-foreground/15">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              isConnected ? "bg-green-400" : "bg-red-400"
            }`}
          />
          <Settings className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Configure your API key and default interview values.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="llm">
          <TabsList>
            <TabsTrigger value="llm">LLM</TabsTrigger>
            <TabsTrigger value="organization">Organization</TabsTrigger>
            <TabsTrigger value="testing" className="gap-1">
              <FlaskConical className="h-3 w-3" />
              Testing
            </TabsTrigger>
          </TabsList>

          {/* ─── LLM Tab ─── */}
          <TabsContent value="llm">
            <div className="space-y-4 py-2">
              {/* Connection status */}
              <div className="flex items-center gap-2 rounded border px-3 py-2 text-sm">
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    isConnected ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                <span className="font-medium">
                  {isConnected ? "Connected" : "Disconnected"}
                </span>
                {hasKey && (
                  <span className="ml-auto text-xs text-muted-foreground">API key configured</span>
                )}
                {!hasKey && (
                  <span className="ml-auto text-xs text-amber-600">API key needed</span>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="api-key">API Key</Label>
                <Input
                  id="api-key"
                  type="password"
                  placeholder="sk-..."
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="base-url">Endpoint URL (optional)</Label>
                <Input
                  id="base-url"
                  type="url"
                  placeholder="https://api.openai.com/v1"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Leave blank for default OpenAI. Set to your org's proxy or
                  OpenAI-compatible endpoint.
                </p>
              </div>

              <div className="flex items-center justify-between">
                {llmStatus === "saved" && (
                  <span className="text-sm text-green-600">Saved</span>
                )}
                {llmStatus === "error" && (
                  <span className="text-sm text-destructive">
                    Failed to save — is the backend running?
                  </span>
                )}
                {llmStatus === "idle" && <span />}
                <Button onClick={handleSaveLlm} disabled={llmSaving || !apiKey.trim()}>
                  {llmSaving ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* ─── Organization Tab ─── */}
          <TabsContent value="organization">
            <div className="space-y-4 py-2">
              {/* Organization Hierarchy */}
              <div className="space-y-2">
                <Label>Default Organization Hierarchy</Label>
                <p className="text-xs text-muted-foreground">
                  Pre-fills the organization field for new sessions.
                </p>
                <div className="space-y-1 rounded border p-2">
                  {orgList.map((item, i) => (
                    <div key={i} className="flex items-center gap-1 text-sm">
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
                          disabled={i === orgList.length - 1}
                          onClick={() => moveOrg(i, 1)}
                        >
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      </div>
                      <span className="flex-1 truncate text-xs">{item}</span>
                      <button
                        className="text-muted-foreground hover:text-destructive shrink-0"
                        onClick={() => removeOrg(i)}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                  <div className="flex items-center gap-1 pt-1">
                    <Input
                      className="h-7 text-xs"
                      placeholder="Add level..."
                      value={orgAdding}
                      onChange={(e) => setOrgAdding(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") addOrg()
                      }}
                    />
                    <button
                      className="text-primary hover:text-primary/80 shrink-0"
                      onClick={addOrg}
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Mission Text */}
              <div className="space-y-2">
                <Label htmlFor="mission-text">Mission Text</Label>
                <textarea
                  id="mission-text"
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  placeholder="Describe the organization's mission..."
                  value={missionText}
                  onChange={(e) => setMissionText(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Used to enrich the introduction section with organizational context.
                </p>
              </div>

              <div className="flex items-center justify-between">
                {orgStatus === "saved" && (
                  <span className="text-sm text-green-600">Saved</span>
                )}
                {orgStatus === "idle" && <span />}
                <Button onClick={handleSaveOrg}>Save</Button>
              </div>
            </div>
          </TabsContent>
          {/* ─── Testing Tab ─── */}
          <TabsContent value="testing">
            <div className="space-y-4 py-2">
              <p className="text-xs text-muted-foreground">
                Select a script for <kbd className="rounded border px-1 py-0.5 text-[10px]">Option+Enter</kbd> auto-fill.
              </p>

              {/* Script selection */}
              <div className="space-y-2">
                {TEST_SCRIPTS.map((script) => (
                  <label
                    key={script.id}
                    className={`flex items-start gap-3 rounded-md border p-3 cursor-pointer transition-colors ${
                      activeScript === script.id
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-muted-foreground/30"
                    }`}
                    onClick={() => {
                      setActiveScript(script.id)
                      setActiveScriptId(script.id)
                    }}
                  >
                    <input
                      type="radio"
                      name="test-script"
                      checked={activeScript === script.id}
                      onChange={() => {
                        setActiveScript(script.id)
                        setActiveScriptId(script.id)
                      }}
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{script.name}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{script.description}</div>
                    </div>
                  </label>
                ))}
              </div>

              {/* Phase jump — only for scripts with field data */}
              {activeScript !== "questions-only" && (
                <div className="space-y-2 rounded border p-3">
                  <Label className="text-xs font-medium">Jump to Phase</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {SEED_PHASES.map((p) => (
                      <button
                        key={p.id}
                        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                          seedPhase === p.id
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border hover:border-muted-foreground/50"
                        }`}
                        onClick={() => setSeedPhase(p.id)}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    {SEED_PHASES.find((p) => p.id === seedPhase)?.description}
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      className="gap-1.5"
                      onClick={handleSeedSession}
                      disabled={seedLoading}
                    >
                      <Play className="h-3 w-3" />
                      {seedLoading ? "Creating..." : seedPhase === "init" ? "New Session" : `Start at ${SEED_PHASES.find((p) => p.id === seedPhase)?.label}`}
                    </Button>
                    {seedStatus === "error" && (
                      <span className="text-xs text-destructive">{seedError}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Push saved config to backend on app startup.
 * Call this once in App.tsx before creating a session.
 */
export async function syncConfigToBackend(): Promise<boolean> {
  const key = localStorage.getItem(LS_KEY)
  if (!key) return false
  const baseUrl = localStorage.getItem(LS_BASE_URL)
  try {
    await api.setConfig(key, baseUrl || undefined)
    return true
  } catch {
    return false
  }
}
