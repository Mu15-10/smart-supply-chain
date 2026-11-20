import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDownLeft, ArrowUpLeft, Bell, Boxes, Check, ChevronDown, CircleHelp,
  ClipboardList, LayoutDashboard, Menu, Package, Plus, Search, Settings2,
  ShoppingCart, Truck, Users, X, Warehouse as WarehouseIcon
} from 'lucide-react'
import { initialData } from './data'
import { adjustInventory, createPurchaseOrder, liveMode, loadDashboardSnapshot, login } from './api'

const navItems = [
  { id: 'dashboard', label: 'لوحة التشغيل', icon: LayoutDashboard },
  { id: 'inventory', label: 'المخزون', icon: Boxes, count: '05' },
  { id: 'orders', label: 'أوامر الشراء', icon: ClipboardList, count: '04' },
  { id: 'suppliers', label: 'الموردون', icon: Users },
  { id: 'products', label: 'المنتجات', icon: Package },
  { id: 'warehouses', label: 'المستودعات', icon: WarehouseIcon }
]

const toneClass = (tone) => `badge badge-${tone || 'slate'}`
const formatNumber = (value) => new Intl.NumberFormat('ar-SA').format(value)

function Badge({ children, tone }) {
  return <span className={toneClass(tone)}><span className="badge-dot" />{children}</span>
}

function Modal({ title, onClose, children }) {
  const titleId = `modal-title-${title.replace(/\s+/g, '-')}`
  const modalRef = useRef(null)
  useEffect(() => { modalRef.current?.querySelector('input, select, button')?.focus() }, [])
  return <div className="modal-backdrop" onMouseDown={onClose}>
    <section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} onMouseDown={(event) => event.stopPropagation()}>
      <div className="modal-header"><div><span className="context-line">إضافة جديدة</span><h2 id={titleId}>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="إغلاق الحوار"><X size={19} /></button></div>
      {children}
    </section>
  </div>
}

function EmptyNotice({ text }) {
  return <div className="empty-notice"><CircleHelp size={18} /><span>{text}</span></div>
}

function LoginPage({ onLogin, error, loading }) {
  return <main className="login-shell" dir="rtl"><section className="login-card"><div className="brand"><div className="brand-mark"><span /></div><div><strong>مدار الإمداد</strong><small>MADAR SUPPLY CONTROL</small></div></div><h1>تسجيل الدخول</h1><p>ادخل إلى لوحة تشغيل سلسلة التوريد.</p><form onSubmit={onLogin}><Field label="البريد الإلكتروني" name="email" type="email" required placeholder="name@example.com" /><Field label="كلمة المرور" name="password" type="password" required placeholder="••••••••" /><button className="button button-primary full" disabled={loading}>{loading ? 'جارٍ التحقق…' : 'دخول آمن'}</button>{error && <div className="form-error" role="alert">تعذر تسجيل الدخول: {error}</div>}</form></section></main>
}

