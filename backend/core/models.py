"""
Database Models
===============
SQLAlchemy table definitions for the grocery price comparison app.
Supports SQLite (development) and PostgreSQL (production) via config.
"""

import hashlib
from datetime import datetime, timezone
UTC = timezone.utc
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Store(Base):
    """Supermarket store registry (Jumbo, Santa Isabel, Lider, etc.)."""

    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)      # "Jumbo"
    slug = Column(String(50), unique=True, nullable=False)        # "jumbo"
    base_url = Column(String(255), nullable=False)                # "https://www.jumbo.cl"
    logo_url = Column(String(500), default="")

    store_products = relationship("StoreProduct", back_populates="store")
    branches = relationship("Branch", back_populates="store")

    def __repr__(self):
        return f"<Store(name='{self.name}')"



class Location(Base):
    """Geographic region or city registry."""

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)      # "Santiago"
    region_code = Column(String(10), nullable=True)             # "RM"

    branches = relationship("Branch", back_populates="location")

    def __repr__(self):
        return f"<Location(name='{self.name}')>"


class Branch(Base):
    """
    Physical branch of a supermarket chain.
    e.g. 'Jumbo Costanera' with external_store_id='jumboclj411'.
    branch_id is optional on StoreProduct — existing data remains unaffected.
    """

    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    name = Column(String(200), nullable=False)          # "Jumbo Costanera"
    city = Column(String(100), default="")              # "Santiago" (de-normalized copy)
    region = Column(String(100), default="")            # "RM"
    address = Column(Text, nullable=True)               # Physical address
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    external_store_id = Column(String(100), nullable=False)  # API key e.g. "jumboclj411"
    is_active = Column(Boolean, default=True)
    verified_at = Column(DateTime, nullable=True) # Timestamp of last FluxEngine audit

    __table_args__ = (
        UniqueConstraint("store_id", "external_store_id", name="uq_branch_store_external"),
    )

    store = relationship("Store", back_populates="branches")
    location = relationship("Location", back_populates="branches")
    store_products = relationship("StoreProduct", back_populates="branch")
    prices = relationship("Price", back_populates="branch")

    @property
    def store_name(self) -> str:
        return self.store.name if self.store else ""

    def __repr__(self):
        return f"<Branch(name='{self.name}', store_id={self.store_id})>"


