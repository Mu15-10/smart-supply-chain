import hashlib, json, os, threading, uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional

import jwt
import redis
from fastapi import Depends, FastAPI, Header, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from pymongo import MongoClient
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, create_engine, select
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

class Base(DeclarativeBase): pass
class Tenant(Base):
    __tablename__="tenants"; id:Mapped[str]=mapped_column(String(36),primary_key=True); code:Mapped[str]=mapped_column(String(80),unique=True,index=True); name:Mapped[str]=mapped_column(String(200))
class User(Base):
    __tablename__="users"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); email:Mapped[str]=mapped_column(String(255),index=True); display_name:Mapped[str]=mapped_column(String(200)); password_hash:Mapped[str]=mapped_column(String(255)); roles:Mapped[list]=mapped_column(JSON,default=lambda:["viewer"])
class Supplier(Base):
    __tablename__="suppliers"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36),index=True); supplier_code:Mapped[str]=mapped_column(String(80)); legal_name:Mapped[str]=mapped_column(String(200)); status:Mapped[str]=mapped_column(String(30),default="active"); lead_time_days:Mapped[int]=mapped_column(Integer,default=0)
class Warehouse(Base):
    __tablename__="warehouses"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36),index=True); code:Mapped[str]=mapped_column(String(80)); name:Mapped[str]=mapped_column(String(200))
class Product(Base):
    __tablename__="products"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36),index=True); sku:Mapped[str]=mapped_column(String(80)); name:Mapped[str]=mapped_column(String(200)); unit_of_measure:Mapped[str]=mapped_column(String(30),default="unit"); reorder_point:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0)
class Inventory(Base):
    __tablename__="inventory_balances"; warehouse_id:Mapped[str]=mapped_column(String(36),primary_key=True); product_id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36),index=True); on_hand:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); reserved:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); on_order:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); updated_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))
class PurchaseOrder(Base):
    __tablename__="purchase_orders"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36),index=True); po_number:Mapped[str]=mapped_column(String(80)); supplier_id:Mapped[str]=mapped_column(String(36)); warehouse_id:Mapped[str]=mapped_column(String(36)); status:Mapped[str]=mapped_column(String(30),default="draft"); currency:Mapped[str]=mapped_column(String(3)); subtotal:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); tax_total:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); total:Mapped[Decimal]=mapped_column(Numeric(18,4),default=0); created_by:Mapped[str]=mapped_column(String(36)); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class POLine(Base):
    __tablename__="purchase_order_lines"; id:Mapped[str]=mapped_column(String(36),primary_key=True); purchase_order_id:Mapped[str]=mapped_column(ForeignKey("purchase_orders.id")); product_id:Mapped[str]=mapped_column(String(36)); line_no:Mapped[int]=mapped_column(Integer); ordered_qty:Mapped[Decimal]=mapped_column(Numeric(18,4)); unit_price:Mapped[Decimal]=mapped_column(Numeric(18,4)); tax_rate:Mapped[Decimal]=mapped_column(Numeric(8,5),default=0)
class Outbox(Base):
    __tablename__="outbox_events"; id:Mapped[str]=mapped_column(String(36),primary_key=True); tenant_id:Mapped[str]=mapped_column(String(36)); event_type:Mapped[str]=mapped_column(String(120)); aggregate_id:Mapped[str]=mapped_column(String(36)); payload:Mapped[dict]=mapped_column(JSON); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))

pwd=CryptContext(schemes=["pbkdf2_sha256"],deprecated="auto")
try: rds=redis.from_url(os.getenv("REDIS_URL","redis://localhost:6379/0"),decode_responses=True)
except Exception: rds=None
try: mongo=MongoClient(os.getenv("MONGO_URL","mongodb://localhost:27017"),serverSelectionTimeoutMS=500).supply_events
except Exception: mongo=None
app=FastAPI(title=f"Madar Supply Control - {SERVICE} service",version="0.2.0")
IDEM_CACHE={}; IDEM_LOCK=threading.RLock()

