export const initialData = {
  suppliers: [
    { id: 'sup-1', code: 'SUP-001', name: 'شركة المدار للتوريد', contact: 'أحمد سالم', phone: '+966 55 123 8877', status: 'نشط', tone: 'green' },
    { id: 'sup-2', code: 'SUP-002', name: 'مصنع النخبة للصناعات', contact: 'سارة محمد', phone: '+966 54 893 1200', status: 'نشط', tone: 'green' },
    { id: 'sup-3', code: 'SUP-003', name: 'موردو الخليج', contact: 'خالد عبدالعزيز', phone: '+966 50 222 4610', status: 'مراجعة', tone: 'amber' },
    { id: 'sup-4', code: 'SUP-004', name: 'حلول التعبئة الحديثة', contact: 'منى حسن', phone: '+966 56 771 0933', status: 'موقوف', tone: 'red' }
  ],
  products: [
    { id: 'prd-1', sku: 'SKU-1042', name: 'عبوة مياه 500 مل', category: 'مشروبات', unit: 'كرتون', reorder: 80, status: 'متوفر', tone: 'green' },
    { id: 'prd-2', sku: 'SKU-2210', name: 'أكواب ورقية 8 أونص', category: 'تعبئة', unit: 'كرتون', reorder: 45, status: 'منخفض', tone: 'amber' },
    { id: 'prd-3', sku: 'SKU-3408', name: 'مناديل مطبخ كبيرة', category: 'مستهلكات', unit: 'كرتون', reorder: 30, status: 'متوفر', tone: 'green' },
    { id: 'prd-4', sku: 'SKU-5122', name: 'أكياس تسوق متوسطة', category: 'تعبئة', unit: 'حزمة', reorder: 100, status: 'حرج', tone: 'red' },
    { id: 'prd-5', sku: 'SKU-6118', name: 'منظف أسطح 1 لتر', category: 'تنظيف', unit: 'كرتون', reorder: 25, status: 'متوفر', tone: 'green' }
  ],
  warehouses: [
    { id: 'wh-1', code: 'WH-RYD', name: 'المستودع الرئيسي — الرياض', city: 'الرياض', capacity: '78%', status: 'يعمل', tone: 'green' },
    { id: 'wh-2', code: 'WH-JED', name: 'مستودع التوزيع — جدة', city: 'جدة', capacity: '61%', status: 'يعمل', tone: 'green' },
    { id: 'wh-3', code: 'WH-DMM', name: 'مستودع المنطقة الشرقية', city: 'الدمام', capacity: '92%', status: 'قريب من الامتلاء', tone: 'amber' }
  ],
  inventory: [
    { id: 'inv-1', product: 'عبوة مياه 500 مل', sku: 'SKU-1042', warehouse: 'الرياض', onHand: 420, reserved: 112, available: 308, reorder: 80, unit: 'كرتون', tone: 'green' },
    { id: 'inv-2', product: 'أكواب ورقية 8 أونص', sku: 'SKU-2210', warehouse: 'جدة', onHand: 94, reserved: 63, available: 31, reorder: 45, unit: 'كرتون', tone: 'amber' },
    { id: 'inv-3', product: 'مناديل مطبخ كبيرة', sku: 'SKU-3408', warehouse: 'الرياض', onHand: 196, reserved: 44, available: 152, reorder: 30, unit: 'كرتون', tone: 'green' },
    { id: 'inv-4', product: 'أكياس تسوق متوسطة', sku: 'SKU-5122', warehouse: 'الدمام', onHand: 41, reserved: 19, available: 22, reorder: 100, unit: 'حزمة', tone: 'red' },
    { id: 'inv-5', product: 'منظف أسطح 1 لتر', sku: 'SKU-6118', warehouse: 'جدة', onHand: 88, reserved: 20, available: 68, reorder: 25, unit: 'كرتون', tone: 'green' }
  ],
  orders: [
    { id: 'po-1', number: 'PO-2026-0108', supplier: 'شركة المدار للتوريد', date: '19 نوفمبر 2026', total: '48,750 ر.س', status: 'قيد الاعتماد', tone: 'amber', items: 4 },
    { id: 'po-2', number: 'PO-2026-0107', supplier: 'مصنع النخبة للصناعات', date: '18 نوفمبر 2026', total: '26,400 ر.س', status: 'تم الاعتماد', tone: 'blue', items: 2 },
    { id: 'po-3', number: 'PO-2026-0106', supplier: 'حلول التعبئة الحديثة', date: '17 نوفمبر 2026', total: '18,950 ر.س', status: 'تم الاستلام', tone: 'green', items: 6 },
    { id: 'po-4', number: 'PO-2026-0105', supplier: 'موردو الخليج', date: '16 نوفمبر 2026', total: '31,200 ر.س', status: 'مسودة', tone: 'slate', items: 3 }
  ]
}
