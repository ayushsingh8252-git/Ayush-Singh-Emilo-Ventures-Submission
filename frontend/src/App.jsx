import { useCallback, useEffect, useRef, useState } from 'react'
import { Gift } from 'lucide-react'
import NavBar from './components/NavBar.jsx'
import SearchPanel from './components/SearchPanel.jsx'
import Results from './components/Results.jsx'
import { API_URL, getCategories, getHealth, getOccasions, getRecommendations } from './api.js'

const EMPTY_FILTERS = { minPrice: '', maxPrice: '', category: '' }
const initialQuery = () => new URLSearchParams(window.location.search).get('q') || ''

function Stats({ health, categories, occasions }) {
  if (!health) return null
  const items = [
    [health.eligible_products, 'products indexed'],
    [categories.length, 'categories'],
    [occasions.length, 'occasions understood'],
  ].filter(([value]) => value > 0)
  return (
    <dl className="mx-auto mt-10 grid max-w-xl grid-cols-3 divide-x divide-sand-200">
      {items.map(([value, label]) => (
        <div key={label} className="px-2 text-center sm:px-6">
          <dt className="sr-only">{label}</dt>
          <dd className="text-xl font-semibold tabular-nums tracking-tight text-ink-900">{value}</dd>
          <dd className="text-xs text-ink-500">{label}</dd>
        </div>
      ))}
    </dl>
  )
}

function Footer() {
  return (
    <footer className="mt-16 border-t border-sand-200/70 bg-white">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-3 sm:px-6">
        <div>
          <div className="flex items-center gap-2 font-semibold text-ink-900">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-ink-900 text-white">
              <Gift className="h-3.5 w-3.5" />
            </span>
            Occasion Gift Finder
          </div>
          <p className="mt-3 leading-relaxed text-ink-500">
            Recommendations come only from the supplied product catalog. Category labels are inferred from product text.
          </p>
        </div>
        <div>
          <p className="font-semibold text-ink-900">How ranking works</p>
          <ul className="mt-3 space-y-1.5 text-ink-500">
            <li>Semantic search with MiniLM embeddings + FAISS</li>
            <li>Keyword and occasion-theme relevance</li>
            <li>Diversity-aware ordering with explanations</li>
          </ul>
        </div>
        <div>
          <p className="font-semibold text-ink-900">Developers</p>
          <ul className="mt-3 space-y-1.5 text-ink-500">
            <li><a className="hover:text-ink-900" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">API documentation</a></li>
            <li><a className="hover:text-ink-900" href={`${API_URL}/api/health`} target="_blank" rel="noreferrer">Service health</a></li>
          </ul>
        </div>
      </div>
    </footer>
  )
}

export default function App() {
  const [query, setQuery] = useState(initialQuery)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [categories, setCategories] = useState([])
  const [occasions, setOccasions] = useState([])
  const [examples, setExamples] = useState([])
  const [health, setHealth] = useState(null)
  const [engineStatus, setEngineStatus] = useState('checking')
  const [status, setStatus] = useState('idle') // idle | loading | success | error
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const lastSearch = useRef('')
  const requestId = useRef(0)
  const resultsRef = useRef(null)

  useEffect(() => {
    // Optional metadata: the page still works if these fail.
    getHealth()
      .then((h) => { setHealth(h); setEngineStatus(h.recommendation_mode) })
      .catch(() => setEngineStatus('offline'))
    getCategories().then((r) => setCategories(r.categories)).catch(() => {})
    getOccasions().then((r) => { setOccasions(r.occasions); setExamples(r.examples) }).catch(() => {})
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
      <NavBar engineStatus={engineStatus} />

      <header className="relative overflow-hidden border-b border-sand-200/70 bg-gradient-to-b from-sand-50 to-ivory">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(194,100,60,0.07),transparent)]" />
        <div className="relative mx-auto max-w-6xl px-4 pb-14 pt-14 text-center sm:px-6 sm:pt-20">
          <p className="inline-flex items-center gap-2 rounded-full border border-sand-200 bg-white/70 px-3 py-1 text-xs font-medium text-ink-500">
            <span className="h-1.5 w-1.5 rounded-full bg-clay-500" />
            AI-powered, explainable gift discovery
          </p>
          <h1 className="mx-auto mt-5 max-w-2xl font-display text-4xl font-medium tracking-tight text-ink-900 sm:text-6xl">
            Find the Perfect Gift
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base text-ink-500 sm:text-lg">
            Tell us what you're celebrating. We'll find something special.
          </p>
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
          <Stats health={health} categories={categories} occasions={occasions} />
        </div>
      </header>

      <main ref={resultsRef} className="mx-auto max-w-6xl scroll-mt-20 px-4 py-12 sm:px-6">
        <Results
          status={status}
          result={result}
          error={error}
          onRetry={() => search(lastSearch.current, filters)}
          onSuggest={runSearch}
          filters={filters}
          categories={categories}
          onFiltersChange={setFilters}
        />
      </main>

      <Footer />
    </div>
  )
}
