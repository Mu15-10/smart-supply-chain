import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional

import jwt
import redis
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from pymongo import MongoClient
from sqlalchemy import (
    DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint,
    create_engine, select
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

SERVICE = os.getenv("SERVICE", "all")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./supply.db")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be configured")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters")

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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Invitation(Base):
    __tablename__ = "user_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
try:
    rds = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
except Exception:
    rds = None
try:
    mongo = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=500).supply_events
except Exception:
    mongo = None

app = FastAPI(title=f"Madar Supply Control - {SERVICE} service", version="0.3.0")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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
            mongo.events.insert_one({"_id": event_id, "tenantId": tenant_id, "type": event_type, "aggregateId": aggregate_id, "data": payload, "occurredAt": datetime.now(timezone.utc)})
    except Exception:
        pass
    return event_id

def auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "UNAUTHENTICATED")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"], audience="madar-api", issuer="madar-auth", options={"require": ["sub", "tenant_id", "roles", "exp", "iss", "aud"]})
    except Exception:
        raise HTTPException(401, "UNAUTHENTICATED")

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
    existing = db.scalar(select(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant, IdempotencyKey.route == route, IdempotencyKey.key == key).with_for_update())
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
        if existing.status == "done":
            return existing, existing.response
        raise HTTPException(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
    row = IdempotencyKey(id=str(uuid.uuid4()), tenant_id=tenant, route=route, key=key, request_hash=digest, status="processing")
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant, IdempotencyKey.route == route, IdempotencyKey.key == key).with_for_update())
        if existing and existing.request_hash == digest and existing.status == "done":
            return existing, existing.response
        raise HTTPException(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
    return row, None

def finish_idem(row, response):
    row.response = response
    row.status = "done"

class Register(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str
    tenant_code: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    tenant_name: str = Field(min_length=2, max_length=200)

class Login(BaseModel):
    email: str
    password: str

class InvitationIn(BaseModel):
    email: str
    role: Literal["admin", "purchasing", "inventory", "viewer"]

class AcceptInvitation(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=200)

class SupplierIn(BaseModel):
    supplier_code: str
    legal_name: str
    lead_time_days: int = Field(ge=0, default=0)

class ProductIn(BaseModel):
    sku: str
    name: str
    unit_of_measure: str = "unit"
    reorder_point: Decimal = Field(ge=0, default=0)

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
    tax_rate: Decimal = Field(ge=0, le=1, default=0)

class POIn(BaseModel):
    supplier_id: str
    warehouse_id: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[LineIn] = Field(min_length=1)
    notes: str | None = None

@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE, "environment": ENVIRONMENT}

@app.post("/auth/register", status_code=201)
def register(x: Register):
    with Session(engine) as db:
        if db.scalar(select(Tenant).where(Tenant.code == x.tenant_code)):
            raise HTTPException(409, "TENANT_CODE_TAKEN_USE_INVITATION")
        email = x.email.strip().lower()
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "EMAIL_ALREADY_REGISTERED")
        tenant = Tenant(id=str(uuid.uuid4()), code=x.tenant_code, name=x.tenant_name)
        db.add(tenant)
        db.flush()
        user = User(id=str(uuid.uuid4()), tenant_id=tenant.id, email=email, display_name=x.display_name, password_hash=pwd.hash(x.password), roles=["admin"])
        db.add(user)
        db.commit()
        return {"data": {"id": user.id, "tenant_id": tenant.id, "email": user.email, "roles": user.roles}}

