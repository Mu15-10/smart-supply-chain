
## الوحدة الثانية — enforcement والمصفوفات والتدقيق

### policy enforcement كمصدر حقيقة مفروض

- `FastAPI` أصبح يركب dependency مركزية واحدة باسم `enforce_route_policy`.
- dependency تستخرج path template وHTTP method من `request.scope["route"]`، ثم تقرأ `RoutePolicy` من `ROUTE_POLICY_TABLE`.
- المسار العام يمر فقط إذا كان موجوداً في `PUBLIC_ROUTE_WHITELIST` عبر policy الجدول.
- المسار المحمي يتطلب claims فيها `tenant_id`، ويفرض الأدوار المعلنة. الدور `authenticated` يعني أي token مصادق عليه، بينما الأدوار التشغيلية تطابق intersection صريحاً.
- `validate_route_policy_table(app.routes)` يفشل الإقلاع إذا وجد route بلا policy أو method غير مغطى.
- أزيلت فحوص `require_roles(...)` الموزعة من handlers؛ handlers المحمية تستخدم `auth`، والـdependency المركزية هي مصدر قرار الدور.

### المصفوفات المولّدة

- مصفوفة authorization تُبنى من `app.routes`، وتدور آلياً على الأدوار `admin/purchasing/inventory/viewer` وحالتي owner/other-tenant. القرار 403 مشتق من policy؛ أما 404 للموارد التابعة فيثبت عبر اختبارات BOLA HTTP المنفصلة.
- HTTP mass-assignment matrix تستخرج body routes من `app.routes` وتضيف كل حقل server-owned (`tenant_id`, `roles`, `status`, `id`, `is_active`, `version`) إلى الحالات. النتيجة الفعلية: **66 حالة passed** وكلها 422.
- اختبارات BOLA تغطي كل معرّف nested منفرداً في inventory وPurchase Orders، مع supplier/product/warehouse مختلطين، وتثبت 404 موحداً وعدم وجود المعرف في body أو headers.
- أُصلح الرد `PRODUCT_NOT_FOUND` إلى `RESOURCE_NOT_FOUND` بعد أن كشف اختبار BOLA أن الرد لم يكن موحداً.

### إثبات mutation

شُغّل `scripts/mutation_tenant_queries.py` على PostgreSQL. السكربت يزيل tenant predicate واحداً في كل مرة، يشغل `tests/test_phase1c_isolation.py`، ثم يعيد الملف إلى حالته الأصلية في `finally`.

| الاستعلام/الموضع | هل فشل اختبار؟ |
|---|---|
| supplier list tenant predicate | نعم — `FAIL_DETECTED` |
| product list tenant predicate | نعم — `FAIL_DETECTED` |
| warehouse list tenant predicate | نعم — `FAIL_DETECTED` |
| purchase-order list tenant predicate | نعم — `FAIL_DETECTED` |
| inventory adjust product predicate | نعم — `FAIL_DETECTED` |
| inventory adjust warehouse predicate | نعم — `FAIL_DETECTED` |
| purchase-order supplier predicate | نعم — `FAIL_DETECTED` |
| purchase-order warehouse predicate | نعم — `FAIL_DETECTED` |
| purchase-order transition predicate | نعم — `FAIL_DETECTED` |

النتيجة: **9/9 mutations detected**. ظهرت فجوتان أثناء التدقيق، ثم أضيفت حالات mixed-ownership التي جعلت كل mutation يفشل اختباراً واحداً على الأقل.

### Redis وIdempotency

الجرد الكامل موثق في [REDIS-TENANT-AUDIT.md](REDIS-TENANT-AUDIT.md). المفاتيح قبل authentication أو الخاصة بـ`jti` معلّمة صراحة كعامة مقصودة؛ لا توجد Redis caches لموارد tenant. `IdempotencyKey` يستخدم `(tenant_id, route, key)` في ORM والاستعلامات، وPostgreSQL inspector أثبت `uq_idem_tenant_route_key`. اختبار تزامني لنفس المفتاح من tenantين أعاد `201, 201`.

### ADR-002 وRLS prototype

