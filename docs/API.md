# API compatibility

The existing unversioned routes remain the compatibility surface during phase 0. Any breaking API change requires an explicit decision and a versioned route. Authentication routes include login, registration, invitation, refresh and logout. Tenant-owned catalog, inventory and purchasing routes must preserve tenant isolation and current response shapes until a later approved phase.