@app.post("/auth/login")
def login(x: Login):
    email = x.email.strip().lower()
    client_key = f"login-fail:{email}:{os.getenv('CLIENT_IP', 'unknown')}"
    try:
        if rds and int(rds.get(client_key) or 0) >= 5:
            raise HTTPException(429, "INVALID_CREDENTIALS")
    except HTTPException:
        raise
    except Exception:
        pass
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user or not pwd.verify(x.password, user.password_hash):
            try:
                if rds:
                    count = rds.incr(client_key)
                    if count == 1:
                        rds.expire(client_key, 900)
            except Exception:
                pass
            raise HTTPException(401, "INVALID_CREDENTIALS")
        try:
            if rds:
                rds.delete(client_key)
        except Exception:
            pass
        token = jwt.encode({"sub": user.id, "tenant_id": user.tenant_id, "roles": user.roles, "iss": "madar-auth", "aud": "madar-api", "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, JWT_SECRET, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer", "roles": user.roles}

@app.post("/auth/invitations", status_code=201)
def create_invitation(x: InvitationIn, c=Depends(require_roles("admin"))):
    raw = secrets.token_urlsafe(32)
    with Session(engine) as db:
        invitation = Invitation(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], email=x.email.strip().lower(), role=x.role, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(hours=72))
        db.add(invitation)
        db.commit()
        return {"data": {"id": invitation.id, "email": invitation.email, "role": invitation.role, "expiresAt": invitation.expires_at.isoformat(), "token": raw}}

@app.post("/auth/accept-invitation", status_code=201)
def accept_invitation(x: AcceptInvitation):
    token_hash = hashlib.sha256(x.token.encode()).hexdigest()
    with Session(engine) as db:
        invite = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash).with_for_update())
        if not invite or invite.used_at or invite.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            raise HTTPException(400, "INVITATION_INVALID_OR_EXPIRED")
        if db.scalar(select(User).where(User.email == invite.email)):
            raise HTTPException(409, "EMAIL_ALREADY_REGISTERED")
        user = User(id=str(uuid.uuid4()), tenant_id=invite.tenant_id, email=invite.email, display_name=x.display_name, password_hash=pwd.hash(x.password), roles=[invite.role])
        db.add(user)
        invite.used_at = datetime.now(timezone.utc)
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
            raise HTTPException(409, "SUPPLIER_CODE_ALREADY_EXISTS")
        return {"data": {"id": s.id, **x.model_dump(), "status": s.status}}

@app.get("/suppliers")
def suppliers(c=Depends(auth)):
    with Session(engine) as db:
        return {"data": [{"id": s.id, "supplierCode": s.supplier_code, "legalName": s.legal_name, "status": s.status} for s in db.scalars(select(Supplier).where(Supplier.tenant_id == c["tenant_id"])).all()]}

@app.post("/products", status_code=201)
def create_product(x: ProductIn, c=Depends(require_roles("admin", "purchasing", "inventory"))):
    with Session(engine) as db:
        p = Product(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], **x.model_dump())
        db.add(p)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "SKU_ALREADY_EXISTS")
        return {"data": {"id": p.id, **x.model_dump(mode="json")}}

@app.get("/products")
def products(c=Depends(auth)):
    with Session(engine) as db:
        return {"data": [{"id": p.id, "sku": p.sku, "name": p.name, "unitOfMeasure": p.unit_of_measure, "reorderPoint": str(p.reorder_point)} for p in db.scalars(select(Product).where(Product.tenant_id == c["tenant_id"]).order_by(Product.name)).all()]}

@app.post("/warehouses", status_code=201)
def create_warehouse(x: WarehouseIn, c=Depends(require_roles("admin", "inventory"))):
    with Session(engine) as db:
        w = Warehouse(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], **x.model_dump())
        db.add(w)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "WAREHOUSE_CODE_ALREADY_EXISTS")
        return {"data": {"id": w.id, **x.model_dump()}}

@app.get("/warehouses")
def warehouses(c=Depends(auth)):
    with Session(engine) as db:
        return {"data": [{"id": w.id, "code": w.code, "name": w.name} for w in db.scalars(select(Warehouse).where(Warehouse.tenant_id == c["tenant_id"]).order_by(Warehouse.code)).all()]}

@app.get("/inventory")
def inventory(warehouse_id: Optional[str] = None, product_id: Optional[str] = None, low_stock: bool = False, c=Depends(auth)):
    with Session(engine) as db:
        q = select(Inventory).where(Inventory.tenant_id == c["tenant_id"])
        if warehouse_id: q = q.where(Inventory.warehouse_id == warehouse_id)
        if product_id: q = q.where(Inventory.product_id == product_id)
        rows = []
        for i in db.scalars(q):
            p = db.scalar(select(Product).where(Product.id == i.product_id, Product.tenant_id == c["tenant_id"]))
            available = i.on_hand - i.reserved
            if low_stock and p and available > p.reorder_point: continue
            rows.append({"warehouseId": i.warehouse_id, "productId": i.product_id, "onHand": str(i.on_hand), "reserved": str(i.reserved), "available": str(available), "onOrder": str(i.on_order), "reorderPoint": str(p.reorder_point if p else 0)})
        return {"data": rows}

