# حزمة تصميم نظام إدارة سلسلة التوريد الذكي

**المشروع:** Smart Supply Chain Management System
**المسار:** 011 — إنشاء نظام أتمتة متكامل
**الحالة:** تصميم مرجعي قابل للتنفيذ، غير منشور في الإنتاج
**الجدول المستهدف:** MVP خلال 4 أسابيع، نسخة كاملة خلال 12 أسبوعًا

## 1. القرار التنفيذي

المنصة المقترحة هي نظام متعدد المستأجرين لإدارة الموردين، الأصناف، المخزون، أوامر الشراء، الشحن والاستلام، مع أحداث لحظية وتنبيهات استباقية. تستخدم خدمات مخصصة للمعاملات والمنطق المعقد، وn8n أو Integration Workers للتكاملات الخارجية وwebhooks والمهام المجدولة. لا تُتخذ قرارات شراء آلية نهائية دون مراجعة بشرية في النسخة الأولى.

المعمارية المرجعية: PostgreSQL كمصدر حقيقة للمعاملات، MongoDB/Read Models للتتبع والقراءات غير المهيكلة، Kafka كسجل أحداث، Redis للتخزين المؤقت والأقفال وidempotency قصيرة العمر، وS3-compatible Object Storage للوثائق والملفات. تُنشر خدمات التطبيق على Kubernetes، مع OpenTelemetry وPrometheus/Grafana وLoki/Tempo للمراقبة.

## 2. محتويات الحزمة

- [وثيقة المعمارية والمخططات](architecture.md): حدود الخدمات، Kafka، PostgreSQL، Redis، Object Storage، Kubernetes، observability، ADRs، ومخططا المعمارية وتدفق العمل.
- [وثيقة البيانات وواجهات API](data-api.md): SQL schema، MongoDB collections، عقود الأحداث، API endpoints، idempotency، وثلاثة Sequence Diagrams.
- [الخطة والأمان وضمان الجودة](plan-security.md): خطة 12 أسبوعًا، بوابات ML، RBAC/2FA، SLOs، CI/CD، الاختبارات، rollback، المخاطر والأسئلة المفتوحة.
- [مخططات Mermaid قابلة للرسم](diagrams/): ملفات `.mmd` ومخرجات PNG للتحقق البصري.

## 3. نطاق MVP مقابل النسخة الكاملة

### MVP — الأسبوع 1 إلى 4

1. الهوية والمستأجرون وRBAC و2FA للحسابات الإدارية.
2. كتالوج المنتجات والموردين والمستودعات.
3. إنشاء الطلبات وأوامر الشراء والاستلام.
4. أرصدة المخزون والحجز الذري وحركات المخزون.
5. شحن مبسط: إنشاء الشحنة، التتبع، webhook حالة الناقل، وإثبات الاستلام.
6. تنبيهات low-stock والتأخير عبر Notification Worker.
7. تكامل أول عبر REST أو CSV باستخدام n8n/Integration Worker.
8. Dashboard أولي: الرصيد، الطلبات المتأخرة، الشحنات، وأوامر الشراء.
9. Audit Log وOutbox وIdempotency وDLQ وreplay موثق.

### النسخة الكاملة — الأسبوع 5 إلى 12

1. توقع الطلب كل 6 ساعات مع baseline ثم نموذج ML في shadow/canary.
2. RFID/IoT ingestion مع device registry، deduplication، وقراءة lot/expiry.
3. تنبيهات انتهاء الصلاحية وبطء الحركة وخرق حدود التخزين.
4. اقتراحات replenishment مرتبطة بالتنبؤ، مع موافقة بشرية قبل إصدار أمر شراء.
5. Route Optimization يعتمد على المرور، الوقود، أولوية الطلب، قدرة المركبة، وقيود نافذة التسليم؛ يعيد الحساب عند حدث طارئ.
6. لوحات تنفيذية قابلة للتخصيص ومؤشرات تكلفة وتسليم وأخطاء شحن.
7. موصلات ERP/WMS/TMS والتجارة الإلكترونية والدفع، مع reconciliation وretry.
8. HA/DR، صلاحيات حسب الموقع، audit غير قابل للعبث، واختبارات ضغط وفشل.

## 4. Workflowات 011 المقترحة

كل Workflow يتبع النمط: **Trigger → Normalize → Validate → Deduplicate → Enrich → Decide → Execute → Record → Notify**.

| Workflow | Trigger | القرار والتنفيذ | السجل والضمانات |
|---|---|---|---|
| مزامنة ERP/WMS | Cron أو webhook | mapping ثم تحقق schema ثم upsert | sync_runs، checksum، retry، DLQ |
| قراءة RFID/IoT | MQTT/HTTP gateway | normalize device event ثم تحديث inventory | event_id، device_id، occurred_at، dedupe |
| اكتشاف انخفاض المخزون | `StockChanged` | مقارنة available مع reorder point | Alert + `ReplenishmentSuggested` |
| توقع الطلب | Cron كل 6 ساعات | feature build → forecast → confidence gate | model/data version، baseline fallback |
| اقتراح أمر شراء | `StockShortage` أو forecast | حساب الكمية والمورد والمهلة | human approval، idempotency، audit |
| تحسين المسار | shipment/traffic/incident event | إعادة حل route مع قيود المركبة والأولوية | route version، ETA، سبب إعادة الحساب |
| تحديث الشحنة | carrier webhook | normalize status ثم state transition | provider event dedupe، audit، notify |
| التنبيه | أي critical business event | severity policy ثم قناة الإشعار | delivery attempts، escalation، suppression |
| التقرير التنفيذي | query أو schedule | read model/aggregate وليس OLTP | cached snapshot، RBAC، export audit |

