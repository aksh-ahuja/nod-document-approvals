import { useState } from 'react'
import { ArrowLeft, Check, CheckCheck, Clock3, FileText, LockKeyhole, Send, X } from 'lucide-react'
import { ApiError, post } from '../api'
import { useApi } from '../hooks'
import { Avatar, ErrorBanner, Spinner, StatusBadge } from '../components/ui'
import type { Submission, SubmissionEvent, User } from '../types'
import { DocumentViewer } from '../components/DocumentViewer'

export function Detail({
  id,
  user,
  notify,
}: {
  id: string
  user: User
  notify: (message: string) => void
}) {
  const detail = useApi<Submission>(`submissions/detail/${id}/`, true)
  const history = useApi<SubmissionEvent[]>(`submissions/history/${id}/`, true)
  const [note, setNote] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const submission = detail.data
  const canDecide =
    submission?.assigned_reviewer.id === user.id &&
    user.can_review &&
    submission.status === 'pending'
  const decision = history.data?.find((event) => event.event_type !== 'submitted')
  const decide = async (status: 'approved' | 'rejected') => {
    if (status === 'rejected' && !note.trim()) {
      setError(new Error('Add a reason so the submitter knows what needs fixing.'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await post(`submissions/decision/${id}/`, { decision: status, note })
      notify(status === 'approved' ? 'Document approved.' : 'Document rejected. Feedback saved.')
      detail.refresh()
      history.refresh()
    } catch (error) {
      setError(error)
      if (error instanceof ApiError && error.status === 409) {
        detail.refresh()
        history.refresh()
      }
    } finally {
      setBusy(false)
    }
  }
  return (
    <main id="main-content" tabIndex={-1} className="workspace-content">
      <a className="back-link" href={user.can_review ? '#/review' : '#/app'}>
        <ArrowLeft size={15} /> Back to submissions
      </a>
      <ErrorBanner error={detail.error} retry={detail.refresh} />
      {detail.loading ? (
        <div className="detail-loading">
          <div className="skeleton skeleton-heading" />
          <div className="skeleton skeleton-document" />
        </div>
      ) : (
        submission && (
          <>
            <div className="page-heading detail-heading">
              <div>
                <div className="eyebrow">DOCUMENT / {submission.id.slice(0, 8).toUpperCase()}</div>
                <h1>{submission.title}</h1>
                <div className="detail-meta">
                  <span>
                    Submitted by <strong>{submission.submitter.name}</strong>
                  </span>
                  <span>·</span>
                  <time>
                    {new Date(submission.created_at).toLocaleDateString(undefined, {
                      month: 'long',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </time>
                </div>
              </div>
              <StatusBadge status={submission.status} />
            </div>
            <div className="detail-grid">
              {submission.file ? (
                <DocumentViewer submission={submission} />
              ) : (
                <section className="document-paper">
                  <header>
                    <span>
                      <FileText size={16} /> DOCUMENT CONTENT
                    </span>
                    <LockKeyhole size={14} />
                  </header>
                  <div className="document-body">{submission.content}</div>
                  <footer>
                    <LockKeyhole size={12} /> Original content · Locked after submission
                  </footer>
                </section>
              )}
              <aside className="detail-sidebar">
                <section className="review-card">
                  <div className="card-eyebrow">{canDecide ? 'YOUR REVIEW' : 'REVIEW STATUS'}</div>
                  <div className={`review-symbol ${submission.status}`}>
                    {submission.status === 'pending' ? (
                      <Clock3 size={25} />
                    ) : submission.status === 'approved' ? (
                      <CheckCheck size={27} />
                    ) : (
                      <X size={25} />
                    )}
                  </div>
                  <h2>
                    {canDecide
                      ? 'Review document'
                      : submission.status === 'pending'
                        ? 'Awaiting review'
                        : submission.status === 'approved'
                          ? 'Approved'
                          : 'Rejected'}
                  </h2>
                  <p>
                    {canDecide
                      ? 'Read the document, then record your decision.'
                      : submission.status === 'pending'
                        ? `Waiting for ${submission.assigned_reviewer.name.split(' ')[0]} to review your document.`
                        : submission.status === 'approved'
                          ? 'Approved and ready for the next step.'
                          : 'Your reviewer has shared feedback below.'}
                  </p>
                  <div className="reviewer-assignment">
                    <Avatar user={submission.assigned_reviewer} small />
                    <div>
                      <strong>{submission.assigned_reviewer.name}</strong>
                      <span>Assigned reviewer</span>
                    </div>
                  </div>
                  {canDecide && (
                    <>
                      <div className="form-divider" />
                      <label>
                        {rejecting ? 'What needs to change? *' : 'Leave a note (optional)'}
                        <textarea
                          maxLength={2000}
                          rows={4}
                          disabled={busy}
                          value={note}
                          onChange={(event) => setNote(event.target.value)}
                          placeholder={
                            rejecting
                              ? 'Help them understand what to improve…'
                              : 'Add context for your decision…'
                          }
                        />
                      </label>
                      <ErrorBanner error={error} />
                      {rejecting ? (
                        <>
                          <button
                            className="button danger full"
                            disabled={busy || !note.trim()}
                            onClick={() => decide('rejected')}
                          >
                            {busy ? (
                              <Spinner />
                            ) : (
                              <>
                                <X size={16} /> Confirm rejection
                              </>
                            )}
                          </button>
                          <button
                            className="cancel-link"
                            disabled={busy}
                            onClick={() => {
                              setRejecting(false)
                              setError(null)
                            }}
                          >
                            Back to review
                          </button>
                        </>
                      ) : (
                        <div className="decision-buttons">
                          <button
                            className="button primary"
                            disabled={busy}
                            onClick={() => decide('approved')}
                          >
                            {busy ? (
                              <Spinner />
                            ) : (
                              <>
                                <Check size={16} /> Approve
                              </>
                            )}
                          </button>
                          <button
                            className="button secondary"
                            disabled={busy}
                            onClick={() => setRejecting(true)}
                          >
                            Reject
                          </button>
                        </div>
                      )}
                      <span className="decision-hint">
                        Decisions are final and recorded in the timeline.
                      </span>
                    </>
                  )}
                  {!canDecide && error ? <ErrorBanner error={error} /> : null}
                  {decision?.note && (
                    <div className="decision-note">
                      <span>REVIEWER’S NOTE</span>
                      <p>{decision.note}</p>
                    </div>
                  )}
                </section>
                <section className="timeline-card">
                  <h3>Activity</h3>
                  <ErrorBanner error={history.error} retry={history.refresh} />
                  {history.loading ? (
                    <div className="skeleton skeleton-row" />
                  ) : (
                    <ol className="timeline">
                      {history.data?.map((event) => (
                        <li key={event.id}>
                          <span className={`timeline-dot ${event.event_type}`}>
                            {event.event_type === 'submitted' ? (
                              <Send size={12} />
                            ) : event.event_type === 'approved' ? (
                              <Check size={13} />
                            ) : (
                              <X size={13} />
                            )}
                          </span>
                          <div>
                            <strong>
                              {event.event_type === 'submitted'
                                ? 'Sent for review'
                                : event.event_type === 'approved'
                                  ? 'Approved'
                                  : 'Rejected'}
                            </strong>
                            <p>{event.actor.name}</p>
                            <time>
                              {new Date(event.created_at).toLocaleString(undefined, {
                                month: 'short',
                                day: 'numeric',
                                hour: 'numeric',
                                minute: '2-digit',
                              })}
                            </time>
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </aside>
            </div>
          </>
        )
      )}
    </main>
  )
}
