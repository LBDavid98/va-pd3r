/**
 * Scripted answers for Option+Send auto-fill during development/demos.
 * Select the active script in Settings → Testing.
 */
import type { SessionState, Phase } from "@/types/api"

// ---------------------------------------------------------------------------
// Script definitions
// ---------------------------------------------------------------------------

export interface TestScript {
  id: string
  name: string
  description: string
  /** Opening message to kick off the session */
  opening: string
  /** Field name → scripted answer for the interview phase */
  fields: Record<string, string>
  /** Phase → response for non-interview phases */
  phaseResponses: Partial<Record<Phase, string>>
  /** Default response during drafting (approve sections) */
  draftingResponse: string
  /** Ordered list of extra messages injected at specific points (optional) */
  extraMessages?: { phase: Phase; trigger: "missing_empty"; message: string }[]
}

const SCRIPT_PROGRAM_ANALYST: TestScript = {
  id: "program-analyst",
  name: "GS-11 Program Analyst",
  description: "Standard non-supervisory PD — full interview through drafting",
  opening: "Hi, I'd like to create a position description for a Program Analyst.",
  fields: {
    position_title: "Program Analyst",
    series: "0343",
    grade: "11",
    organization_hierarchy:
      "Department of Veterans Affairs, Veterans Health Administration, Office of Health Informatics",
    reports_to: "Supervisory Program Analyst",
    daily_activities:
      "Analyze program performance data and prepare reports; Coordinate with stakeholders on program requirements; Develop and maintain tracking systems for key performance indicators; Draft policy recommendations based on data analysis; Support budget formulation and execution reviews",
    major_duties:
      "Analyze healthcare program effectiveness and develop improvement recommendations 40%; Coordinate cross-functional projects and track milestones 30%; Prepare briefings, reports, and policy documents for senior leadership 30%",
    is_supervisor: "no",
    mission_text:
      "Deliver modern, innovative, and user-centered digital health solutions to create outstanding health care experiences for Veterans and their care teams.",
    work_schedule: "Full-time permanent",
    supervisor_name: "Sarah Chen, Branch Chief",
  },
  phaseResponses: {
    requirements: "yes, that looks correct",
    review: "approved",
    complete: "no",
  },
  draftingResponse: "approve",
}

const SCRIPT_SUPERVISORY: TestScript = {
  id: "supervisory",
  name: "GS-14 Supervisory IT Specialist",
  description: "Supervisory position with full GSSG factors",
  opening: "I need to write a PD for a supervisory IT Specialist position.",
  fields: {
    position_title: "Supervisory IT Specialist (SYSADMIN)",
    series: "2210",
    grade: "14",
    organization_hierarchy:
      "Department of Veterans Affairs, Office of Information and Technology, Enterprise Cloud Solutions Office",
    reports_to: "Deputy Chief Information Officer",
    daily_activities:
      "Oversee cloud infrastructure operations and team of system administrators; Conduct performance reviews and mentoring sessions; Coordinate with security team on ATO compliance; Review and approve change requests; Attend leadership meetings on IT modernization",
    major_duties:
      "Direct cloud infrastructure operations and ensure 99.9% uptime for Veteran-facing systems 35%; Supervise and develop a team of 8 IT specialists across GS-9 to GS-13 levels 30%; Lead IT modernization initiatives and cloud migration projects 20%; Serve as technical advisor to senior leadership on infrastructure strategy 15%",
    is_supervisor: "yes",
    supervised_employees:
      "3 GS-13 Senior System Administrators, 3 GS-12 System Administrators, 2 GS-9 Junior System Administrators",
    num_supervised: "8",
    percent_supervising: "30",
    f1_program_scope: "4",
    f2_organizational_setting: "3",
    f3_supervisory_authorities: "4",
    f4_key_contacts: "3",
    f5_subordinate_details:
      "8 subordinates across 3 grade levels performing systems administration, cloud operations, and security compliance work",
    f6_special_conditions:
      "24/7 on-call responsibility for critical system outages; manages classified and sensitive Veteran health data systems",
    mission_text:
      "Provide reliable, secure, and modern IT infrastructure that enables VA to deliver world-class healthcare and benefits services to our nation's Veterans.",
    work_schedule: "Full-time permanent",
    supervisor_name: "Robert Kim, Deputy CIO",
  },
  phaseResponses: {
    requirements: "yes, confirmed",
    review: "approved",
    complete: "no",
  },
  draftingResponse: "approve",
}