function App() {
  const [data, setData] = useState(initialData)
  const [token, setToken] = useState(() => sessionStorage.getItem('madar_access_token') || '')
  const [loading, setLoading] = useState(liveMode)
  const [error, setError] = useState('')
  const [active, setActive] = useState('dashboard')
  const [search, setSearch] = useState('')
  const [orderFilter, setOrderFilter] = useState('all')
  const [modal, setModal] = useState(null)
  const [toast, setToast] = useState('')
  const [mobileNav, setMobileNav] = useState(false)

  const showToast = (message) => { setToast(message); window.setTimeout(() => setToast(''), 2600) }
  useEffect(() => {
    if (!liveMode || !token) { setLoading(false); return }
    setLoading(true); setError('')
    loadDashboardSnapshot(token).then((snapshot) => setData((current) => ({ ...current, ...snapshot }))).catch((err) => setError(err.message)).finally(() => setLoading(false))
  }, [token])
  const handleLogin = async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); setLoading(true); setError(''); try { const result = await login(form.get('email'), form.get('password')); sessionStorage.setItem('madar_access_token', result.access_token); setToken(result.access_token) } catch (err) { setError(err.message) } finally { setLoading(false) } }
  if (liveMode && !token) return <LoginPage onLogin={handleLogin} error={error} loading={loading} />
  const currentLabel = navItems.find((item) => item.id === active)?.label || 'لوحة التشغيل'
  const lowStock = data.inventory.filter((item) => item.available <= item.reorder)
  const filteredInventory = useMemo(() => data.inventory.filter((item) => `${item.product} ${item.sku} ${item.warehouse}`.includes(search)), [data.inventory, search])
  const filteredSuppliers = useMemo(() => data.suppliers.filter((item) => `${item.name} ${item.code} ${item.contact}`.includes(search)), [data.suppliers, search])
  const filteredProducts = useMemo(() => data.products.filter((item) => `${item.name} ${item.sku} ${item.category}`.includes(search)), [data.products, search])
  const filteredOrders = useMemo(() => data.orders.filter((item) => `${item.number} ${item.supplier} ${item.status}`.includes(search) && (orderFilter === 'all' || (orderFilter === 'draft' && item.status === 'مسودة') || (orderFilter === 'approval' && item.status === 'قيد الاعتماد'))), [data.orders, search, orderFilter])

  const openCreate = (type) => setModal(type)
  const addSupplier = (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    setData((current) => ({ ...current, suppliers: [{ id: `sup-${Date.now()}`, code: form.get('code'), name: form.get('name'), contact: form.get('contact') || '—', phone: form.get('phone') || '—', status: 'مراجعة', tone: 'amber' }, ...current.suppliers] }))
    setModal(null); showToast('تمت إضافة المورد إلى القائمة')
  }
  const addProduct = (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    setData((current) => ({ ...current, products: [{ id: `prd-${Date.now()}`, sku: form.get('sku'), name: form.get('name'), category: form.get('category') || 'عام', unit: form.get('unit') || 'وحدة', reorder: Number(form.get('reorder') || 0), status: 'متوفر', tone: 'green' }, ...current.products] }))
    setModal(null); showToast('تمت إضافة المنتج إلى الكتالوج')
  }
  const addOrder = (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    const items = Number(form.get('items')); const total = Number(form.get('total'))
    if (!Number.isInteger(items) || items < 1 || !Number.isFinite(total) || total < 0) { showToast('تحقق من عدد البنود والإجمالي'); return }
    setData((current) => ({ ...current, orders: [{ id: `po-${Date.now()}`, number: `PO-2026-${String(current.orders.length + 109).padStart(4, '0')}`, supplier: form.get('supplier'), date: 'اليوم', total: `${total} ر.س`, status: 'مسودة', tone: 'slate', items }, ...current.orders] }))
    setModal(null); showToast('تم إنشاء أمر الشراء كمسودة')
  }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><span /></div><div><strong>مدار الإمداد</strong><small>MADAR SUPPLY CONTROL</small></div><button className="mobile-close icon-button" aria-label="إغلاق القائمة" onClick={() => setMobileNav(false)}><X size={18} /></button></div>
      <div className="workspace-switch"><span className="workspace-avatar">ن</span><div><small>مساحة العمل</small><strong>شركة المدار</strong></div><ChevronDown size={16} /></div>
      <nav className="main-nav"><p className="nav-label">التشغيل اليومي</p>{navItems.map(({ id, label, icon: Icon, count }) => <button key={id} className={`nav-item ${active === id ? 'nav-active' : ''}`} onClick={() => { setActive(id); setSearch(''); setMobileNav(false) }}><Icon size={18} strokeWidth={active === id ? 2.3 : 1.8} /><span>{label}</span>{count && <em>{count}</em>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="sync-card"><span className="sync-pulse" /><div><strong>النظام يعمل بشكل طبيعي</strong><small>آخر مزامنة منذ 4 دقائق</small></div></div><button className="nav-item"><Settings2 size={18} /><span>الإعدادات</span></button><div className="user-mini"><div className="user-avatar">م</div><div><strong>محمد حسين</strong><small>مدير النظام</small></div><ChevronDown size={15} /></div></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><button className="mobile-menu icon-button" aria-label="فتح القائمة" onClick={() => setMobileNav(true)}><Menu size={20} /></button><div className="breadcrumb"><span>الرئيسية</span><span>/</span><strong>{currentLabel}</strong></div><div className="top-actions"><div className="connection-pill"><span /> {liveMode ? 'بيانات حية' : 'بيانات تجريبية'}</div><button className="icon-button notification-button" aria-label="الإشعارات غير متاحة في النسخة التجريبية"><Bell size={19} /><i /></button>{liveMode && <button className="button button-ghost" onClick={() => { sessionStorage.removeItem('madar_access_token'); setToken('') }}>خروج</button>}<div className="top-user" aria-label="حساب محمد حسين"><span>م</span><ChevronDown size={14} /></div></div></header>
      <div className="page-wrap">
        {error && <div className="form-error" role="alert">تعذر تحميل البيانات الحية: {error}</div>}
        {active === 'dashboard' && <Dashboard data={data} lowStock={lowStock} onNavigate={setActive} onCreate={openCreate} />}
        {active === 'inventory' && <InventoryPage rows={filteredInventory} search={search} setSearch={setSearch} onCreate={() => openCreate('adjust')} />}
        {active === 'orders' && <OrdersPage rows={filteredOrders} search={search} setSearch={setSearch} filter={orderFilter} setFilter={setOrderFilter} onCreate={() => openCreate('order')} />}
        {active === 'suppliers' && <SuppliersPage rows={filteredSuppliers} search={search} setSearch={setSearch} onCreate={() => openCreate('supplier')} />}
        {active === 'products' && <ProductsPage rows={filteredProducts} search={search} setSearch={setSearch} onCreate={() => openCreate('product')} />}
        {active === 'warehouses' && <WarehousesPage rows={data.warehouses} onCreate={() => showToast('إضافة المستودع ستكون متاحة في النسخة التالية')} />}
      </div>
    </main>
    {modal === 'supplier' && <Modal title="إضافة مورد جديد" onClose={() => setModal(null)}><form className="form-grid" onSubmit={addSupplier}><Field label="اسم المورد" name="name" placeholder="مثال: شركة التوريد المتحدة" required /><Field label="رمز المورد" name="code" placeholder="SUP-005" required /><Field label="جهة الاتصال" name="contact" placeholder="اسم المسؤول" /><Field label="رقم التواصل" name="phone" placeholder="05xxxxxxxx" /><FormActions onClose={() => setModal(null)} /></form></Modal>}
    {modal === 'product' && <Modal title="إضافة منتج جديد" onClose={() => setModal(null)}><form className="form-grid" onSubmit={addProduct}><Field label="اسم المنتج" name="name" placeholder="مثال: عبوات مياه" required /><Field label="SKU" name="sku" placeholder="SKU-0001" required /><Field label="التصنيف" name="category" placeholder="تعبئة، مشروبات..." /><Field label="وحدة القياس" name="unit" placeholder="كرتون" /><Field label="نقطة إعادة الطلب" name="reorder" type="number" placeholder="50" /><FormActions onClose={() => setModal(null)} /></form></Modal>}
    {modal === 'order' && <Modal title="إنشاء أمر شراء" onClose={() => setModal(null)}><form className="form-grid" onSubmit={addOrder}><label className="field full"><span>المورد</span><select name="supplier" required><option value="">اختر المورد</option>{data.suppliers.filter((s) => s.status !== 'موقوف').map((s) => <option key={s.id}>{s.name}</option>)}</select></label><Field label="عدد البنود" name="items" type="number" placeholder="1" /><Field label="الإجمالي التقديري (ر.س)" name="total" type="number" placeholder="0" /><div className="form-note full"><CircleHelp size={15} /> سيُحفظ الأمر كمسودة ويمكن اعتماده لاحقًا.</div><FormActions onClose={() => setModal(null)} /></form></Modal>}
    {modal === 'adjust' && <Modal title="تسجيل حركة مخزون" onClose={() => setModal(null)}><form className="form-grid" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const quantity = Number(form.get('quantity')); const movement = form.get('movement'); if (!Number.isFinite(quantity) || quantity <= 0) { showToast('أدخل كمية أكبر من صفر'); return } setData((current) => ({ ...current, inventory: current.inventory.map((item) => { const product = current.products.find((p) => p.name === form.get('product')); if (!product || item.product !== product.name) return item; const onHand = movement === 'صرف' ? Math.max(0, item.onHand - quantity) : item.onHand + quantity; return { ...item, onHand, available: onHand - item.reserved, tone: onHand - item.reserved <= item.reorder ? 'amber' : 'green' } }) })); setModal(null); showToast('تم تحديث رصيد المخزون في المعاينة') }}><label className="field full"><span>المنتج</span><select name="product" required><option value="">اختر المنتج</option>{data.products.map((p) => <option key={p.id}>{p.name}</option>)}</select></label><Field label="الكمية" name="quantity" type="number" min="0.01" step="0.01" placeholder="0" required /><label className="field"><span>نوع الحركة</span><select name="movement"><option>استلام</option><option>تسوية</option><option>صرف</option></select></label><FormActions onClose={() => setModal(null)} /></form></Modal>}
    {toast && <div className="toast"><Check size={17} />{toast}</div>}
  </div>
}

