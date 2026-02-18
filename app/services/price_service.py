import logging
from typing import List, Optional
from uuid import UUID

from app.config import settings
from app.models import ProductScrapeResponse, ProductPriceComputedEvent, ProductCreatedEvent
from app.scraper.jumia_scraper import scrape_jumia_prices

logger = logging.getLogger(__name__)


def compute_recommended_price(average_price: float) -> float:
    """Calcule le prix recommandé basé sur le prix moyen du marché"""
    discount_factor = 1 - (settings.scraping.discount_percentage / 100)
    recommended_price = average_price * discount_factor
    return round(recommended_price, 2)


async def scrape_market_price(product_name: str) -> Optional[float]:
    """
    Scrape les prix depuis Jumia et retourne le PRIX MINIMUM.
    
    Returns:
        Prix minimum du marché ou None si aucun prix trouvé
    """
    scraped_prices = await scrape_jumia_prices(product_name)
    
    if not scraped_prices:
        logger.warning(f"Aucun prix trouvé sur le marché pour '{product_name}'")
        return None
    
    # Prendre le prix minimum (le plus compétitif sur le marché)
    min_price = min(scraped_prices)
    avg_price = sum(scraped_prices) / len(scraped_prices)
    logger.info(f"Prix minimum du marché pour '{product_name}': {min_price:.2f} (moyenne: {avg_price:.2f}, sur {len(scraped_prices)} prix)")
    
    return round(min_price, 2)


def calculate_intelligent_pricing(
    owner_price: float,
    market_avg_price: float
) -> dict:
    """
    Calcule le prix intelligent basé sur la stratégie de pricing avec vérification de rentabilité.
    
    Logique:
    - Le scraper ne doit JAMAIS vendre à perte
    - On propose un prix à 10% ou 5% en dessous du prix moyen du marché
    - Si aucun de ces prix n'est supérieur au prix owner, on alerte le fournisseur
    
    Returns:
        Dict contenant: computed_price, strategy, profitable, alert_supplier
    """
    price10 = market_avg_price * 0.90
    price5 = market_avg_price * 0.95
    
    logger.info(
        f"Stratégie de pricing pour owner_price={owner_price:.2f}: "
        f"price10={price10:.2f}, price5={price5:.2f}"
    )
    
    # Stratégie 1: Prix moyen - 10% (si supérieur au prix owner)
    if price10 > owner_price:
        computed_price = round(price10, 2)
        strategy = "MARKET_MINUS_10"
        profitable = True
        alert_supplier = False
        
        logger.info(
            f"Stratégie {strategy} appliquée: computed_price={computed_price:.2f}, "
            f"rentable={profitable}"
        )
    
    # Stratégie 2: Prix moyen - 5% (si supérieur au prix owner)
    elif price5 > owner_price:
        computed_price = round(price5, 2)
        strategy = "MARKET_MINUS_5"
        profitable = True
        alert_supplier = False
        
        logger.info(
            f"Stratégie {strategy} appliquée: computed_price={computed_price:.2f}, "
            f"rentable={profitable}"
        )
    
    # Pas rentable: le prix du marché est trop bas par rapport au prix owner
    else:
        computed_price = None
        strategy = "NOT_PROFITABLE"
        profitable = False
        alert_supplier = True
        
        logger.warning(
            f"Prix non rentable! owner_price={owner_price:.2f}, "
            f"market_avg={market_avg_price:.2f}, diff={market_avg_price - owner_price:.2f}. "
            f"Alerte fournisseur déclenchée."
        )
    
    return {
        "computed_price": computed_price,
        "strategy": strategy,
        "profitable": profitable,
        "alert_supplier": alert_supplier
    }


