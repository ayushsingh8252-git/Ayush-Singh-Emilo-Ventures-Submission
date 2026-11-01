import { BookOpen, Gift } from 'lucide-react'
import { API_URL } from '../api.js'

const STATUS = {
  semantic: { dot: 'bg-emerald-500', label: 'AI ranking active', hint: 'MiniLM embeddings + FAISS hybrid ranking' },
  tfidf_fallback: { dot: 'bg-amber-500', label: 'Keyword fallback', hint: 'Embedding model unavailable: TF-IDF ranking' },
  offline: { dot: 'bg-rose-500', label: 'Service offline', hint: 'The recommendation API is not reachable' },
  checking: { dot: 'bg-ink-400 animate-pulse', label: 'Connecting…', hint: 'Checking the recommendation API' },
}

export default function NavBar({ engineStatus }) {
  const status = STATUS[engineStatus] || STATUS.checking
  return (
    <nav className="sticky top-0 z-30 border-b border-sand-100 bg-ivory/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <a href="/" className="flex items-center gap-2.5 text-ink-900">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-900 text-white">
            <Gift className="h-4 w-4" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">Occasion Gift Finder</span>
        </a>
        <div className="flex items-center gap-2 sm:gap-4">
          <span
            className="hidden items-center gap-2 rounded-full border border-sand-200 bg-white px-3 py-1 text-xs font-medium text-ink-700 sm:inline-flex"
            title={status.hint}
            data-testid="engine-status"
          >
            <span className={`h-2 w-2 rounded-full ${status.dot}`} />
            {status.label}
          </span>
          <a
            href={`${API_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-ink-500 transition hover:bg-sand-50 hover:text-ink-900"
          >
            <BookOpen className="h-4 w-4" /> API docs
          </a>
        </div>
      </div>
    </nav>
  )
}
