export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const apiClient = {
  async get<T>(path: string): Promise<T> {
    try {
      const res = await fetch(path)
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(body.detail ?? res.statusText, res.status)
      }
      return res.json() as Promise<T>
    } catch (err) {
      if (err instanceof ApiError) throw err
      throw new Error('Cannot connect to Clef Server')
    }
  },

  async post<T>(path: string, body: unknown): Promise<T> {
    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(errBody.detail ?? res.statusText, res.status)
      }
      return res.json() as Promise<T>
    } catch (err) {
      if (err instanceof ApiError) throw err
      throw new Error('Cannot connect to Clef Server')
    }
  },

  async put<T>(path: string, body: unknown): Promise<T> {
    try {
      const res = await fetch(path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(errBody.detail ?? res.statusText, res.status)
      }
      return res.json() as Promise<T>
    } catch (err) {
      if (err instanceof ApiError) throw err
      throw new Error('Cannot connect to Clef Server')
    }
  },
}
