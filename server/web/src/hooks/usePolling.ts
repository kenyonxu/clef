import { useEffect, useRef } from 'react'

export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  shouldStop?: () => boolean,
): void {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    const id = setInterval(() => {
      if (shouldStop?.()) {
        clearInterval(id)
        return
      }
      callbackRef.current()
    }, intervalMs)

    return () => clearInterval(id)
  }, [intervalMs, shouldStop])
}
