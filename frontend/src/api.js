export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error(`Can't reach the recommendation service at ${API_URL}. Is the backend running?`)
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return body
}

export const getHealth = () => request('/api/health')
export const getOccasions = () => request('/api/occasions')
export const getCategories = () => request('/api/categories')

export function getRecommendations({ occasion, limit = 12, minPrice, maxPrice, category }) {
  const toNumber = (value) => (value === '' || value == null ? null : Number(value))
  return request('/api/recommend', {
    method: 'POST',
    body: JSON.stringify({
      query: occasion, // natural-language text; the backend interprets it (rules or optional LLM)
      limit,
      min_price: toNumber(minPrice),
      max_price: toNumber(maxPrice),
      category: category || null,
    }),
  })
}
