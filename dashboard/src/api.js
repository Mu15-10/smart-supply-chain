const urls = {
  auth: import.meta.env.VITE_AUTH_URL || 'http://localhost:8001',
  supplier: import.meta.env.VITE_SUPPLIER_URL || 'http://localhost:8002',
  inventory: import.meta.env.VITE_INVENTORY_URL || 'http://localhost:8003',
  order: import.meta.env.VITE_ORDER_URL || 'http://localhost:8004',
}
export const liveMode = import.meta.env.VITE_API_MODE === 'live'
const refreshKey = 'madar_refresh_token'
export const clearSession = () => { sessionStorage.removeItem('madar_access_token'); sessionStorage.removeItem(refreshKey) }
async function refreshSession() {
  const refreshToken = sessionStorage.getItem(refreshKey)
  if (!refreshToken) throw new Error('SESSION_EXPIRED')
  const response = await fetch(`${urls.auth}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refreshToken }) })
  const payload = await response.json().catch(() => ({}))
  if (response.status === 401 && liveMode && !retried && path !== '/auth/refresh') { const freshToken = await refreshSession(); return request(base, path, { token: freshToken, method, body, idempotencyKey, retried: true }) }
  if (!response.ok) { clearSession(); throw new Error(payload.detail || 'SESSION_EXPIRED') }
  sessionStorage.setItem('madar_access_token', payload.access_token); sessionStorage.setItem(refreshKey, payload.refresh_token)
  return payload.access_token
}
async function request(base, path, { token, method = 'GET', body, idempotencyKey, retried = false } = {}) {
  const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}), ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) }
  const response = await fetch(`${base}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  const payload = await response.json().catch(() => ({}))
  if (response.status === 401 && liveMode && !retried && path !== '/auth/refresh') { const freshToken = await refreshSession(); return request(base, path, { token: freshToken, method, body, idempotencyKey, retried: true }) }
  if (!response.ok) { const error = new Error(payload.detail || payload.message || `API ${response.status}`); error.status = response.status; throw error }
  return payload
}
export async function login(email, password) { return request(urls.auth, '/auth/login', { method: 'POST', body: { email, password } }) }
export async function logout(token) { const refreshToken = sessionStorage.getItem(refreshKey); if (refreshToken) await request(urls.auth, '/auth/logout', { token, method: 'POST', body: { refresh_token: refreshToken }, retried: true }).catch(() => {}); clearSession() }
export async function loadDashboardSnapshot(token) {
  const [suppliers, products, warehouses, inventory, orders] = await Promise.all([
    request(urls.supplier, '/suppliers', { token }), request(urls.supplier, '/products', { token }), request(urls.supplier, '/warehouses', { token }), request(urls.inventory, '/inventory', { token }), request(urls.order, '/purchase-orders', { token }),
  ])
  const productMap = new Map((products.data || []).map((p) => [p.id, p])); const warehouseMap = new Map((warehouses.data || []).map((w) => [w.id, w]))
  return {
    suppliers: (suppliers.data || []).map((s) => ({ id: s.id, code: s.supplierCode, name: s.legalName, contact: '—', phone: '—', status: s.status === 'active' ? 'نشط' : s.status, tone: 'green' })),
    products: (products.data || []).map((p) => ({ id: p.id, sku: p.sku, name: p.name, category: 'عام', unit: p.unitOfMeasure, reorder: Number(p.reorderPoint || 0), status: 'متوفر', tone: 'green' })),
    warehouses: (warehouses.data || []).map((w) => ({ id: w.id, code: w.code, name: w.name, city: '—', capacity: '0%', status: 'نشط', tone: 'green' })),
    inventory: (inventory.data || []).map((i) => { const p = productMap.get(i.productId); const w = warehouseMap.get(i.warehouseId); const available = Number(i.available || 0); const reorder = Number(i.reorderPoint || 0); return { id: `${i.warehouseId}-${i.productId}`, product: p?.name || i.productId, sku: p?.sku || '—', warehouse: w?.name || i.warehouseId, onHand: Number(i.onHand || 0), reserved: Number(i.reserved || 0), available, reorder, unit: p?.unitOfMeasure || 'وحدة', tone: available <= reorder ? 'amber' : 'green' } }),
    orders: (orders.data || []).map((o) => ({ id: o.id, number: o.poNumber, supplier: o.supplierId, date: '—', total: `${o.total} ر.س`, status: o.status === 'draft' ? 'مسودة' : o.status, tone: o.status === 'draft' ? 'slate' : 'amber', items: 0 })),
  }
}
export function createResource(service, path, token, body) { return request(urls[service], path, { token, method: 'POST', body, idempotencyKey: crypto.randomUUID() }) }
export function adjustInventory(token, body) { return createResource('inventory', '/inventory/adjust', token, body) }
export function createPurchaseOrder(token, body) { return createResource('order', '/purchase-orders', token, body) }
