from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from ninja import Field, Schema


class Pagination(Schema):
    skip: Annotated[int, Field(description="Number of items to skip")] = 0
    limit: Annotated[int, Field(description="Max number of items to return")] = 10
    sort_by: Annotated[str | None, Field(description="Field to sort by")] = None


class ItemId(Schema):
    item_id: Annotated[int, Field(description="ID of the item")]

    def __eq__(self, other):
        return self.item_id == other


class Item(Schema):
    id: int
    name: str
    description: str | None = None
    price: float
    tags: list[str] = []


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CASH_ON_DELIVERY = "cash_on_delivery"


class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    FOOD = "food"
    BOOKS = "books"
    OTHER = "other"


class ProductVariant(Schema):
    sku: str = Field(..., description="Stock keeping unit code")
    color: str | None = Field(None, description="Color variant")
    size: str | None = Field(None, description="Size variant")
    weight: float | None = Field(None, description="Weight in kg", gt=0)
    dimensions: dict[str, float] | None = Field(None, description="Dimensions in cm (length, width, height)")
    in_stock: bool = Field(True, description="Whether this variant is in stock")
    stock_count: int | None = Field(None, description="Number of items in stock", ge=0)


class Address(Schema):
    street: str
    city: str
    state: str
    postal_code: str
    country: str
    is_primary: bool = False


class CustomerTier(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    VIP = "vip"


class Customer(Schema):
    id: UUID
    email: str
    full_name: str
    phone: str | None = Field(None, min_length=10, max_length=15)
    tier: CustomerTier = CustomerTier.STANDARD
    addresses: list[Address] = []
    is_active: bool = True
    created_at: datetime
    last_login: datetime | None = None
    preferences: dict[str, Any] = {}
    consent: dict[str, bool] = {}


class Product(Schema):
    id: UUID
    name: str
    description: str
    category: ProductCategory
    price: float = Field(..., gt=0)
    discount_percent: float | None = Field(None, ge=0, le=100)
    tax_rate: float | None = Field(None, ge=0, le=100)
    variants: list[ProductVariant] = []
    tags: list[str] = []
    image_urls: list[str] = []
    rating: float | None = Field(None, ge=0, le=5)
    review_count: int = Field(0, ge=0)
    created_at: datetime
    updated_at: datetime | None = None
    is_available: bool = True
    metadata: dict[str, Any] = {}


class OrderItem(Schema):
    product_id: UUID
    variant_sku: str | None = None
    quantity: int = Field(..., gt=0)
    unit_price: float
    discount_amount: float = 0
    total: float


class PaymentDetails(Schema):
    method: PaymentMethod
    transaction_id: str | None = None
    status: str
    amount: float
    currency: str = "USD"
    paid_at: datetime | None = None


class OrderRequest(Schema):
    customer_id: UUID
    items: list[OrderItem]
    shipping_address_id: UUID
    billing_address_id: UUID | None = None
    payment_method: PaymentMethod
    notes: str | None = None
    use_loyalty_points: bool = False


class OrderResponse(Schema):
    id: UUID
    customer_id: UUID
    status: OrderStatus = OrderStatus.PENDING
    items: list[OrderItem]
    shipping_address: Address
    billing_address: Address
    payment: PaymentDetails
    subtotal: float
    shipping_cost: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    tracking_number: str | None = None
    estimated_delivery: date | None = None
    created_at: datetime
    updated_at: datetime | None = None
    notes: str | None = None
    metadata: dict[str, Any] = {}


class PaginatedResponse(Schema):
    items: list[Any]
    total: int
    page: int
    size: int
    pages: int


class ErrorResponse(Schema):
    status_code: int
    message: str
    details: dict[str, Any] | None = None
