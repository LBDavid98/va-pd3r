/** Fetch wrappers for all PD3r API endpoints. */

import type {
  CreateSessionResponse,
  DraftState,
  LLMConfigResponse,
  SendMessageResponse,
  SessionState,
} from "@/types/api"

const BASE = "" // Uses vite proxy

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

export async function createSession(): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>("/sessions", { method: "POST" })
}

export async function createSeededSession(
  scriptId: string,
  phase: string,
): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>("/sessions/seed", {
    method: "POST",
    body: JSON.stringify({ script_id: scriptId, phase }),
  })
}

export async function getSession(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/sessions/${sessionId}`)
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request(`/sessions/${sessionId}`, { method: "DELETE" })
}

export async function sendMessage(
  sessionId: string,
  content: string,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(`/sessions/${sessionId}/message`, {
    method: "POST",
    body: JSON.stringify({ content }),
  })
}

export async function patchFields(
  sessionId: string,
  fieldOverrides: Record<string, unknown>,
): Promise<{ status: string; fields_updated: string[] }> {
  return request(`/sessions/${sessionId}/fields`, {
    method: "PATCH",
    body: JSON.stringify({ field_overrides: fieldOverrides }),
  })
}

export async function getDraft(sessionId: string): Promise<DraftState> {
  return request<DraftState>(`/sessions/${sessionId}/draft`)
}

export async function getConfig(): Promise<LLMConfigResponse> {
  return request<LLMConfigResponse>("/config")
}

export async function setConfig(
  apiKey: string,
  baseUrl?: string,
): Promise<LLMConfigResponse> {
  return request<LLMConfigResponse>("/config", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey, base_url: baseUrl || null }),
  })
}

export async function stopSession(sessionId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/sessions/${sessionId}/stop`, { method: "POST" })
}

export async function restartSession(sessionId: string): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>(`/sessions/${sessionId}/restart`, { method: "POST" })
}

export async function exportDocument(
  sessionId: string,
  format: "markdown" | "word" = "markdown",
): Promise<Blob> {
  const res = await fetch(
    `${BASE}/sessions/${sessionId}/export?format=${format}`,
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Export failed ${res.status}: ${body}`)
  }
  return res.blob()
}
