const API_BASE = '/console/api'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 204) return undefined as T
  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try { payload = JSON.parse(text) } catch { throw new ApiError(502, 'console.invalid_json', 'Respuesta inválida del servidor') }
  }
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string } } | null)?.error
    throw new ApiError(response.status, error?.code ?? 'console.request_failed', error?.message ?? 'La operación no pudo completarse')
  }
  return payload as T
}

function query(params: Record<string, string | number | undefined | null>) {
  const output = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') output.set(key, String(value))
  })
  const value = output.toString()
  return value ? `?${value}` : ''
}

export const api = {
  get<T>(path: string) { return request<T>(path) },
  post<T>(path: string, body?: unknown) { return request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }) },
  patch<T>(path: string, body: unknown) { return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }) },
  query,
}
