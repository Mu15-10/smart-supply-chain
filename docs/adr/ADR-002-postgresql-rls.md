# ADR-002: تقييم PostgreSQL Row-Level Security للعزل متعدد العملاء

## الحالة

`proposed — prototype completed; no production adoption`

لم يُفعّل RLS على جداول التطبيق الحالية. هذا القرار يحتاج موافقة منفصلة قبل أي migration إنتاجية.

## السياق

العزل الحالي يطبق `tenant_id` predicates في handlers، وتوجد اختبارات عزل وBOLA وmutation audit. RLS قد يوفر defense-in-depth، لكنه يضيف عقداً مع connection pooling وtransaction context، ويحتاج دور تطبيق غير مالك ولا يملك `BYPASSRLS` مع `FORCE ROW LEVEL SECURITY`.

## Prototype المنفذ

السكربت القابل لإعادة التشغيل هو `scripts/rls_prototype.sql`، ونُفذ على PostgreSQL المحلي `supply_ci` بتاريخ التقرير:

- جدولان فقط: `rls_probe.suppliers_probe` و`rls_probe.inventory_probe`.
- 10,000 صف لكل جدول، موزعة بالتساوي بين `tenant-a` و`tenant-b`.
- index على `tenant_id` في الجدولين.
- `supply_rls_owner` يملك الجداول.
- `supply_rls_app` هو دور `NOSUPERUSER NOBYPASSRLS` غير مالك.
- `FORCE ROW LEVEL SECURITY` مفعّل على الجدولين.
- policy تستخدم `current_setting('app.tenant_id', true)`.
- كل قراءة اختبارية تستخدم `BEGIN; SET LOCAL app.tenant_id = ...; ... COMMIT;` لتفادي تسريب tenant context إلى connection لاحقة في pool.
- بعد القياس حُذف schema والأدوار التجريبية؛ لم يتغير schema التطبيق.

## النتيجة الأمنية

الناتج الفعلي:

```text
SET LOCAL app.tenant_id = 'tenant-a' -> suppliers_visible=5000, inventory_visible=5000
SET LOCAL app.tenant_id = 'tenant-b' -> suppliers_visible=5000, inventory_visible=5000
supply_rls_app: NOSUPERUSER, NOBYPASSRLS
```

الدور غير المالك لم يستطع تجاوز policy، ولم تظهر صفوف tenant الآخر.

## قياس أولي للأداء

استخدم `EXPLAIN (ANALYZE, BUFFERS)` على نفس البيانات والفهارس في تشغيل واحد. الأرقام التالية هي `Execution Time` الظاهرة في التشغيل الفعلي وليست benchmark نهائياً:

| الجدول | قبل RLS: explicit tenant predicate | بعد RLS: policy predicate | Buffers بعد RLS |
|---|---:|---:|---:|
| suppliers_probe | 3.067 ms | 2.346 ms | shared hit=80 |
| inventory_probe | 3.375 ms | 2.316 ms | shared hit=70 |

الأرقام لا تثبت تفوق RLS؛ cache state وحجم البيانات والتشغيل المفرد يمنعان استنتاج نسبة ثابتة. لا بد من benchmark متكرر تحت حمل staging قبل قرار الإنتاج.

## أثر pooling

`SET LOCAL` صالح داخل transaction فقط، وهو مطلوب مع pool حتى لا يرث connection التالية tenant سابقاً. أي repository أو middleware ينسى transaction boundary قد يسبب فشلاً مغلقاً أو سياقاً خاطئاً. لذلك adoption يحتاج:

1. helper واحد يفتح transaction ويضبط `SET LOCAL` parameterized.
2. اختبار يثبت reset عبر إعادة استخدام connection.
3. منع `SET` session-level في كود التطبيق.
4. مراقبة أخطاء missing tenant context؛ policy يجب أن تعيد صفر صفوف أو تفشل، لا أن تستخدم tenant افتراضياً.

## القرار المؤقت

**رفض التفعيل الشامل الآن، مع اعتماد RLS كـdefense-in-depth مرشح للمرحلة التالية بعد prototype إضافي.**

التعويض الحالي:

- policy dependency مركزية fail-closed على مستوى route/method/role/tenant claim.
- tenant predicates في queries الحالية.
- اختبارات cross-tenant lists وnested BOLA و404 uniform.
- mutation audit يزيل كل predicate معروفاً واحداً واحداً ويثبت فشل اختبار عزل على كل mutation.
- PostgreSQL unique constraint على `(tenant_id, route, key)` لـidempotency.

قبل إعادة طرح adoption، يجب تنفيذ benchmark متعدد الجولات، اختبار pooling حقيقي عبر SQLAlchemy pool، سياسات write (`WITH CHECK`)، migrations قابلة للرجوع، ومراجعة أثر RLS على workers وadmin tooling.
