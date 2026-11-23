import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import jwt
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, model_validator
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .core.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("madar.security")
SERVICE = settings.service
ENVIRONMENT = settings.environment
DATABASE_URL = settings.database_url
JWT_SECRET = settings.jwt_secret

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list] = mapped_column(JSON, default=lambda: ["viewer"])


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "supplier_code", name="uq_supplier_tenant_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    supplier_code: Mapped[str] = mapped_column(String(80))
    legal_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="active")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouse_tenant_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    sku: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="unit")
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)


class Inventory(Base):
    __tablename__ = "inventory_balances"
    warehouse_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    on_order: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    po_number: Mapped[str] = mapped_column(String(80))
    supplier_id: Mapped[str] = mapped_column(String(36))
    warehouse_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class POLine(Base):
    __tablename__ = "purchase_order_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[str] = mapped_column(String(36))
    line_no: Mapped[int] = mapped_column(Integer)
    ordered_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(8, 5), default=0)


class Outbox(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(120))
    aggregate_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "route", "key", name="uq_idem_tenant_route_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    route: Mapped[str] = mapped_column(String(160))
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Invitation(Base):
    __tablename__ = "user_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
DUMMY_PASSWORD_HASH = pwd.hash(secrets.token_urlsafe(32))
LOGIN_MAX_PER_IP = settings.login_max_per_ip
LOGIN_MAX_PER_ACCOUNT_IP = settings.login_max_per_account_ip
LOGIN_WINDOW_SECONDS = settings.login_window_seconds
ACCESS_TOKEN_MINUTES = settings.access_token_minutes
REFRESH_TOKEN_DAYS = settings.refresh_token_days
ALLOW_PUBLIC_REGISTRATION = settings.allow_public_registration
MAX_XFF_ENTRIES = 64
MAX_XFF_LENGTH = 8192
try:
    TRUSTED_PROXY_NETWORKS = tuple(
        ipaddress.ip_network(value.strip(), strict=False)
        for value in settings.trusted_proxy_cidrs.split(",")
        if value.strip()
    )
except ValueError as exc:
    raise ValueError("TRUSTED_PROXY_CIDRS contains an invalid CIDR") from exc
CLIENT_IP_FALLBACK_TOTAL: Counter[str] = Counter()
if ENVIRONMENT == "production" and not TRUSTED_PROXY_NETWORKS:
    logger.warning("TRUSTED_PROXY_CIDRS is empty in production; X-Forwarded-For will be ignored")
try:
    rds = redis.from_url(settings.redis_url, decode_responses=True)
except (RedisError, ValueError, TypeError):
    rds = None
try:
    mongo: Database | None = None
    mongo = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=500).supply_events
except (PyMongoError, ValueError):
    mongo = None

