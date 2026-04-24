from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_validator, conint, conlist

class StoreOut(BaseModel):
    id: int
    name: str = ""
    slug: str = ""
    base_url: str = ""
    logo_url: str = ""

    class Config:
        from_attributes = True


class BranchOut(BaseModel):
    id: int
    store_id: int
    store_name: str = ""
    name: str = ""
    city: str = ""
    region: Optional[str] = None
    address: Optional[str] = None
    external_store_id: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None

    class Config:
        from_attributes = True


class PricePointOut(BaseModel):
    store_id: int
    store_name: str = ""
    store_slug: str = ""
    store_logo: str = ""
    price: Optional[float] = None
    list_price: Optional[float] = None
    promo_price: Optional[float] = None
    promo_description: str = ""
    has_discount: bool = False
    in_stock: bool = True
    product_url: str = ""
    last_sync: str = ""
    is_card_price: bool = False
    card_label: str = ""
    offer_type: str = "generic"
    club_price: Optional[float] = None
    unit_price: Optional[float] = None
    price_per_unit: Optional[float] = None   # $/100g o $/100ml normalizado
    unit_label: Optional[str] = None         # "$/100g", "$/100ml"
    is_stale: bool = False                   # datos > 6h sin refresh


class PriceHistoryOut(BaseModel):
    price: Optional[float]
    scraped_at: str


class PriceInsightOut(BaseModel):
    avg_price: Optional[float]
    min_price_all_time: Optional[float]
    max_price_all_time: Optional[float]
    price_trend: str
    is_deal_now: bool
    deal_score: int
    last_consolidated: str


class ProductOut(BaseModel):
    id: int
    name: str = ""
    brand: str = ""
    category: str = ""
    image_url: str = ""
    weight_value: Optional[float] = None
    weight_unit: Optional[str] = None
    prices: List[PricePointOut] = []
    best_price: Optional[float] = None
    best_store: Optional[str] = None
    best_store_slug: Optional[str] = None
    price_insight: Optional[PriceInsightOut] = None
    is_favorite: bool = False


class ProductDetailOut(ProductOut):
    category_path: str = ""
    price_history: List[PriceHistoryOut] = []


class DealOut(BaseModel):
    product_id: int
    product_name: str = ""
    brand: str = ""
    category: str = ""
    image_url: str = ""
    store_name: str = ""
    store_slug: str = ""
    store_logo: str = ""
    price: Optional[float] = None
    current_price: Optional[float] = None  # alias de price para compatibilidad con clientes
    list_price: Optional[float] = None
    promo_price: Optional[float] = None
    promo_description: str = ""
    discount_percent: Optional[float] = None
    deal_score: int = 0
    product_url: str = ""


class CategoryOut(BaseModel):
    name: str
    product_count: int


class SearchResponse(BaseModel):
    results: List[ProductOut]
    total: int
    page: int
    page_size: int


class NotificationOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    title: str
    message: str
    type: str
    is_read: bool
    created_at: str
    link_url: Optional[str] = None


class PlanItemOut(BaseModel):
    product_id: int
    product_name: str
    store_name: str
    price: float


class PlanResponse(BaseModel):
    plan_type: str
    items_requested: int
    items_found: int
    estimated_total: float
    trip_count: int
    strategy: List[Dict[str, Any]]


class CartItem(BaseModel):
    product_id: conint(gt=0)
    name: str
    quantity: conint(ge=1, le=100) = 1

class OptimizeCartRequest(BaseModel):
    items: conlist(CartItem, min_length=1, max_length=100)


class ChatMessage(BaseModel):
    role: str # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class UnifiedResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


class PantryItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str = ""
    image_url: str = ""
    last_purchased_at: str
    purchase_count: int
    current_stock_level: str
    estimated_depletion_at: Optional[str] = None
    days_remaining: Optional[int] = None

    class Config:
        from_attributes = True


class PantryPurchaseRequest(BaseModel):
    product_id: int
    stock_level: str = "full"


class HistoricLowOut(BaseModel):
    product_id: int
    product_name: str = ""
    brand: str = ""
    image_url: str = ""
    store_name: str = ""
    store_slug: str = ""
    store_logo: str = ""
    price: Optional[float] = None
    min_price_all_time: Optional[float] = None
    deal_score: int = 0
