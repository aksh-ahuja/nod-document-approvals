let csrfToken = ''

export class ApiError extends Error {
  status: number
  fields: Record<string, string[]>
  constructor(message: string, status: number, fields: Record<string, string[]> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

export function setCsrf(token: string) {
  csrfToken = token
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1/${path}`, {
      ...options,
      credentials: 'same-origin',
      headers: {
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        'X-CSRFToken': csrfToken,
        ...options.headers,
      },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Could not connect to Nod. Your work is still here. Please try again.', 0)
  }
  const body = await response.json().catch(() => null)
  if (!response.ok || !body?.status) {
    throw new ApiError(
      body?.message || 'Nod is temporarily unavailable. Please try again.',
      response.status,
      body?.errors || {},
    )
  }
  return body.data as T
}

export function post<T>(path: string, data: unknown = {}) {
  return api<T>(path, {
    method: 'POST',
    body: data instanceof FormData ? data : JSON.stringify(data),
  })
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

export type UploadInstruction = {
  upload_id: string
  upload_url: string
  method: 'PUT'
  headers: Record<string, string>
  expires_in: number
  local: boolean
}

export type UploadState = {
  upload_id: string
  status: 'pending' | 'validating' | 'ready' | 'rejected' | 'attached' | 'expired'
  error: string
}

export function transferFile(
  instruction: UploadInstruction,
  file: File,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const url = new URL(instruction.upload_url, window.location.origin)
    const local = instruction.local && url.origin === window.location.origin

    if (instruction.local && !local) {
      reject(new Error('The upload address is invalid. Please try again.'))
      return
    }

    xhr.open(instruction.method, url.href)
    xhr.timeout = 240_000
    for (const [key, value] of Object.entries(instruction.headers)) xhr.setRequestHeader(key, value)
    if (local) xhr.setRequestHeader('X-CSRFToken', csrfToken)

    const abort = () => xhr.abort()
    const cleanup = () => signal.removeEventListener('abort', abort)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      cleanup()
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new ApiError('Upload did not finish. Your file is still here. Try again.', xhr.status))
    }
    xhr.onerror = xhr.ontimeout = () => {
      cleanup()
      reject(new ApiError('Upload interrupted. Check your connection and try again.', 0))
    }
    xhr.onabort = () => {
      cleanup()
      reject(new DOMException('Aborted', 'AbortError'))
    }
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    signal.addEventListener('abort', abort, { once: true })
    xhr.send(file)
  })
}

export async function waitForUpload(id: string, signal: AbortSignal): Promise<void> {
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    const upload = await api<UploadState>(`uploads/status/${id}/`, { signal })
    if (upload.status === 'ready' || upload.status === 'attached') return
    if (upload.status === 'rejected' || upload.status === 'expired') {
      throw new ApiError(upload.error || 'Please choose the file again.', 422)
    }
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException('Aborted', 'AbortError'))
        return
      }
      const abort = () => {
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      }
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', abort)
        resolve()
      }, 1500)
      signal.addEventListener('abort', abort, { once: true })
    })
  }
  throw new ApiError('Your file is still being checked. Try again shortly to continue.', 408)
}