app = FastAPI(
    title=f"Madar Supply Control - {SERVICE} service",
    version="0.3.0",
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
origins = [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(IntegrityError)
def integrity_error_handler(request, exc):
    return fastapi_json_response(409, {"error": "CONFLICT", "message": "RESOURCE_CONFLICT"})


def fastapi_json_response(status_code: int, content: dict):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content=content)


def emit(db, tenant_id, event_type, aggregate_id, payload):
    event_id = str(uuid.uuid4())
    db.add(Outbox(id=event_id, tenant_id=tenant_id, event_type=event_type, aggregate_id=aggregate_id, payload=payload))
    try:
        if mongo is not None:
            mongo.events.insert_one(
                {
                    "_id": event_id,
                    "tenantId": tenant_id,
                    "type": event_type,
                    "aggregateId": aggregate_id,
                    "data": payload,
                    "occurredAt": datetime.now(UTC),
                }
            )
    except (PyMongoError, OSError):
        logger.warning("Mongo event delivery failed; transactional outbox retained")
    return event_id


def _record_client_ip_fallback(reason: str) -> None:
    CLIENT_IP_FALLBACK_TOTAL[reason] += 1
    logger.warning("client_ip_fallback_total{reason=%s}", reason)


def _normalized_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _trusted_proxy(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address in network for network in TRUSTED_PROXY_NETWORKS)


def get_client_ip(request: Request) -> str:
    fallback = request.client.host if request.client else "unknown"
    if not TRUSTED_PROXY_NETWORKS:
        _record_client_ip_fallback("peer_not_trusted")
        return fallback
    if not request.client:
        _record_client_ip_fallback("peer_not_trusted")
        return fallback
    try:
        peer = _normalized_ip(request.client.host)
    except ValueError:
        _record_client_ip_fallback("peer_not_trusted")
        return fallback
    if not _trusted_proxy(peer):
        _record_client_ip_fallback("peer_not_trusted")
        return fallback

    header_values = request.headers.getlist("x-forwarded-for")
    if not header_values or not any(header_values):
        _record_client_ip_fallback("no_xff")
        return fallback
    joined = ",".join(header_values)
    if len(joined) > MAX_XFF_LENGTH:
        _record_client_ip_fallback("too_many_entries")
        return fallback
    raw_values = [value.strip() for value in joined.split(",")]
    if len(raw_values) > MAX_XFF_ENTRIES:
        _record_client_ip_fallback("too_many_entries")
        return fallback
    saw_trusted = False
    for raw_value in reversed(raw_values):
        try:
            address = _normalized_ip(raw_value)
        except ValueError:
            _record_client_ip_fallback("invalid_entry")
            return fallback
        if _trusted_proxy(address):
            saw_trusted = True
            continue
        # Once selected, values to the left are attacker-controlled prefix data.
        return str(address)
    if saw_trusted:
        _record_client_ip_fallback("all_trusted")
        return fallback
    _record_client_ip_fallback("all_trusted")
    return fallback


def rate_limit_ip(value: str) -> str:
    try:
        address = _normalized_ip(value)
    except ValueError:
        return value
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address) + "/64"
    return str(address)


def redis_available():
    try:
        if not rds:
            raise RuntimeError("redis unavailable")
        rds.ping()
        return True
    except (RedisError, RuntimeError, OSError):
        if ENVIRONMENT == "production":
            raise HTTPException(503, "AUTH_TEMPORARILY_UNAVAILABLE") from None
        logger.warning("Redis unavailable; development security controls are degraded")
        return False


def limiter_key(prefix, value):
    digest = hmac.new(JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{prefix}:{digest}"


def check_limit(key, limit):
    if not redis_available():
        return
    try:
        if int(rds.get(key) or 0) >= limit:
            raise HTTPException(429, "TOO_MANY_ATTEMPTS", headers={"Retry-After": str(max(1, int(rds.ttl(key))))})
    except HTTPException:
        raise
    except (RedisError, OSError, ValueError, TypeError):
        if ENVIRONMENT == "production":
            raise HTTPException(503, "AUTH_TEMPORARILY_UNAVAILABLE") from None
        logger.warning("Redis limiter read failed")


def hit_limit(key, window=LOGIN_WINDOW_SECONDS):
    if not rds:
        return
    try:
        # Keep INCR and EXPIRE in one Redis transaction so a key cannot lose its TTL.
        pipe = rds.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window)
        pipe.execute()
    except (RedisError, OSError, ValueError, TypeError):
        if ENVIRONMENT == "production":
            raise HTTPException(503, "AUTH_TEMPORARILY_UNAVAILABLE") from None
        logger.warning("Redis limiter write failed")


def auth(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "UNAUTHENTICATED") from None
    try:
        claims = jwt.decode(
            authorization[7:],
            JWT_SECRET,
            algorithms=["HS256"],
            audience="madar-api",
            issuer="madar-auth",
            options={"require": ["sub", "tenant_id", "roles", "exp", "iss", "aud", "jti"]},
        )
        if redis_available() and rds.get(f"jwt-deny:{claims['jti']}"):
            raise HTTPException(401, "UNAUTHENTICATED") from None
        return claims
    except HTTPException:
        raise
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "UNAUTHENTICATED") from None


