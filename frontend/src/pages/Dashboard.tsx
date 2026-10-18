import { useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  FileText,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import { useApi } from '../hooks'
import { Avatar, DateLabel, EmptyState, ErrorBanner, StatusBadge, age } from '../components/ui'
import type { Page, Submission, Summary } from '../types'

const filters = [
  ['all', 'All documents'],
  ['pending', 'Pending'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
] as const

export function Dashboard({ assigned }: { assigned: boolean }) {
  const [filter, setFilter] = useState(assigned ? 'pending' : 'all')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim())
      setPage(1)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])
  const scope = assigned ? 'assigned' : 'mine'
  const params = new URLSearchParams({ scope, page: String(page), search: query })
  if (filter !== 'all') params.set('status', filter)
  const list = useApi<Page<Submission>>(`submissions/list/?${params}`, true)
  const summary = useApi<Summary>(`submissions/summary/?scope=${scope}`, true)
  const oldestFirst = assigned && filter === 'pending'
  const pending = summary.data?.pending
  return (
    <main id="main-content" tabIndex={-1} className="workspace-content dashboard">
      <div className="page-heading">
        <div>
          <h1>{assigned ? 'Assigned to me' : 'My submissions'}</h1>
          <p>
            {pending === undefined
              ? 'Your documents and their decisions.'
              : pending > 0
                ? `${pending} document${pending === 1 ? '' : 's'} ${assigned ? 'ready for your review' : 'awaiting a decision'}.`
                : assigned
                  ? 'You’re up to date. No reviews waiting.'
                  : 'Your documents and their decisions, in one place.'}
          </p>
        </div>
      </div>
      <ErrorBanner error={summary.error} retry={summary.refresh} />
      <section
        className="submission-panel"
        aria-label={assigned ? 'Assigned documents' : 'Your submissions'}
      >
        <div className="status-filters" role="group" aria-label="Filter by status">
          {filters.map(([value, label]) => (
            <button
              key={value}
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value)
                setPage(1)
              }}
            >
              {value !== 'all' && <span className={`filter-dot ${value}`} aria-hidden="true" />}
              {label}
              <span className="filter-count">
                {summary.data?.[value === 'all' ? 'total' : value] ?? '…'}
              </span>
            </button>
          ))}
        </div>
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={16} aria-hidden="true" />
            <input
              aria-label="Search submissions"
              placeholder="Search documents…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {search && (
              <button
                className="icon-button"
                aria-label="Clear search"
                onClick={() => setSearch('')}
              >
                <X size={14} />
              </button>
            )}
          </label>
          <div className="table-tools">
            <span className="table-order">
              {oldestFirst ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
              {oldestFirst ? 'Oldest first' : 'Newest first'}
            </span>
            <button
              className="icon-button"
              aria-label="Refresh submissions"
              title="Refresh submissions"
              disabled={list.refreshing || summary.refreshing}
              onClick={() => {
                list.refresh()
                summary.refresh()
              }}
            >
              <RefreshCw size={15} className={list.refreshing ? 'refreshing' : ''} />
            </button>
          </div>
        </div>
        <ErrorBanner error={list.error} retry={list.refresh} />
        {list.loading ? (
          <div className="table-loading" role="status" aria-label="Loading submissions">
            {[0, 1, 2, 3].map((i) => (
              <div className="skeleton skeleton-row" key={i} />
            ))}
          </div>
        ) : list.data?.results.length ? (
          <div className="table-scroll">
            <table className="document-table">
              <thead>
                <tr>
                  <th scope="col">Document</th>
                  <th scope="col">Status</th>
                  <th scope="col">{assigned ? 'Submitted by' : 'Reviewer'}</th>
                  <th scope="col">Submitted</th>
                  <th scope="col">
                    <span className="sr-only">Open document</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((item) => (
                  <tr key={item.id}>
                    <td className="document-title-cell">
                      <a className="document-cell" href={`#/submissions/${item.id}`}>
                        <span className="file-icon">
                          <FileText size={19} strokeWidth={1.5} />
                        </span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>
                            {item.status === 'pending'
                              ? `Submitted ${age(item.created_at).toLowerCase()}`
                              : `Decision recorded ${age(item.decided_at!).toLowerCase()}`}
                          </small>
                        </span>
                      </a>
                    </td>
                    <td className="document-status-cell">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="document-person-cell">
                      <div className="person-cell">
                        <Avatar user={assigned ? item.submitter : item.assigned_reviewer} small />
                        <span>
                          <span className="mobile-person-label">
                            {assigned ? 'From ' : 'Reviewer: '}
                          </span>
                          {(assigned ? item.submitter : item.assigned_reviewer).name}
                        </span>
                      </div>
                    </td>
                    <td className="date-cell">
                      <DateLabel value={item.created_at} />
                    </td>
                    <td className="document-open-cell">
                      <a
                        className="row-arrow"
                        href={`#/submissions/${item.id}`}
                        aria-label={`Open ${item.title}`}
                      >
                        <ArrowUpRight size={17} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !list.error && (
            <EmptyState
              assigned={assigned}
              filtered={!!query || (filter !== 'all' && !(assigned && filter === 'pending'))}
            />
          )
        )}
        {list.data && list.data.count > 0 && !list.loading && (
          <div className="table-footer">
            <span>
              {(page - 1) * 12 + 1}–{Math.min(page * 12, list.data.count)} of {list.data.count}{' '}
              documents
            </span>
            <div>
              <button
                className="icon-button"
                aria-label="Previous page"
                onClick={() => setPage(page - 1)}
                disabled={page <= 1}
              >
                <ChevronLeft size={16} />
              </button>
              <span>
                Page {page} of {list.data.pages}
              </span>
              <button
                className="icon-button"
                aria-label="Next page"
                onClick={() => setPage(page + 1)}
                disabled={page >= list.data.pages}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </section>
    </main>
  )
}
