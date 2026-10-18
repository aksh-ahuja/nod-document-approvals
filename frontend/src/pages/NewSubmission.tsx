import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Check, FileText, LockKeyhole, Send, Upload, X } from 'lucide-react'
import { api, ApiError, transferFile, waitForUpload } from '../api'
import type { UploadInstruction, UploadState } from '../api'
import { navigate, useApi } from '../hooks'
import { Avatar, ErrorBanner, Spinner } from '../components/ui'
import { DocumentTypePicker, findDocumentType, titlePrefix } from '../components/DocumentType'
import type { DocumentType } from '../components/DocumentType'
import type { Submission, User } from '../types'

export function NewSubmission({
  initialType,
  notify,
}: {
  initialType: string | null
  notify: (message: string) => void
}) {
  const [docType, setDocType] = useState<DocumentType | null>(() => findDocumentType(initialType))
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [reviewer, setReviewer] = useState('')
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState('')
  const [progress, setProgress] = useState(0)
  const upload = useRef<UploadInstruction | null>(null)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  const [error, setError] = useState<unknown>(null)
  const reviewers = useApi<User[]>('reviewers/list/')
  const selected = reviewers.data?.find((user) => user.id === reviewer)
  const fields = error instanceof ApiError ? error.fields : {}
  const edited = () => {
    setRequestId(crypto.randomUUID())
    setError(null)
  }
  const chooseFile = (files: FileList | null) => {
    setDragging(false)
    if (!files?.length || busy) return
    if (files.length !== 1) {
      setError(new Error('Choose one document per submission.'))
      return
    }
    const chosen = files[0]
    if (!/\.(pdf|docx|txt)$/i.test(chosen.name)) {
      setError(new Error('Choose a PDF, DOCX, or TXT document.'))
      return
    }
    if (!chosen.size || chosen.size > 10 * 1024 * 1024) {
      setError(
        new Error(chosen.size ? 'Your file must be 10 MB or smaller.' : 'This file is empty.'),
      )
      return
    }
    upload.current = null
    setPhase('')
    setFile(chosen)
    edited()
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!docType || !file) return
    setBusy(true)
    setError(null)
    try {
      controller.current = new AbortController()
      const signal = controller.current.signal
      setPhase('Preparing upload…')
      const resuming = Boolean(upload.current)
      if (!upload.current) {
        upload.current = await api<UploadInstruction>('uploads/create/', {
          method: 'POST',
          body: JSON.stringify({ filename: file.name, size: file.size, content_type: file.type }),
          signal,
        })
      }
      const instruction = upload.current
      let state: UploadState | undefined
      try {
        if (resuming) {
          state = await api<UploadState>(`uploads/complete/${instruction.upload_id}/`, {
            method: 'POST',
            signal,
          })
        }
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error
      }
      if (!state) {
        setPhase('Uploading…')
        setProgress(0)
        await transferFile(instruction, file, setProgress, signal)
        await api<UploadState>(`uploads/complete/${instruction.upload_id}/`, {
          method: 'POST',
          signal,
        })
      }
      setPhase('Checking file…')
      await waitForUpload(instruction.upload_id, signal)

      setPhase('Sending for review…')
      const result = await api<Submission>('submissions/create/', {
        method: 'POST',
        body: JSON.stringify({
          // The backend still requires a title, so derive it from the type and file name.
          title: `${titlePrefix(docType)}${file.name.replace(/\.[^.]+$/, '')}`.slice(0, 200),
          reviewer_id: reviewer,
          client_request_id: requestId,
          upload_id: instruction.upload_id,
        }),
        signal,
      })
      notify('Document sent for review.')
      navigate(`/submissions/${result.id}`)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      if (error instanceof ApiError && [400, 403, 410, 422].includes(error.status)) {
        upload.current = null
      }
      setError(error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <main id="main-content" tabIndex={-1} className="workspace-content narrow-content">
      <a className="back-link" href="#/app">
        <ArrowLeft size={15} /> My submissions
      </a>
      <div className="page-heading">
        <div>
          <h1>Upload document</h1>
          <p>Add your document and choose who reviews it.</p>
        </div>
      </div>
      {!docType ? (
        <section className="compose-main">
          <div className="form-section-title">
            <span className="step-circle">1</span>
            <div>
              <h2>Document type</h2>
              <p>Choose what kind of document you are sending.</p>
            </div>
            <FileText size={20} />
          </div>
          <DocumentTypePicker
            onSelect={(type) => {
              setDocType(type)
              edited()
            }}
          />
        </section>
      ) : (
        <form className="submission-compose" onSubmit={submit}>
          <section className="compose-main">
            <div className="form-section-title">
              <span className="step-circle">2</span>
              <div>
                <h2>Upload {docType.label}</h2>
                <p>Add a clear copy for your reviewer.</p>
              </div>
              <button
                type="button"
                className="change-type"
                disabled={busy}
                onClick={() => {
                  upload.current = null
                  setPhase('')
                  setFile(null)
                  setDocType(null)
                  edited()
                }}
              >
                Change type
              </button>
            </div>
            <div className="upload-area">
              <label
                className={`file-dropzone ${dragging ? 'dragging' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault()
                  if (!busy) setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  chooseFile(event.dataTransfer.files)
                }}
              >
                <input
                  className="sr-only"
                  type="file"
                  accept=".pdf,.docx,.txt"
                  aria-label="Upload document"
                  aria-describedby="file-hint"
                  disabled={busy}
                  onChange={(event) => {
                    chooseFile(event.target.files)
                    event.target.value = ''
                  }}
                />
                <Upload size={24} strokeWidth={1.5} />
                <strong>
                  {file ? 'Choose a different file' : 'Choose a file or drop it here'}
                </strong>
                <span id="file-hint">PDF, DOCX, or TXT · Up to 10 MB</span>
              </label>
              {file && (
                <div className="selected-file">
                  <FileText size={22} />
                  <div>
                    <strong>{file.name}</strong>
                    <span>
                      {file.size < 1024 * 1024
                        ? `${Math.ceil(file.size / 1024)} KB`
                        : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Remove file"
                    disabled={busy}
                    onClick={() => {
                      upload.current = null
                      setPhase('')
                      setFile(null)
                      edited()
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              {busy && phase && (
                <div className="upload-progress" role="status" aria-live="polite">
                  <span>
                    {phase}
                    {phase === 'Uploading…' ? ` ${progress}%` : ''}
                  </span>
                  {phase === 'Uploading…' && (
                    <progress value={progress} max={100} aria-label="Upload progress" />
                  )}
                </div>
              )}
              {fields.file && <p className="field-error">{fields.file}</p>}
            </div>
          </section>
          <aside className="compose-side">
            <section className="form-card">
              <div className="form-section-title">
                <span className="step-circle">3</span>
                <div>
                  <h2>Reviewer</h2>
                  <p>Choose who makes the decision.</p>
                </div>
              </div>
              <ErrorBanner error={reviewers.error} retry={reviewers.refresh} />
              <label>
                Send to
                <select
                  required
                  disabled={busy || reviewers.loading}
                  value={reviewer}
                  onChange={(event) => {
                    setReviewer(event.target.value)
                    edited()
                  }}
                >
                  <option value="">
                    {reviewers.loading ? 'Loading reviewers…' : 'Choose a reviewer'}
                  </option>
                  {reviewers.data?.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name} · {user.email}
                    </option>
                  ))}
                </select>
              </label>
              {reviewers.data?.length === 0 && (
                <p className="field-error">
                  No reviewers are available yet. Ask your workspace administrator to grant reviewer
                  access.
                </p>
              )}
              {selected && (
                <div className="selected-reviewer">
                  <Avatar user={selected} />
                  <div>
                    <strong>{selected.name}</strong>
                    <span>Will review your document</span>
                  </div>
                  <Check size={16} />
                </div>
              )}
              <div className="form-divider" />
              <div className="submission-rules">
                <LockKeyhole size={16} />
                <p>
                  After you send, the content and reviewer are locked. Every decision stays on
                  record.
                </p>
              </div>
              <ErrorBanner error={error} />
              <button className="button primary full" disabled={busy || !reviewer || !file}>
                {busy ? (
                  <>
                    <Spinner /> {phase || 'Preparing…'}
                  </>
                ) : (
                  <>
                    <Send size={16} /> Send for review
                  </>
                )}
              </button>
              <a className="cancel-link" href="#/app">
                Cancel
              </a>
            </section>
          </aside>
        </form>
      )}
    </main>
  )
}