async def calculate_pricing(
    product_name: str,
    owner_price: float
) -> ProductScrapeResponse:
    """
    Calcule le prix selon les règles métier:
    1. Scrape les prix depuis Jumia et prend le PLUS PETIT prix (market_min_price)
    2. Applique 10% de réduction pour obtenir recommended_price
    3. final_price = max(recommended_price, owner_price) - toujours >= owner_price
    4. Arrondit final_price à l'entier le plus proche
    """
    # Scrape les prix depuis Jumia
    scraped_prices = await scrape_jumia_prices(product_name)
    
    # Prendre le plus petit prix (le plus compétitif sur le marché)
    if scraped_prices:
        market_min_price = min(scraped_prices)
        average_price = sum(scraped_prices) / len(scraped_prices)
    else:
        logger.warning(f"Aucun prix trouvé pour '{product_name}', utilisation du prix owner")
        market_min_price = owner_price
        average_price = owner_price
    
    # Appliquer 10% de réduction pour obtenir recommended_price (basé sur le prix minimum)
    recommended_price = market_min_price * 0.90
    
    # final_price = max(recommended_price, owner_price) - jamais en dessous du prix owner
    final_price = max(recommended_price, owner_price)
    
    # Arrondir à l'entier le plus proche
    final_price = round(final_price)
    
    # Le fournisseur est respecté si recommended_price >= owner_price
    accept_owner_price = recommended_price >= owner_price
    
    logger.info(
        f"Produit: {product_name} | "
        f"Prix owner: {owner_price} | "
        f"Prix min Jumia: {market_min_price:.2f} | "
        f"Prix moyen Jumia: {average_price:.2f} | "
        f"Prix recommandé (-10%): {recommended_price:.2f} | "
        f"Prix final: {final_price} | "
        f"Accepté: {accept_owner_price}"
    )
    
    return ProductScrapeResponse(
        average_price=round(average_price, 2),
        recommended_price=round(recommended_price, 2),
        owner_price=owner_price,
        final_price=final_price,
        accept_owner_price=accept_owner_price,
        product_name=product_name,
        scraped_prices_count=len(scraped_prices)
    )


async def process_product_created_event(
    event: ProductCreatedEvent | dict
) -> ProductPriceComputedEvent:
    """
    Traite l'événement product.created et calcule le prix selon les règles métier:
    
    1. Scrape le prix minimum depuis Jumia (prix le plus compétitif)
    2. Applique 10% de réduction pour recommended_price
    3. final_price = max(recommended_price, owner_price) - toujours rentable
    4. Publie l'événement RabbitMQ avec computed_price=final_price
    
    Args:
        event: L'événement product.created (soit en tant que modèle, soit en tant que dict)
        
    Returns:
        ProductPriceComputedEvent avec les informations de pricing
    """
    # Extraire les données de l'événement
    if isinstance(event, dict):
        product_id = event.get("product_id")
        product_name = event.get("product_name")
        owner_price = event.get("owner_price")
    else:
        product_id = event.product_id
        product_name = event.product_name
        owner_price = event.owner_price
    
    logger.info(
        f"Traitement de l'événement pour le produit: {product_name} "
        f"(ID: {product_id}, prix owner: {owner_price})"
    )
    
    # Scraper les prix du marché
    scraped_prices = await scrape_jumia_prices(product_name)
    
    # Prendre le prix minimum (le plus compétitif sur le marché)
    if scraped_prices:
        market_min_price = min(scraped_prices)
        market_avg_price = sum(scraped_prices) / len(scraped_prices)
    else:
        logger.warning(
            f"Aucun prix trouvé sur le marché pour '{product_name}'. "
            f"Utilisation du prix owner."
        )
        market_min_price = owner_price
        market_avg_price = owner_price
    
    # Calculer recommended_price (minimum_price * 0.90)
    recommended_price = market_min_price * 0.90
    
    # Calculer final_price = max(recommended_price, owner_price)
    # Le prix final ne doit jamais être inférieur au prix owner
    final_price = max(recommended_price, owner_price)
    
    # Arrondir à l'entier le plus proche
    final_price = round(final_price)
    
    # Stratégie: Le fournisseur est respecté si recommended_price >= owner_price
    accept_owner_price = recommended_price >= owner_price
    
    if accept_owner_price:
        strategy = "MARKET_PLUS_OWNER_SAFE"
    else:
        strategy = "OWNER_PRICE_HIGHER"
    
    logger.info(
        f"Résultat du pricing pour '{product_name}': "
        f"market_min_price={market_min_price:.2f}, "
        f"market_avg_price={market_avg_price:.2f}, "
        f"recommended_price={recommended_price:.2f}, "
        f"final_price={final_price}, "
        f"strategy={strategy}, "
        f"accept_owner_price={accept_owner_price}"
    )
    
    # Construire l'événement de réponse
    return ProductPriceComputedEvent(
        product_id=product_id,
        product_name=product_name,
        owner_price=owner_price,
        computed_price=final_price,
        found=True,
        profitable=True,  # Toujours rentable car final_price >= owner_price
        strategy=strategy,
        alert_supplier=not accept_owner_price,  # Alerte si le prix recommandé est inférieur au prix owner
        source="SCRAPER",
        market_avg_price=market_min_price  # On utilise le prix min comme référence du marché
    )
