# تدقيق tenant predicates بالـ AST

## المنهج

تكتشف `scripts/mutation_tenant_queries.py` كل عقدة AST من نوع `Compare` تحتوي على `.tenant_id` تحت `backend/app`. لكل موضع تُنشأ نسخة مؤقتة من المستودع ويُستبدل التعبير بـ`True`، ثم تُشغّل `tests/test_phase1c_isolation.py`. فشل الاختبار أو فشل الاستيراد/الترجمة يعني أن الـ mutant اكتُشف. لا يُعدَّل working tree الأصلي، ويعيد السكربت guard يفشل إذا لم يكن كل target مختبراً أو مصنفاً.

التشغيل الفعلي:

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
python scripts/mutation_tenant_queries.py --json /tmp/tenant-mutation-results.json
```

النتيجة الفعلية: **18 موضعاً مكتشفاً، 12 موضعاً فشل اختباره، و6 survivors مصنفين**. توجد 7 تعبيرات mutant فريدة لأن بعض المواضع تستخدم التعبير نفسه؛ لذلك يظهر ملخص guard الفريد `discovered=7 tested=6 classified=4`، مع بقاء كل المواضع الـ18 ممثلة في النتائج.

## التصنيف

| التعبير | المواضع | التصنيف | الدليل/الفجوة |
|---|---:|---|---|
| `User.tenant_id == row.tenant_id` | 737 | equivalent | `User.id` مفتاح أساسي عالمي، و`row.tenant_id` هو tenant الخاص بالـ refresh token المحدد؛ بعد اختيار `row` لا يمكن أن يطابق `user_id` مستخدماً من tenant آخر ضمن invariant المخطط. |
| `Product.tenant_id == c["tenant_id"]` | 942 | test gap | suite الحالي لا ينشئ inventory row فاسداً يشير إلى product من tenant آخر. predicate باقٍ كـ defense-in-depth، ويجب إضافة fixture فساد مقصود وإثبات عدم تسريب reorder point. |
| `Inventory.tenant_id == c["tenant_id"]` | 980، 1145، 1168 | test gap | suite الحالي لا ينشئ inventory rows فاسدة بمالك مختلف مع نفس warehouse/product أو نفس PO. predicate ضروري لمنع adjust/approve/receive من تحديث صف tenant آخر؛ يلزم اختبار DB-corruption صريح. |
| `IdempotencyKey.tenant_id == tenant` في مسار IntegrityError | 495 | equivalent بعد constraint | `uq_idem_tenant_route_key` يجعل تعارض الإدراج ممكناً فقط داخل نفس `(tenant_id, route, key)`؛ الاستعلام اللاحق بعد التعارض لا يستطيع التقاط صف tenant آخر. |

الـ test gaps ليست موافقة على حذف predicates؛ هي حدود mutation suite الحالية موثقة صراحة. الـ guard يرفض survivor غير المصنف، والتصنيفات مثبتة في `SURVIVOR_CLASSES` داخل السكربت.

## CI

أضيف job باسم `tenant-mutation` يعمل عند `workflow_dispatch` أو في الجدولة الليلية، مع PostgreSQL 16 وRedis 7، timeout قدره 45 دقيقة، ويشغّل نفس السكربت. لا يبطئ push/PR العادي بسبب كلفة تشغيل 18 نسخة اختبارية.
