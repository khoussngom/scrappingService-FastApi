import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from app.models import ProductScrapeRequest, ProductScrapeResponse
from app.services.price_service import calculate_pricing
from app.scraper.jumia_scraper import scrape_jumia_prices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["pricing"])


@router.post(
    "/scrape-price",
    response_model=ProductScrapeResponse,
    summary="Calcule le prixconseillé pour un produit",
    description="""
    Ce endpoint permet de:
    1. Récupérer les prix du produit sur Jumia
    2. Calculer le prix moyen
    3. Appliquer une réduction de 10% pour le prixconseillé
    4. Comparer avec le prix owner
    """
)
async def scrape_price(request: ProductScrapeRequest):
    """
    Calcule le prixconseillé pour un produit.
    
    - **product_name**: Nom du produit à rechercher sur Jumia
    - **owner_price**: Prix fixé par le propriétaire
    """
    try:
        result = await calculate_pricing(
            product_name=request.product_name,
            owner_price=float(request.owner_price)
        )
        return result
    except Exception as e:
        logger.error(f"Erreur lors du calcul du prix: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul du prix: {str(e)}"
        )


@router.get(
    "/scrape/{product_name}",
    response_model=List[float],
    summary="Récupère les prix d'un produit sur Jumia",
    description="Retourne la liste des prix trouvés sur Jumia pour un produit"
)
async def get_jumia_prices(product_name: str):
    """
    Récupère les prix d'un produit sur Jumia.
    
    - **product_name**: Nom du produit à rechercher
    """
    try:
        prices = await scrape_jumia_prices(product_name)
        return prices
    except Exception as e:
        logger.error(f"Erreur lors du scraping: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du scraping: {str(e)}"
        )


@router.get(
    "/health",
    summary="Vérifie l'état du service",
    description="Endpoint de santé pour vérifier que le service est opérationnel"
)
async def health_check():
    """Vérifie que le service est opérationnel"""
    return {
        "status": "healthy",
        "service": "Scraping & Dynamic Pricing Service"
    }
