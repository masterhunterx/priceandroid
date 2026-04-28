
export interface PriceHistory {
  price: number;
  scraped_at: string;
}

export interface PricePoint {
  store_id: number;
  store_name: string;
  store_slug: string;
  store_logo: string;
  price: number | null;
  list_price: number | null;
  promo_price: number | null;
  promo_description: string;
  has_discount: boolean;
  in_stock: boolean;
  product_url: string;
  last_sync: string;
  is_card_price?: boolean;     // true si requiere tarjeta del supermercado
  card_label?: string;          // ej: 'Tarjeta Cencosud', 'Club Unimarc'
  offer_type?: 'card' | 'internet' | 'app' | 'generic';
  club_price?: number | null;
  unit_price?: number | null;
  price_per_unit?: number | null;  // $/100g o $/100ml normalizado
  unit_label?: string | null;      // "$/100g", "$/100ml"
  is_stale?: boolean;              // datos > 6h sin refresh (backend)
  // Compatibility for older mocks
  storeId?: string | number;
  originalPrice?: number | null;
  url?: string;
}

export interface PriceInsight {
  avg_price: number | null;
  min_price_all_time: number | null;
  max_price_all_time: number | null;
  price_trend: 'falling' | 'rising' | 'stable';
  is_deal_now: boolean;
  deal_score: number;
  last_consolidated: string;
}

export interface Product {
  // M2: el backend siempre retorna int — string | number causaba comparaciones con === que fallaban
  id: number;
  name: string;
  brand: string;
  category: string;
  category_path?: string;
  image_url: string;
  weight_value: number | null;
  weight_unit: string | null;
  unit?: string;
  description?: string;
  images?: string[];
  is_favorite?: boolean;
  prices: PricePoint[];
  best_price: number | null;
  best_store: string | null;
  best_store_slug: string | null;
  price_history?: PriceHistory[];
  price_insight?: PriceInsight | null;
}

export interface Notification {
  id: number;
  product_id?: number;
  title: string;
  message: string;
  type: 'price_drop' | 'restock' | 'system' | 'price_luca' | 'price_under_2k';
  is_read: boolean;
  created_at: string;
  link_url?: string;
}

export interface PlanningResult {
  plan_type: string;
  items_requested: number;
  items_found: number;
  estimated_total: number;
  trip_count: number;
  strategy: Array<{
    store_name: string;
    items: Array<{
      product_name: string;
      price: number;
    }>;
    subtotal: number;
  }>;
}

export interface Branch {
  id: number;
  store_id: number;
  store_name: string;
  name: string;
  city: string;
  // H4: backend BranchOut tiene region: Optional[str] = None — puede llegar null
  region?: string | null;
  address?: string | null;
  external_store_id: string;
  latitude?: number | null;
  longitude?: number | null;
  distance_km?: number | null;
}

export interface Deal {
  product_id: number;
  product_name: string;
  brand: string;
  category: string;
  image_url: string;
  store_name: string;
  store_slug: string;
  store_logo: string;
  price: number | null;
  list_price: number | null;
  promo_price: number | null;
  promo_description: string;
  discount_percent: number | null;
  // M1: deal_score existe en DealOut del backend pero faltaba en el tipo frontend
  deal_score: number;
  product_url: string;
  // Compatibility for older mocks
  productId?: string | number;
  discount?: string;
  title?: string;
  imageUrl?: string;
  storeLogo?: string;
}

export interface Category {
  id?: string | number;
  name: string;
  icon?: string;
  product_count?: number;
}

export interface Comuna {
  name: string;
  lat: number;
  lng: number;
  store_count: number;
  details?: string;
}

export interface LocationHierarchy {
  [region: string]: Comuna[];
}

export interface SearchSuggestion {
  term: string;
  type: 'product' | 'brand' | 'category';
  product_id?: number | null;
  store?: string;
  store_slug?: string;
  store_logo?: string;
}

export interface HistoricLow {
  product_id: number;
  product_name: string;
  min_price_all_time: number | null;
  image_url?: string;
  store_name: string;
  store_slug?: string;
  brand?: string;
  savings_pct?: number;
}
