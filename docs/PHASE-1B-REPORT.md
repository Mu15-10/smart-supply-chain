# تقرير المرحلة 1-ب — إصلاح trusted proxy وrefresh family

## الحالة

أُغلقت الوحدة 1-ب-إصلاح تقنياً بناءً على مراجعة المدير. الوحدة لا تزال قبل أي تقسيم لـ`main.py`، ولم يبدأ 1-ج.

المراجعة صححت نتيجة الوحدة السابقة: التغيير في `e07a31d` لم يكن off-by-one سليماً؛ بل كان تغييراً خاطئاً أعاد ثغرة تزوير العنوان لأن الاختبار افترض أن عنوان الـproxy يظهر داخل XFF، وهو ليس النموذج المعتاد عندما يضيف الـproxy عنوان peer إلى نهاية القائمة.

## ما تم تنفيذه

### trusted proxy وX-Forwarded-For

- استبدال `TRUSTED_PROXY_COUNT` بـ`TRUSTED_PROXY_CIDRS`.
- وجود `TRUSTED_PROXY_COUNT` في البيئة أو مدخلات `Settings` يفشل الإقلاع برسالة واضحة.
- إذا كان socket peer خارج CIDRs الموثوقة، يتم تجاهل XFF بالكامل.
- يتم جمع كل أسطر XFF بالترتيب في قائمة واحدة.
- يتم اختيار أول عنوان غير موثوق من اليمين بعد تخطي عناوين الشبكات الموثوقة.
- يتوقف التحليل فور اختيار أول عنوان صالح غير موثوق؛ العناصر الواقعة يساره لا تُحلَّل ولا يُتحقق منها لأنها prefix يمكن للمهاجم التحكم به.
- تم وضع حد أقصى 64 عنصراً و8192 بايتاً للـXFF؛ التجاوز يعود إلى socket peer.
- العناوين غير الصالحة أو التي تحتوي ports أو tokens مثل `unknown` و`_hidden` تعود إلى socket peer.
- IPv4-mapped IPv6 تطبع كـIPv4.
- مفاتيح rate limit تستخدم IPv4 الكامل أو شبكة `/64` لعناوين IPv6.
- أضيفت `client_ip_fallback_total{reason}` مع الأسباب: `peer_not_trusted`, `no_xff`, `invalid_entry`, `too_many_entries`, `all_trusted`، مع عدم تسجيل العناوين الخام.
- أضيف endpoint metrics داخلي غير ظاهر في OpenAPI لقراءة العداد.
- production مع CIDRs فارغة يصدر تحذيراً واضحاً؛ ويظل قفل الأصل عبر الشبكة شرط Go-Live.

تم توثيق أساس القرار والمصادر في [ADR-001-trusted-proxy-cidrs.md](adr/ADR-001-trusted-proxy-cidrs.md)، بما في ذلك الاقتباس الحرفي الذي تمت قراءته من توثيق nginx الرسمي.

### logout وrefresh family

- logout يلغي كل refresh tokens في family الخاصة بالرمز المرسل، وليس الرمز الحالي فقط.
- deny-list الخاص بـaccess-token `jti` بقي موجوداً.
- logout برمز refresh غير معروف يعيد الاستجابة العامة نفسها ولا يكشف وجود الرمز.
- reuse عبر عدة أجيال يلغي بقية العائلة ويسجل حدث outbox باسم `security.refresh_token_reuse_detected` دون تسجيل token خام.

## الاختبارات

تم استبدال نموذج proxy غير الواقعي باختبارات تمثل proxy يضيف عنوان العميل إلى نهاية XFF، وتشمل:

- proxy واحد، مع prefix مزيف يرسله المهاجم.
- proxyان وثلاثة مع suffix موثوق.
- IPv4 وIPv6 وIPv4-mapped IPv6.
- كل أسطر XFF في طلب واحد وبترتيب wire order.
- values تالفة، ports، `unknown`، `_hidden`، المسافات، الفواصل، والسقف 64/8192.
- socket peer خارج CIDR، وsocket peer مفقود، وXFF فارغ، وسلسلة كلها trusted.
- تدوير prefix مزيف لا يتجاوز حدود login أو registration أو refresh.
- `garbage!!, <client-ip>, <proxy-ip>` يعيد `<client-ip>`؛ يثبت الاختبار أن prefix غير الصالح يسار العنوان المختار لا يُحلَّل.
- logout يلغي ثلاثة أجيال.
- reuse بعد ثلاثة أجيال يلغي العائلة ويسجل event.
- Redis fail-closed في production.

كل اختبار يحاكي سلوكاً خارجياً يضع تعليقاً يشرح النموذج. الأساس الخارجي المستخدم هو MDN وCloudflare وnginx كما هو موثق في ADR؛ لم تُفترض ranges لمنصة استضافة بعينها.

## الـcommits

| التغيير | commit | النتيجة |
|---|---|---|
| إصلاح CIDR parser وrate-limit normalization وrefresh family | `a188b78` | إزالة count، إضافة CIDR، السقف والتطبيع والmetric، وإلغاء family في logout وتسجيل reuse. |
| اختبارات الإصلاح ومراجعة نماذج الاختبار | `1f6f60e` | اختبارات XFF الواقعية، integration limits، logout family، reuse متعدد الأجيال، وتعليقات النمذجة. |
| تحسين CI | `6138068` | timeout وconcurrency وRedis health وpip-audit منفصل وSemgrep مستقل. |
| إصلاح حدود تحليل XFF وتدقيق ADR-001 | `f6ab425` | تجاهل prefix الواقع يسار العنوان المختار، اختبار `garbage!!`، ومعايير staging وتقييم port. |

