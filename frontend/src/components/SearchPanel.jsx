import { useState } from 'react'
import { Loader2, Search, SlidersHorizontal, X } from 'lucide-react'

const FEATURED = ['Birthday', 'Wedding', 'Diwali', "Valentine's Day", 'Anniversary', 'Office Party']

function Filters({ filters, onChange, categories }) {
  const set = (key) => (event) => onChange({ ...filters, [key]: event.target.value })
  const active = filters.minPrice || filters.maxPrice || filters.category
  return (
    <div className="grid gap-3 rounded-2xl border border-sand-100 bg-white/70 p-4 sm:grid-cols-[1fr_1fr_2fr_auto] sm:items-end">
      <label className="text-xs font-medium text-ink-500">
        Min price (₹)
        <input type="number" min="0" inputMode="numeric" placeholder="0" className="field mt-1"
          value={filters.minPrice} onChange={set('minPrice')} />
      </label>
      <label className="text-xs font-medium text-ink-500">
        Max price (₹)
        <input type="number" min="0" inputMode="numeric" placeholder="Any" className="field mt-1"
          value={filters.maxPrice} onChange={set('maxPrice')} />
      </label>
      <label className="text-xs font-medium text-ink-500">
        Category <span className="font-normal text-ink-400">(labels inferred from product text)</span>
        <select className="field mt-1" value={filters.category} onChange={set('category')}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.category_id} value={c.category_id}>
              {c.label} ({c.product_count})
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={!active}
        onClick={() => onChange({ minPrice: '', maxPrice: '', category: '' })}
        className="inline-flex h-[38px] items-center justify-center gap-1 rounded-xl px-3 text-sm text-ink-500 transition hover:bg-sand-50 hover:text-ink-900 disabled:opacity-40"
      >
        <X className="h-4 w-4" /> Clear
      </button>
    </div>
  )
}

export default function SearchPanel({ query, onQueryChange, onSearch, loading, filters, onFiltersChange,
  categories, examples }) {
  const [showFilters, setShowFilters] = useState(false)
  const activeFilters = [filters.minPrice, filters.maxPrice, filters.category].filter(Boolean).length

  const submit = (event) => {
    event.preventDefault()
    onSearch(query)
  }

  return (
    <section className="mx-auto w-full max-w-3xl">
      <form onSubmit={submit} role="search">
        <label htmlFor="occasion" className="mb-2 block text-sm font-medium text-ink-700">
          What's the occasion?
        </label>
        <div className="flex flex-col gap-2 rounded-2xl border border-sand-200 bg-white p-2 shadow-soft transition focus-within:border-clay-500 focus-within:ring-4 focus-within:ring-clay-100 sm:flex-row">
          <div className="flex flex-1 items-center gap-3 px-3">
            <Search className="h-5 w-5 shrink-0 text-ink-400" />
            <input
              id="occasion"
              type="text"
              autoComplete="off"
              maxLength={200}
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="e.g. Diwali, a colleague's farewell, something romantic under ₹1,500"
              className="h-12 w-full bg-transparent text-base text-ink-900 outline-none placeholder:text-ink-400"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowFilters((v) => !v)}
              aria-expanded={showFilters}
              className={`relative inline-flex h-12 items-center gap-2 rounded-xl px-4 text-sm font-medium transition ${showFilters ? 'bg-sand-100 text-ink-900' : 'text-ink-500 hover:bg-sand-50 hover:text-ink-900'}`}
            >
              <SlidersHorizontal className="h-4 w-4" /> Filters
              {activeFilters > 0 && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-clay-500 text-[11px] text-white">
                  {activeFilters}
                </span>
              )}
            </button>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-ink-900 px-6 text-sm font-semibold text-white transition hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {loading ? 'Finding…' : 'Find gifts'}
            </button>
          </div>
        </div>
      </form>

      {showFilters && (
        <div className="mt-3 animate-rise">
          <Filters filters={filters} onChange={onFiltersChange} categories={categories} />
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {FEATURED.map((occasion) => (
          <button
            key={occasion}
            type="button"
            onClick={() => onSearch(occasion)}
            className={`rounded-full border px-4 py-1.5 text-sm transition ${query === occasion ? 'border-ink-900 bg-ink-900 text-white' : 'border-sand-200 bg-white text-ink-700 hover:border-ink-400 hover:text-ink-900'}`}
          >
            {occasion}
          </button>
        ))}
      </div>
      {examples.length > 0 && (
        <p className="mt-3 text-center text-xs text-ink-400">
          Or describe it:{' '}
          {examples.slice(0, 3).map((example, i) => (
            <span key={example}>
              {i > 0 && ' · '}
              <button type="button" onClick={() => onSearch(example)} className="underline decoration-sand-300 underline-offset-2 hover:text-ink-700">
                {example}
              </button>
            </span>
          ))}
        </p>
      )}
    </section>
  )
}
