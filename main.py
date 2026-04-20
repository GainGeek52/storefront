from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

try:
    from data.catalog_db import get_products_for_tenant as _catalog_products
except ImportError:
    _catalog_products = None

try:
    from tenants.loader import get_default_tenant as _default_tenant_loader
    from tenants.loader import load_tenant as _tenant_loader
except ImportError:
    _default_tenant_loader = None
    _tenant_loader = None

try:
    from utils.logger import get_logger as _custom_logger
except ImportError:
    _custom_logger = None


def _get_logger() -> logging.Logger:
    if _custom_logger is not None:
        try:
            return _custom_logger(__name__)
        except TypeError:
            return _custom_logger()

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    return logging.getLogger("storefront")


logger = _get_logger()


def _fallback_tenants() -> dict[str, SimpleNamespace]:
    return {
        "default": SimpleNamespace(
            tenant_id="default",
            shop_name="Auric Bazaar",
            greeting_message="Handpicked pieces for everyday rituals",
            business_description="A warm showcase of curated gifting, fragrances, and slow-living essentials.",
            welcome_image_url="",
            categories=["Featured", "Fragrance", "Gifts"],
        ),
        "cookie-shop": SimpleNamespace(
            tenant_id="cookie-shop",
            shop_name="Cookie Shop",
            greeting_message="Fresh batches, boxed beautifully",
            business_description="Small-batch cookies, celebration hampers, and tea-time favorites.",
            welcome_image_url="",
            categories=["Cookies", "Gift Boxes", "Best Sellers"],
        ),
        "aroma-palace": SimpleNamespace(
            tenant_id="aroma-palace",
            shop_name="Aroma Palace",
            greeting_message="Signature scents for every mood",
            business_description="Perfumes, mists, and scented essentials with a luxe storefront feel.",
            welcome_image_url="",
            categories=["Perfumes", "Mists", "Featured"],
        ),
    }


def _fallback_products() -> dict[str, list[SimpleNamespace]]:
    return {
        "default": [
            SimpleNamespace(
                id="gift-box",
                name="Amber Gift Box",
                description="A festive box with candles, fragrance oil, and a handwritten note.",
                price=1499,
                category="Featured",
                image_url="",
                tags=["gift", "festival"],
                product_type="Limited",
                in_stock=True,
            ),
            SimpleNamespace(
                id="linen-mist",
                name="Linen Mist",
                description="Soft home fragrance with bergamot, cedar, and white tea.",
                price=699,
                category="Fragrance",
                image_url="",
                tags=["home", "fresh"],
                product_type="New",
                in_stock=True,
            ),
            SimpleNamespace(
                id="tea-candle",
                name="Tea Candle Trio",
                description="Three slow-burn candles made for evenings and gifting.",
                price=899,
                category="Gifts",
                image_url="",
                tags=["candle", "gift"],
                product_type="Popular",
                in_stock=False,
            ),
        ],
        "cookie-shop": [
            SimpleNamespace(
                id="butter-cookies",
                name="Butter Cookies Tin",
                description="Classic buttery cookies in a reusable celebration tin.",
                price=499,
                category="Cookies",
                image_url="",
                tags=["bestseller", "tin"],
                product_type="Best Seller",
                in_stock=True,
            ),
            SimpleNamespace(
                id="choco-box",
                name="Chocolate Gift Box",
                description="Assorted double-chocolate cookies packed for gifting.",
                price=899,
                category="Gift Boxes",
                image_url="",
                tags=["gift", "party"],
                product_type="Gift Pick",
                in_stock=True,
            ),
        ],
        "aroma-palace": [
            SimpleNamespace(
                id="oud-noir",
                name="Oud Noir",
                description="Deep oud perfume with warm spice and woody dry-down.",
                price=2299,
                category="Perfumes",
                image_url="",
                tags=["oud", "evening"],
                product_type="Signature",
                in_stock=True,
            ),
            SimpleNamespace(
                id="rose-mist",
                name="Rose Mist",
                description="A light floral body mist designed for everyday wear.",
                price=799,
                category="Mists",
                image_url="",
                tags=["rose", "daily"],
                product_type="Fresh",
                in_stock=True,
            ),
        ],
    }


def _coerce_tenant(raw: Any) -> SimpleNamespace | None:
    if raw is None:
        return None
    if isinstance(raw, SimpleNamespace):
        return raw
    if isinstance(raw, dict):
        return SimpleNamespace(**raw)
    return SimpleNamespace(**getattr(raw, "__dict__", {})) if hasattr(raw, "__dict__") else raw


def _coerce_product(raw: Any) -> SimpleNamespace:
    if isinstance(raw, SimpleNamespace):
        return raw
    if isinstance(raw, dict):
        return SimpleNamespace(**raw)
    return SimpleNamespace(**getattr(raw, "__dict__", {})) if hasattr(raw, "__dict__") else raw


def _derive_categories(products: list[SimpleNamespace]) -> list[str]:
    categories = []
    for product in products:
        category = getattr(product, "category", None)
        if category and category not in categories:
            categories.append(category)
    return categories


def _load_tenant(tenant_id: str | None) -> SimpleNamespace | None:
    if _tenant_loader is not None and _default_tenant_loader is not None:
        tenant = _tenant_loader(tenant_id) if tenant_id else _default_tenant_loader()
        return _coerce_tenant(tenant)

    tenants = _fallback_tenants()
    lookup_id = tenant_id or "default"
    return tenants.get(lookup_id)


def _load_products(tenant_id: str) -> list[SimpleNamespace]:
    if _catalog_products is not None:
        return [_coerce_product(product) for product in _catalog_products(tenant_id)]

    products = _fallback_products()
    return [_coerce_product(product) for product in products.get(tenant_id, products["default"])]


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting storefront API")
    yield
    logger.info("Shutting down storefront API")


app = FastAPI(title="Telegram Storefront", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/miniapp.html")


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "app_env": os.getenv("APP_ENV", "development"),
    }


@app.get("/api/storefront", tags=["Storefront"])
async def storefront(tenant_id: str | None = Query(default=None)):
    tenant = _load_tenant(tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    products = _load_products(tenant.tenant_id)
    categories = getattr(tenant, "categories", None) or _derive_categories(products)

    return {
        "tenant_id": tenant.tenant_id,
        "shop_name": tenant.shop_name,
        "tagline": getattr(tenant, "greeting_message", None)
        or getattr(tenant, "business_description", None)
        or "Welcome",
        "business_description": getattr(tenant, "business_description", ""),
        "hero_title": f"Shop {tenant.shop_name}",
        "hero_subtitle": getattr(tenant, "business_description", None) or "Browse our latest collection",
        "accent_color": "#ba7a38",
        "logo_url": getattr(tenant, "welcome_image_url", ""),
        "currency": "INR",
        "categories": categories,
        "products": [
            {
                "id": getattr(product, "id", ""),
                "name": getattr(product, "name", "Untitled Product"),
                "description": getattr(product, "description", ""),
                "price": getattr(product, "price", 0),
                "category": getattr(product, "category", "General"),
                "image_url": getattr(product, "image_url", ""),
                "tags": getattr(product, "tags", []),
                "emoji": "🛍",
                "badge": getattr(product, "product_type", "") or "",
                "in_stock": getattr(product, "in_stock", True),
            }
            for product in products
        ],
    }


public_dir = Path(__file__).parent / "public"
if public_dir.exists():
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