- [ADR-002-postgresql-rls.md](adr/ADR-002-postgresql-rls.md) يقترح **رفض التفعيل الشامل حالياً** مع إبقاء RLS مرشحاً لـdefense-in-depth.
- `scripts/rls_prototype.sql` شُغّل فعلياً على جدولين تجريبيين، 10,000 صف لكل جدول، دور `NOSUPERUSER NOBYPASSRLS` غير مالك، `FORCE RLS`، و`SET LOCAL` داخل transaction.
- `tenant-a` و`tenant-b` رأى كل منهما 5000 صف فقط في كل جدول.
- قياس EXPLAIN ANALYZE في تشغيل واحد لم يثبت overhead سلبياً؛ الفرق لا يكفي لقرار أداء نهائي، ويحتاج benchmark متكرر تحت staging load.
- لم يُطبق RLS على جداول التطبيق ولم تُضف migration إنتاجية.

## أدلة التحقق المحدثة

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
[test-bootstrap] database dialect: postgresql
```

- `pytest -s -q -rs`: **150 passed, 1 warning**.
- `tests/test_phase1c_isolation.py`: **5 passed, 1 warning**.
- HTTP mass-assignment matrix: **66 passed, 1 warning**.
- `ruff check .`: **All checks passed**.
- `ruff format --check .`: **23 files already formatted**.
- `mypy app --ignore-missing-imports`: **Success: no issues found in 4 source files**.
- mutation audit: **9/9 FAIL_DETECTED**.
- RLS prototype: نجح تشغيل PostgreSQL الفعلي، ثم حُذف schema والأدوار التجريبية.

## Commits الجديدة

| التغيير | commit | النتيجة |
|---|---|---|
| central policy enforcement | `00a110d` | dependency مركزية، fail-closed route validation، وإزالة role checks المكررة. |
| BOLA/mixed ownership وresponse موحد | `cd7b41e` | 404 موحد واختبارات nested identifiers والتزامن. |
| authorization وmass-assignment matrices | `b63a21d` | مصفوفات مولّدة من routes، 66 حالة HTTP. |
| Redis audit وRLS prototype وmutation tool | `ca30cb6` | جرد المفاتيح، ADR-002، و9/9 mutation detection. |

## الحالة والبوابة

الوحدة الثانية جاهزة للمراجعة المحلية والبعيدة، وليست مقبولة نهائياً من المدير بعد. commits `00a110d` و`cd7b41e` و`b63a21d` و`ca30cb6` و`8c7f7c7` رُفعت إلى `hardening/phase-0`. لا يبدأ 1-د قبل الموافقة الكتابية.

## CI البعيد

- [Foundation CI #46024088025](https://github.com/Mu15-10/smart-supply-chain/actions/runs/46024088025) على SHA `8c7f7c797ba74b43710417bf8e23578c457fd05d`: **success**.
- `backend`: success — PostgreSQL/Redis، pytest، Ruff، format، mypy، وAlembic round-trip/check.
- `semgrep`: success — `semgrep==1.186.0` مع `p/python` و`p/security-audit`.
- `frontend`, `container`, `dependency-audit`, و`secrets`: success.
- ظهرت annotations غير حاجبة من GitHub حول إجبار بعض actions التي تستهدف Node.js 20 على Node.js 24؛ لم يفشل أي job بسببها.

## مخاطر مفتوحة

- matrix الحالية مشتقة من routes الموجودة حالياً؛ routes جديدة ستفشل `validate_route_policy_table` لكنها تحتاج أيضاً payload/BOLA contract في الاختبارات.
- resource ownership لا يمكن حسمه من route dependency وحدها؛ لذلك يبقى query predicate وBOLA HTTP اختباراً إلزامياً.
- مفاتيح rate-limit العامة قبل authentication مقصودة، لكن إضافة أي Redis cache جديدة تتطلب تحديث الجرد.
- RLS prototype ليس benchmark production وليس تفويضاً لتطبيق RLS على schema الحالي.
- warning `passlib/crypt` غير حاجب لكنه يحتاج خطة hashing في 1-د.