class Product(Base):
    """
    Canonical (unified) product entry.
    Represents the real-world product independent of any store.
    Multiple StoreProducts can link to the same Product.
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(Text, nullable=False, index=True)      # Cleaned name
    brand = Column(String(200), default="")
    category = Column(String(200), default="")                     # Top-level category
    category_path = Column(Text, default="")                       # Full path
    weight_value = Column(Float, nullable=True)                    # e.g., 397
    weight_unit = Column(String(10), nullable=True)                # e.g., "g"
    image_url = Column(Text, default="")                           # Best available image
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    matches = relationship("ProductMatch", back_populates="product")
    insights = relationship("PriceInsight", back_populates="product")
    preferences = relationship("UserPreference", back_populates="product")

    def __repr__(self):
        return f"<Product(name='{self.canonical_name[:40]}', brand='{self.brand}')>"


class StoreProduct(Base):
    """
    Per-store product instance.
    This is the product as it appears in a specific supermarket with its
    store-specific name, ID, URL, and availability.
    """

    __tablename__ = "store_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)   # Null = chain-wide
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # Null until matched
    external_id = Column(String(200), nullable=False, index=True)  # Store's own product ID
    sku_id = Column(String(200), default="")
    name = Column(Text, nullable=False, index=True)                # Original name from store
    brand = Column(String(200), default="", index=True)
    slug = Column(String(500), default="")
    product_url = Column(Text, default="")
    image_url = Column(Text, default="")
    category_path = Column(Text, default="")
    top_category = Column(String(200), default="")
    measurement_unit = Column(String(20), default="")
    in_stock = Column(Boolean, default=True, index=True)
    content_hash = Column(String(32), nullable=True)               # MD5 of scraped metadata
    last_seen = Column(DateTime, default=lambda: datetime.now(UTC))
    last_sync = Column(DateTime, default=lambda: datetime.now(UTC), index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("store_id", "external_id", name="uq_store_external_id"),
    )

    store = relationship("Store", back_populates="store_products")
    branch = relationship("Branch", back_populates="store_products")
    product = relationship("Product")
    prices = relationship("Price", back_populates="store_product", order_by="Price.scraped_at.desc()")
    matches = relationship("ProductMatch", back_populates="store_product")

    @property
    def latest_price(self):
        """Return the most recent price entry, or None."""
        return self.prices[0] if self.prices else None

    def __repr__(self):
        return f"<StoreProduct(store_id={self.store_id}, name='{self.name[:40]}')>"


class Price(Base):
    """
    Price snapshot at a point in time.
    Allows tracking price history for a product at a specific store.
    """

    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_product_id = Column(Integer, ForeignKey("store_products.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True) # Null = chain-wide fallback
    price = Column(Float, nullable=True)                           # Current selling price
    list_price = Column(Float, nullable=True)                      # Original/list price
    promo_price = Column(Float, nullable=True)                     # Promotional price
    promo_description = Column(Text, default="")
    has_discount = Column(Boolean, default=False, index=True)
    savings_amount = Column(Float, nullable=True)                   # list_price - price
    discount_percent = Column(Integer, nullable=True)               # % off list_price
    scraped_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False, index=True)

    store_product = relationship("StoreProduct", back_populates="prices")
    branch = relationship("Branch", back_populates="prices")

    def __repr__(self):
        return f"<Price(store_product_id={self.store_product_id}, price={self.price})>"


class ProductMatch(Base):
    """
    Cross-store product matching link.
    Links a canonical Product to a StoreProduct with a confidence score.
    """

    __tablename__ = "product_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    store_product_id = Column(Integer, ForeignKey("store_products.id"), nullable=False)
    match_score = Column(Float, nullable=False)                    # 0.0 to 1.0
    match_method = Column(String(20), default="auto")              # "auto" or "manual"
    verified = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("product_id", "store_product_id", name="uq_product_store_match"),
    )

    product = relationship("Product", back_populates="matches")
    store_product = relationship("StoreProduct", back_populates="matches")

    def __repr__(self):
        return f"<ProductMatch(product_id={self.product_id}, score={self.match_score:.2f})>"


class PriceInsight(Base):
    """
    Consolidated price trends generated by the 'Dream System'.
    Stores metadata like 'Cheapest Store', 'Average Price', and 'Is Good Deal'.
    """

    __tablename__ = "price_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)
    last_consolidated = Column(DateTime, default=lambda: datetime.now(UTC))
    
    avg_price = Column(Float)
    min_price_all_time = Column(Float)
    max_price_all_time = Column(Float)
    cheapest_store_id = Column(Integer, ForeignKey("stores.id"))
    
    price_trend = Column(String(20), default="stable") # "falling", "rising", "stable"
    is_deal_now = Column(Boolean, default=False)
    deal_score = Column(Integer, default=0) # 0-100

    product = relationship("Product", back_populates="insights")
    cheapest_store = relationship("Store")

    def __repr__(self):
        return f"<PriceInsight(product_id={self.product_id}, deal={self.is_deal_now})>"


class Notification(Base):
    """
    Proactive alerts generated by KAIROS.
    user_id scopes notifications per user so each user sees only their own alerts.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), default="default_user", nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="price_drop") # "price_drop", "restock", "system"
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    link_url = Column(String(500), nullable=True)

    product = relationship("Product")

    def __repr__(self):
        return f"<Notification(user='{self.user_id}', title='{self.title[:20]}')>"