## الأدلة المحلية الفعلية

تم التشغيل على PostgreSQL 16 وRedis الحقيقيين:

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
```

النتائج:

- `[test-bootstrap] database dialect: postgresql`.
- `pytest -s -q -rs`: **50 passed, 1 warning**.
- اختبارات 1-ب وPostgreSQL concurrency: **19 passed, 1 warning**.
- `ruff check backend`: **All checks passed**.
- `ruff format --check backend`: **18 files already formatted**.
- `mypy backend/app --ignore-missing-imports`: **Success: no issues found in 3 source files**.
- `git diff --check`: passed.
- Semgrep لم يكن مثبتاً محلياً؛ سيُتحقق منه في job CI مستقل باستخدام `--metrics=off`، ولا يُدّعى نجاحه محلياً.

## تغييرات CI

أضيفت:

- `timeout-minutes` لكل job.
- `concurrency` مع إلغاء التشغيل الأقدم لنفس المرجع.
- Redis health check صريح عبر `redis-cli ping`.
- job مستقل لـ`pip-audit`.
- job مستقل لـSemgrep مع `--metrics=off`.
- لم تتغير أي action SHA.

## ما لم يُتحقق منه بعد

- لم يُنفذ Semgrep محلياً لأن CLI غير مثبت؛ تم تشغيله بنجاح في job CI المستقل.
- لم تُختبر آلية origin lockdown من خارج شبكة النشر؛ هذا شرط المرحلة 9.
- لم يُتخذ قرار استضافة. قبل Render/Railway/أي منصة، يجب قراءة توثيقها الرسمي عن socket peer والheaders وتحديث ADR؛ إن لم يكن موثقاً يسجل كمخاطرة.
- لم يُنفذ ADR مستقل لتقييم `CF-Connecting-IP`؛ مؤجل إلى المرحلة 9 عند النشر خلف Cloudflare.
- لم تُنفذ load testing أو backup/restore أو managed PostgreSQL أو monitoring production.

## تحقق GitHub Actions

تم تشغيل workflow بعد دفع الإصلاح، وكانت النتيجة **success** على commit `f6ab425`:

- [Foundation CI #45259043452](https://github.com/Mu15-10/smart-supply-chain/actions/runs/45259043452)
- `backend`: **success** — PostgreSQL/Redis، pytest، Ruff، format، mypy، وmigration checks.
- `dependency-audit`: **success** — `pip-audit` في job مستقل.
- `semgrep`: **success** — Semgrep مع `--metrics=off`.
- `frontend`: **success**.
- `container`: **success**.
- `secrets`: **success** — gitleaks مع full history.
- التشغيل أظهر تنبيهاً غير حاجب عن إجبار بعض actions التي تستهدف Node.js 20 على Node.js 24؛ لم يفشل أي job بسبب ذلك.

## درس مستفاد

اختبار الأمان يجب أن يمثل سلوك العالم الحقيقي، لا الشكل الذي نتمنى أن تكون عليه البيانات. اختبار XFF السابق أدخل عنوان proxy داخل القائمة، بينما proxy الشائع يضيف عنوان peer إلى النهاية؛ لذلك بدا الإصلاح صحيحاً داخل الاختبار لكنه أعاد مساراً يسمح للمهاجم بتدوير prefix مزيف. منذ هذه الوحدة، كل اختبار proxy يحدد socket peer وسلوك الإضافة ومصدر الافتراض، وأي سلوك غير موثق يذكر كمخاطرة بدلاً من اعتباره حقيقة.

## المخاطر وقائمة Go-Live

- يجب قفل origin على مستوى الشبكة حتى لا يتصل به الإنترنت مباشرة مع XFF مزيف.
- يجب تزويد `TRUSTED_PROXY_CIDRS` من إعداد النشر وتحديثها من المصدر الرسمي للبنية التحتية.
- production مع CIDRs فارغة يحتاج قراراً تشغيلياً صريحاً قبل Go-Live.
- في staging يجب مراقبة `client_ip_fallback_total` والتأكد من أن معدله للطلبات المشروعة قريب من الصفر مع تنبيه عند الارتفاع.
- عند تقييم أي منصة استضافة يجب توثيق هل تضيف `port` داخل `X-Forwarded-For`؛ غياب التوثيق يسجل كمخاطرة.
- عند Cloudflare نحتاج ADR مستقلاً لتقييم `CF-Connecting-IP` والتحقق من Authenticated Origin Pulls أو Tunnel.
- logout family يغير سلوك الجلسات المقصود لصالح الإبطال الكامل؛ يجب مراجعة هذا في product acceptance.

## الخطوة التالية

بعد نجاح CI على commit `f6ab425` أُغلقت بوابة 1-ب-إصلاح. الوحدة التالية المقترحة هي 1-ج لعزل tenants والصلاحيات، لكنها لا تبدأ قبل موافقة المدير الكتابية التالية.
