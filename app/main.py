import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import price_route
from app.consumers.rabbit_consumer import start_rabbitmq_consumer, get_rabbitmq_consumer

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Démarrage du service de scraping...")
    
    try:
        loop = asyncio.get_event_loop()
        consumer_task = loop.create_task(start_rabbitmq_consumer())
        logger.info("Consumer RabbitMQ démarré")
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du consumer RabbitMQ: {e}")
    
    yield
    

    logger.info("Arrêt du service de scraping...")
    
    try:
        consumer = await get_rabbitmq_consumer()
        await consumer.disconnect()
    except Exception as e:
        logger.error(f"Erreur lors de la déconnexion RabbitMQ: {e}")



app = FastAPI(
    title=settings.app_name,
    description="""
    Service de scraping et de tarification dynamique.
    
    Fonctionnalités:
    - Scraping des prix sur Jumia
    - Calcul du prix moyen
    - Application d'une réduction de 10%
    - Comparaison avec le prix du propriétaire
    - Intégration RabbitMQ pour les événements
    """,
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(price_route.router)


@app.get("/", tags=["root"])
async def root():
    """Route racine"""
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
