// Small building blocks shared by the product card and the product detail panel.
import { useState } from 'react'
import {
  Baby, Candy, CreditCard, Flame, Flower2, Gem, Gift, HeartHandshake, Leaf, PenLine, Shirt, ToyBrick, Watch,
} from 'lucide-react'

export const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const LOW_STOCK = 20

// Monochrome placeholder icon per inferred category, used when the product image fails to load.
const CATEGORY_ICONS = {
  Flowers: Flower2,
  'Chocolates & Treats': Candy,
  Jewellery: Gem,
  Watches: Watch,
  'Fragrances & Candles': Flame,
  Apparel: Shirt,
  'Festive Hampers': Gift,
  'Gift Cards': CreditCard,
  'Gift Wrapping & Accessories': Gift,
  'Toys & Kids': ToyBrick,
  'Wellness & Self-care': Leaf,
  Stationery: PenLine,
  'Eco Home & Decor': Leaf,
  'Personalised & Couple Gifts': HeartHandshake,
  'Life Event Gifts': Baby,
}

export function ProductImage({ src, alt, category, size = 'md' }) {
  const [failed, setFailed] = useState(!src)
  if (failed) {
    const Icon = CATEGORY_ICONS[category] || Gift
    const box = size === 'lg' ? 'h-20 w-20' : 'h-14 w-14'
    const icon = size === 'lg' ? 'h-9 w-9' : 'h-6 w-6'
    return (
      <div
        data-testid="image-fallback"
        className="flex h-full w-full flex-col items-center justify-center gap-3 bg-[linear-gradient(135deg,#F6F2EB_0%,#EFE9DF_100%)]"
      >
        <span className={`flex ${box} items-center justify-center rounded-2xl bg-white/80 text-ink-500 shadow-sm ring-1 ring-sand-200`}>
          <Icon className={icon} strokeWidth={1.4} />
        </span>
        <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Image unavailable</span>
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
    />
  )
}

export function Price({ price, finalPrice, discount, large = false }) {
  if (price == null) return <span className="text-sm text-ink-500">Price unavailable</span>
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span
        data-testid="final-price"
        data-value={finalPrice}
        className={`${large ? 'text-2xl' : 'text-lg'} font-semibold tracking-tight text-ink-900`}
      >
        {inr.format(finalPrice)}
      </span>
      {discount > 0 && (
        <>
          <span className="text-sm text-ink-400 line-through">{inr.format(price)}</span>
          <span className="rounded-md bg-sage-50 px-1.5 py-0.5 text-[11px] font-semibold text-sage-600">
            {Math.round(discount)}% off
          </span>
        </>
      )}
    </div>
  )
}

export function Stock({ stock }) {
  const low = stock < LOW_STOCK
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${low ? 'text-clay-600' : 'text-ink-500'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${low ? 'bg-clay-500' : 'bg-emerald-500'}`} />
      {low ? `Only ${stock} left` : `${stock} in stock`}
    </span>
  )
}

export function MatchBadge({ score }) {
  const pct = Math.round(score * 100)
  const tone = pct >= 75 ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
    : pct >= 50 ? 'bg-sand-50 text-ink-700 ring-sand-200' : 'bg-white text-ink-500 ring-sand-200'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ring-1 ${tone}`}
      title="Hybrid relevance score: semantic similarity, keyword match and occasion fit"
    >
      {pct}% match
    </span>
  )
}
