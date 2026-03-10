import { create } from "zustand"
import { nanoid } from "nanoid"
import type { ChatMessage, ChatMessageType } from "@/types/api"

const HUNG_THRESHOLD_MS = 120_000

interface ChatStore {
  messages: ChatMessage[]
  isTyping: boolean
  typingSince: number | null
  isHung: boolean

  addMessage: (role: "user" | "agent", content: string, type?: ChatMessageType) => void
  setTyping: (typing: boolean) => void
  checkHung: () => void
  clear: () => void
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  isTyping: false,
  typingSince: null,
  isHung: false,

  addMessage: (role, content, type = "normal") =>
    set((s) => {
      // Deduplicate: skip if the last message has identical role + content
      // within a 2-second window. This prevents WS echo duplicates while
      // still allowing legitimate repeated messages (e.g. approving
      // different sections that produce the same confirmation text).
      const last = s.messages[s.messages.length - 1]
      if (last && last.role === role && last.content === content && Date.now() - last.timestamp < 2000) {
        return s
      }
      return {
        messages: [
          ...s.messages,
          { id: nanoid(), role, content, timestamp: Date.now(), type },
        ],
      }
    }),

  setTyping: (typing) =>
    set({
      isTyping: typing,
      typingSince: typing ? Date.now() : null,
      isHung: typing ? get().isHung : false,
    }),

  checkHung: () => {
    const { typingSince, isTyping } = get()
    if (isTyping && typingSince && Date.now() - typingSince > HUNG_THRESHOLD_MS) {
      set({ isHung: true })
    }
  },

  clear: () => set({ messages: [], isTyping: false, typingSince: null, isHung: false }),
}))
