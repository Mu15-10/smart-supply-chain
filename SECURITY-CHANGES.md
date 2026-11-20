# Security changes

| المهمة | الملفات المتغيرة | إعدادات البيئة الجديدة | تأثير الواجهة أو النشر |
|---|---|---|---|
| 1 | `backend/app/main.py`، اختبارات backend | `TRUSTED_PROXY_COUNT`, `LOGIN_MAX_PER_IP`, `LOGIN_MAX_PER_ACCOUNT_IP`, `LOGIN_WINDOW_SECONDS` | limiter حسب IP وaccount+IP؛ Redis fail-closed في production |
| 2–4 | `backend/app/main.py`, `.env.example` | `ALLOW_PUBLIC_REGISTRATION`, `RETURN_INVITATION_TOKEN` | التسجيل العام قابل للتعطيل؛ البريد وكلمات المرور والتحقق وCORS أقوى |
| 5 | `main.py`, `002_refresh_tokens.py`, `dashboard/src/api.js`, `App.jsx` | `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` | access قصير، refresh rotation، logout، sessionStorage |
| 6 | `main.py`, `dashboard/index.html` | origins الخاصة بالـ API | security headers وCSP؛ GitHub Pages لا يضيف response headers |
| 7 | `pyproject.toml`, workflow, Dependabot | lock/digests تحتاج إكمالاً موثقاً | CI أمني وDependabot مضافان |
| 8 | `docker-compose.yml`, `main.py` | `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_URL` | Mongo auth، no-store للدعوات، warning بدلاً من pass |

## Notes

`ALLOWED_ORIGINS` في الإنتاج يجب أن يحتوي origin صريحاً مثل `https://mu15-10.github.io` دون path. التسجيل العام افتراضه آمن خارج production للتوافق مع بيئة التطوير الحالية، لكنه معطل افتراضياً في production؛ القرار التشغيلي النهائي هو invitation-only في الإنتاج.

بعد نشر الكود شغّل `alembic upgrade head`. يفضّل مستقبلاً نقل refresh token إلى httpOnly Secure cookie عندما يكون الـ API والواجهة على نفس الموقع. CSP الحالية تسمح origins المحلية؛ يجب إضافة origins الفعلية وقت build/deployment.
