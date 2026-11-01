import { useMemo, useState } from 'react'
import { AlertCircle, ListOrdered, MessageSquareText, RotateCw, ScanSearch, SearchX, Sparkles, X } from 'lucide-react'
import ProductCard from './ProductCard.jsx'
import ProductDetail from './ProductDetail.jsx'

const SORTS = {
  relevance: { label: 'Best match', fn: null },
  'price-asc': { label: 'Price: low to high', fn: (a, b) => (a.final_price ?? Infinity) - (b.final_price ?? Infinity) },
  'price-desc': { label: 'Price: high to low', fn: (a, b) => (b.final_price ?? -1) - (a.final_price ?? -1) },
  discount: { label: 'Biggest discount', fn: (a, b) => b.discount_percentage - a.discount_percentage },
}

const STEPS = [
  [ScanSearch, 'Understands the occasion', 'Recognises 20+ occasions, typos and free text like “something romantic under ₹1,500”.'],
  [ListOrdered, 'Ranks the whole catalog', 'Combines semantic similarity, keyword match and occasion themes, then balances variety.'],
  [MessageSquareText, 'Explains every pick', 'Each recommendation cites words from the product listing that made it a match.'],
]

const rupees = (value) => `₹${Number(value).toLocaleString('en-IN')}`

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-xl border border-sand-200/70 bg-white">
      <div className="aspect-[4/3] animate-pulse bg-sand-50" />
      <div className="space-y-3 p-5">
        <div className="h-3 w-1/3 animate-pulse rounded bg-sand-100" />
        <div className="h-5 w-3/4 animate-pulse rounded bg-sand-100" />
        <div className="h-3 w-full animate-pulse rounded bg-sand-50" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-sand-50" />
        <div className="h-14 w-full animate-pulse rounded bg-sand-50" />
      </div>
    </div>
  )
}

