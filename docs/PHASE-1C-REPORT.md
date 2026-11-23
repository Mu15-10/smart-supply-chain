# تقرير المرحلة 1-ج — الوحدة الأولى: policy contracts وعزل tenants

## الحالة

أُغلقت هذه الوحدة التنفيذية محلياً فقط. لم تُغلق المرحلة 1-ج كاملة، ولم يُرفع commit جديد إلى GitHub بعد هذه الوحدة. لا يبدأ تقسيم `main.py` في هذه المرحلة.

## ما تم تنفيذه

### 1. جدول سياسات مركزي

أُضيف `backend/app/core/policy.py` ويحتوي على:

- `RoutePolicy` ثابتة لتوثيق methods والأدوار واشتراط tenant ونوع الوصول.
- `ROUTE_POLICY_TABLE` للـroutes المسجلة حالياً.
- `PUBLIC_ROUTE_WHITELIST` بقائمة صريحة تشمل `/health` ومسارات readiness/live، و`/metrics` كمدخل محجوز صريح غير مسجل في FastAPI، إضافة إلى مسارات التوثيق العامة والمسارات العامة للمصادقة.
- اختبار يمر على كل `APIRoute` مسجل ويتحقق من وجود policy متطابقة وعدم وجود route عام خارج القائمة.

### 2. منع mass assignment

أصبحت نماذج الإدخال ترث `StrictInputModel` ذي `ConfigDict(extra="forbid")`. أضيفت حالات اختبار تقدم حقولاً مملوكة للخادم مثل `tenant_id` و`roles` و`status` و`id`، وتتوقع `ValidationError` بدلاً من تجاهل الحقول أو تمريرها.

### 3. عزل tenants وBOLA

أضيفت `backend/tests/test_phase1c_isolation.py` وتثبت على PostgreSQL:

- قوائم suppliers/products/warehouses/purchase-orders لا تُظهر موارد tenant آخر.
- محاولة تعديل inventory باستخدام warehouse/product من tenant آخر تعيد 404.
- محاولة إنشاء Purchase Order بعناصر nested مملوكة لـtenant آخر تعيد 404.
- tenant آخر لا يستطيع تنفيذ transition على Purchase Order لا يملكه، وتكون النتيجة 404.
- نفس `Idempotency-Key` لا يتداخل بين tenantين مختلفين على inventory adjustment.

كل اختبار يوضح في تعليق السلوك الخارجي الذي ينمذجه. اختبارات BOLA صممت لتفشل على كود لا يطبق tenant ownership predicate، ولا تعدّل الاختبارات لتناسب نتيجة التطبيق.

## الـcommits

| التغيير | commit | النتيجة |
|---|---|---|
| policy contracts وStrictInputModel واختبارات policy/mass assignment | `193bb9f` | جدول سياسات مركزي واختبارات تغطية ورفض الحقول الإضافية. |
| اختبارات tenant isolation وnested BOLA وidempotency isolation | `4915c48` | اختبارات عزل مستقلة، محفوظة في commit مستقل. |

تم التحقق من النوعين عبر `git cat-file -t`: النتيجة `commit`.

## الأدلة الفعلية

بيئة التشغيل:

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
[test-bootstrap] database dialect: postgresql
```

النتائج:

- `pytest -s -q tests/test_phase1c_isolation.py`: **3 passed, 1 warning**.
- `pytest -s -q -rs`: **69 passed, 1 warning**.
- `ruff check .`: **All checks passed**.
- `ruff format --check .`: **21 files already formatted**.
- `mypy app --ignore-missing-imports`: **Success: no issues found in 4 source files**.

التحذير الوحيد هو `DeprecationWarning` من اعتماد `passlib` على وحدة `crypt`، وليس فشلاً في الاختبارات.

## ما لم يُنفذ بعد

- لم تُستكمل مصفوفة 100% لكل route مع مقارنة آلية بين routes FastAPI وpolicy metadata، بما في ذلك أي حالات method/path إضافية تظهر أثناء التوسع.
- لم يُنفذ تدقيق كامل لمفاتيح Redis/idempotency في كل endpoints للتأكد من وجود `tenant_id` وعدم وجود key collision خارج الحالات المختبرة.
- لم يُتخذ قرار PostgreSQL RLS ولم يُكتب ADR الخاص به.
- لم يُفصل `main.py` إلى modules.
- لم يُشغّل CI على GitHub لهذه commits ولم تُثبت نتيجة remote بعد.
- لم تُنفذ load test أو backup/restore أو monitoring production.

## المخاطر

- جدول policy الحالي هو metadata contract واختبار inventory، وليس بعد middleware مركزي يفرض كل policy تلقائياً؛ enforcement ما زال موزعاً في handlers الحالية.
- اختبار idempotency الحالي يغطي endpoint inventory adjustment فقط؛ يلزم تدقيق باقي المسارات قبل اعتبار العزل شاملاً.
- الاعتماد على 404 في BOLA يحافظ على عدم كشف وجود المورد، لكن يلزم مراجعة response shapes الحالية عند توسيع التغطية.

## بوابة الإغلاق التالية

لا تُعتبر 1-ج مكتملة قبل:

1. إكمال route matrix لكل المسارات والـmethods المسجلة.
2. تدقيق tenant-specific Redis keys وidempotency في كامل التطبيق.
3. قرار موثق لـPostgreSQL RLS مع حدود تطبيقه وعدم كسر API الحالي.
4. تشغيل الاختبارات والفحوصات نفسها في CI أخضر على PostgreSQL/Redis.
5. تقرير قبول مستقل يحدد ما تم التحقق منه وما بقي مفتوحاً.