class UserPreference(Base):
    """
    Tracks products the user is interested in for proactive alerts.
    user_id allows multi-user favorites without cross-user conflicts.
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), default="default_user", nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    alert_threshold_price = Column(Float, nullable=True)
    notify_on_deal = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    product = relationship("Product", back_populates="preferences")

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_pref_product"),
    )

    def __repr__(self):
        return f"<UserPreference(user_id='{self.user_id}', product_id={self.product_id})>"


class BotState(Base):
    """
    Persistent memory for KAIROS agents.
    Tracks 'last_run' for different bot tasks (crawling, matching, etc).
    """

    __tablename__ = "bot_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_key = Column(String(100), unique=True, nullable=False) # e.g. "crawl:leche", "matching:all"
    last_run = Column(DateTime, default=lambda: datetime.now(UTC))
    meta_data = Column(Text, default="{}") # JSON metadata if needed

    def __repr__(self):
        return f"<BotState(task='{self.task_key}', last_run={self.last_run})>"


class UserAssistantState(Base):
    """
    Persistent memory for the KAIROS Conversational Assistant.
    Stores user budget, preferences, and last generated meal plan.
    Expires after 45 days of inactivity.
    """

    __tablename__ = "user_assistant_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), default="default_user", unique=True)
    
    budget = Column(Float, nullable=True)
    persons = Column(Integer, default=1)
    preferred_stores = Column(Text, default="[]") # JSON list of store slugs
    strategy = Column(String(50), default="cheapest") # "cheapest" or "single_store"
    
    last_plan_json = Column(Text, nullable=True)     # Cached last successful meal plan
    chat_history_json = Column(Text, nullable=True)  # JSON: [{role, content}, ...] últimas 20 rondas

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<UserAssistantState(user='{self.user_id}', budget={self.budget})>"


class BlockedIP(Base):
    """
    Persistent blacklist for Shield 3.1.
    """
    __tablename__ = "blocked_ips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String(50), unique=True, nullable=False)
    reason = Column(String(255), default="Suspicious Activity")
    blocked_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<BlockedIP(ip='{self.ip}', reason='{self.reason}')>"


class RateLimitState(Base):
    """
    Stateful rate limiting for Shield 4.0.
    Identifies clients by fingerprint (header hash) to prevent rotation attacks.
    """
    __tablename__ = "rate_limit_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), unique=True, nullable=False, index=True)
    ip = Column(String(50), index=True)
    request_count = Column(Integer, default=1)
    reset_at = Column(DateTime, nullable=False)
    last_request_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<RateLimitState(fingerprint='{self.fingerprint[:10]}', count={self.request_count})>"


class SecurityLog(Base):
    """
    Persistent audit log for all security events.
    """
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String(50), index=True)
    event_type = Column(String(50), nullable=False) # "RATE_LIMIT", "IPS_BLOCK", "AUTH_FAILURE", "THREAT"
    severity = Column(String(20), default="INFO")   # "INFO", "WARNING", "CRITICAL"
    details = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<SecurityLog(type='{self.event_type}', ip='{self.ip}')>"


class SecurityReport(Base):
    """
    Reportes del Security Audit Agent.
    Cada fila es un hallazgo con severidad, descripción y estado de corrección.
    """
    __tablename__ = "security_reports"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(UTC))
    severity        = Column(String(10), nullable=False)   # CRITICAL HIGH MEDIUM LOW INFO
    category        = Column(String(50), nullable=False)   # AUTH CONFIG EXPOSURE INJECTION INFRA
    title           = Column(String(200), nullable=False)
    description     = Column(Text, nullable=False)
    affected        = Column(String(100), default="")      # componente afectado
    auto_fixable    = Column(Boolean, default=False)
    fixed           = Column(Boolean, default=False)
    fixed_at        = Column(DateTime, nullable=True)
    fix_description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SecurityReport(severity='{self.severity}', title='{self.title[:40]}')>"


class PantryItem(Base):
    """
    Tracks items in the user's pantry/fridge to predict restocking needs.
    Generated when a user marks a product as 'purchased'.
    """
    __tablename__ = "pantry_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    last_purchased_at = Column(DateTime, default=lambda: datetime.now(UTC))
    purchase_count = Column(Integer, default=1)
    
    # Analytics for KAIROS
    average_days_between_purchases = Column(Float, default=14.0)
    estimated_depletion_at = Column(DateTime, nullable=True)
    
    # User status overrides
    is_active = Column(Boolean, default=True) # If false, user stopped tracking this
    current_stock_level = Column(String(20), default="full") # "full", "medium", "low", "empty"

    product = relationship("Product")

    def __repr__(self):
        return f"<PantryItem(product_id={self.product_id}, stock='{self.current_stock_level}')>"


class Feedback(Base):
    """
    Reportes de bugs, mejoras y sugerencias enviados por el usuario desde la app.
    El agente FeedbackAnalyzer lee los pendientes y genera un plan de acción con IA.
    """
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(20), nullable=False)           # 'bug', 'mejora', 'sugerencia'
    description = Column(Text, nullable=False)
    page_context = Column(String(200), nullable=True)   # URL o nombre de la pantalla
    status = Column(String(20), default="pending")      # 'pending', 'analyzed', 'resolved', 'dismissed'
    ai_plan = Column(Text, nullable=True)               # JSON: plan de acción generado por IA
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<Feedback(id={self.id}, type='{self.type}', status='{self.status}')>"


class IdeaAdmin(Base):
    """
    Ideas enviadas por el admin desde Discord para mejorar el sistema.
    """
    __tablename__ = "ideas_admin"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    idea        = Column(Text, nullable=False)
    status      = Column(String(20), default="pendiente")   # pendiente | en_progreso | implementada | descartada
    source      = Column(String(50), default="discord")     # discord | app
    created_at  = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at  = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<IdeaAdmin(id={self.id}, status='{self.status}')>"
