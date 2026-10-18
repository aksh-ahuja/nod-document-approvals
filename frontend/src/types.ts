export type User = { id: string; name: string; email: string; can_review: boolean }
export type Status = 'pending' | 'approved' | 'rejected'
export type Submission = {
  id: string
  title: string
  status: Status
  submitter: User
  assigned_reviewer: User
  created_at: string
  decided_at: string | null
  content?: string
  file: { name: string; size: number; content_type: string } | null
}
export type SubmissionEvent = {
  id: string
  actor: User
  event_type: 'submitted' | 'approved' | 'rejected'
  previous_status: string
  new_status: Status
  note: string
  created_at: string
}
export type Summary = {
  pending: number
  approved: number
  rejected: number
  total: number
  oldest_pending_at: string | null
}
export type Page<T> = { results: T[]; count: number; page: number; pages: number }
