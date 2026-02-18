from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class ProductScrapeRequest(BaseModel):
    """Modèle de requête pour le scraping de prix"""
    product_name: str = Field(..., min_length=2, max_length=150, description="Nom du produit")
    owner_price: Decimal = Field(..., gt=0, description="Prix fixé par le propriétaire")
    
    @field_validator('product_name')
    @classmethod
    def validate_product_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du produit ne peut pas être vide")
        return v.strip()


class ProductScrapeResponse(BaseModel):
    """Modèle de réponse après calcul du prixconseillé"""
    average_price: float = Field(..., description="Prix moyen trouvé sur Jumia")
    recommended_price: float = Field(..., description="Prix conseillé après réduction de 10%")
    owner_price: float = Field(..., description="Prix du propriétaire")
    final_price: float = Field(..., description="Prix final (max entre recommended_price et owner_price)")
    accept_owner_price: bool = Field(..., description="True si le prix owner >= prixconseillé")
    product_name: str = Field(..., description="Nom du produit")
    scraped_prices_count: int = Field(default=0, description="Nombre de prix récupérés depuis Jumia")


class ProductCreatedEvent(BaseModel):
    """Événement reçu depuis Boutique Service lors de la création d'un produit"""
    product_id: str = Field(..., description="ID unique du produit")
    product_name: str = Field(..., description="Nom du produit")
    owner_price: float = Field(..., gt=0, description="Prix fixé par le propriétaire")


class ProductPriceComputedEvent(BaseModel):
    """Événement envoyé à Boutique Service après calcul du prixconseillé"""
    product_id: str = Field(..., description="ID unique du produit")
    product_name: str = Field(..., description="Nom du produit")
    owner_price: float = Field(..., description="Prix du propriétaire")
    computed_price: float | None = Field(default=None, description="Prix calculé selon la stratégie")
    found: bool = Field(default=False, description="True si un prix moyen a été trouvé sur le marché")
    profitable: bool = Field(default=False, description="True si le prix calculé est rentable (>= owner_price)")
    strategy: str = Field(default="UNKNOWN", description="Stratégie de pricing appliquée")
    alert_supplier: bool = Field(default=False, description="True si le fournisseur doit être alerté (prix non rentable)")
    source: str = Field(default="SCRAPER", description="Source du calcul de prix")
    market_avg_price: float | None = Field(default=None, description="Prix moyen trouvé sur le marché")
