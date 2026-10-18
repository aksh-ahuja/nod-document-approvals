import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const { api, post, setCsrf, ApiError } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
)
const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

test('mutations send the current CSRF token and same-origin cookies', async () => {
  setCsrf('rotated-csrf-token')
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/submissions/create/')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.headers['X-CSRFToken'], 'rotated-csrf-token')
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), { title: 'Proposal' })
    return Response.json({ status: true, data: { id: 'submission-id' } }, { status: 201 })
  }
  assert.deepEqual(await post('submissions/create/', { title: 'Proposal' }), {
    id: 'submission-id',
  })
})

test('field validation details survive the API boundary', async () => {
  globalThis.fetch = async () =>
    Response.json(
      { status: false, message: 'Check the form.', errors: { reviewer_id: ['Required.'] } },
      { status: 400 },
    )
  await assert.rejects(
    api('submissions/create/'),
    (error) =>
      error instanceof ApiError &&
      error.status === 400 &&
      error.fields.reviewer_id[0] === 'Required.',
  )
})

test('conflicts remain distinguishable from transport failures', async () => {
  globalThis.fetch = async () =>
    Response.json({ status: false, message: 'Already decided.' }, { status: 409 })
  await assert.rejects(
    post('submissions/decision/id/'),
    (error) => error.status === 409 && error.message === 'Already decided.',
  )
})

test('network failure produces a recoverable message', async () => {
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch')
  }
  await assert.rejects(
    api('auth/me/'),
    (error) => error.status === 0 && error.message.includes('try again'),
  )
})

test('cancelled navigation does not become a network error', async () => {
  globalThis.fetch = async () => {
    throw new DOMException('Aborted', 'AbortError')
  }
  await assert.rejects(api('submissions/list/'), (error) => error.name === 'AbortError')
})

test('a proxy error page produces a readable error', async () => {
  globalThis.fetch = async () => new Response('<h1>Bad gateway</h1>', { status: 502 })
  await assert.rejects(
    api('submissions/list/'),
    (error) => error.status === 502 && error.message.includes('temporarily unavailable'),
  )
})

test('file uploads keep CSRF protection and let the browser set the multipart boundary', async () => {
  const form = new FormData()
  form.set('file', new Blob(['review this']), 'notes.txt')
  setCsrf('upload-token')
  globalThis.fetch = async (url, options) => {
    assert.equal(options.body, form)
    assert.equal(options.headers['Content-Type'], undefined)
    assert.equal(options.headers['X-CSRFToken'], 'upload-token')
    assert.equal(options.credentials, 'same-origin')
    return Response.json({ status: true, data: { id: 'uploaded-document' } }, { status: 201 })
  }
  assert.deepEqual(await post('submissions/create/', form), { id: 'uploaded-document' })
})

test('cloud upload sends raw bytes without Nod credentials or CSRF tokens', async () => {
  const { transferFile } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
  const originalWindow = globalThis.window
  const originalXhr = globalThis.XMLHttpRequest
  let request
  globalThis.window = { location: { origin: 'https://nod.example' } }
  globalThis.XMLHttpRequest = class {
    constructor() { request = this; this.upload = {}; this.headers = {} }
    open(method, url) { this.method = method; this.url = url }
    setRequestHeader(key, value) { this.headers[key] = value }
    send(body) { this.body = body; this.status = 201; this.onload() }
  }
  try {
    setCsrf('secret-csrf')
    const file = new File(['hello'], 'notes.txt')
    await transferFile({
      upload_id: 'id', upload_url: 'https://storage.example/staging/key?signature', method: 'PUT',
      headers: { 'Content-Type': 'text/plain', 'x-ms-blob-type': 'BlockBlob' }, local: false,
    }, file, () => {}, new AbortController().signal)
    assert.equal(request.body, file)
    assert.equal(request.method, 'PUT')
    assert.equal(request.headers['X-CSRFToken'], undefined)
    assert.notEqual(request.withCredentials, true)
  } finally {
    globalThis.window = originalWindow
    globalThis.XMLHttpRequest = originalXhr
  }
})

test('local upload keeps CSRF protection and refuses a foreign local address', async () => {
  const { transferFile } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
  const originalWindow = globalThis.window
  const originalXhr = globalThis.XMLHttpRequest
  let request
  globalThis.window = { location: { origin: 'http://localhost:5173' } }
  globalThis.XMLHttpRequest = class {
    constructor() { request = this; this.upload = {}; this.headers = {} }
    open() {}
    setRequestHeader(key, value) { this.headers[key] = value }
    send() { this.status = 201; this.onload() }
  }
  try {
    setCsrf('local-csrf')
    const instruction = { upload_url: '/api/v1/uploads/content/id/?token=signed', method: 'PUT', headers: {}, local: true }
    await transferFile(instruction, new File(['hello'], 'notes.txt'), () => {}, new AbortController().signal)
    assert.equal(request.headers['X-CSRFToken'], 'local-csrf')
    await assert.rejects(transferFile({ ...instruction, upload_url: 'https://evil.example' },
      new File(['hello'], 'notes.txt'), () => {}, new AbortController().signal), /invalid/)
  } finally {
    globalThis.window = originalWindow
    globalThis.XMLHttpRequest = originalXhr
  }
})

test('validation polling exposes rejection and accepts a ready upload', async () => {
  const { waitForUpload } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
  globalThis.fetch = async () => Response.json({ status: true, data: { status: 'rejected', error: 'Invalid PDF.' } })
  await assert.rejects(waitForUpload('id', new AbortController().signal), /Invalid PDF/)
  globalThis.fetch = async () => Response.json({ status: true, data: { status: 'ready' } })
  await waitForUpload('id', new AbortController().signal)
})
