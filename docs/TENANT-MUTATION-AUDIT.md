# تدقيق tenant predicates بالـAST

## المنهج

تكتشف `scripts/mutation_tenant_queries.py` كل مقارنة AST تحتوي `.tenant_id` تحت `backend/app`. هوية كل target مستقرة ومكوّنة من `(الملف، الدالة المحيطة، رقم ترتيب التعبير داخل الدالة)`، وليست من hash التعبير؛ لذلك لا يمكن لموضع جديد أن يرث تصنيف موضع قديم. القائمة الكاملة ملتزمة في [tenant_predicate_manifest.json](../scripts/tenant_predicate_manifest.json).

يوجد guard سريع `--guard-only` يعمل على كل push وpull request، ويقارن الاكتشاف الحالي بالـmanifest وبالتصنيفات. كما يوجد اختبار يضيف endpoint وهمياً بنفس expression ويثبت أن guard يرفضه. التشغيل الكامل ينشئ نسخة مؤقتة لكل mutant ويستبدل predicate بـ`True` ثم يشغّل اختبارات العزل؛ لا يعدّل working tree الأصلي.

## التشغيل الفعلي بعد إغلاق G1

```text
TEST_DATABASE_URL=postgresql+psycopg://supply_ci:supply_ci@127.0.0.1:5432/supply_ci
REDIS_URL=redis://127.0.0.1:6379/15
python scripts/mutation_tenant_queries.py --json /tmp/tenant-mutation-g1.json
```

النتيجة الفعلية: **18 target مكتشفاً، 16 `FAIL_DETECTED`، و2 survivors مصنفين equivalent**. لم يبق أي `test-gap`؛ اختبارات DB-corruption المباشرة تستخدم PostgreSQL SQL لإدراج صفوف inventory بمالك مختلف، وتثبت عدم تحديث الصف الفاسد وعدم تسريب reorder point.

| target | النتيجة | التصنيف/الدليل |
|---|---|---|
| `backend/app/main.py::refresh::1` | survivor | equivalent: `User.id` مفتاح أساسي عالمي، و`row.tenant_id` tenant الخاص بالـrefresh row. |
| `backend/app/main.py::claim_idem::2` | survivor | equivalent بعد `uq_idem_tenant_route_key`: تعارض الإدراج لا يمكن أن يأتي من tenant آخر. |
| بقية 16 target | `FAIL_DETECTED` | تشمل GET inventory reorder-point، adjust، approve، receive، القوائم، PO، وidempotency predicate الأول. |

## الاختبارات الجديدة

- `test_corrupt_inventory_product_owner_cannot_leak_reorder_point`: يثبت أن predicate المنتج يمنع قراءة reorder point من tenant آخر.
- `test_corrupt_inventory_adjust_cannot_update_other_tenant_row`: مع composite PK، يمنع predicate تحديث الصف الفاسد؛ النتيجة `409` والرصيد لم يتغير.
- `test_corrupt_inventory_approve_cannot_update_other_tenant_row`: لا يتم تحديث on-order للمالك الفاسد.
- `test_corrupt_inventory_receive_cannot_update_other_tenant_row`: لا يُسمح بالاستلام اعتماداً على on-order للمالك الفاسد.
- `test_tenant_manifest_rejects_a_new_endpoint_with_existing_expression`: يثبت fail-closed للـmanifest.
- `test_real_http_role_matrix_covers_invitation_to_jwt_to_policy`: ينشئ مستخدماً admin، يدعو الأدوار الثلاثة، يقبل الدعوات، يسجل الدخول، ثم يختبر كل `(method, path)` عبر JWT حقيقي مقابل golden table.

## CI

- `tenant-manifest-guard` يعمل على كل push وpull request بلا تشغيل mutants.
- `tenant-mutation` يعمل يدوياً أو ليلياً مع PostgreSQL 16 وRedis 7 وtimeout قدره 45 دقيقة.
