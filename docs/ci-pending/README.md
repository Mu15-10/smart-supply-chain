# Pending CI publication

The workflow in `ci.yml.txt` is the complete Phase 0-B CI candidate. It was not copied to
`.github/workflows/` on the published branch because the current GitHub App lacks the `workflows`
permission. The repository owner must publish it using an account or App installation with the
minimum required workflow write permission, then verify a green run on PostgreSQL and Redis.
