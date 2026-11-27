# تدقيق Redis وIdempotency في المرحلة 1-ج

## نطاق التدقيق

تمت مراجعة كل مواضع إنشاء مفاتيح Redis في `backend/app/main.py`، وكل استعمالات `IdempotencyKey`، ثم أضيف اختبار PostgreSQL للقيد الفريد واختبار تزامني بين tenantين.

## جرد المفاتيح

| المفتاح | يتضمن `tenant_id`؟ | عام عن قصد؟ | المبرر والضوابط |
|---|---:|---:|---|
| `registration:<HMAC(value)>` | لا | نعم | التسجيل العام لا يملك tenant موثقاً بعد؛ المفتاح يقيّد المصدر بعد تطبيع client IP. القيمة لا تظهر في الاسم، وتستخدم HMAC بمفتاح JWT السري. |
| `login-fail:acct:<HMAC(email:ip)>` | لا | نعم | login يسبق اختيار tenant، والحساب email فريد عالمياً في النموذج الحالي؛ البريد والعنوان لا يظهران خاماً. |
| `login-fail:ip:<HMAC(ip)>` | لا | نعم | حد أمني على مصدر الشبكة قبل authentication، لذلك لا يمكن ربطه بـtenant بأمان. |
| `refresh:<HMAC(rate-limit-ip)>` | لا | نعم | refresh endpoint لا يعتمد على access token؛ الحد قبل معرفة tenant، ومقصوده حماية مصدر الشبكة. |
| `jwt-deny:<jti>` | لا | نعم | deny-list لرمز access محدد؛ `jti` عالمي وفريد، ولا يحتاج tenant لتجنب collision. JWT نفسه يثبت tenant قبل استخدام الموارد. |

لا توجد مفاتيح Redis أخرى ينشئها التطبيق. أي مفتاح عام مقصود في الجدول أعلاه هو control قبل authentication أو token-specific، وليس storage لمورد tenant.

## Idempotency

- `IdempotencyKey` يستخدم `tenant_id`, `route`, و`key` في كل lookup وinsert.
- migration `001_initial` تنشئ `uq_idem_tenant_route_key` على `(tenant_id, route, key)`.
- اختبار database inspector يتحقق من القيد على PostgreSQL، وليس من metadata ORM فقط.
- اختبار HTTP تزامني يستخدم نفس `Idempotency-Key` من tenantين مختلفين؛ النتيجة الفعلية: `201, 201`، لأن كل tenant يملك namespace مستقلاً.
- الاختبارات الموجودة سابقاً تغطي إعادة استخدام المفتاح داخل tenant مع body مختلف، وحالة processing/done.

## أدلة التشغيل

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
[test-bootstrap] database dialect: postgresql

tests/test_phase1c_isolation.py: 5 passed, 1 warning
```

التحذير الوحيد من `passlib` و`crypt` كما في التقارير السابقة.

## حدود التدقيق

- rate-limit keys قبل authentication ليست tenant-scoped بطبيعتها؛ تحويلها إلى tenant-scoped سيجعل الحماية قابلة للتجاوز قبل وجود tenant موثوق، لذلك بقيت عامة ومبررة.
- `jwt-deny` لا يستخدم tenant في الاسم لأن `jti` عشوائي وفريد، ولأن access-token deny-list ليست cache لمورد tenant.
- لا توجد حالياً مفاتيح Redis لتخزين موارد أو نتائج idempotency؛ نتائج idempotency في PostgreSQL.
- يلزم عند إضافة worker أو cache جديد تحديث هذا الجرد قبل قبوله.
