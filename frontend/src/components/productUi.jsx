// Small building blocks shared by the product card and the product detail panel.
import { useState } from 'react'
import {
  Baby, Bath, BookOpen, Brain, Candy, Coffee, CreditCard, Droplet, Drum, Dumbbell, Flame, Flower2, Gem, Gift, Guitar,
  HeartHandshake, House, KeyRound, Leaf, Mail, Music, Notebook, Package, Palette, PenLine, Popcorn, Rabbit, Shirt,
  ShoppingBag, Sparkles, SprayCan, Sprout, Stamp, Star, ToyBrick, Watch,
} from 'lucide-react'
import PRODUCT_PHOTOS from '../productImages.json'

export const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const LOW_STOCK = 20

// The catalog's image bucket no longer exists (every mainImage URL returns 404), so each
// product gets generated artwork from its own data: an icon chosen from its title (then its
// inferred category), its name and brand. First matching rule wins; order matters.
const TITLE_ICONS = [
  [/watch/, Watch],
  [/perfume|fragrance/, SprayCan],
  [/soap|bath|scrub/, Bath],
  [/candle/, Flame],
  [/chocolate/, Candy],
  [/snack/, Popcorn],
  [/keychain/, KeyRound],
  [/teddy|plush|soft toy/, Rabbit],
  [/guitar/, Guitar],
  [/drum|percussion/, Drum],
  [/xylophone|music|\bdj\b/, Music],
  [/neckla|choker|bracelet|ear+ings?|studs|jewel|engagement/, Gem],
  [/slime|craft|paint|colou?ring/, Palette],
  [/star map/, Star],
  [/story ?book/, BookOpen],
  [/notebook|journal/, Notebook],
  [/letter|greeting|gretting/, Mail],
  [/\bpens?\b/, PenLine],
  [/mug/, Coffee],
  [/tea|infusion/, Leaf],
  [/mental/, Brain],
  [/fitness/, Dumbbell],
  [/skincare|oil/, Droplet],
  [/self-care/, Sparkles],
  [/plant/, Sprout],
  [/\bbags?\b|pouch/, ShoppingBag],
  [/bamboo|fib(er|re)|d[ée]cor|recycled|upcycled/, Leaf],
  [/rose|flower|lil(y|ies)|marigold|tulip|bouquet/, Flower2],
  [/shirt|polo|print|cargo|jeans|pants|kurti|saree|suit|wear/, Shirt],
  [/hamper|dry fruit/, Package],
  [/gift card/, CreditCard],
  [/seal|sticker/, Stamp],
  [/housewarming/, House],
  [/baby|newborn/, Baby],
  [/couple/, HeartHandshake],
]

// Fallback icon per inferred category (labels can be combined, e.g. "Flowers · Jewellery").
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

// Background patterns, picked per product so neighbouring cards look distinct.
const PATTERNS = [
  { backgroundImage: 'radial-gradient(#D4D4D4 1px, transparent 1px)', backgroundSize: '14px 14px' },
  { backgroundImage: 'repeating-linear-gradient(45deg, #E6E6E6 0 1px, transparent 1px 11px)' },
  {
    backgroundImage: 'linear-gradient(#EDEDED 1px, transparent 1px), linear-gradient(90deg, #EDEDED 1px, transparent 1px)',
    backgroundSize: '22px 22px',
  },
  { backgroundImage: 'repeating-radial-gradient(circle at 50% 50%, #EAEAEA 0 1px, transparent 1px 16px)' },
]

function hash(text = '') {
  let h = 0
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) >>> 0
  return h
}

export function productIcon(name = '', category = '') {
  const title = name.toLowerCase()
  const byTitle = TITLE_ICONS.find(([pattern]) => pattern.test(title))
  if (byTitle) return byTitle[1]
  const byCategory = category.split(' · ').map((label) => CATEGORY_ICONS[label]).find(Boolean)
  return byCategory || Gift
}

function ProductArtwork({ name, brand, category, seed, size }) {
  const Icon = productIcon(name, category)
  const large = size === 'lg'
  const title = name ? name.charAt(0).toUpperCase() + name.slice(1) : 'Gift'
  return (
    <div
      data-testid="image-fallback"
      role="img"
      aria-label={`Illustration of ${title}`}
      className="relative flex h-full w-full flex-col items-center justify-center gap-3 overflow-hidden bg-white px-6 text-center"
      style={PATTERNS[hash(seed || name) % PATTERNS.length]}
    >
      <span
        className={`flex ${large ? 'h-24 w-24' : 'h-16 w-16'} items-center justify-center rounded-full bg-ink-900 text-white shadow-[0_0_0_6px_#FFFFFF,0_0_0_7px_#0A0A0A] transition duration-500 group-hover:scale-105`}
      >
        <Icon className={large ? 'h-11 w-11' : 'h-7 w-7'} strokeWidth={1.4} />
      </span>
      <span className={`line-clamp-2 max-w-[90%] bg-white/90 px-2 font-display ${large ? 'text-2xl' : 'text-lg'} leading-tight text-ink-900`}>
        {title}
      </span>
      {brand && (
        <span className="bg-white/90 px-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-500">{brand}</span>
      )}
      <span className="absolute bottom-2 right-2 rounded bg-white px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-ink-400 ring-1 ring-sand-200">
        Illustration
      </span>
    </div>
  )
}

// Representative photo for a product, downloaded from Wikimedia Commons by
// backend/scripts/fetch_product_images.py (with author and licence for the credit).
export function webPhoto(productId) {
  const entry = PRODUCT_PHOTOS[productId]
  return entry ? { ...entry, url: `/product-images/${entry.file}` } : null
}

// Sources are tried in order: the catalog's own photo, then the representative web photo.
// Artwork shows until one loads (and stays if none does), so there is never an empty frame,
// and the vendor's real photos take over with no code change if their bucket comes back.
export function ProductImage({ src, alt, category, brand, seed, size = 'md' }) {
  const sources = [src, webPhoto(seed)?.url].filter(Boolean)
  const [attempt, setAttempt] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const current = sources[attempt]
  return (
    <div className="relative h-full w-full">
      {!loaded && <ProductArtwork name={alt} brand={brand} category={category} seed={seed} size={size} />}
      {current && (
        <img
          key={current}
          src={current}
          alt={alt}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => { setLoaded(false); setAttempt((n) => n + 1) }}
          className={`absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03] ${loaded ? 'opacity-100' : 'opacity-0'}`}
        />
      )}
      {loaded && current !== src && (
        <span
          className="absolute bottom-2 right-2 rounded bg-white/90 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-ink-500 ring-1 ring-sand-200"
          title="Representative photo of this product type; the vendor's own photo is unavailable"
        >
          Representative photo
        </span>
      )}
    </div>
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
    <span className={`inline-flex items-center gap-1.5 text-xs ${low ? 'font-semibold text-ink-900' : 'font-medium text-ink-500'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${low ? 'bg-ink-900' : 'bg-white ring-1 ring-ink-400'}`} />
      {low ? `Only ${stock} left` : `${stock} in stock`}
    </span>
  )
}

export function MatchBadge({ score }) {
  const pct = Math.round(score * 100)
  const tone = pct >= 75 ? 'bg-ink-900 text-white ring-ink-900'
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
