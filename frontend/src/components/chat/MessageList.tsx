import { useChatStore } from "@/stores/chatStore"
import { useAutoScroll } from "@/hooks/useAutoScroll"
import { MessageBubble } from "./MessageBubble"
import { TypingIndicator } from "./TypingIndicator"
import { ScrollArea } from "@/components/ui/scroll-area"

export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const isTyping = useChatStore((s) => s.isTyping)
  const scrollRef = useAutoScroll<HTMLDivElement>([messages.length, isTyping])

  return (
    <ScrollArea className="flex-1 min-h-0">
      <div className="flex flex-col gap-3 p-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={scrollRef} />
      </div>
    </ScrollArea>
  )
}
