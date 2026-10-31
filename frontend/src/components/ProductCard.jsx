import { useState } from 'react'
import {
  Baby, Candy, CreditCard, Flame, Flower2, Gem, Gift, HeartHandshake, Leaf, Package, PenLine, Shirt,
  Sparkles, ToyBrick, Watch,
} from 'lucide-react'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const LOW_STOCK = 20

// Placeholder artwork per inferred category, used when the product image fails to load.
const PLACEHOLDERS = {
  Flowers: [Flower2, 'from-rose-50 to-clay-50 text-rose-400'],
  'Chocolates & Treats': [Candy, 'from-amber-50 to-sand-100 text-amber-700'],
  Jewellery: [Gem, 'from-violet-50 to-sand-50 text-violet-400'],
  Watches: [Watch, 'from-slate-100 to-sand-50 text-slate-500'],
  'Fragrances & Candles': [Flame, 'from-orange-50 to-sand-50 text-orange-400'],
  Apparel: [Shirt, 'from-sky-50 to-sand-50 text-sky-500'],
  'Festive Hampers': [Gift, 'from-amber-50 to-clay-50 text-clay-500'],
  'Gift Cards': [CreditCard, 'from-emerald-50 to-sand-50 text-emerald-600'],
  'Gift Wrapping & Accessories': [Gift, 'from-pink-50 to-sand-50 text-pink-400'],
  'Toys & Kids': [ToyBrick, 'from-yellow-50 to-sky-50 text-yellow-600'],
  'Wellness & Self-care': [Leaf, 'from-sage-50 to-sand-50 text-sage-600'],
  Stationery: [PenLine, 'from-indigo-50 to-sand-50 text-indigo-400'],
  'Eco Home & Decor': [Leaf, 'from-lime-50 to-sand-50 text-lime-700'],
  'Personalised & Couple Gifts': [HeartHandshake, 'from-rose-50 to-sand-50 text-rose-400'],
  'Life Event Gifts': [Baby, 'from-teal-50 to-sand-50 text-teal-500'],
}

function ProductImage({ src, alt, category }) {
  const [failed, setFailed] = useState(!src)
  if (failed) {
    const [Icon, tone] = PLACEHOLDERS[category] || [Gift, 'from-sand-50 to-sand-100 text-ink-400']
    return (
      <div data-testid="image-fallback" className={`flex h-full w-full flex-col items-center justify-center gap-2 bg-gradient-to-br ${tone}`}>
        <Icon className="h-12 w-12" strokeWidth={1.25} />
        <span className="text-[11px] text-ink-400">Image unavailable</span>
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]"
    />
  )
}

function Price({ price, finalPrice, discount }) {
  if (price == null) return <span className="text-sm text-ink-500">Price unavailable</span>
  return (
    <div className="flex items-baseline gap-2">
      <span data-testid="final-price" data-value={finalPrice} className="text-lg font-semibold text-ink-900">{inr.format(finalPrice)}</span>
      {discount > 0 && (
        <>
          <span className="text-sm text-ink-400 line-through">{inr.format(price)}</span>
          <span className="text-xs font-semibold text-sage-600">{Math.round(discount)}% off</span>
        </>
      )}
    </div>
  )
}

function Stock({ stock }) {
  const low = stock < LOW_STOCK
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${low ? 'text-clay-600' : 'text-ink-500'}`}>
      <Package className="h-3.5 w-3.5" />
      {low ? `Only ${stock} left` : `${stock} in stock`}
    </span>
  )
}

function Relevance({ score }) {
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-2" title="Hybrid relevance score: semantic similarity, keyword match and occasion concepts">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-sand-100">
        <div className="h-full rounded-full bg-clay-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium tabular-nums text-ink-700">{pct}% match</span>
    </div>
  )
}

export default function ProductCard({ product, rank, index }) {
  return (
    <article
      data-testid="product-card"
      className="group flex flex-col overflow-hidden rounded-2xl border border-sand-100 bg-white shadow-soft transition duration-300 hover:-translate-y-1 hover:shadow-lift animate-rise"
      style={{ animationDelay: `${Math.min(index, 11) * 45}ms` }}
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-sand-50">
        <ProductImage src={product.image_url} alt={product.name} category={product.category_label} />
        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-xs font-semibold text-ink-900 backdrop-blur">
          #{rank}
        </span>
        <span
          className="absolute right-3 top-3 rounded-full bg-ink-900/75 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur"
          title={`Category inferred from the product text (category ID ${product.category_id})`}
        >
          {product.category_label}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-ink-400">{product.brand || 'Unbranded'}</p>
          <h3 className="mt-1 font-display text-xl leading-snug text-ink-900">{product.name}</h3>
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-500">
            {product.description || product.short_description || 'No description provided.'}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Price price={product.price} finalPrice={product.final_price} discount={product.discount_percentage} />
          <Stock stock={product.stock} />
        </div>

        <div className="mt-auto rounded-xl bg-sand-50 p-3.5">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-clay-700">
              <Sparkles className="h-3.5 w-3.5" /> Why this gift
            </span>
            <Relevance score={product.similarity_score} />
          </div>
          <p className="line-clamp-4 text-[13px] leading-relaxed text-ink-700">{product.reason}</p>
        </div>
      </div>
    </article>
  )
}
