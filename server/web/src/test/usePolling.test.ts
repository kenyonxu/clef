import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls callback at interval', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()

    renderHook(() => usePolling(callback, 1000))

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(2)
  })

  it('stops polling when stop condition returns true', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()
    let shouldStop = false

    renderHook(() =>
      usePolling(callback, 1000, () => shouldStop),
    )

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    shouldStop = true
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('cleans up interval on unmount', async () => {
    const { usePolling } = await import('../hooks/usePolling')
    const callback = vi.fn()

    const { unmount } = renderHook(() => usePolling(callback, 1000))

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(callback).toHaveBeenCalledTimes(1)

    unmount()

    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })
})