function Field({ label, name, type = 'text', placeholder, required, min, step }) { return <label className="field"><span>{label}</span><input name={name} type={type} placeholder={placeholder} required={required} min={min} step={step} /></label> }
function FormActions({ onClose }) { return <div className="form-actions full"><button type="button" className="button button-ghost" onClick={onClose}>إلغاء</button><button type="submit" className="button button-primary"><Check size={16} />حفظ البيانات</button></div> }

function PageHeading({ eyebrow, title, description, action, onAction }) { return <div className="page-heading"><div><div className="heading-context"><span className="status-led" />{eyebrow}</div><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <button className="button button-primary" onClick={onAction}><Plus size={17} />{action}</button>}</div> }
function SearchBar({ value, onChange, placeholder = 'ابحث في القائمة...' }) { const id = `search-${placeholder.replace(/\W/g, '')}`; return <label className="search-box" htmlFor={id}><Search size={17} aria-hidden="true" /><span className="sr-only">بحث</span><input id={id} aria-label={placeholder} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /></label> }

function Dashboard({ data, lowStock, onNavigate, onCreate }) {
  return <><PageHeading eyebrow="الأربعاء، 19 نوفمبر 2026" title="صباح الخير، محمد" description="هذه صورة سريعة عن حركة سلسلة التوريد اليوم." action="أمر شراء جديد" onAction={() => onCreate('order')} />
    <section className="hero-strip"><div className="hero-copy"><h2>حرّك الإمداد<br /><em>بثقة.</em></h2><p>من نقطة الطلب إلى باب المستودع، في مسار واحد.</p></div><div className="hero-metric"><span>قيمة المشتريات هذا الشهر</span><strong>125,300 <small>ر.س</small></strong><div className="trend positive"><ArrowUpLeft size={14} /> 12.8% عن الشهر الماضي</div></div><div className="hero-art"><div className="art-circle circle-one" /><div className="art-circle circle-two" /><div className="art-bars"><i /><i /><i /><i /><i /></div></div></section>
    <div className="stat-grid"><StatCard icon={Users} label="الموردون النشطون" value={data.suppliers.filter((s) => s.status === 'نشط').length} suffix={`من ${data.suppliers.length}`} tone="mint" onClick={() => onNavigate('suppliers')} /><StatCard icon={Package} label="إجمالي المنتجات" value={data.products.length} suffix="في الكتالوج" tone="blue" onClick={() => onNavigate('products')} /><StatCard icon={Boxes} label="قيمة المخزون" value="86.4K" suffix="ر.س · +8.4%" tone="amber" onClick={() => onNavigate('inventory')} /><StatCard icon={ShoppingCart} label="أوامر مفتوحة" value={data.orders.filter((o) => o.status !== 'تم الاستلام').length} suffix={`من ${data.orders.length} أوامر`} tone="violet" onClick={() => onNavigate('orders')} /></div>
    <div className="dashboard-grid"><section className="panel stock-panel"><PanelHeader title="تنبيهات المخزون" note={`${lowStock.length} أصناف تحتاج انتباه`} action="عرض الكل" onAction={() => onNavigate('inventory')} />{lowStock.map((item) => <div className="alert-row" key={item.id}><div className={`alert-icon ${item.tone}`}><Package size={17} /></div><div className="alert-info"><strong>{item.product}</strong><span>{item.warehouse} · {item.sku}</span></div><div className="stock-progress"><div className="progress-track"><i style={{ width: `${Math.min((item.available / item.reorder) * 100, 100)}%` }} /></div><small>{item.available} / {item.reorder} {item.unit}</small></div><Badge tone={item.tone}>{item.tone === 'red' ? 'حرج' : 'منخفض'}</Badge></div>)}<button className="inline-action" onClick={() => onCreate('adjust')}><Plus size={15} /> تسجيل حركة مخزون</button></section><section className="panel orders-panel"><PanelHeader title="آخر أوامر الشراء" note="آخر 30 يومًا" action="كل الأوامر" onAction={() => onNavigate('orders')} />{data.orders.slice(0, 4).map((order) => <div className="order-row" key={order.id}><div className="order-symbol"><ClipboardList size={16} /></div><div className="order-info"><strong>{order.number}</strong><span>{order.supplier} · {order.items} بنود</span></div><div className="order-total"><strong>{order.total}</strong><span>{order.date}</span></div><Badge tone={order.tone}>{order.status}</Badge></div>)}</section></div>
    <section className="quick-panel"><div><span className="context-line">إجراءات سريعة</span><h3>أنجز مهمتك التالية</h3></div><QuickAction icon={ShoppingCart} title="أنشئ أمر شراء" caption="ابدأ طلبًا جديدًا" onClick={() => onCreate('order')} /><QuickAction icon={Package} title="أضف منتجًا" caption="حدّث الكتالوج" onClick={() => onCreate('product')} /><QuickAction icon={Truck} title="سجّل استلامًا" caption="حدّث المخزون" onClick={() => onCreate('adjust')} /></section>
  </>
}
function StatCard({ icon: Icon, label, value, suffix, tone, onClick }) { return <button className={`stat-card stat-${tone}`} onClick={onClick}><div className="stat-top"><span className="stat-icon"><Icon size={18} /></span><ArrowUpLeft size={16} className="stat-arrow" /></div><div className="stat-value">{value}</div><div className="stat-label">{label}</div><div className="stat-suffix">{suffix}</div></button> }
function PanelHeader({ title, note, action, onAction }) { return <div className="panel-header"><div><h3>{title}</h3><p>{note}</p></div><button onClick={onAction}>{action}<ArrowDownLeft size={14} /></button></div> }
function QuickAction({ icon: Icon, title, caption, onClick }) { return <button className="quick-action" onClick={onClick}><span><Icon size={18} /></span><div><strong>{title}</strong><small>{caption}</small></div><ArrowDownLeft size={16} /></button> }

