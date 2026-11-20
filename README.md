# مدار الإمداد — Smart Supply Chain

نظام MVP لإدارة سلسلة التوريد يتكون من Backend بخدمات Auth/Supplier/Inventory/Order ولوحة تحكم عربية React RTL. يحتوي المستودع على طبقات حماية للعزل بين المستأجرين، RBAC، idempotency دائمة، migrations عبر Alembic، وCI للفحوصات والبناء.

## المكونات

- `backend/`: FastAPI، PostgreSQL، MongoDB، Redis، Docker Compose، Alembic واختبارات API.
- `dashboard/`: لوحة تشغيل React/Vite عربية RTL. الوضع الافتراضي Demo؛ لتفعيل API الحقيقي استخدم `VITE_API_MODE=live` واضبط `VITE_AUTH_URL` و`VITE_SUPPLIER_URL` و`VITE_INVENTORY_URL` و`VITE_ORDER_URL`.
- `CODE-REVIEW.md`: نتائج المراجعة الأمنية والهندسية.
- `IMPLEMENTATION-REPORT.md`: مراحل الإصلاح ونتائج التحقق الفعلية.

## تشغيل آمن

انسخ `backend/.env.example` إلى ملف بيئة محلي، وولّد قيمًا خاصة بك لـ `JWT_SECRET` وبيانات PostgreSQL وRedis. لا تضع هذه القيم في Git. شغّل migrations أولًا عبر خدمة `migrate` في Compose، ثم شغّل الخدمات. راجع `backend/README.md` للتفاصيل.

لتشغيل الواجهة محليًا:

```bash
cd dashboard
npm ci
npm run dev
```

## التحقق

```bash
cd backend && pytest -q
cd ../dashboard && npm ci && npm run build && npm audit --audit-level=high
```

Docker غير متاح في بيئة التطوير الحالية، لذلك يجب اختبار `docker compose` في بيئة تحتوي Docker قبل النشر. ملف `.github/workflows/ci.yml` يشغّل الاختبارات والبناء وSemgrep وعمليات تدقيق الاعتماديات على GitHub Actions.

## Security hardening

For production set explicit HTTPS `ALLOWED_ORIGINS`, a strong `JWT_SECRET`, Mongo/Redis/Postgres credentials, and `ALLOW_PUBLIC_REGISTRATION=false`. Run `alembic upgrade head` before starting services. GitHub Pages requires the API origin in the build CSP and CORS allow-list. The backend image and Compose images still need registry-verified digest pinning before production deployment; no digest was invented.

## Security hardening

For production set explicit HTTPS `ALLOWED_ORIGINS`, a strong `JWT_SECRET`, Mongo/Redis/Postgres credentials, and `ALLOW_PUBLIC_REGISTRATION=false`. Run `alembic upgrade head` before starting services. GitHub Pages requires the API origin in the build CSP and CORS allow-list. Backend and Compose image digest pinning remains pending registry verification; no digest was invented.