لا تُحفظ أسرار التكاملات داخل Workflow JSON. يستخدم n8n credential store أو Secret Manager، وتُمرر المراجع عبر متغيرات بيئة. كل webhook خارجي يجب أن يوقع payload أو يستخدم mTLS/API key، مع rate limit وفحص replay.

## 5. مصفوفة تتبع المتطلبات

| المطلب | المكوّن/التصميم | معيار القبول |
|---|---|---|
| ML Demand Forecasting | Planning & Forecast + Feature pipeline + model registry | تشغيل كل 6 ساعات، backtest زمني، أداء مقابل baseline، و85% لا تُقبل إلا بعد تعريف metric وholdout ممثل |
| RFID/IoT لحظي | IoT Gateway + Inventory Ingestion + Kafka | وصول الحدث ضمن freshness SLA، dedupe، تحديث الرصيد دون double count |
| low-stock/expiry/slow-moving | Inventory Rules + Notification | تنبيه قابل للتدقيق مع severity وowner وsnooze/escalation |
| اقتراح شراء تلقائي | Replenishment Service + Procurement | اقتراح idempotent مع lead time/safety stock وموافقة بشرية |
| Route Optimization | Logistics + Traffic/Fuel adapters + Route Solver | route يراعي القيود، نسخة route، ETA، وإعادة حساب عند incident |
| Executive Dashboard | Reporting Read Model + Query API + UI | KPI يطابق مصدرًا مرجعيًا، RBAC، فلاتر وتصدير مدقق |
| ERP/e-commerce/carriers/payments | Integration Service/n8n adapters | contract tests، retry/backoff، DLQ، reconciliation، وعدم تكرار |
| Webhooks | API Gateway/Webhook Handler | توقيع/مصادقة، dedupe، replay protection، state transition |
| RBAC/2FA | Identity & Access + OIDC | منع horizontal/vertical escalation و2FA للعمليات الحساسة |
| تشفير البيانات | TLS + KMS/managed encryption + secret manager | لا أسرار في Git/logs، مفاتيح منفصلة، rotation موثق |
| Audit Log | Audit Service + append-only sink | actor/action/resource/time/result/correlation، وقابلية بحث وتصدير |
| Microservices | bounded contexts مع ملكية بيانات | لا قراءة مباشرة لقاعدة خدمة أخرى، عقود versioned |
| SQL + NoSQL | PostgreSQL + MongoDB/read models | OLTP في SQL، قراءات وتتبعات غير مهيكلة في NoSQL |
| Kafka/RabbitMQ | Kafka مع outbox وDLQ | at-least-once مع consumer idempotency وreplay |
| Docker/Kubernetes/CI/CD | containerized services + Helm/GitOps | build reproducible، SBOM، scan، staging smoke، rollback |
| Prometheus/Grafana | OTel + Prometheus/Grafana/Loki/Tempo | API/queue/business/security dashboards وrunbooks |

## 6. معايير الجودة قبل اعتبار المشروع جاهزًا

- نجاح مسار E2E: إنشاء طلب → فحص/حجز → نقص → اقتراح/موافقة شراء → استلام → شحنة → تقرير.
- نجاح حالات التكرار والـtimeout و429 و5xx وفقد الاتصال وDLQ/replay.
- لا ثغرات Critical/High غير مقبولة، ولا secrets أو PII في السجلات.
- اختبار backup/restore وrollback وexpand/contract migrations.
- إثبات أرقام Dashboard مقابل query مرجعي.
- اختبار صلاحيات لكل دور وعلى مستوى tenant/site/warehouse.
- ML لا يدخل قرارات شراء تلقائية قبل اجتياز data gate وmodel gate وbusiness gate؛ يوجد fallback إلى baseline/rules.
- اجتياز SLOs في بيئة Pilot ممثلة، مع owner وrunbook لكل alert.

## 7. قرارات مطلوبة من صاحب المشروع قبل Sprint 1

1. الأنظمة الفعلية: ERP/WMS/TMS/e-commerce/carrier/payment، وأشكال API أو الملفات المتاحة.
2. حجم الأحداث: الطلبات اليومية، SKU، المستودعات، أجهزة RFID/IoT، ومعدل الرسائل.
3. تعريف دقة 85%: المقياس، أفق التنبؤ، الشرائح الحرجة، وفترة holdout.
4. قيود Route Optimization: الدول، مزود المرور، أحجام المركبات، نوافذ التسليم، والميزانية.
5. الدولة والامتثال وموقع البيانات ومدة الاحتفاظ بالـPII والعقود.
6. مزود OIDC/KMS/Kafka/observability والميزانية التشغيلية.
7. من يوافق على أمر الشراء أو يتجاوز توصية ML، ومن يملك بيانات الحقيقة.

## 8. حالة التنفيذ الحالية

هذه الحزمة **تصميم ووثائق قابلة للتنفيذ** وليست نشرًا أو تكاملًا فعليًا مع أنظمة خارجية. تم التحقق من وجود الوثائق ومن رسم مخططات Mermaid الخمسة بنجاح. الخطوة التالية الصحيحة هي اعتماد القرارات المفتوحة، ثم إنشاء مستودع التطبيق وبدء Sprint 1 وفق الخطة.

**Checkpoint:** `design-v1 — architecture/data-api/plan-security reviewed; mermaid diagrams rendered successfully; no production deployment performed.`