function Message({ icon: Icon, title, children, tone = 'neutral' }) {
  const toneClass = tone === 'error' ? 'bg-clay-50 text-clay-600 ring-clay-100' : 'bg-white text-ink-500 ring-sand-200'
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center animate-rise">
      <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl ring-1 ${toneClass}`}>
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="text-lg font-semibold tracking-tight text-ink-900">{title}</h3>
      <div className="mt-2 text-sm leading-relaxed text-ink-500">{children}</div>
    </div>
  )
}

function HowItWorks() {
  return (
    <section className="animate-rise">
      <div className="text-center">
        <h3 className="text-lg font-semibold tracking-tight text-ink-900">Your shortlist will appear here</h3>
        <p className="mt-1 text-sm text-ink-500">Pick an occasion above, or describe who the gift is for.</p>
      </div>
      <ol className="mt-8 grid gap-4 sm:grid-cols-3">
        {STEPS.map(([Icon, title, text], i) => (
          <li key={title} className="rounded-xl border border-sand-200/70 bg-white p-5">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-sand-50 text-ink-700 ring-1 ring-sand-200">
                <Icon className="h-4 w-4" />
              </span>
              <span className="text-xs font-semibold tabular-nums text-ink-400">0{i + 1}</span>
            </div>
            <p className="mt-4 text-sm font-semibold text-ink-900">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-500">{text}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

function ActiveFilters({ filters, categories, onFiltersChange }) {
  const chips = []
  if (filters.minPrice) chips.push(['minPrice', `Min ${rupees(filters.minPrice)}`])
  if (filters.maxPrice) chips.push(['maxPrice', `Max ${rupees(filters.maxPrice)}`])
  if (filters.category) {
    const label = categories.find((c) => c.category_id === filters.category)?.label || 'Category'
    chips.push(['category', label])
  }
  if (!chips.length) return null
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-ink-400">Filtered by</span>
      {chips.map(([key, label]) => (
        <span key={key} className="inline-flex items-center gap-1 rounded-full bg-ink-900 py-1 pl-3 pr-1.5 text-xs font-medium text-white">
          {label}
          <button
            type="button"
            aria-label={`Remove ${label} filter`}
            onClick={() => onFiltersChange({ ...filters, [key]: '' })}
            className="flex h-4 w-4 items-center justify-center rounded-full hover:bg-white/20"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  )
}

function Toolbar({ result, sort, onSortChange }) {
  const { interpretation: it, total_results: total, recommendation_mode: mode } = result
  const budget = [
    it.applied_min_price != null && `from ${rupees(it.applied_min_price)}`,
    it.applied_max_price != null && `up to ${rupees(it.applied_max_price)}`,
  ].filter(Boolean).join(' ')
  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-sand-200/70 pb-5 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <h2 className="font-display text-2xl text-ink-900 sm:text-3xl">
          {total} {total === 1 ? 'idea' : 'ideas'} for {it.matched_occasion || `“${result.occasion}”`}
        </h2>
        {it.concepts.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-ink-400">
              Looking for
              {it.match_type === 'fuzzy' && ` (interpreted from “${result.occasion}”)`}
              {it.match_type === 'semantic' && ` (closest occasion to “${result.occasion}”)`}
            </span>
            {it.concepts.slice(0, 6).map((concept) => (
              <span key={concept} className="rounded-full bg-white px-2.5 py-0.5 text-xs text-ink-700 ring-1 ring-sand-200">
                {concept}
              </span>
            ))}
          </div>
        )}
        {budget && <p className="mt-2 text-sm text-ink-500">Budget {budget}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span
          className="inline-flex items-center gap-1.5 text-xs text-ink-500"
          title={mode === 'semantic' ? 'Ranked with MiniLM sentence embeddings + FAISS, keyword and occasion signals' : 'Embedding model unavailable: ranked with TF-IDF keyword similarity'}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {mode === 'semantic' ? 'Semantic ranking' : 'Keyword fallback ranking'}
        </span>
        <label className="flex items-center gap-2 text-xs font-medium text-ink-500">
          <span className="sr-only sm:not-sr-only">Sort by</span>
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value)}
            className="field w-auto py-1.5 pr-8 text-sm"
            aria-label="Sort results"
          >
            {Object.entries(SORTS).map(([key, { label }]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
      </div>
    </div>
  )
}

export default function Results({ status, result, error, onRetry, onSuggest, filters, categories, onFiltersChange }) {
  const [sort, setSort] = useState('relevance')
  const [openId, setOpenId] = useState(null)

  // Keep each product's relevance rank, whatever order it is displayed in.
  const items = useMemo(() => {
    if (!result) return []
    const ranked = result.recommendations.map((product, i) => ({ product, rank: i + 1 }))
    const compare = SORTS[sort].fn
    return compare ? [...ranked].sort((a, b) => compare(a.product, b.product)) : ranked
  }, [result, sort])

  if (status === 'idle') return <HowItWorks />
  if (status === 'loading') {
    return (
      <div aria-busy="true" aria-label="Loading recommendations" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }
  if (status === 'error') {
    return (
      <Message icon={AlertCircle} title="Something went wrong" tone="error">
        <p>{error}</p>
        <button type="button" onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-ink-900 px-4 py-2 text-sm font-medium text-white hover:bg-ink-700">
          <RotateCw className="h-4 w-4" /> Try again
        </button>
      </Message>
    )
  }
  if (!result.recommendations.length) {
    return (
      <>
        <ActiveFilters filters={filters} categories={categories} onFiltersChange={onFiltersChange} />
        <Message icon={SearchX} title="No matches yet">
          <p>{result.message || 'No relevant products found for this occasion. Try another occasion.'}</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {['Birthday', 'Anniversary', 'Housewarming'].map((occasion) => (
              <button key={occasion} type="button" onClick={() => onSuggest(occasion)}
                className="rounded-full border border-sand-200 bg-white px-3 py-1 text-sm text-ink-700 hover:border-ink-400">
                {occasion}
              </button>
            ))}
          </div>
        </Message>
      </>
    )
  }

  const open = items.find(({ product }) => product.product_id === openId)
  const occasionName = result.interpretation.matched_occasion || `“${result.occasion}”`
  return (
    <section aria-live="polite">
      <Toolbar result={result} sort={sort} onSortChange={setSort} />
      <ActiveFilters filters={filters} categories={categories} onFiltersChange={onFiltersChange} />
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {items.map(({ product, rank }, i) => (
          <ProductCard
            key={product.product_id}
            product={product}
            rank={rank}
            index={i}
            onOpen={() => setOpenId(product.product_id)}
          />
        ))}
      </div>
      {open && (
        <ProductDetail product={open.product} rank={open.rank} occasion={occasionName} onClose={() => setOpenId(null)} />
      )}
    </section>
  )
}