@app.post("/inventory/adjust", status_code=201)
def adjust(x: AdjustIn, key: Optional[str] = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "inventory"))):
    if x.movement_type != "adjustment" and x.quantity <= 0:
        raise HTTPException(422, "QUANTITY_MUST_BE_POSITIVE")
    if x.movement_type == "adjustment" and x.quantity == 0:
        raise HTTPException(422, "ADJUSTMENT_CANNOT_BE_ZERO")
    body = x.model_dump(mode="json")
    with Session(engine) as db:
        row, old = claim_idem(db, key, c["tenant_id"], "inventory/adjust", body)
        if old: return old
        p = db.scalar(select(Product).where(Product.id == x.product_id, Product.tenant_id == c["tenant_id"]))
        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))
        if not p or not w: raise HTTPException(404, "RESOURCE_NOT_FOUND")
        i = db.scalar(select(Inventory).where(Inventory.warehouse_id == x.warehouse_id, Inventory.product_id == x.product_id, Inventory.tenant_id == c["tenant_id"]).with_for_update())
        if not i:
            i = Inventory(warehouse_id=x.warehouse_id, product_id=x.product_id, tenant_id=c["tenant_id"], on_hand=0, reserved=0, on_order=0)
            db.add(i)
            db.flush()
        if x.movement_type == "receipt":
            i.on_hand += x.quantity
        elif x.movement_type == "adjustment":
            if i.on_hand + x.quantity < i.reserved: raise HTTPException(409, "BELOW_RESERVED_STOCK")
            i.on_hand += x.quantity
        elif i.on_hand - i.reserved < x.quantity:
            raise HTTPException(409, "INSUFFICIENT_AVAILABLE_STOCK")
        else:
            i.on_hand -= x.quantity
        emit(db, c["tenant_id"], "supply.inventory.adjusted.v1", x.product_id, body)
        out = {"data": {"warehouseId": x.warehouse_id, "productId": x.product_id, "onHand": str(i.on_hand), "reserved": str(i.reserved), "available": str(i.on_hand - i.reserved)}}
        finish_idem(row, out)
        db.commit()
        return out

@app.post("/purchase-orders", status_code=201)
def create_po(x: POIn, key: Optional[str] = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "purchasing"))):
    body = x.model_dump(mode="json")
    with Session(engine) as db:
        row, old = claim_idem(db, key, c["tenant_id"], "purchase-orders", body)
        if old: return old
        s = db.scalar(select(Supplier).where(Supplier.id == x.supplier_id, Supplier.tenant_id == c["tenant_id"]))
        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))
        ids = {l.product_id for l in x.lines}
        products_found = {p.id for p in db.scalars(select(Product).where(Product.tenant_id == c["tenant_id"], Product.id.in_(ids)))}
        if not s or not w: raise HTTPException(404, "RESOURCE_NOT_FOUND")
        if len(products_found) != len(ids): raise HTTPException(404, "PRODUCT_NOT_FOUND")
        po = PurchaseOrder(id=str(uuid.uuid4()), tenant_id=c["tenant_id"], po_number=f"PO-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}", supplier_id=x.supplier_id, warehouse_id=x.warehouse_id, currency=x.currency.upper(), created_by=c["sub"])
        db.add(po); db.flush(); subtotal = Decimal(0); lines = []
        for n, l in enumerate(x.lines, 1):
            subtotal += l.ordered_qty * l.unit_price
            line = POLine(id=str(uuid.uuid4()), purchase_order_id=po.id, line_no=n, **l.model_dump())
            db.add(line); lines.append({"id": line.id, "lineNo": n, "productId": line.product_id, "orderedQty": str(line.ordered_qty), "unitPrice": str(line.unit_price)})
        po.subtotal = subtotal; po.tax_total = sum((l.ordered_qty * l.unit_price * l.tax_rate for l in x.lines), Decimal(0)); po.total = po.subtotal + po.tax_total
        emit(db, c["tenant_id"], "supply.purchase-order.created.v1", po.id, {"poId": po.id, "poNumber": po.po_number, "status": po.status, "total": money(po.total), "lines": lines})
        out = {"data": {"id": po.id, "poNumber": po.po_number, "status": po.status, "supplierId": po.supplier_id, "warehouseId": po.warehouse_id, "subtotal": money(po.subtotal), "taxTotal": money(po.tax_total), "total": money(po.total), "lines": lines}}
        finish_idem(row, out); db.commit(); return out

