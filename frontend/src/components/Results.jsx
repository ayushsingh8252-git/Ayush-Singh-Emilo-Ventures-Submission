import { AlertCircle, Gift, RotateCw, SearchX } from 'lucide-react'
import ProductCard from './ProductCard.jsx'

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-2xl border border-sand-100 bg-white">
      <div className="aspect-[4/3] animate-pulse bg-sand-50" />
      <div className="space-y-3 p-5">
        <div className="h-3 w-1/4 animate-pulse rounded bg-sand-100" />
        <div className="h-5 w-3/4 animate-pulse rounded bg-sand-100" />
        <div className="h-3 w-full animate-pulse rounded bg-sand-50" />
        <div className="h-16 w-full animate-pulse rounded-xl bg-sand-50" />
      </div>
    </div>
  )
}

function Message({ icon: Icon, title, children, tone = 'neutral' }) {
  const toneClass = tone === 'error' ? 'bg-clay-50 text-clay-600' : 'bg-sand-50 text-ink-400'
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center animate-rise">
      <div className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full ${toneClass}`}>
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="font-display text-xl text-ink-900">{title}</h3>
      <div className="mt-2 text-sm leading-relaxed text-ink-500">{children}</div>
    </div>
  )
}

function Summary({ result }) {
  const { interpretation: it, total_results: total, recommendation_mode: mode } = result
  const budget = [
    it.applied_min_price != null && `from ₹${it.applied_min_price.toLocaleString('en-IN')}`,
    it.applied_max_price != null && `up to ₹${it.applied_max_price.toLocaleString('en-IN')}`,
  ].filter(Boolean).join(' ')
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="font-display text-2xl text-ink-900 sm:text-3xl">
          {total} {total === 1 ? 'idea' : 'ideas'} for {it.matched_occasion || `“${result.occasion}”`}
        </h2>
        {it.concepts.length > 0 && (
          <p className="mt-1 text-sm text-ink-500">
            Looking for {it.concepts.slice(0, 5).join(', ')}
            {it.match_type === 'fuzzy' && ` (interpreted from “${result.occasion}”)`}
            {it.match_type === 'semantic' && ` (closest known occasion to “${result.occasion}”)`}
          </p>
        )}
        {budget && <p className="mt-1 text-sm text-ink-500">Budget {budget}</p>}
      </div>
      <span
        className="self-start rounded-full border border-sand-200 bg-white px-3 py-1 text-xs text-ink-500 sm:self-auto"
        title={mode === 'semantic' ? 'Ranked with MiniLM sentence embeddings + FAISS, keyword and occasion signals' : 'Embedding model unavailable: ranked with TF-IDF keyword similarity'}
      >
        {mode === 'semantic' ? 'Semantic ranking' : 'Keyword fallback ranking'}
      </span>
    </div>
  )
}

export default function Results({ status, result, error, onRetry, onSuggest }) {
  if (status === 'idle') {
    return (
      <Message icon={Gift} title="Your shortlist will appear here">
        Pick an occasion above, or describe who the gift is for.
      </Message>
    )
  }
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
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-ink-900 px-4 py-2 text-sm font-medium text-white hover:bg-ink-700">
          <RotateCw className="h-4 w-4" /> Try again
        </button>
      </Message>
    )
  }
  if (!result.recommendations.length) {
    return (
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
    )
  }
  return (
    <section aria-live="polite">
      <Summary result={result} />
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {result.recommendations.map((product, i) => (
          <ProductCard key={product.product_id} product={product} rank={i + 1} index={i} />
        ))}
      </div>
    </section>
  )
}
