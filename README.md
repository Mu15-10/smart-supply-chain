# مدار الإمداد — Smart Supply Chain

نظام MVP لإدارة سلسلة التوريد يتكون من Backend بخدمات Auth/Supplier/Inventory/Order ولوحة تحكم عربية React.

- `backend/`: FastAPI، PostgreSQL، MongoDB، Redis، Docker Compose واختبارات API.
- `dashboard/`: لوحة تشغيل عربية RTL مبنية بـ React/Vite.
- `CODE-REVIEW.md`: نتائج المراجعة الأمنية والهندسية.
- `IMPLEMENTATION-REPORT.md`: الإصلاحات المنفذة ونتائج التحقق.

للتشغيل راجع `backend/README.md` ثم شغّل لوحة التحكم من `dashboard/`.

## النشر العام

الواجهة التجريبية منشورة على GitHub Pages:

- الموقع: https://mu15-10.github.io/smart-supply-chain/
- مستودع GitHub: https://github.com/Mu15-10/smart-supply-chain
- فرع النشر: `gh-pages`

النسخة العامة الحالية تعمل بوضع Demo. تشغيل البيانات الحية يحتاج نشر Backend وقواعد البيانات وضبط متغيرات `VITE_*` على منصة الاستضافة.
