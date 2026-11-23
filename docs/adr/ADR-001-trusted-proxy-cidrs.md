# ADR-001: اختيار عنوان العميل خلف trusted proxies

- **الحالة:** معتمد مع تعديلات إلزامية — التنفيذ جارٍ في إصلاح 1-ب
- **النطاق:** إصلاح الوحدة 1-ب فقط
- **المشكلة:** التغيير في `e07a31d` استخدم `len(values) - TRUSTED_PROXY_COUNT - 1`، مع اختبار يفترض أن عنوان الـproxy يظهر داخل XFF. هذا النموذج لا يمثل proxy شائعاً يضيف عنوان الاتصال به إلى نهاية XFF، وأعاد إمكانية تزوير العنوان المستخدم في rate limiting وaudit logs.

## الأدلة الخارجية التي تمت مراجعتها

- توضح MDN أن عناوين XFF تُرتب بحيث يكون العنوان الأيمن هو أحدث proxy، وأن استخدام XFF في rate limiting أو access control يجب أن يعتمد فقط على العناوين التي أضافتها trusted proxy. كما توثق طريقتين لاختيار العنوان الموثوق: trusted proxy count وtrusted proxy list. [1]
- توثق nginx أن `$proxy_add_x_forwarded_for` يضيف `$remote_addr` إلى نهاية XFF، أو يساوي `$remote_addr` إذا لم يكن header موجوداً. [2]
- توثق Cloudflare أن XFF يبدأ بعنوان الزائر عندما لا يكون موجوداً، وأن Cloudflare يضيف عنوان الـHTTP proxy المتصل به إلى نهاية القيمة عند وجود proxies سابقة. [3]

هذه المصادر تثبت ترتيب الإضافة ومبدأ الثقة، لكنها لا تثبت ranges الخاصة بالبنية التحتية لهذا المشروع. يجب أن تأتي `TRUSTED_PROXY_CIDRS` من إعدادات النشر الفعلية، لا من قيمة مخمّنة في التطبيق.

النص الحرفي الذي تمت قراءته من توثيق nginx الرسمي هو: “the `X-Forwarded-For` client request header field with the `$remote_addr` variable appended to it, separated by a comma. If the `X-Forwarded-For` field is not present in the client request header, the `$proxy_add_x_forwarded_for` variable is equal to the `$remote_addr` variable.” [2]

## القرار المقترح

اعتماد `TRUSTED_PROXY_CIDRS` كآلية الثقة الأساسية، والاستغناء عن `TRUSTED_PROXY_COUNT` في منطق التطبيق بعد موافقة المدير.

الخوارزمية المقترحة:

1. إذا كانت قائمة `TRUSTED_PROXY_CIDRS` فارغة، تجاهل XFF تماماً واستخدم `request.client.host`. في production يصدر التطبيق تحذيراً واضحاً، وتبقى تهيئة CIDR بنداً إلزامياً في Go-Live.
2. تحقق من أن `request.client.host` — أي socket peer — يقع داخل إحدى شبكات `TRUSTED_PROXY_CIDRS`. إذا لم يقع، تجاهل XFF واستخدم socket peer.
3. اجمع كل أسطر XFF بالترتيب الذي وصلت به، ثم اضممها بفواصل إلى قائمة واحدة قبل التحليل.
4. ارفض header إذا تجاوز طولاً أقصى محدداً أو تجاوز 64 عنصراً، وسجّل fallback بسبب `too_many_entries` دون تسجيل العناوين الخام.
5. طبّع IPv4-mapped IPv6 إلى IPv4، وارفض العناوين التي تحتوي ports أو tokens مثل `unknown` و`_hidden` أو أي شكل غير صالح.
6. افحص القائمة من اليمين إلى اليسار. تخطَّ عناوين IP الواقعة داخل شبكات trusted proxy.
7. خذ أول عنوان صالح لا يقع داخل شبكات trusted proxy.
8. إذا كانت القائمة فارغة، أو تضمنت قيمة غير صالحة، أو لم يوجد عنوان صالح مناسب، استخدم socket peer وسجّل `client_ip_fallback_total{reason}`.
9. مفاتيح rate limit تستخدم عنوان IPv4 الكامل، أو شبكة `/64` لعناوين IPv6.
10. لا نثق بأي header بديل مثل `X-Real-IP` في هذه الوحدة.

بهذا، في نموذج proxy واحد:

```text
المهاجم يرسل: XFF: 6.6.6.6
proxy يضيف عنوان العميل الحقيقي: XFF: 6.6.6.6, <client-ip>
socket peer: <trusted-proxy-ip>
النتيجة: <client-ip>
```

