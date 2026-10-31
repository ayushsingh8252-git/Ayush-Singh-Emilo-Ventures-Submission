import { useCallback, useEffect, useRef, useState } from 'react'
import { Gift } from 'lucide-react'
import SearchPanel from './components/SearchPanel.jsx'
import Results from './components/Results.jsx'
import { getCategories, getOccasions, getRecommendations } from './api.js'

const EMPTY_FILTERS = { minPrice: '', maxPrice: '', category: '' }
const initialQuery = () => new URLSearchParams(window.location.search).get('q') || ''

export default function App() {
  const [query, setQuery] = useState(initialQuery)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [categories, setCategories] = useState([])
  const [examples, setExamples] = useState([])
  const [status, setStatus] = useState('idle') // idle | loading | success | error
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const lastSearch = useRef('')
  const requestId = useRef(0)
  const resultsRef = useRef(null)

  useEffect(() => {
    // Optional metadata: the page still works if these fail.
    getCategories().then((r) => setCategories(r.categories)).catch(() => {})
    getOccasions().then((r) => setExamples(r.examples)).catch(() => {})
  }, [])

  const search = useCallback(async (occasion, activeFilters) => {
    const text = occasion.trim()
    if (!text) return
    const id = ++requestId.current // ignore responses from superseded searches
    lastSearch.current = text
    setQuery(text)
    setStatus('loading')
    setError('')
    const url = new URL(window.location.href)
    url.searchParams.set('q', text)
    window.history.replaceState(null, '', url)
    try {
      const data = await getRecommendations({ occasion: text, limit: 12, ...activeFilters })
      if (id !== requestId.current) return
      setResult(data)
      setStatus('success')
    } catch (err) {
      if (id !== requestId.current) return
      setError(err.message)
      setStatus('error')
    }
  }, [])

  // Run a search from a shared ?q= link.
  useEffect(() => {
    if (initialQuery()) search(initialQuery(), EMPTY_FILTERS)
  }, [search])

  // Re-run the current search when filters change (debounced for typing in price fields).
  const firstFilterRender = useRef(true)
  useEffect(() => {
    if (firstFilterRender.current) {
      firstFilterRender.current = false
      return
    }
    if (!lastSearch.current) return
    const timer = setTimeout(() => search(lastSearch.current, filters), 400)
    return () => clearTimeout(timer)
  }, [filters, search])

  const runSearch = (occasion) => {
    search(occasion, filters)
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="min-h-screen">
      <header className="relative overflow-hidden border-b border-sand-100 bg-gradient-to-b from-sand-50 to-ivory">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-clay-100/60 blur-3xl" />
        <div className="pointer-events-none absolute -left-24 top-24 h-64 w-64 rounded-full bg-sage-50 blur-3xl" />
        <div className="relative mx-auto max-w-6xl px-4 pb-14 pt-8 sm:px-6">
          <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-900 text-white">
              <Gift className="h-4 w-4" />
            </span>
            Occasion Gift Finder
          </div>
          <div className="mx-auto mt-12 max-w-2xl text-center">
            <h1 className="font-display text-4xl font-medium tracking-tight text-ink-900 sm:text-6xl">
              Find the Perfect Gift
            </h1>
            <p className="mt-4 text-base text-ink-500 sm:text-lg">
              Tell us what you're celebrating. We'll find something special.
            </p>
          </div>
          <div className="mt-10">
            <SearchPanel
              query={query}
              onQueryChange={setQuery}
              onSearch={runSearch}
              loading={status === 'loading'}
              filters={filters}
              onFiltersChange={setFilters}
              categories={categories}
              examples={examples}
            />
          </div>
        </div>
      </header>

      <main ref={resultsRef} className="mx-auto max-w-6xl scroll-mt-4 px-4 py-10 sm:px-6">
        <Results
          status={status}
          result={result}
          error={error}
          onRetry={() => search(lastSearch.current, filters)}
          onSuggest={runSearch}
        />
      </main>

      <footer className="border-t border-sand-100 py-6 text-center text-xs text-ink-400">
        Recommendations come only from the supplied product catalog. Category labels are inferred from product text.
      </footer>
    </div>
  )
}
