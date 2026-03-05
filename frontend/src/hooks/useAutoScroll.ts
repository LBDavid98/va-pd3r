import { useEffect, useRef, type RefObject } from "react"

/**
 * Returns a ref to attach to a sentinel element at the bottom of a scrollable
 * list. When any value in `deps` changes, the sentinel is scrolled into view.
 *
 * Works correctly inside Radix ScrollArea (which scrolls an internal viewport
 * element) because `scrollIntoView` walks up to the nearest scrollable ancestor
 * regardless of which element that is.
 */
export function useAutoScroll<T extends HTMLElement>(
  deps: unknown[],
): RefObject<T | null> {
  const ref = useRef<T>(null)

  useEffect(() => {
    const el = ref.current
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "end" })
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  return ref
}