def require_roles(*allowed_roles):
    def dependency(c=Depends(auth)):
        if not set(c.get("roles", [])) & set(allowed_roles):
            raise HTTPException(403, "FORBIDDEN")
        return c

    return dependency


def digest_body(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def money(value):
    return format(Decimal(value or 0).quantize(Decimal("0.0001")), "f")


def require_idem(key, tenant, route, body):
    if not key or len(key) > 200:
        raise HTTPException(400, "Idempotency-Key header is required")
    return digest_body(body)


def claim_idem(db, key, tenant, route, body):
    digest = require_idem(key, tenant, route, body)
    existing = db.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.tenant_id == tenant, IdempotencyKey.route == route, IdempotencyKey.key == key)
        .with_for_update()
    )
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
        if existing.status == "done":
            return existing, existing.response
        raise HTTPException(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS") from None
    row = IdempotencyKey(
        id=str(uuid.uuid4()), tenant_id=tenant, route=route, key=key, request_hash=digest, status="processing"
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(IdempotencyKey)
            .where(IdempotencyKey.tenant_id == tenant, IdempotencyKey.route == route, IdempotencyKey.key == key)
            .with_for_update()
        )
        if existing and existing.request_hash == digest and existing.status == "done":
            return existing, existing.response
        raise HTTPException(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS") from None
    return row, None


def finish_idem(row, response):
    row.response = response
    row.status = "done"


def password_is_weak(value: str, email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    if len(value) < 10 or len(value) > 128 or (local and local in value.lower()):
        return True
    if len(set(value)) == 1 or value in {"0123456789", "1234567890", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop"}:
        return True
    try:
        with open(os.path.join(os.path.dirname(__file__), "common_passwords.txt"), encoding="utf-8") as f:
            if value.lower() in {line.strip().lower() for line in f if line.strip()}:
                return True
    except OSError:
        logger.warning("Common password list unavailable")
    return False


class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str
    tenant_code: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    tenant_name: str = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def validate_password(self):
        if password_is_weak(self.password, str(self.email)):
            raise ValueError("PASSWORD_TOO_WEAK")
        return self


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class InvitationIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "purchasing", "inventory", "viewer"]


class AcceptInvitation(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=256)


class SupplierIn(BaseModel):
    supplier_code: str
    legal_name: str
    lead_time_days: int = Field(ge=0, default=0)


class ProductIn(BaseModel):
    sku: str
    name: str
    unit_of_measure: str = "unit"
    reorder_point: Decimal = Field(ge=0, default=Decimal("0"))


class WarehouseIn(BaseModel):
    code: str
    name: str


class AdjustIn(BaseModel):
    warehouse_id: str
    product_id: str
    quantity: Decimal
    movement_type: Literal["receipt", "adjustment", "issue"] = "receipt"


class LineIn(BaseModel):
    product_id: str
    ordered_qty: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(ge=0, le=1, default=Decimal("0"))


class POIn(BaseModel):
    supplier_id: str
    warehouse_id: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[LineIn] = Field(min_length=1)
    notes: str | None = None


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    checks = {"database": False, "redis": False}
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        checks["database"] = True
    except SQLAlchemyError:
        logger.warning("Readiness database check failed")
    try:
        if rds:
            rds.ping()
            checks["redis"] = True
    except (RedisError, OSError):
        logger.warning("Readiness Redis check failed")
    if not all(checks.values()):
        raise HTTPException(503, {"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE, "environment": ENVIRONMENT}


@app.get("/metrics", include_in_schema=False)
def metrics():
    lines = [
        f'client_ip_fallback_total{{reason="{reason}"}} {CLIENT_IP_FALLBACK_TOTAL[reason]}'
        for reason in sorted(CLIENT_IP_FALLBACK_TOTAL)
    ]
    return Response("\n".join(lines) + ("\n" if lines else ""), media_type="text/plain; version=0.0.4")


@app.post("/auth/register", status_code=201)
def register(request: Request, x: Register):
    if not ALLOW_PUBLIC_REGISTRATION:
        raise HTTPException(403, "REGISTRATION_DISABLED")
    registration_key = limiter_key("registration", rate_limit_ip(get_client_ip(request)))
    check_limit(registration_key, settings.registration_max_per_ip)
    hit_limit(registration_key, settings.login_window_seconds)
    email = str(x.email).strip().lower()
    with Session(engine) as db:
        tenant_exists = db.scalar(select(Tenant).where(Tenant.code == x.tenant_code)) is not None
        email_exists = db.scalar(select(User).where(User.email == email)) is not None
        if tenant_exists or email_exists:
            logger.info("Registration conflict for normalized identity")
            raise HTTPException(409, "REGISTRATION_FAILED")
        tenant = Tenant(id=str(uuid.uuid4()), code=x.tenant_code, name=x.tenant_name)
        db.add(tenant)
        db.flush()
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            email=email,
            display_name=x.display_name,
            password_hash=pwd.hash(x.password),
            roles=["admin"],
        )
        db.add(user)
        db.commit()
        return {"data": {"id": user.id, "tenant_id": tenant.id, "email": user.email, "roles": user.roles}}


@app.post("/auth/login")
def login(request: Request, x: Login):
    email = str(x.email).strip().lower()
    ip = rate_limit_ip(get_client_ip(request))
    acct_key = limiter_key("login-fail:acct", f"{email}:{ip}")
    ip_key = limiter_key("login-fail:ip", ip)
    check_limit(ip_key, LOGIN_MAX_PER_IP)
    check_limit(acct_key, LOGIN_MAX_PER_ACCOUNT_IP)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        valid = pwd.verify(x.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if not user or not valid:
            hit_limit(ip_key)
            hit_limit(acct_key)
            raise HTTPException(401, "INVALID_CREDENTIALS")
        if rds:
            try:
                rds.delete(acct_key)
            except (RedisError, OSError):
                logger.warning("Redis account limiter cleanup failed")
        now = datetime.now(UTC)
        jti = str(uuid.uuid4())
        token = jwt.encode(
            {
                "sub": user.id,
                "tenant_id": user.tenant_id,
                "roles": user.roles,
                "jti": jti,
                "iss": "madar-auth",
                "aud": "madar-api",
                "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        raw_refresh = secrets.token_urlsafe(48)
        db.add(
            RefreshToken(
                id=str(uuid.uuid4()),
                user_id=user.id,
                tenant_id=user.tenant_id,
                token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
                family_id=str(uuid.uuid4()),
                expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
            )
        )
        db.commit()
        return {"access_token": token, "refresh_token": raw_refresh, "token_type": "bearer", "roles": user.roles}


@app.post("/auth/refresh")
def refresh(request: Request, x: RefreshIn):
    ip = rate_limit_ip(get_client_ip(request))
    refresh_key = limiter_key("refresh", ip)
    check_limit(refresh_key, settings.refresh_max_per_ip)
    hit_limit(refresh_key, settings.refresh_window_seconds)
    token_hash = hashlib.sha256(x.refresh_token.encode()).hexdigest()
    now = datetime.now(UTC)
    with Session(engine) as db:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update())
        if not row or row.expires_at.replace(tzinfo=UTC) <= now:
            raise HTTPException(401, "UNAUTHENTICATED") from None
        if row.revoked_at:
            db.query(RefreshToken).filter(
                RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None)
            ).update({"revoked_at": now})
            emit(
                db,
                row.tenant_id,
                "security.refresh_token_reuse_detected",
                row.user_id,
                {"familyId": row.family_id},
            )
            db.commit()
            raise HTTPException(401, "REFRESH_TOKEN_REUSE_DETECTED")
        user = db.scalar(select(User).where(User.id == row.user_id, User.tenant_id == row.tenant_id))
        if not user:
            raise HTTPException(401, "UNAUTHENTICATED") from None
        row.revoked_at = now
        raw = secrets.token_urlsafe(48)
        db.add(
            RefreshToken(
                id=str(uuid.uuid4()),
                user_id=user.id,
                tenant_id=user.tenant_id,
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                family_id=row.family_id,
                expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
            )
        )
        access = jwt.encode(
            {
                "sub": user.id,
                "tenant_id": user.tenant_id,
                "roles": user.roles,
                "jti": str(uuid.uuid4()),
                "iss": "madar-auth",
                "aud": "madar-api",
                "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        db.commit()
        return {"access_token": access, "refresh_token": raw, "token_type": "bearer", "roles": user.roles}


@app.post("/auth/logout")
def logout(x: RefreshIn, authorization: str | None = Header(None)):
    claims = auth(authorization)
    exp = int(claims["exp"]) - int(datetime.now(UTC).timestamp())
    if rds and exp > 0:
        try:
            rds.setex(f"jwt-deny:{claims['jti']}", exp, "1")
        except (RedisError, OSError):
            if ENVIRONMENT == "production":
                raise HTTPException(503, "AUTH_TEMPORARILY_UNAVAILABLE") from None
            logger.warning("Redis logout deny-list write failed")
    token_hash = hashlib.sha256(x.refresh_token.encode()).hexdigest()
    with Session(engine) as db:
        row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == claims["sub"])
        )
        if row and not row.revoked_at:
            db.query(RefreshToken).filter(
                RefreshToken.family_id == row.family_id,
                RefreshToken.user_id == claims["sub"],
                RefreshToken.revoked_at.is_(None),
            ).update({"revoked_at": datetime.now(UTC)}, synchronize_session=False)
            db.commit()
    return {"data": {"logged_out": True}}


@app.post("/auth/invitations", status_code=201)
def create_invitation(x: InvitationIn, c=Depends(require_roles("admin"))):
    raw = secrets.token_urlsafe(32)
    with Session(engine) as db:
        invitation = Invitation(
            id=str(uuid.uuid4()),
            tenant_id=c["tenant_id"],
            email=str(x.email).strip().lower(),
            role=x.role,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        db.add(invitation)
        db.commit()
        result = {
            "id": invitation.id,
            "email": invitation.email,
            "role": invitation.role,
            "expiresAt": invitation.expires_at.isoformat(),
        }
        if settings.return_invitation_token:
            result["token"] = raw
        return Response(
            content=json.dumps({"data": result}),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
            status_code=201,
        )


@app.post("/auth/accept-invitation", status_code=201)
def accept_invitation(x: AcceptInvitation):
    token_hash = hashlib.sha256(x.token.encode()).hexdigest()
    with Session(engine) as db:
        invite = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash).with_for_update())
        if not invite or invite.used_at or invite.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            raise HTTPException(400, "INVITATION_INVALID_OR_EXPIRED")
        if db.scalar(select(User).where(User.email == invite.email)):
            raise HTTPException(409, "REGISTRATION_FAILED")
        if password_is_weak(x.password, invite.email):
            raise HTTPException(422, "PASSWORD_TOO_WEAK")
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=invite.tenant_id,
            email=invite.email,
            display_name=x.display_name,
            password_hash=pwd.hash(x.password),
            roles=[invite.role],
        )
        db.add(user)
        invite.used_at = datetime.now(UTC)
        db.commit()
        return {"data": {"id": user.id, "tenant_id": user.tenant_id, "email": user.email, "roles": user.roles}}


@app.post("/suppliers", status_code=201)
def create_supplier(x: SupplierIn, c=Depends(require_roles("admin", "purchasing"))):
    with Session(engine) as db:
        s = Supplier(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], **x.model_dump())
        db.add(s)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "SUPPLIER_CODE_ALREADY_EXISTS") from None
        return {"data": {"id": s.id, **x.model_dump(), "status": s.status}}


@app.get("/suppliers")
def suppliers(c=Depends(auth)):
    with Session(engine) as db:
        return {
            "data": [
                {"id": s.id, "supplierCode": s.supplier_code, "legalName": s.legal_name, "status": s.status}
                for s in db.scalars(select(Supplier).where(Supplier.tenant_id == c["tenant_id"])).all()
            ]
        }


@app.post("/products", status_code=201)
def create_product(x: ProductIn, c=Depends(require_roles("admin", "purchasing", "inventory"))):
    with Session(engine) as db:
        p = Product(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], **x.model_dump())
        db.add(p)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "SKU_ALREADY_EXISTS") from None
        return {"data": {"id": p.id, **x.model_dump(mode="json")}}


