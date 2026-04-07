import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiClient } from '../api/client'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

beforeEach(() => {
  mockFetch.mockReset()
})

describe('apiClient', () => {
  describe('get', () => {
    it('calls fetch with correct URL and returns parsed JSON', async () => {
      const data = { session_id: 'clef-abc123', status: 'done' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(data),
      })

      const result = await apiClient.get('/status/clef-abc123')
      expect(mockFetch).toHaveBeenCalledWith('/status/clef-abc123')
      expect(result).toEqual(data)
    })

    it('throws ApiError on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: 'Session not found' }),
      })

      await expect(apiClient.get('/status/missing')).rejects.toThrow('Session not found')
    })

    it('throws "Cannot connect" on network error', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

      await expect(apiClient.get('/status/clef-abc123')).rejects.toThrow('Cannot connect to Clef Server')
    })
  })

  describe('post', () => {
    it('calls fetch with POST method and JSON body', async () => {
      const response = { session_id: 'clef-new', status: 'created' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(response),
      })

      const result = await apiClient.post('/compose', { prompt: 'Epic theme' })
      expect(mockFetch).toHaveBeenCalledWith('/compose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Epic theme' }),
      })
      expect(result).toEqual(response)
    })
  })
})
