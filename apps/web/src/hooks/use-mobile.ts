import * as React from "react"

const MOBILE_BREAKPOINT = 768

const query = () => `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribe(onChange: () => void) {
  const mql = window.matchMedia(query())
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

// Window width is an external system, so subscribe to it rather than mirroring
// it into state from an effect: the matchMedia listener is the source of truth
// and useSyncExternalStore keeps getSnapshot's boolean stable, so there is no
// cascade and no stale first paint (the old version rendered false, then
// corrected itself after mount).
//
// getServerSnapshot returns false so SSR and the first client render agree;
// the store re-reads on hydration and settles on the real breakpoint.
export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query()).matches,
    () => false,
  )
}
