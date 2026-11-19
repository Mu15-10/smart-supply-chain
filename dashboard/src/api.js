const urls = {
  auth: import.meta.env.VITE_AUTH_URL || 'http://localhost:8001',
  supplier: import.meta.env.VITE_SUPPLIER_URL || 'http://localhost:8002',
  inventory: import.meta.env.VITE_INVENTORY_URL || 'http://localhost:8003',
  order: import.meta.env.VITE_ORDER_URL || 'http://localhost:8004',
}

async function request(base, path, token) {
  const response = await fetch(`${base}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!response.ok) throw new Error(`API ${response.status}`)
  return response.json()
}

export async function loadDashboardSnapshot(token) {
  const [suppliers, products, inventory, orders] = await Promise.all([
    request(urls.supplier, '/suppliers', token),
    request(urls.supplier, '/products', token).catch(() => ({ data: [] })),
    request(urls.inventory, '/inventory', token),
    request(urls.order, '/purchase-orders', token),
  ])
  return { suppliers: suppliers.data || [], products: products.data || [], inventory: inventory.data || [], orders: orders.data || [] }
}
