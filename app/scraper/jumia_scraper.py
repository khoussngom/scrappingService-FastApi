import re
import logging
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)


async def scrape_jumia_prices(
    product_name: str,
    max_prices: Optional[int] = None
) -> List[float]:
    if max_prices is None:
        max_prices = settings.scraping.max_prices
    
    
    search_query = product_name.replace(" ", "%20")
    url = f"https://www.jumia.sn/catalog/?q={search_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    prices = []
    
    try:
        async with httpx.AsyncClient(timeout=settings.scraping.timeout) as client:
            logger.info(f"Scraping Jumia pour: {product_name}")
            
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
        
            price_selectors = [
                ".prc",
                "[data-price]",
                ".price._扣",
            ]
            
            for selector in price_selectors:
                price_elements = soup.select(selector)
                
                for element in price_elements:
                    price_text = element.get_text(strip=True)
                    
                    price_cleaned = re.sub(r"[^\d]", "", price_text)
                    
                    if price_cleaned:
                        try:
                            price = float(price_cleaned)
                            if price > 0:
                                prices.append(price)
                        except ValueError:
                            continue
                
                
                if prices:
                    break
            
            
            if max_prices and len(prices) > max_prices:
                prices = prices[:max_prices]
            
            logger.info(f"Trouvé {len(prices)} prix pour '{product_name}'")
            
    except httpx.TimeoutException:
        logger.warning(f"Timeout lors du scraping de {product_name}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Erreur HTTP {e.response.status_code} pour {product_name}")
    except Exception as e:
        logger.error(f"Erreur lors du scraping de {product_name}: {str(e)}")
    
    return prices


async def get_average_price(product_name: str) -> Optional[float]:

    prices = await scrape_jumia_prices(product_name)
    
    if prices:
        return sum(prices) / len(prices)
    
    return None