@app.on_event("startup")
def startup(): Base.metadata.create_all(engine)
def emit(db,tenant_id,event_type,aggregate_id,payload):
    event_id=str(uuid.uuid4()); db.add(Outbox(id=event_id,tenant_id=tenant_id,event_type=event_type,aggregate_id=aggregate_id,payload=payload))
    try:
        if mongo is not None: mongo.events.insert_one({"_id":event_id,"tenantId":tenant_id,"type":event_type,"aggregateId":aggregate_id,"data":payload,"occurredAt":datetime.now(timezone.utc)})
    except Exception: pass
    return event_id
def auth(authorization:Optional[str]=Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"UNAUTHENTICATED")
    try: return jwt.decode(authorization[7:],JWT_SECRET,algorithms=["HS256"],audience="madar-api",issuer="madar-auth",options={"require":["sub","tenant_id","roles","exp","iss","aud"]})
    except Exception: raise HTTPException(401,"UNAUTHENTICATED")
def require_roles(*allowed_roles):
    def dependency(c=Depends(auth)):
        if not set(c.get("roles",[])) & set(allowed_roles): raise HTTPException(403,"FORBIDDEN")
        return c
    return dependency
def idem_key(key,tenant,route,body):
    if not key or len(key)>200: raise HTTPException(400,"Idempotency-Key header is required")
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,default=str).encode()).hexdigest(); return f"idem:{tenant}:{route}:{key}",digest
def get_idem(key,tenant,route,body):
    cache_key,digest=idem_key(key,tenant,route,body)
    with IDEM_LOCK:
        if rds:
            try:
                old=rds.get(cache_key)
                if old:
                    data=json.loads(old)
                    if data["hash"]!=digest: raise HTTPException(409,"IDEMPOTENCY_KEY_REUSED")
                    return cache_key,digest,data["response"]
            except HTTPException: raise
            except Exception: pass
        old=IDEM_CACHE.get(cache_key)
        if old:
            if old["hash"]!=digest: raise HTTPException(409,"IDEMPOTENCY_KEY_REUSED")
            return cache_key,digest,old["response"]
    return cache_key,digest,None
def save_idem(cache_key,digest,response):
    data={"hash":digest,"response":response}
    with IDEM_LOCK:
        if rds:
            try: rds.setex(cache_key,86400,json.dumps(data,default=str))
            except Exception: pass
        IDEM_CACHE[cache_key]=data

class Register(BaseModel):
    email:str; password:str=Field(min_length=8); display_name:str; tenant_code:str=Field(min_length=2,max_length=80,pattern=r"^[a-zA-Z0-9_-]+$"); tenant_name:str=Field(min_length=2,max_length=200)
class Login(BaseModel): email:str; password:str
class SupplierIn(BaseModel): supplier_code:str; legal_name:str; lead_time_days:int=Field(ge=0,default=0)
class ProductIn(BaseModel): sku:str; name:str; unit_of_measure:str="unit"; reorder_point:Decimal=Field(ge=0,default=0)
class WarehouseIn(BaseModel): code:str; name:str
class AdjustIn(BaseModel): warehouse_id:str; product_id:str; quantity:Decimal=Field(gt=0); movement_type:Literal["receipt","adjustment","issue"]="receipt"
class LineIn(BaseModel): product_id:str; ordered_qty:Decimal=Field(gt=0); unit_price:Decimal=Field(ge=0); tax_rate:Decimal=Field(ge=0,le=1,default=0)
class POIn(BaseModel): supplier_id:str; warehouse_id:str; currency:str=Field(default="USD",min_length=3,max_length=3); lines:list[LineIn]=Field(min_length=1); notes:str|None=None

@app.get("/health")
def health(): return {"status":"ok","service":SERVICE,"environment":ENVIRONMENT}
@app.post("/auth/register",status_code=201)
def register(x:Register):
    with Session(engine) as db:
        if db.scalar(select(Tenant).where(Tenant.code==x.tenant_code)): raise HTTPException(409,"TENANT_CODE_TAKEN_USE_INVITATION")
        tenant=Tenant(id=str(uuid.uuid4()),code=x.tenant_code,name=x.tenant_name); db.add(tenant); db.flush()
        user=User(id=str(uuid.uuid4()),tenant_id=tenant.id,email=x.email.strip().lower(),display_name=x.display_name,password_hash=pwd.hash(x.password),roles=["admin"]); db.add(user); db.commit()
        return {"data":{"id":user.id,"tenant_id":tenant.id,"email":user.email,"roles":user.roles}}
