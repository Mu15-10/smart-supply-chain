# تقرير المرحلة 1-ب — مراجعة refresh/logout وproxy وRedis

## الحالة

بدأت الوحدة 1-ب بعد موافقة المستخدم الكتابية. ركزت هذه الوحدة على مراجعة أمنية محدودة قبل أي تقسيم لـ`main.py`، مع الحفاظ على أشكال استجابات API الحالية.

## نطاق المراجعة

- refresh-token rotation وreuse detection.
- logout وإبطال access/refresh tokens.
- rate limiting الخاص بـrefresh.
- fail-closed behavior عند تعطل Redis في production.
- استخراج عنوان العميل مع `TRUSTED_PROXY_COUNT` و`X-Forwarded-For`.
- CORS وsecurity headers ذات الصلة.
- تزامن refresh لنفس الرمز على PostgreSQL.

## ما اكتُشف وأُصلح

### 1. refresh limiter كان يستخدم IP صريحاً وحدوداً hard-coded

كان مفتاح Redis هو `refresh:{ip}` وكانت القيم `30` و`60` مكتوبة داخل endpoint. تم تغييره إلى `limiter_key("refresh", ip)`، الذي يستخدم HMAC، مع قراءة `refresh_max_per_ip` و`refresh_window_seconds` من `Settings`.

الفائدة: عدم تسريب عنوان IP في مفتاح Redis، وتوحيد الإعدادات القابلة للضبط مع بقية rate limits.

### 2. خطأ off-by-one في trusted proxy parsing

كان التطبيق يختار عنوان proxy بدلاً من أول عنوان غير موثوق في بعض سلاسل `X-Forwarded-For`. تم تصحيح الحساب ليختار العنوان الصحيح وفق عدد الـproxies الموثوقة، مع fallback إلى عنوان اتصال العميل عند غياب قيمة صالحة.

الفائدة: منع بناء rate limits وقرارات التدقيق على عنوان proxy بدلاً من عنوان العميل الحقيقي.

### 3. اختبارات fail-closed

أضيفت اختبارات تثبت أن Redis عند تعطلِه في production يسبب `503 AUTH_TEMPORARILY_UNAVAILABLE` بدلاً من السماح بتجاوز ضوابط المصادقة أو rate limiting.

## التغييرات والـcommits

| التغيير | commit | النتيجة |
|---|---|---|
| اختبارات characterization للأمان والتزامن | `c3e0df6` | اختبارات refresh limits، proxy parsing، CORS، logout، وتزامن refresh على PostgreSQL. |
| إصلاح refresh limits وtrusted proxy parsing | `e07a31d` | إزالة IP الصريح والحدود hard-coded وتصحيح اختيار عنوان العميل. |
| اختبارات Redis fail-closed | `c46b7d8` | تغطية صريحة لفشل Redis في production. |

## الأدلة الفعلية

تم التشغيل باستخدام:

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
```

والنتائج:

- `pytest -s -q -rs`: **40 passed, 1 warning**.
- ظهر في بداية التشغيل: `[test-bootstrap] database dialect: postgresql`.
- اختبارات التزامن وحدها: **4 passed, 1 warning**.
- اختبارات 1-ب الأمنية وحدها: **7 passed, 1 warning**.
- `ruff check backend`: **All checks passed**.
- `ruff format --check backend`: **18 files already formatted**.
- `mypy backend/app --ignore-missing-imports`: **Success: no issues found in 3 source files**.
- `git diff --check`: passed.

## تحقق GitHub Actions

تم تشغيل CI بعد دفع commits الوحدة، وكانت النتيجة **success**:

- التشغيل: [Foundation CI #45200819973](https://github.com/Mu15-10/smart-supply-chain/actions/runs/45200819973)
- commit: `382b2c5`.
- `backend`: **success**.
- `frontend`: **success**.
- `container`: **success**.
- `secrets`/gitleaks: **success**.

## ما لم يُنفذ

- لم يبدأ تقسيم `main.py` إلى modules.
- لم تُنفذ مراجعة Semgrep مستقلة.
- لم تُنفذ load testing أو backup/restore أو production managed database.
- لم تُجرَ مراجعة قانونية أو إعداد monitoring production.

## المخاطر المفتوحة

- logout يبطل refresh token المرسل فقط، بينما إبطال كل family/session عند logout قرار تشغيلي وأمني يحتاج موافقة قبل تغييره لأنه قد يغير سلوك المستخدمين.
- semantics الخاصة بإبطال family بعد reuse تحتاج اختباراً أوسع عبر عدة أجيال من rotation.
- `X-Forwarded-For` يظل معتمداً على صحة إعداد `TRUSTED_PROXY_COUNT` في topology الإنتاج؛ القيمة الخاطئة قد تؤثر في rate limiting والتدقيق.
- سياسة CORS الإنتاجية تعتمد على قائمة origins صريحة، ويجب مراجعة القائمة الفعلية قبل Go-Live.

## قرار الوحدة التالية

بعد دفع هذه الوحدة والتحقق من CI، الوحدة التالية المقترحة هي **1-ج**: مراجعة عزل المستأجرين والصلاحيات على جميع مسارات CRUD، مع اختبارات تمنع cross-tenant access وتثبت أن أي استخراج لاحق من `main.py` لا يغير حدود العزل.

لا يبدأ تقسيم `main.py` إلا بعد إغلاق مراجعات المرحلة 1 وموافقة المستخدم الكتابية على ترتيب الاستخراج.