@app.get("/purchase-orders")
def list_po(c=Depends(auth)):
    with Session(engine) as db:
        return {"data": [{"id": p.id, "poNumber": p.po_number, "status": p.status, "total": money(p.total), "supplierId": p.supplier_id, "warehouseId": p.warehouse_id} for p in db.scalars(select(PurchaseOrder).where(PurchaseOrder.tenant_id == c["tenant_id"]).order_by(PurchaseOrder.created_at.desc())).all()]}

def transition_po(po_id, target, roles, c, key=None):
    with Session(engine) as db:
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == c["tenant_id"]).with_for_update())
        if not po: raise HTTPException(404, "PURCHASE_ORDER_NOT_FOUND")
        route = f"purchase-orders/{po_id}/{target}"
        body = {"id": po_id, "target": target}
        row, old = (claim_idem(db, key, c["tenant_id"], route, body) if key else (None, None))
        if old: return old
        allowed = {"submit": {"draft": "pending_approval"}, "approve": {"pending_approval": "approved"}, "receive": {"approved": "received"}}
        if po.status not in allowed[target]: raise HTTPException(409, "INVALID_PURCHASE_ORDER_TRANSITION")
        po.status = allowed[target]
        if target == "approve":
            for line in db.scalars(select(POLine).where(POLine.purchase_order_id == po.id)):
                inv = db.scalar(select(Inventory).where(Inventory.warehouse_id == po.warehouse_id, Inventory.product_id == line.product_id, Inventory.tenant_id == c["tenant_id"]).with_for_update())
                if not inv:
                    inv = Inventory(warehouse_id=po.warehouse_id, product_id=line.product_id, tenant_id=c["tenant_id"], on_hand=0, reserved=0, on_order=0); db.add(inv); db.flush()
                inv.on_order += line.ordered_qty
        elif target == "receive":
            for line in db.scalars(select(POLine).where(POLine.purchase_order_id == po.id)):
                inv = db.scalar(select(Inventory).where(Inventory.warehouse_id == po.warehouse_id, Inventory.product_id == line.product_id, Inventory.tenant_id == c["tenant_id"]).with_for_update())
                if not inv or inv.on_order < line.ordered_qty: raise HTTPException(409, "INVALID_ON_ORDER_BALANCE")
                inv.on_order -= line.ordered_qty; inv.on_hand += line.ordered_qty
        emit(db, c["tenant_id"], f"supply.purchase-order.{target}.v1", po.id, {"poId": po.id, "status": po.status})
        out = {"data": {"id": po.id, "poNumber": po.po_number, "status": po.status}}
        if row: finish_idem(row, out)
        db.commit(); return out

@app.post("/purchase-orders/{po_id}/submit")
def submit_po(po_id: str, c=Depends(require_roles("admin", "purchasing"))):
    return transition_po(po_id, "submit", ("admin", "purchasing"), c)

@app.post("/purchase-orders/{po_id}/approve")
def approve_po(po_id: str, c=Depends(require_roles("admin"))):
    return transition_po(po_id, "approve", ("admin",), c)

@app.post("/purchase-orders/{po_id}/receive")
def receive_po(po_id: str, key: Optional[str] = Header(None, alias="Idempotency-Key"), c=Depends(require_roles("admin", "inventory"))):
    return transition_po(po_id, "receive", ("admin", "inventory"), c, key)