@app.post("/auth/login")
def login(x:Login):
    with Session(engine) as db:
        user=db.scalar(select(User).where(User.email==x.email.strip().lower()))
        if not user or not pwd.verify(x.password,user.password_hash): raise HTTPException(401,"INVALID_CREDENTIALS")
        token=jwt.encode({"sub":user.id,"tenant_id":user.tenant_id,"roles":user.roles,"iss":"madar-auth","aud":"madar-api","exp":datetime.now(timezone.utc)+timedelta(hours=8)},JWT_SECRET,algorithm="HS256")
        return {"access_token":token,"token_type":"bearer"}
@app.post("/suppliers",status_code=201)
def create_supplier(x:SupplierIn,c=Depends(require_roles("admin","purchasing"))):
    with Session(engine) as db:
        s=Supplier(id=str(uuid.uuid4()),tenant_id=c["tenant_id"],**x.model_dump()); db.add(s); db.commit(); return {"data":{"id":s.id,**x.model_dump(),"status":s.status}}
@app.get("/suppliers")
def suppliers(c=Depends(auth)):
    with Session(engine) as db: return {"data":[{"id":s.id,"supplierCode":s.supplier_code,"legalName":s.legal_name,"status":s.status} for s in db.scalars(select(Supplier).where(Supplier.tenant_id==c["tenant_id"])).all()]}
@app.post("/products",status_code=201)
def create_product(x:ProductIn,c=Depends(require_roles("admin","purchasing","inventory"))):
    with Session(engine) as db:
        p=Product(id=str(uuid.uuid4()),tenant_id=c["tenant_id"],**x.model_dump()); db.add(p); db.commit(); return {"data":{"id":p.id,**x.model_dump(mode="json")}}
@app.post("/warehouses",status_code=201)
def create_warehouse(x:WarehouseIn,c=Depends(require_roles("admin","inventory"))):
    with Session(engine) as db:
        w=Warehouse(id=str(uuid.uuid4()),tenant_id=c["tenant_id"],**x.model_dump()); db.add(w); db.commit(); return {"data":{"id":w.id,**x.model_dump()}}
@app.get("/inventory")
def inventory(warehouse_id:Optional[str]=None,product_id:Optional[str]=None,low_stock:bool=False,c=Depends(auth)):
    with Session(engine) as db:
        q=select(Inventory).where(Inventory.tenant_id==c["tenant_id"])
        if warehouse_id:q=q.where(Inventory.warehouse_id==warehouse_id)
        if product_id:q=q.where(Inventory.product_id==product_id)
        rows=[]
        for i in db.scalars(q):
            p=db.scalar(select(Product).where(Product.id==i.product_id,Product.tenant_id==c["tenant_id"])); available=i.on_hand-i.reserved
            if low_stock and p and available>p.reorder_point: continue
            rows.append({"warehouseId":i.warehouse_id,"productId":i.product_id,"onHand":str(i.on_hand),"reserved":str(i.reserved),"available":str(available),"onOrder":str(i.on_order),"reorderPoint":str(p.reorder_point if p else 0)})
        return {"data":rows}
