import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { PhaseAccordion } from "@/components/chat/PhaseAccordion"
import { ChatPanel } from "@/components/chat/ChatPanel"
import { ProductPanel } from "@/components/draft/ProductPanel"

export function AppShell() {
  return (
    <div className="flex flex-1 min-h-0">
      {/* Fixed-width status sidebar — not resizable, always visible */}
      <aside className="w-56 shrink-0 overflow-y-auto border-r bg-muted/30 px-2 py-2">
        <PhaseAccordion />
      </aside>

      {/* Chat + Draft are resizable within the remaining space */}
      <ResizablePanelGroup direction="horizontal" className="flex-1 min-h-0">
        <ResizablePanel defaultSize={50} minSize={30}>
          <ChatPanel />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={50} minSize={30}>
          <ProductPanel />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
