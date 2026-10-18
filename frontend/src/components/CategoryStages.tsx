import { useEffect, useState } from 'react'
import { ArrowUpRight, Clock3, Check, FileText, RefreshCw, Upload, X } from 'lucide-react'
import { api } from '../api'
import { DOCUMENT_TYPES, titlePrefix } from './DocumentType'
import type { DocumentType } from './DocumentType'
import { ErrorBanner, age } from './ui'
import type { Page, Submission } from '../types'

type Stage = 'upload' | 'pending' | 'approved' | 'rejected'
type Category = { type: DocumentType; stage: Stage; latest: Submission | null }

const stages = [
  ['all', 'All documents'],
  ['upload', 'Need to upload'],
  ['pending', 'Pending'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
] as const

const stageLabels: Record<Stage, string> = {
  upload: 'Need to upload',
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
}
const stageIcons = { upload: Upload, pending: Clock3, approved: Check, rejected: X }

// The newest submission of a type decides its stage; no submission yet means it still needs uploading.
async function loadCategory(type: DocumentType, signal: AbortSignal): Promise<Category> {
  const params = new URLSearchParams({ scope: 'mine', search: titlePrefix(type) })
  const page = await api<Page<Submission>>(`submissions/list/?${params}`, { signal })
  const latest = page.results.find((item) => item.title.startsWith(titlePrefix(type))) ?? null
  return { type, stage: latest ? latest.status : 'upload', latest }
}

export function CategoryStages() {
  const [filter, setFilter] = useState<Stage | 'all'>('all')
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    Promise.all(DOCUMENT_TYPES.map((type) => loadCategory(type, controller.signal)))
      .then(setCategories)
      .catch((error) => {
        if (error.name !== 'AbortError') setError(error)
      })
    return () => controller.abort()
  }, [revision])
  const refresh = () => setRevision((value) => value + 1)
  const count = (stage: Stage | 'all') =>
    categories?.filter((item) => stage === 'all' || item.stage === stage).length
  const visible = categories?.filter((item) => filter === 'all' || item.stage === filter)
  const toUpload = count('upload')

  return (
    <main id="main-content" tabIndex={-1} className="workspace-content dashboard">
      <div className="page-heading">
        <div>
          <h1>My submissions</h1>
          <p>
            {toUpload === undefined
              ? 'Your documents and their decisions.'
              : toUpload > 0
                ? `${toUpload} document${toUpload === 1 ? '' : 's'} still to upload.`
                : 'Every document is uploaded. Track the decisions here.'}
          </p>
        </div>
      </div>
      <section className="submission-panel" aria-label="Your documents">
        <div className="status-filters" role="group" aria-label="Filter by status">
          {stages.map(([value, label]) => (
            <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>
              {value !== 'all' && <span className={`filter-dot ${value}`} aria-hidden="true" />}
              {label}
              <span className="filter-count">{count(value) ?? '…'}</span>
            </button>
          ))}
          <button
            className="icon-button category-refresh"
            aria-label="Refresh documents"
            title="Refresh documents"
            onClick={refresh}
          >
            <RefreshCw size={15} />
          </button>
        </div>
        <ErrorBanner error={error} retry={refresh} />
        {!visible && !error ? (
          <div className="table-loading" role="status" aria-label="Loading documents">
            {DOCUMENT_TYPES.map((type) => (
              <div className="skeleton skeleton-row" key={type.id} />
            ))}
          </div>
        ) : visible?.length ? (
          <ul className="category-list">
            {visible.map(({ type, stage, latest }) => {
              const Icon = stageIcons[stage]
              const href = latest ? `#/submissions/${latest.id}` : `#/new?type=${type.id}`
              return (
                <li key={type.id}>
                  <a className="category-row" href={href}>
                    <span className="file-icon">
                      <FileText size={19} strokeWidth={1.5} />
                    </span>
                    <span className="category-text">
                      <strong>{type.label}</strong>
                      <small>
                        {latest
                          ? `${latest.file?.name ?? 'Submitted'} · ${age(latest.decided_at ?? latest.created_at).toLowerCase()}`
                          : type.description}
                      </small>
                    </span>
                    <span className={`status status-${stage}`}>
                      <Icon size={12} strokeWidth={2.4} />
                      {stageLabels[stage]}
                    </span>
                    {latest ? (
                      <ArrowUpRight className="category-action" size={17} />
                    ) : (
                      <span className="button primary category-upload">
                        <Upload size={14} /> Upload now
                      </span>
                    )}
                  </a>
                </li>
              )
            })}
          </ul>
        ) : (
          !error && (
            <div className="empty-state">
              <h3>No documents in this stage</h3>
              <p>Try a different filter.</p>
            </div>
          )
        )}
      </section>
    </main>
  )
}