@app.get("/products")
def products(c=Depends(auth)):
    with Session(engine) as db:
        return {
            "data": [
                {
                    "id": p.id,
                    "sku": p.sku,
                    "name": p.name,
                    "unitOfMeasure": p.unit_of_measure,
                    "reorderPoint": str(p.reorder_point),
                }
                for p in db.scalars(
                    select(Product).where(Product.tenant_id == c["tenant_id"]).order_by(Product.name)
                ).all()
            ]
        }


@app.post("/warehouses", status_code=201)
def create_warehouse(x: WarehouseIn, c=Depends(require_roles("admin", "inventory"))):
    with Session(engine) as db:
        w = Warehouse(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], **x.model_dump())
        db.add(w)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "WAREHOUSE_CODE_ALREADY_EXISTS") from None
        return {"data": {"id": w.id, **x.model_dump()}}


@app.get("/warehouses")
def warehouses(c=Depends(auth)):
    with Session(engine) as db:
        return {
            "data": [
                {"id": w.id, "code": w.code, "name": w.name}
                for w in db.scalars(
                    select(Warehouse).where(Warehouse.tenant_id == c["tenant_id"]).order_by(Warehouse.code)
                ).all()
            ]
        }


@app.get("/inventory")
def inventory(warehouse_id: str | None = None, product_id: str | None = None, low_stock: bool = False, c=Depends(auth)):
    with Session(engine) as db:
        q = select(Inventory).where(Inventory.tenant_id == c["tenant_id"])
        if warehouse_id:
            q = q.where(Inventory.warehouse_id == warehouse_id)
        if product_id:
            q = q.where(Inventory.product_id == product_id)
        rows = []
        for i in db.scalars(q):
            p = db.scalar(select(Product).where(Product.id == i.product_id, Product.tenant_id == c["tenant_id"]))
            available = i.on_hand - i.reserved
            if low_stock and p and available > p.reorder_point:
                continue
            rows.append(
                {
                    "warehouseId": i.warehouse_id,
                    "productId": i.product_id,
                    "onHand": str(i.on_hand),
                    "reserved": str(i.reserved),
                    "available": str(available),
                    "onOrder": str(i.on_order),
                    "reorderPoint": str(p.reorder_point if p else 0),
                }
            )
        return {"data": rows}


