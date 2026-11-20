Historical document: retained for audit context; current status is maintained in docs/ and PROGRESS.md.
# تقرير تنفيذ إصلاحات مدار الإمداد

## ما تم تنفيذه

### Backend

- إضافة تحقق RBAC مركزي عبر `require_roles`.
- منع التسجيل داخل Tenant قائم؛ التسجيل العام ينشئ Tenant جديدًا فقط.
- تطبيع البريد الإلكتروني أثناء التسجيل والدخول.
- إضافة `issuer` و`audience` وclaims مطلوبة إلى JWT والتحقق منها.
- منع تشغيل التطبيق خارج التطوير عند غياب `JWT_SECRET` أو قصره عن 32 حرفًا.
- تقييد supplier وwarehouse وproduct بعزل `tenant_id` عند إنشاء Purchase Order.
- تقييد product وwarehouse بعزل tenant عند تعديل المخزون.
- رفض أنواع حركة المخزون غير المسموحة عبر `Literal`.
- إضافة حماية تزامن داخل العملية حول idempotency والعمليات الحرجة.
- إضافة اختبارات تمنع عودة مشاكل التسجيل والعزل والتحقق.

### Docker والتشغيل

- ربط منافذ PostgreSQL وMongoDB وRedis على `127.0.0.1` بدل نشرها على جميع الواجهات.
- استبدال `dev-secret` بمفتاح تطوير طويل وواضح أنه محلي فقط.
- تشغيل صورة Backend بمستخدم غير root.
- إضافة Docker healthcheck.
- تحديث `.env.example` وREADME بتعليمات التشغيل الآمن.

### Frontend

- تسجيل حركة المخزون أصبح يعدل الرصيد محليًا بدل عرض نجاح زائف.
- إضافة تحقق للكمية وعدد البنود والإجمالي.
- تفعيل تبويبات أوامر الشراء فعليًا مع `aria-selected`.
- إضافة accessible names لحقول البحث والأزرار الأيقونية.
- تحسين Modal باستخدام `role="dialog"` و`aria-modal` و`aria-labelledby` ونقل التركيز لأول عنصر.
- تثبيت إصدارات npm بدل `latest`.
- إضافة `src/api.js` ووضع Live اختياري عبر `VITE_API_MODE=live` و`madar_access_token`، مع بقاء Demo هو الوضع الافتراضي الآمن.

## التحقق

- `pytest -q`: **3 passed**.
- `npm run build`: **نجاح**.
- `npm audit`: **0 vulnerabilities** في الفحص السابق، وnpm install الحالي نجح.
- Semgrep 1.186.0: **0 findings** من 226 قاعدة Community.
- `python -m compileall`: نجاح.
- Compose YAML: تم تحميله بنجاح، والخدمات السبع موجودة.
- `git diff --check`: بلا أخطاء whitespace.

## القيود المتبقية بوضوح

- التسجيل داخل Tenant قائم يحتاج Invitation Service دائمًا؛ المنع الحالي هو السلوك الآمن المؤقت.
- idempotency أصبحت محمية داخل العملية، لكنها تحتاج claim ذري دائم في PostgreSQL أو Redis `SET NX` مضبوطًا للتشغيل متعدد النسخ.
- ما زالت migrations versioned وAlembic وPostgreSQL RLS وOIDC/2FA وpublisher فعلي للأحداث خارج نطاق هذا الإصلاح.
- وضع Live في الواجهة يحتاج شاشة دخول أو آلية إدارة token؛ لم يتم تخزين أي credentials داخل الواجهة.
- لم يتم تشغيل Docker فعليًا لأن Docker CLI غير متاح في بيئة التنفيذ الحالية.
