# تقرير المرحلة 1-أ — مراجعة الأساس الأمني واختبارات السلوك

## الحالة

بدأت المرحلة 1 بموافقة المستخدم الكتابية. هذه الوحدة هي **1-أ** فقط: مراجعة أولية للأساس المستورد من
`origin/security/hardening`، وإنشاء characterization tests قبل أي تقسيم لـ`main.py`.
لم يبدأ استخراج modules، ولم تتغير response shapes عمداً.

## نطاق المراجعة

تمت مراجعة commits الأساس الأمني التالية:

- `9c9bd3d` — authentication/registration hardening، CORS، security headers، common passwords، وlogin limiting.
- `46b1faa` — refresh-token rotation وlogout/reuse detection مع migration `002_refresh_tokens`.
- `6561b5b` — Dependabot، Mongo authentication/configuration، ووثائق متطلبات النشر.

المراجعة في 1-أ هي baseline/characterization review وليست اعتماداً نهائياً لكل قرار أمني. المراجعة التفصيلية
لـ refresh-family semantics، fail-closed behavior، Mongo/outbox، proxy trust، وCORS production policy ما زالت
ضمن وحدات لاحقة من المرحلة 1.

## التغييرات

| التغيير | commit | النتيجة |
|---|---|---|
| إصلاح انتقال حالة أمر الشراء | `40f7d36` | كان الكود يعيّن قاموس الانتقالات كاملاً إلى `po.status`، ما يفشل على PostgreSQL. أصبح يعيّن الحالة المستهدفة الصحيحة. |
| إصلاح status code لإنشاء الدعوة | `40f7d36` | المسار معلن `201` لكنه كان يعيد `200` بسبب Response مخصص؛ أصبح يعيد `201` صراحةً. |
| characterization tests للمسارات الحالية | `fd420ac` | أضيفت اختبارات المصادقة، refresh/logout، invitations، role boundaries، CRUD/list، inventory، purchase-order transitions، idempotency، والـ health/security headers. |
| إصلاح فحص gitleaks في CI | `fbac3f6` | أضيف `fetch-depth: 0` إلى checkout الخاص بـ`secrets` حتى يتوفر نطاق Git الكامل؛ لا يوجد leak جديد. |

## الأدلة الفعلية

- characterization tests على PostgreSQL وRedis الحقيقيين: **19 passed, 1 warning**.
- suite backend كاملة بعد تغييرات 1-أ: **32 passed, 1 warning**.
- `ruff check backend`: **All checks passed**.
- `ruff format --check backend`: **17 files already formatted**.
- `mypy backend/app --ignore-missing-imports`: **Success: no issues found in 3 source files**.
- ظهر صراحةً أثناء التشغيل: `[test-bootstrap] database dialect: postgresql`.
- `git diff --check`: passed.

## تحقق GitHub Actions

تم تشغيل workflow المنشور بعد إصلاح shallow checkout، والنتيجة **success**:

- التشغيل: [Foundation CI #45196301267](https://github.com/Mu15-10/smart-supply-chain/actions/runs/45196301267)
- commit الذي شُغّل عليه: `fbac3f6` (`ci: fetch full history for gitleaks`)
- `secrets`/gitleaks: **passed**؛ فحص كامل للتاريخ ولم يسجل أسراراً.
- `backend`: **passed**؛ PostgreSQL 16 وRedis 7، ruff، format، mypy، pytest، pip-audit، وmigration round-trip/check.
- `frontend`: **passed**؛ npm audit وbuild.
- `container`: **passed**؛ Docker build وTrivy.
- ظهرت تحذيرات GitHub غير مانعة عن Node.js 20 في بعض actions؛ لم تفشل أي بوابة.

## ما لم يُنفذ

- لم يبدأ تقسيم `main.py` إلى modules.
- لم تُنفذ مراجعة Semgrep.
- لم تُتخذ قرارات جديدة حول حذف MongoDB أو تغيير response/API contracts.
- لم تُنفذ اختبارات load أو backup/restore أو production managed database.
- لم يُشغّل CI على commit التقرير الحالي نفسه؛ التشغيل الأخضر الموثق أعلاه كان على commit `fbac3f6`، بينما commit التقرير لا يغيّر كود التطبيق.

## المخاطر المفتوحة

- refresh-token family rotation يحتاج مراجعة أمنية تفصيلية، خصوصاً السباقات، reuse detection، والإبطال الكامل للعائلة.
- سلوك Redis عند انقطاع الخدمة يحتاج تثبيتاً باختبارات production configuration إضافية.
- سياسة trusted proxies و`X-Forwarded-For` تحتاج characterization مستقل حسب topology الإنتاج.
- Mongo transactional outbox fallback يحتاج قراراً تشغيلياً واضحاً قبل Go-Live.
- `main.py` ما زال ملفاً واحداً كبيراً، لكن أي استخراج مؤجل حتى اكتمال characterization والموافقة على الوحدة التالية.

## القرار التالي

الوحدة التالية المقترحة هي **1-ب**: مراجعة أمنية مركزة لـ refresh rotation/logout وproxy/CORS/headers مع اختبارات
fail-closed وconcurrency إضافية. لا يبدأ استخراج أي module إلا بعد إغلاق مراجعة 1-ب وموافقة المستخدم كتابةً.
