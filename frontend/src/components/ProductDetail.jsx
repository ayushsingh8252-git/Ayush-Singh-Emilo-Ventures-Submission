import { useEffect, useRef } from 'react'
import { Sparkles, X } from 'lucide-react'
import { MatchBadge, Price, ProductImage, Stock, webPhoto } from './productUi.jsx'

const SIGNALS = [
  ['semantic', 'Semantic similarity', 'How close the listing text is in meaning to the occasion (MiniLM embeddings).'],
  ['keyword', 'Keyword match', 'Share of the words you typed that appear in the listing.'],
  ['concept', 'Occasion fit', 'Themes associated with the occasion (e.g. romance, flowers) found in the listing.'],
]

function ScoreBar({ label, hint, value }) {
  const pct = Math.round(value * 100)
  return (
    <div title={hint}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ink-700">{label}</span>
        <span className="tabular-nums text-ink-500">{pct}%</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sand-100">
        <div className="h-full rounded-full bg-ink-900" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function ProductDetail({ product, rank, occasion, onClose }) {
  const closeRef = useRef(null)
  const photo = webPhoto(product.product_id)

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', onKey)
    closeRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-ink-900/40 backdrop-blur-[2px] animate-fade" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-detail-title"
        className="relative max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-t-2xl bg-white shadow-2xl animate-rise sm:rounded-2xl"
      >
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-ink-700 shadow-sm ring-1 ring-sand-200 transition hover:bg-sand-50"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="grid sm:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="relative aspect-[4/3] bg-sand-50 sm:aspect-auto sm:min-h-full">
            <ProductImage src={product.image_url} alt={product.name} category={product.category_label} brand={product.brand} seed={product.product_id} size="lg" />
            <span className="absolute left-4 top-4 rounded-md bg-ink-900 px-2 py-0.5 text-xs font-semibold text-white">
              #{rank} for {occasion}
            </span>
          </div>

          <div className="p-6 sm:p-8">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-clay-600">
              {product.category_label}
              <span className="ml-1 font-normal normal-case tracking-normal text-ink-400">(inferred)</span>
            </p>
            <h2 id="product-detail-title" className="mt-2 font-display text-2xl leading-tight text-ink-900 sm:text-3xl">
              {product.name}
            </h2>
            <p className="mt-1 text-sm text-ink-500">by {product.brand || 'Unbranded'}</p>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <Price price={product.price} finalPrice={product.final_price} discount={product.discount_percentage} large />
              <Stock stock={product.stock} />
            </div>

            <p className="mt-5 text-sm leading-relaxed text-ink-700">
              {product.description || product.short_description || 'No description provided.'}
            </p>

            <section className="mt-6 rounded-xl bg-sand-50 p-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-700">
                  <Sparkles className="h-3.5 w-3.5 text-clay-500" /> Why we picked this
                </h3>
                <MatchBadge score={product.similarity_score} />
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-ink-700">{product.reason}</p>
              {product.matched_concepts.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {product.matched_concepts.map((concept) => (
                    <span key={concept} className="rounded-full bg-white px-2.5 py-0.5 text-[11px] font-medium text-ink-700 ring-1 ring-sand-200">
                      {concept}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-5 grid gap-3">
                {SIGNALS.map(([key, label, hint]) => (
                  <ScoreBar key={key} label={label} hint={hint} value={product.score_breakdown[key]} />
                ))}
              </div>
            </section>

            <p className="mt-4 text-[11px] text-ink-400">
              Product ID {product.product_id} · Category ID {product.category_id}
            </p>
            {photo && (
              <p className="mt-1 text-[11px] text-ink-400" data-testid="photo-credit">
                Representative photo (the vendor's image is unavailable):{' '}
                <a href={photo.source} target="_blank" rel="noreferrer" className="underline hover:text-ink-900">
                  {photo.author}
                </a>
                {' · '}
                {photo.license_url
                  ? <a href={photo.license_url} target="_blank" rel="noreferrer" className="underline hover:text-ink-900">{photo.license}</a>
                  : photo.license}
                {' · Wikimedia Commons'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
