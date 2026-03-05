import { create } from "zustand"
import type { DraftElementSummary } from "@/types/api"
import * as api from "@/api/client"

interface DraftStore {
  elements: DraftElementSummary[]
  isLoading: boolean

  fetchDraft: (sessionId: string) => Promise<void>
  updateElement: (name: string, update: Partial<DraftElementSummary>) => void
  setElements: (elements: DraftElementSummary[]) => void
  clear: () => void
}

export const useDraftStore = create<DraftStore>((set) => ({
  elements: [],
  isLoading: false,

  fetchDraft: async (sessionId) => {
    set({ isLoading: true })
    try {
      const draft = await api.getDraft(sessionId)
      // Preserve local-only fields (locked, notes, edited, hand-edited content)
      const current = new Map(
        useDraftStore.getState().elements.map((el) => [el.name, el]),
      )
      const merged = draft.elements.map((el) => {
        const prev = current.get(el.name)
        if (!prev) return el
        return {
          ...el,
          locked: prev.locked,
          notes: prev.notes,
          edited: prev.edited,
          // If user hand-edited, keep their content
          ...(prev.edited ? { content: prev.content } : {}),
          // Prefer fresh QA from server, fall back to local
          qa_review: el.qa_review ?? prev.qa_review,
        }
      })
      set({ elements: merged, isLoading: false })
    } catch {
      set({ isLoading: false })
    }
  },

  updateElement: (name, update) =>
    set((s) => ({
      elements: s.elements.map((el) =>
        el.name === name ? { ...el, ...update } : el,
      ),
    })),

  setElements: (elements) => set({ elements }),
  clear: () => set({ elements: [], isLoading: false }),
}))