وفي نموذج عدة proxies:

```text
XFF: <spoofed-prefix>, <client-ip>, <proxy-a-ip>, <proxy-b-ip>
socket peer: <proxy-c-ip>
```

تُتخطى عناوين `proxy-b` و`proxy-a` من اليمين، ثم تُستخدم `<client-ip>` كأول عنوان غير موثوق. وجود prefix مزيف قبل عنوان العميل لا يغير النتيجة.

## لماذا لا نُبقي TRUSTED_PROXY_COUNT في المنطق؟

العدد وحده يعتمد على ثبات topology وترتيب proxies. إذا تغير مسار CDN أو load balancer، أو كان عدد proxies مختلفاً عن الإعداد، فقد يُستخدم عنوان proxy أو قيمة يسيطر عليها العميل. قائمة CIDR تربط الثقة بهوية الشبكة التي اتصلت فعلياً بالتطبيق، وتتيح خوارزمية "أول عنوان غير موثوق من اليمين" التي تدعمها MDN.

تم اعتماد إزالة `TRUSTED_PROXY_COUNT` من المنطق والإعدادات النشطة. وجوده في البيئة أو مدخلات `Settings` يفشل الإقلاع برسالة واضحة، ثم يُحذف نهائياً في إصدار لاحق بعد اكتمال انتقال الإعدادات.

## متطلبات النشر غير المحسومة

يجب قفل الأصل بحيث لا يمكن الوصول إلى التطبيق إلا عبر proxies الموثوقة. هذا شرط نشر، وليس شيئاً يمكن لتطبيق HTTP إثباته من داخل الطلب. في المرحلة 9 يجب اختبار ذلك من خارج الشبكة: طلب مباشر إلى origin مع XFF مزيف يجب أن يُعامل كطلب من socket peer ويُتجاهل XFF.

نطاقات Cloudflare أو أي CDN/load balancer آخر تأتي من إعداد النشر أو secret وتُحدّث من المصدر الرسمي، لا من الكود. لم يُتخذ قرار استضافة في هذه الوحدة؛ لذلك لم تُفترض peer addresses أو headers لمنصة مثل Render أو Railway. قبل قرار الاستضافة يجب قراءة توثيق المنصة الرسمي وتوثيق ما هو socket peer وما headers التي تضيفها فعلاً، وإذا لم يكن ذلك موثقاً يسجل كمخاطرة. عند النشر خلف Cloudflare سنقيّم `CF-Connecting-IP` في ADR مستقل ضمن المرحلة 9، ولا نثق به تلقائياً هنا.

## الاختبارات المطلوبة بعد الاعتماد

سيتم إنشاء اختبارات لا تفترض أن عنوان proxy يظهر داخل XFF، وتشمل:

- proxy واحد مع عميل عادي.
- proxy واحد مع XFF مزيف بعنوان واحد وبعدة عناوين.
- proxyان وثلاثة، في الحالات العادية والمزيفة.
- IPv4 وIPv6 وقائمة مختلطة.
- قيم تالفة، فارغة، فواصل زائدة، مسافات، وقائمة كبيرة جداً.
- socket peer خارج CIDR الموثوقة، مع تجاهل XFF.
- peer موثوق بدون XFF، وسلسلة كلها trusted، و`request.client is None`.
- IPv4-mapped IPv6، IPv6 `/64`، ports، `unknown`، `_hidden`، المسافات، الفواصل الزائدة، والقائمة الكبيرة.
- كل أسطر XFF في طلب واحد، مع اختبار يثبت ترتيب join.
- تجاوز login rate limit مع تغيير XFF مزيف، ويجب أن يبقى الحد فعالاً.
- تجاوز registration وrefresh بالطريقة نفسها.
- تعليقات داخل كل اختبار تشرح النموذج الواقعي ومصدره.

كما ستُراجع اختبارات 1-أ و1-ب التي تحاكي proxy أو Redis أو client، مع وسم الافتراضات التي لا يمكن إثباتها من مصدر رسمي.

## ملاحظة نطاق

تم اعتماد هذا ADR في 2026-11-23. لا يبدأ 1-ج قبل تنفيذ إصلاح 1-ب بالكامل، ونجاح CI على commit الإصلاح، وتسليم التقرير، وموافقة المدير التالية.

## References

[1]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For "MDN X-Forwarded-For header"
[2]: https://nginx.org/en/docs/http/ngx_http_proxy_module.html "nginx proxy module"
[3]: https://developers.cloudflare.com/fundamentals/reference/http-headers/ "Cloudflare HTTP headers"
