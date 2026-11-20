# Security model

Tenant identity is taken from authenticated claims and every tenant-owned query must constrain by tenant. JWT validation uses issuer, audience, expiry and algorithm checks. Login and refresh controls fail closed in production when Redis is unavailable. Secrets belong in deployment secret storage, never in the repository.

Security events must not log passwords, authorization headers, refresh/invitation tokens, request bodies or unnecessary personal data. Production requires explicit HTTPS CORS origins, TLS, managed backups and independent migration credentials.
