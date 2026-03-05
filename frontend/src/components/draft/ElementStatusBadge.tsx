import { Badge } from "@/components/ui/badge"
import { STATUS_COLORS } from "@/lib/constants"
import type { ElementStatus } from "@/types/api"
import { cn } from "@/lib/utils"

export function ElementStatusBadge({ status }: { status: ElementStatus }) {
  const style = STATUS_COLORS[status] ?? STATUS_COLORS.pending

  return (
    <Badge variant="secondary" className={cn(style.bg, style.text, "text-xs")}>
      {style.label}
    </Badge>
  )
}
