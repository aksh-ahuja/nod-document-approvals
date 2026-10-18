import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, ChevronRight, FileText, Inbox, LogOut, Menu, X } from 'lucide-react'
import { Avatar, Logo } from './ui'
import type { User } from '../types'

export function Shell({
  user,
  route,
  onLogout,
  children,
}: {
  user: User
  route: string
  onLogout: () => void
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const title =
    route === '/review'
      ? 'Assigned to me'
      : route.startsWith('/new')
        ? 'Upload document'
        : route.startsWith('/submissions/')
          ? 'Document details'
          : 'My submissions'
  const closeNavigation = () => {
    setOpen(false)
    if (open) menuButton.current?.focus()
  }
  return (
    <div
      className="app-shell"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) closeNavigation()
      }}
    >
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault()
          document.getElementById('main-content')?.focus()
        }}
      >
        Skip to content
      </a>
      <div className="mobile-header">
        <Logo />
        <button
          ref={menuButton}
          className="icon-button"
          onClick={() => setOpen(!open)}
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open}
          aria-controls="workspace-navigation"
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      <aside id="workspace-navigation" className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <Logo />
          <span>WORKSPACE</span>
        </div>
        <nav className="sidebar-nav" aria-label="Workspace">
          <a
            href="#/app"
            aria-current={route === '/app' ? 'page' : undefined}
            onClick={closeNavigation}
          >
            <FileText size={17} /> My submissions
          </a>
          {user.can_review && (
            <a
              href="#/review"
              aria-current={route === '/review' ? 'page' : undefined}
              onClick={closeNavigation}
            >
              <Inbox size={17} /> Assigned to me
            </a>
          )}
        </nav>
        <div className="sidebar-bottom">
          <a className="sidebar-home" href="#/">
            <span>About Nod</span>
            <ArrowUpRight size={14} />
          </a>
          <div className="profile">
            <Avatar user={user} />
            <div>
              <strong>{user.name}</strong>
              <span>{user.can_review ? 'Reviewer & submitter' : 'Submitter'}</span>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              title="Sign out"
              onClick={onLogout}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <span>{title}</span>
          </div>
          <span className="topbar-account">{user.email}</span>
        </header>
        {children}
      </div>
    </div>
  )
}