@app.post("/inventory/adjust",status_code=201)
def adjust(x:AdjustIn,key:Optional[str]=Header(None,alias="Idempotency-Key"),c=Depends(require_roles("admin","inventory"))):
    body=x.model_dump(mode="json"); cache_key,digest,old=get_idem(key,c["tenant_id"],"inventory/adjust",body)
    if old:return old
    with IDEM_LOCK:
        with Session(engine) as db:
            p=db.scalar(select(Product).where(Product.id==x.product_id,Product.tenant_id==c["tenant_id"])); w=db.scalar(select(Warehouse).where(Warehouse.id==x.warehouse_id,Warehouse.tenant_id==c["tenant_id"]))
            if not p or not w: raise HTTPException(404,"RESOURCE_NOT_FOUND")
            i=db.get(Inventory,{"warehouse_id":x.warehouse_id,"product_id":x.product_id})
            if i and i.tenant_id!=c["tenant_id"]: raise HTTPException(404,"RESOURCE_NOT_FOUND")
            if not i:i=Inventory(warehouse_id=x.warehouse_id,product_id=x.product_id,tenant_id=c["tenant_id"],on_hand=0,reserved=0,on_order=0);db.add(i)
            if x.movement_type in ("receipt","adjustment"): i.on_hand+=x.quantity
            elif i.on_hand-i.reserved<x.quantity: raise HTTPException(409,"INSUFFICIENT_AVAILABLE_STOCK")
            else:i.on_hand-=x.quantity
            emit(db,c["tenant_id"],"supply.inventory.adjusted.v1",x.product_id,body);db.commit(); out={"data":{"warehouseId":x.warehouse_id,"productId":x.product_id,"onHand":str(i.on_hand),"reserved":str(i.reserved),"available":str(i.on_hand-i.reserved)}};save_idem(cache_key,digest,out);return out
@app.post("/purchase-orders",status_code=201)
def create_po(x:POIn,key:Optional[str]=Header(None,alias="Idempotency-Key"),c=Depends(require_roles("admin","purchasing"))):
    body=x.model_dump(mode="json"); cache_key,digest,old=get_idem(key,c["tenant_id"],"purchase-orders",body)
    if old:return old
    with IDEM_LOCK:
        with Session(engine) as db:
            s=db.scalar(select(Supplier).where(Supplier.id==x.supplier_id,Supplier.tenant_id==c["tenant_id"])); w=db.scalar(select(Warehouse).where(Warehouse.id==x.warehouse_id,Warehouse.tenant_id==c["tenant_id"]))
            ids={l.product_id for l in x.lines}; products={p.id:p for p in db.scalars(select(Product).where(Product.tenant_id==c["tenant_id"],Product.id.in_(ids)))}
            if not s or not w: raise HTTPException(404,"RESOURCE_NOT_FOUND")
            if len(products)!=len(ids): raise HTTPException(404,"PRODUCT_NOT_FOUND")
            po=PurchaseOrder(id=str(uuid.uuid4()),tenant_id=c["tenant_id"],po_number=f"PO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",supplier_id=x.supplier_id,warehouse_id=x.warehouse_id,currency=x.currency.upper(),created_by=c["sub"]);db.add(po);db.flush();subtotal=Decimal(0);lines=[]
            for n,l in enumerate(x.lines,1):
                subtotal+=l.ordered_qty*l.unit_price; line=POLine(id=str(uuid.uuid4()),purchase_order_id=po.id,line_no=n,**l.model_dump());db.add(line);lines.append({"id":line.id,"lineNo":n,"productId":line.product_id,"orderedQty":str(line.ordered_qty),"unitPrice":str(line.unit_price)})
            po.subtotal=subtotal;po.tax_total=sum((l.ordered_qty*l.unit_price*l.tax_rate for l in x.lines),Decimal(0));po.total=po.subtotal+po.tax_total;emit(db,c["tenant_id"],"supply.purchase-order.created.v1",po.id,{"poId":po.id,"poNumber":po.po_number,"status":po.status,"total":str(po.total),"lines":lines});db.commit();out={"data":{"id":po.id,"poNumber":po.po_number,"status":po.status,"supplierId":po.supplier_id,"warehouseId":po.warehouse_id,"subtotal":str(po.subtotal),"taxTotal":str(po.tax_total),"total":str(po.total),"lines":lines}};save_idem(cache_key,digest,out);return out
@app.get("/purchase-orders")
def list_po(c=Depends(auth)):
    with Session(engine) as db:return {"data":[{"id":p.id,"poNumber":p.po_number,"status":p.status,"total":str(p.total),"supplierId":p.supplier_id} for p in db.scalars(select(PurchaseOrder).where(PurchaseOrder.tenant_id==c["tenant_id"]).order_by(PurchaseOrder.created_at.desc())).all()]}
