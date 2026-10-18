import { Check, Circle, Clock3, FileText, RefreshCw, X } from 'lucide-react'
import { errorMessage } from '../api'
import type { Status, User } from '../types'

export function Logo({ inverse = false }: { inverse?: boolean }) {
  return (
    <a className={`logo ${inverse ? 'inverse' : ''}`} href="#/" aria-label="Nod home">
      nod<span>.</span>
    </a>
  )
}
export function Avatar({ user, small = false }: { user: Pick<User, 'name'>; small?: boolean }) {
  const initials = user.name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
  const tint = user.name.charCodeAt(0) % 3
  return (
    <span className={`avatar tint-${tint} ${small ? 'small' : ''}`} aria-hidden="true">
      {initials}
    </span>
  )
}
export function StatusBadge({ status }: { status: Status }) {
  const Icon = status === 'approved' ? Check : status === 'rejected' ? X : Clock3
  return (
    <span className={`status status-${status}`}>
      <Icon size={12} strokeWidth={2.4} />
      {status === 'pending' ? 'Pending' : status === 'approved' ? 'Approved' : 'Rejected'}
    </span>
  )
}
export function ErrorBanner({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null
  return (
    <div className="error-banner" role="alert">
      <span>{errorMessage(error)}</span>
      {retry && (
        <button onClick={retry}>
          <RefreshCw size={14} /> Try again
        </button>
      )}
    </div>
  )
}
export function Spinner() {
  return <span className="spinner" aria-label="Loading" />
}
export function EmptyState({ assigned, filtered }: { assigned: boolean; filtered: boolean }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <FileText size={26} />
      </span>
      <h3>
        {filtered
          ? 'No matching documents'
          : assigned
            ? 'No reviews waiting'
            : 'No submissions yet'}
      </h3>
      <p>
        {filtered
          ? 'Try a different filter or search.'
          : assigned
            ? 'Documents assigned to you will appear here.'
            : 'Send your first document to a reviewer and keep its progress here.'}
      </p>
    </div>
  )
}
export function DateLabel({ value }: { value: string }) {
  return (
    <time dateTime={value} title={new Date(value).toLocaleString()}>
      {new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
    </time>
  )
}
export function age(value: string) {
  const hours = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 3600000))
  if (hours < 1) return 'Just now'
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
export function DotLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="dot-label">
      <Circle size={6} fill="currentColor" />
      {children}
    </span>
  )
}