const SCRIPT_QUESTIONS_ONLY: TestScript = {
  id: "questions-only",
  name: "Curious User (No PD)",
  description: "Asks lots of questions about PDs and HR, then quits without writing one",
  opening: "Hi, I have some questions about position descriptions before I get started.",
  fields: {}, // No field answers — this script never completes the interview
  phaseResponses: {
    requirements: "no, I'm not ready yet",
    complete: "no",
  },
  draftingResponse: "approve",
  extraMessages: [],
}

// The questions-only script uses a sequence of questions instead of field answers
const QUESTIONS_SEQUENCE = [
  "What exactly is a position description? How is it different from a job posting?",
  "What's the Factor Evaluation System? How does it determine the grade level?",
  "Can you explain what a series code is? Like what's the difference between 0343 and 2210?",
  "How do supervisory positions get evaluated differently from non-supervisory ones?",
  "What are the major sections that go into a PD?",
  "How long does it typically take to write a good PD?",
  "What's the difference between GS-12 and GS-13 level work for an analyst?",
  "I think I need more time to gather my information. Let's stop here for now.",
  "quit",
]

// ---------------------------------------------------------------------------
// Script registry & localStorage persistence
// ---------------------------------------------------------------------------

export const TEST_SCRIPTS: TestScript[] = [
  SCRIPT_PROGRAM_ANALYST,
  SCRIPT_SUPERVISORY,
  SCRIPT_QUESTIONS_ONLY,
]

const LS_ACTIVE_SCRIPT = "pd3r_test_script"
const LS_QUESTION_INDEX = "pd3r_question_index"

export function getActiveScriptId(): string {
  return localStorage.getItem(LS_ACTIVE_SCRIPT) || TEST_SCRIPTS[0].id
}

export function setActiveScriptId(id: string): void {
  localStorage.setItem(LS_ACTIVE_SCRIPT, id)
  // Reset question index when switching scripts
  localStorage.setItem(LS_QUESTION_INDEX, "0")
}

function getActiveScript(): TestScript {
  const id = getActiveScriptId()
  return TEST_SCRIPTS.find((s) => s.id === id) ?? TEST_SCRIPTS[0]
}

function getAndAdvanceQuestionIndex(): number {
  const idx = parseInt(localStorage.getItem(LS_QUESTION_INDEX) ?? "0", 10)
  localStorage.setItem(LS_QUESTION_INDEX, String(idx + 1))
  return idx
}

// ---------------------------------------------------------------------------
// Main export — called by ChatPanel on Option+Send
// ---------------------------------------------------------------------------

/**
 * Get the next auto-fill response based on current session state and phase.
 * Returns null if no appropriate scripted response is available.
 */
export function getAutoFillResponse(
  state: SessionState | null,
  phase: Phase,
): string | null {
  const script = getActiveScript()

  // No state yet — send the opening greeting
  if (!state || phase === "init") {
    // Reset question index at session start
    localStorage.setItem(LS_QUESTION_INDEX, "0")
    return script.opening
  }

  // Questions-only script — cycle through question sequence
  if (script.id === "questions-only" && phase === "interview") {
    const idx = getAndAdvanceQuestionIndex()
    if (idx < QUESTIONS_SEQUENCE.length) {
      return QUESTIONS_SEQUENCE[idx]
    }
    return "quit"
  }

  // Interview phase — answer the current field being asked about
  if (phase === "interview") {
    const field = state.current_field ?? state.missing_fields[0]
    if (field) {
      return script.fields[field] ?? `Test data for ${field.replace(/_/g, " ")}`
    }
    // All fields collected but still in interview — confirm
    return "yes, that's everything"
  }

  // Phase-specific confirmation
  const phaseResponse = script.phaseResponses[phase]
  if (phaseResponse) return phaseResponse

  // Drafting — approve sections
  if (phase === "drafting") {
    return script.draftingResponse
  }

  return "continue"
}