@app.post("/inventory/adjust", status_code=201)
def adjust(
    x: AdjustIn, key: str | None = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "inventory"))
):
    if x.movement_type != "adjustment" and x.quantity <= 0:
        raise HTTPException(422, "QUANTITY_MUST_BE_POSITIVE")
    if x.movement_type == "adjustment" and x.quantity == 0:
        raise HTTPException(422, "ADJUSTMENT_CANNOT_BE_ZERO")
    body = x.model_dump(mode="json")
    with Session(engine) as db:
        row, old = claim_idem(db, key, c["tenant_id"], "inventory/adjust", body)
        if old:
            return old
        p = db.scalar(select(Product).where(Product.id == x.product_id, Product.tenant_id == c["tenant_id"]))
        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))
        if not p or not w:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        i = db.scalar(
            select(Inventory)
            .where(
                Inventory.warehouse_id == x.warehouse_id,
                Inventory.product_id == x.product_id,
                Inventory.tenant_id == c["tenant_id"],
            )
            .with_for_update()
        )
        if not i:
            i = Inventory(
                warehouse_id=x.warehouse_id,
                product_id=x.product_id,
                tenant_id=c["tenant_id"],
                on_hand=0,
                reserved=0,
                on_order=0,
            )
            db.add(i)
            db.flush()
        if x.movement_type == "receipt":
            i.on_hand += x.quantity
        elif x.movement_type == "adjustment":
            if i.on_hand + x.quantity < i.reserved:
                raise HTTPException(409, "BELOW_RESERVED_STOCK")
            i.on_hand += x.quantity
        elif i.on_hand - i.reserved < x.quantity:
            raise HTTPException(409, "INSUFFICIENT_AVAILABLE_STOCK")
        else:
            i.on_hand -= x.quantity
        emit(db, c["tenant_id"], "supply.inventory.adjusted.v1", x.product_id, body)
        out = {
            "data": {
                "warehouseId": x.warehouse_id,
                "productId": x.product_id,
                "onHand": str(i.on_hand),
                "reserved": str(i.reserved),
                "available": str(i.on_hand - i.reserved),
            }
        }
        finish_idem(row, out)
        db.commit()
        return out


