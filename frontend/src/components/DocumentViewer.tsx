import { useState } from 'react'
import { Download, ExternalLink, Eye, FileText, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { ErrorBanner, Spinner } from './ui'
import type { Submission } from '../types'

type FileLink = { url: string; expires_in: number; content_type: string }

export function DocumentViewer({ submission }: { submission: Submission }) {
  const [link, setLink] = useState<FileLink | null>(null)
  const [busy, setBusy] = useState<'view' | 'download' | null>(null)
  const [error, setError] = useState<unknown>(null)
  const file = submission.file!
  const getLink = async (download = false) => {
    setBusy(download ? 'download' : 'view')
    setError(null)
    try {
      const result = await api<FileLink>(
        `submissions/file-link/${submission.id}/?download=${download}`,
      )
      if (download) window.location.assign(result.url)
      else setLink(result)
    } catch (error) {
      setError(error)
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="document-paper file-document">
      <header>
        <span>
          <FileText size={16} /> ORIGINAL DOCUMENT
        </span>
        <span>
          {file.size < 1024 * 1024
            ? `${Math.ceil(file.size / 1024)} KB`
            : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}
        </span>
      </header>
      <div className="file-viewer-toolbar">
        <strong>{file.name}</strong>
        <div className="file-viewer-actions">
          <button className="button primary" disabled={!!busy} onClick={() => getLink()}>
            {busy === 'view' ? <Spinner /> : link ? <RefreshCw size={15} /> : <Eye size={15} />}
            {link ? 'Refresh preview' : 'View document'}
          </button>
          <button className="button secondary" disabled={!!busy} onClick={() => getLink(true)}>
            {busy === 'download' ? <Spinner /> : <Download size={15} />} Download original
          </button>
        </div>
      </div>
      <div className="file-viewer-error">
        <ErrorBanner error={error} />
      </div>
      {link ? (
        <>
          <div className="preview-caption">
            <span>
              {file.content_type.includes('wordprocessingml')
                ? 'PDF preview · Formatting may vary'
                : 'Document preview'}
            </span>
            <a href={link.url} target="_blank" rel="noopener noreferrer">
              Open in new tab <ExternalLink size={13} />
            </a>
          </div>
          <iframe
            key={link.url}
            src={link.url}
            title={`Preview of ${file.name}`}
            referrerPolicy="no-referrer"
            className="document-frame"
          />
          <footer>
            Private link · {Math.round(link.expires_in / 60)}-minute access. Refresh to renew.
          </footer>
        </>
      ) : (
        <div className="file-preview-placeholder">
          <FileText size={44} strokeWidth={1} />
          <h2>{busy === 'view' ? 'Preparing your preview…' : 'Ready to review'}</h2>
          <p>
            {busy === 'view' && file.content_type.includes('wordprocessingml')
              ? 'Creating a PDF preview of your Word document.'
              : 'Open the document here, or download the original.'}
          </p>
        </div>
      )}
    </section>
  )
}
