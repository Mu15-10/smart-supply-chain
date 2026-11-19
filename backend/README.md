# مدار الإمداد — Smart Supply Control MVP

نسخة أولية قابلة للتشغيل محليًا لخدمات Auth وSupplier وInventory وOrder، مع PostgreSQL للمعاملات، MongoDB للأحداث، وRedis لـidempotency.

## التشغيل المحلي

```bash
cp .env.example .env
# غيّر JWT_SECRET إلى قيمة عشوائية طويلة قبل أي تشغيل مشترك
docker compose up --build
```

الخدمات: Auth `:8001`، Supplier `:8002`، Inventory `:8003`، وOrder `:8004`. قواعد البيانات مربوطة على localhost فقط في Compose، بينما تتواصل الخدمات داخليًا عبر شبكة Docker.

## المسار السريع

1. أنشئ مؤسسة ومستخدمًا أوليًا عبر `POST http://localhost:8001/auth/register` باستخدام `tenant_code` جديد.
2. لا يسمح التسجيل العام بالانضمام إلى مؤسسة قائمة؛ استخدم تدفق دعوات مؤسسي عند إضافته لاحقًا.
3. سجّل الدخول عبر `/auth/login` للحصول على JWT.
4. أرسل `Authorization: Bearer <token>` إلى endpoints الإدارة.
5. أرسل `Idempotency-Key` فريدًا إلى `POST /inventory/adjust` و`POST /purchase-orders`.

## الصلاحيات والعزل

- المستخدم الأول للمؤسسة الجديدة يحصل على `admin`.
- الكتابة محمية بأدوار: `admin`، `purchasing`، و`inventory` حسب العملية.
- كل supplier وwarehouse وproduct وpurchase order يُتحقق من `tenant_id` في الاستعلام نفسه.
- أنواع حركة المخزون المسموحة: `receipt` و`adjustment` و`issue` فقط.
- خارج `development` و`test` يفشل التطبيق عند غياب `JWT_SECRET` أو قصره عن 32 حرفًا.

## الاختبار

```bash
pip install -e . pytest
pytest -q
```

## حدود MVP

النسخة لا تزال بحاجة إلى invitation service دائم، Alembic migrations، PostgreSQL RLS، publisher فعلي للأحداث، OIDC/2FA، وKubernetes. واجهة لوحة التحكم الحالية تدعم Demo محليًا، مع تجهيزات الربط بالـAPI كخطوة تشغيلية لاحقة.