function InventoryPage({ rows, search, setSearch, onCreate }) { return <><PageHeading eyebrow="إدارة المخزون" title="المخزون" description="راقب الأرصدة المتاحة وحدد الأصناف التي تحتاج إلى إعادة طلب." action="تسجيل حركة" onAction={onCreate} /><div className="page-toolbar"><SearchBar value={search} onChange={setSearch} placeholder="ابحث بالمنتج أو المستودع..." /><div className="toolbar-meta"><span className="live-dot" /> تحديث مباشر · منذ 4 دقائق</div></div><section className="table-panel"><div className="table-summary"><strong>أرصدة المخزون</strong><span>{rows.length} سجلات</span></div><InventoryTable rows={rows} /></section></> }
function InventoryTable({ rows }) { return <div className="table-scroll"><table><thead><tr><th>المنتج</th><th>المستودع</th><th>الرصيد الحالي</th><th>المحجوز</th><th>المتاح</th><th>الحالة</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><div className="table-primary"><span className="product-avatar"><Package size={16} /></span><div><strong>{item.product}</strong><small>{item.sku}</small></div></div></td><td>{item.warehouse}</td><td>{formatNumber(item.onHand)} <small>{item.unit}</small></td><td>{formatNumber(item.reserved)}</td><td><strong>{formatNumber(item.available)}</strong> <small>{item.unit}</small></td><td><Badge tone={item.tone}>{item.available <= item.reorder ? (item.tone === 'red' ? 'حرج' : 'منخفض') : 'طبيعي'}</Badge></td></tr>)}</tbody></table>{rows.length === 0 && <EmptyNotice text="لا توجد نتائج مطابقة للبحث." />}</div> }
function OrdersPage({ rows, search, setSearch, filter, setFilter, onCreate }) { const tabs = [['all', 'كل الأوامر'], ['draft', 'مسودات'], ['approval', 'قيد الاعتماد']]; return <><PageHeading eyebrow="المشتريات والتوريد" title="أوامر الشراء" description="أنشئ الطلبات وتابع الاعتماد والاستلام من قائمة واحدة." action="أمر شراء جديد" onAction={onCreate} /><div className="page-toolbar"><SearchBar value={search} onChange={setSearch} placeholder="ابحث برقم الأمر أو المورد..." /><div className="filter-tabs" role="tablist" aria-label="تصفية أوامر الشراء">{tabs.map(([value, label]) => <button key={value} role="tab" aria-selected={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div></div><section className="table-panel"><div className="table-summary"><strong>قائمة أوامر الشراء</strong><span>{rows.length} أوامر</span></div><div className="table-scroll"><table><thead><tr><th>رقم الأمر</th><th>المورد</th><th>تاريخ الإنشاء</th><th>البنود</th><th>الإجمالي</th><th>الحالة</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><strong className="link-text">{item.number}</strong></td><td>{item.supplier}</td><td>{item.date}</td><td>{item.items} بنود</td><td><strong>{item.total}</strong></td><td><Badge tone={item.tone}>{item.status}</Badge></td></tr>)}</tbody></table>{rows.length === 0 && <EmptyNotice text="لا توجد أوامر مطابقة للبحث." />}</div></section></> }
function SuppliersPage({ rows, search, setSearch, onCreate }) { return <><PageHeading eyebrow="دليل الشركاء" title="الموردون" description="احتفظ ببيانات الموردين وتابع جاهزيتهم للتوريد." action="إضافة مورد" onAction={onCreate} /><div className="page-toolbar"><SearchBar value={search} onChange={setSearch} placeholder="ابحث باسم المورد أو الرمز..." /></div><section className="card-grid">{rows.map((item) => <article className="entity-card" key={item.id}><div className="entity-top"><span className="entity-avatar"><Users size={18} /></span><Badge tone={item.tone}>{item.status}</Badge></div><h3>{item.name}</h3><p className="entity-code">{item.code}</p><div className="entity-detail"><span>جهة الاتصال</span><strong>{item.contact}</strong></div><div className="entity-detail"><span>الهاتف</span><strong dir="ltr">{item.phone}</strong></div></article>)}</section>{rows.length === 0 && <EmptyNotice text="لا توجد نتائج مطابقة للبحث." />}</> }
function ProductsPage({ rows, search, setSearch, onCreate }) { return <><PageHeading eyebrow="الكتالوج الرئيسي" title="المنتجات" description="نظّم أصنافك وحدد نقاط إعادة الطلب لكل منتج." action="إضافة منتج" onAction={onCreate} /><div className="page-toolbar"><SearchBar value={search} onChange={setSearch} placeholder="ابحث باسم المنتج أو SKU..." /></div><section className="table-panel"><div className="table-summary"><strong>كتالوج المنتجات</strong><span>{rows.length} منتجات</span></div><div className="table-scroll"><table><thead><tr><th>المنتج</th><th>التصنيف</th><th>وحدة القياس</th><th>نقطة إعادة الطلب</th><th>الحالة</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><div className="table-primary"><span className="product-avatar"><Package size={16} /></span><div><strong>{item.name}</strong><small>{item.sku}</small></div></div></td><td>{item.category}</td><td>{item.unit}</td><td>{formatNumber(item.reorder)}</td><td><Badge tone={item.tone}>{item.status}</Badge></td></tr>)}</tbody></table>{rows.length === 0 && <EmptyNotice text="لا توجد منتجات مطابقة للبحث." />}</div></section></> }
function WarehousesPage({ rows, onCreate }) { return <><PageHeading eyebrow="شبكة التخزين" title="المستودعات" description="نظرة واضحة على السعة وحالة مواقع التخزين." action="إضافة مستودع" onAction={onCreate} /><section className="warehouse-grid">{rows.map((item) => <article className="warehouse-card" key={item.id}><div className="warehouse-head"><span className="warehouse-icon"><WarehouseIcon size={21} /></span><Badge tone={item.tone}>{item.status}</Badge></div><h3>{item.name}</h3><p>{item.code} · {item.city}</p><div className="capacity-label"><span>السعة المستخدمة</span><strong>{item.capacity}</strong></div><div className="capacity-track"><i style={{ width: item.capacity }} /></div><div className="warehouse-footer"><span><Boxes size={15} /> المخزون متزامن</span><button>التفاصيل <ArrowDownLeft size={14} /></button></div></article>)}</section></> }

export default App
