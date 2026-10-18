import { ChevronRight, FileText } from 'lucide-react'

export type DocumentType = { id: string; label: string; description: string }

// Add a new row here to offer another document type in the submission flow.
export const DOCUMENT_TYPES: DocumentType[] = [
  { id: 'pan', label: 'PAN card', description: 'Permanent Account Number card' },
  { id: 'aadhaar', label: 'Aadhaar card', description: '12-digit UIDAI identity card' },
]

// Submissions carry no type field yet, so the type lives in the title prefix: "PAN card · scan".
export const titlePrefix = (type: DocumentType) => `${type.label} · `

export const findDocumentType = (id: string | null) =>
  DOCUMENT_TYPES.find((type) => type.id === id) ?? null

export const typeOfTitle = (title: string) =>
  DOCUMENT_TYPES.find((type) => title.startsWith(titlePrefix(type))) ?? null

export function DocumentTypePicker({ onSelect }: { onSelect: (type: DocumentType) => void }) {
  return (
    <ul className="document-type-list" aria-label="Document type">
      {DOCUMENT_TYPES.map((type) => (
        <li key={type.id}>
          <button type="button" className="document-type-row" onClick={() => onSelect(type)}>
            <FileText size={20} />
            <div>
              <strong>{type.label}</strong>
              <span>{type.description}</span>
            </div>
            <ChevronRight size={16} />
          </button>
        </li>
      ))}
    </ul>
  )
}