@app.post("/purchase-orders", status_code=201)
def create_po(
    x: POIn, key: str | None = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "purchasing"))
):
    body = x.model_dump(mode="json")
    with Session(engine) as db:
        row, old = claim_idem(db, key, c["tenant_id"], "purchase-orders", body)
        if old:
            return old
        s = db.scalar(select(Supplier).where(Supplier.id == x.supplier_id, Supplier.tenant_id == c["tenant_id"]))
        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))
        ids = {line_input.product_id for line_input in x.lines}
        products_found = {
            p.id for p in db.scalars(select(Product).where(Product.tenant_id == c["tenant_id"], Product.id.in_(ids)))
        }
        if not s or not w:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        if len(products_found) != len(ids):
            raise HTTPException(404, "PRODUCT_NOT_FOUND")
        po = PurchaseOrder(
            id=str(uuid.uuid4()),
            tenant_id=c["tenant_id"],
            po_number=f"PO-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}",
            supplier_id=x.supplier_id,
            warehouse_id=x.warehouse_id,
            currency=x.currency.upper(),
            created_by=c["sub"],
        )
        db.add(po)
        db.flush()
        subtotal = Decimal(0)
        lines = []
        for n, line_input in enumerate(x.lines, 1):
            subtotal += line_input.ordered_qty * line_input.unit_price
            line = POLine(id=str(uuid.uuid4()), purchase_order_id=po.id, line_no=n, **line_input.model_dump())
            db.add(line)
            lines.append(
                {
                    "id": line.id,
                    "lineNo": n,
                    "productId": line.product_id,
                    "orderedQty": str(line.ordered_qty),
                    "unitPrice": str(line.unit_price),
                }
            )
        po.subtotal = subtotal
        po.tax_total = sum(
            (line_input.ordered_qty * line_input.unit_price * line_input.tax_rate for line_input in x.lines),
            Decimal(0),
        )
        po.total = po.subtotal + po.tax_total
        emit(
            db,
            c["tenant_id"],
            "supply.purchase-order.created.v1",
            po.id,
            {"poId": po.id, "poNumber": po.po_number, "status": po.status, "total": money(po.total), "lines": lines},
        )
        out = {
            "data": {
                "id": po.id,
                "poNumber": po.po_number,
                "status": po.status,
                "supplierId": po.supplier_id,
                "warehouseId": po.warehouse_id,
                "subtotal": money(po.subtotal),
                "taxTotal": money(po.tax_total),
                "total": money(po.total),
                "lines": lines,
            }
        }
        finish_idem(row, out)
        db.commit()
        return out


