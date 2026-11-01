import { ArrowUpRight, Sparkles } from 'lucide-react'
import { MatchBadge, Price, ProductImage, Stock } from './productUi.jsx'

export default function ProductCard({ product, rank, index, onOpen }) {
  return (
    <article
      data-testid="product-card"
      className="group flex flex-col overflow-hidden rounded-xl border border-sand-200/70 bg-white transition duration-300 hover:border-sand-300 hover:shadow-lift animate-rise"
      style={{ animationDelay: `${Math.min(index, 11) * 40}ms` }}
    >
      <button
        type="button"
        onClick={onOpen}
        className="relative block aspect-[4/3] overflow-hidden bg-sand-50 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-clay-500"
        aria-label={`View details for ${product.name}`}
      >
        <ProductImage src={product.image_url} alt={product.name} category={product.category_label} />
        <span className="absolute left-3 top-3 rounded-md bg-ink-900 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-white">
          #{rank}
        </span>
      </button>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center justify-between gap-3">
          <p
            className="truncate text-[11px] font-semibold uppercase tracking-wider text-clay-600"
            title={`Category inferred from the product text (category ID ${product.category_id})`}
          >
            {product.category_label}
          </p>
          <MatchBadge score={product.similarity_score} />
        </div>

        <h3 className="mt-2 text-[17px] font-semibold leading-snug tracking-tight text-ink-900">
          <button type="button" onClick={onOpen} className="text-left hover:underline hover:decoration-sand-300 hover:underline-offset-4">
            {product.name}
          </button>
        </h3>
        <p className="mt-0.5 text-xs text-ink-400">by {product.brand || 'Unbranded'}</p>
        <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-ink-500">
          {product.description || product.short_description || 'No description provided.'}
        </p>

        <div className="mt-4 flex items-end justify-between gap-2">
          <Price price={product.price} finalPrice={product.final_price} discount={product.discount_percentage} />
          <Stock stock={product.stock} />
        </div>

        <div className="mt-4 border-t border-sand-100 pt-4">
          <p className="mb-1.5 inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
            <Sparkles className="h-3.5 w-3.5 text-clay-500" /> Why we picked this
          </p>
          <p className="line-clamp-3 text-[13px] leading-relaxed text-ink-700">{product.reason}</p>
          <button
            type="button"
            onClick={onOpen}
            className="mt-3 inline-flex items-center gap-1 text-[13px] font-semibold text-ink-900 hover:text-clay-600"
          >
            View details <ArrowUpRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  )
}