@app.get("/purchase-orders")
def list_po(c=Depends(auth)):
    with Session(engine) as db:
        return {
            "data": [
                {
                    "id": p.id,
                    "poNumber": p.po_number,
                    "status": p.status,
                    "total": money(p.total),
                    "supplierId": p.supplier_id,
                    "warehouseId": p.warehouse_id,
                }
                for p in db.scalars(
                    select(PurchaseOrder)
                    .where(PurchaseOrder.tenant_id == c["tenant_id"])
                    .order_by(PurchaseOrder.created_at.desc())
                ).all()
            ]
        }


def transition_po(po_id, target, roles, c, key=None):
    with Session(engine) as db:
        po = db.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == c["tenant_id"])
            .with_for_update()
        )
        if not po:
            raise HTTPException(404, "PURCHASE_ORDER_NOT_FOUND")
        route = f"purchase-orders/{po_id}/{target}"
        body = {"id": po_id, "target": target}
        row, old = claim_idem(db, key, c["tenant_id"], route, body) if key else (None, None)
        if old:
            return old
        allowed = {
            "submit": {"draft": "pending_approval"},
            "approve": {"pending_approval": "approved"},
            "receive": {"approved": "received"},
        }
        if po.status not in allowed[target]:
            raise HTTPException(409, "INVALID_PURCHASE_ORDER_TRANSITION")
        po.status = allowed[target][po.status]
        if target == "approve":
            for line in db.scalars(select(POLine).where(POLine.purchase_order_id == po.id)):
                inv = db.scalar(
                    select(Inventory)
                    .where(
                        Inventory.warehouse_id == po.warehouse_id,
                        Inventory.product_id == line.product_id,
                        Inventory.tenant_id == c["tenant_id"],
                    )
                    .with_for_update()
                )
                if not inv:
                    inv = Inventory(
                        warehouse_id=po.warehouse_id,
                        product_id=line.product_id,
                        tenant_id=c["tenant_id"],
                        on_hand=0,
                        reserved=0,
                        on_order=0,
                    )
                    db.add(inv)
                    db.flush()
                inv.on_order += line.ordered_qty
        elif target == "receive":
            for line in db.scalars(select(POLine).where(POLine.purchase_order_id == po.id)):
                inv = db.scalar(
                    select(Inventory)
                    .where(
                        Inventory.warehouse_id == po.warehouse_id,
                        Inventory.product_id == line.product_id,
                        Inventory.tenant_id == c["tenant_id"],
                    )
                    .with_for_update()
                )
                if not inv or inv.on_order < line.ordered_qty:
                    raise HTTPException(409, "INVALID_ON_ORDER_BALANCE")
                inv.on_order -= line.ordered_qty
                inv.on_hand += line.ordered_qty
        emit(db, c["tenant_id"], f"supply.purchase-order.{target}.v1", po.id, {"poId": po.id, "status": po.status})
        out = {"data": {"id": po.id, "poNumber": po.po_number, "status": po.status}}
        if row:
            finish_idem(row, out)
        db.commit()
        return out


@app.post("/purchase-orders/{po_id}/submit")
def submit_po(po_id: str, c=Depends(require_roles("admin", "purchasing"))):
    return transition_po(po_id, "submit", ("admin", "purchasing"), c)


@app.post("/purchase-orders/{po_id}/approve")
def approve_po(po_id: str, c=Depends(require_roles("admin"))):
    return transition_po(po_id, "approve", ("admin",), c)


@app.post("/purchase-orders/{po_id}/receive")
def receive_po(
    po_id: str, key: str | None = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "inventory"))
):
    return transition_po(po_id, "receive", ("admin", "inventory"), c, key)


if SERVICE != "all":
    service_prefixes = {
        "auth": ("/auth",),
        "supplier": ("/suppliers", "/products", "/warehouses"),
        "inventory": ("/inventory",),
        "order": ("/purchase-orders",),
    }
    allowed = service_prefixes.get(SERVICE, ())
    app.router.routes = [
        route
        for route in app.router.routes
        if getattr(route, "path", "") == "/health"
        or any(getattr(route, "path", "").startswith(prefix) for prefix in allowed)
    ]
