import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable

import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractRobustConnection, AbstractChannel

from app.config import settings
from app.models import ProductCreatedEvent, ProductPriceComputedEvent
from app.services.price_service import process_product_created_event

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """Consommateur RabbitMQ pour les événements de création de produit"""
    
    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self._consuming = False
    
    async def connect(self) -> None:
        """Établit la connexion avec RabbitMQ"""
        try:
            self.connection = await aio_pika.connect_robust(
                settings.rabbitmq.url,
                timeout=30
            )
            self.channel = await self.connection.channel()
            
            # Déclarer l'exchange principal
            await self.channel.declare_exchange(
                settings.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Déclarer la queue pour product.created
            queue = await self.channel.declare_queue(
                settings.product_created_queue,
                durable=True
            )
            
            # Binder la queue à l'exchange
            await queue.bind(
                settings.exchange_name,
                routing_key="product.created"
            )
            
            logger.info("Connecté à RabbitMQ")
            
        except Exception as e:
            logger.error(f"Erreur de connexion RabbitMQ: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Ferme la connexion RabbitMQ"""
        if self.connection:
            await self.connection.close()
            logger.info("Déconnecté de RabbitMQ")
    
    async def publish_price_computed(
        self,
        event: ProductPriceComputedEvent
    ) -> bool:
        """
        Publie l'événement ProductPriceComputedEvent vers RabbitMQ.
        
        Args:
            event: Événement à publier
            
        Returns:
            True si la publication a réussi, False sinon
        """
        if not self.channel:
            logger.error("Pas de connexion RabbitMQ active")
            return False
        
        try:
            exchange = await self.channel.get_exchange(settings.exchange_name)
            
            message_body = event.model_dump_json().encode()
            
            await exchange.publish(
                aio_pika.Message(
                    body=message_body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key="product.price.computed"
            )
            
            logger.info(
                f"Publié ProductPriceComputedEvent pour {event.product_id} "
                f"(strategy={event.strategy}, profitable={event.profitable})"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Erreur lors de la publication de ProductPriceComputedEvent: {e}"
            )
            return False
    
    async def on_message(self, message: IncomingMessage) -> None:
        """
        Callback lors de la réception d'un message.
        
        Ce handler est conçu pour être robuste et ne jamais crash le consumer.
       Toutes les exceptions sont capturées et journalisées.
        
        Args:
            message: Message reçu
        """
        async with message.process():
            try:
                # Parser le message
                event_data = json.loads(message.body.decode())
                
                # Valider les données
                product_event = ProductCreatedEvent(**event_data)
                
                logger.info(
                    f"Reçu ProductCreatedEvent pour: {product_event.product_name} "
                    f"(ID: {product_event.product_id}, prix: {product_event.owner_price})"
                )
                
                # Traiter l'événement
                price_computed_event = await process_product_created_event(
                    event_data
                )
                
                logger.info(
                    f"Prix calculé pour '{price_computed_event.product_name}': "
                    f"computed_price={price_computed_event.computed_price}, "
                    f"strategy={price_computed_event.strategy}, "
                    f"profitable={price_computed_event.profitable}, "
                    f"alert_supplier={price_computed_event.alert_supplier}"
                )
                
                # Publier le résultat
                publish_success = await self.publish_price_computed(price_computed_event)
                
                if not publish_success:
                    logger.error(
                        f"Échec de la publication pour le produit {price_computed_event.product_id}"
                    )
                
            except json.JSONDecodeError as e:
                logger.error(
                    f"Erreur de décodage JSON du message: {e}. "
                    f"Message ignoré sans crash du consumer."
                )
                # Le message sera ignoré (ack) car on ne fait pas de reject
                
            except Exception as e:
                logger.error(
                    f"Erreur lors du traitement du message: {e}. "
                    f"Message ignoré pour éviter le crash du consumer."
                )
                # Ne pas re-lever l'exception pour éviter de crash le consumer
                # Le message sera ignoré (ack) et traité comme un échec
    
    async def start_consuming(self) -> None:
        """Démarre la consommation des messages"""
        if not self.channel:
            raise RuntimeError("Pas de canal RabbitMQ disponible")
        
        queue = await self.channel.declare_queue(
            settings.product_created_queue,
            durable=True
        )
        
        await queue.consume(self.on_message)
        
        self._consuming = True
        logger.info(f"En attente de messages sur {settings.product_created_queue}")
        
        # Garder le consumer actif
        while self._consuming:
            await asyncio.sleep(1)
    
    async def stop_consuming(self) -> None:
        """Arrête la consommation des messages"""
        self._consuming = False
        logger.info("Arrêt de la consommation des messages")


# Instance globale du consumer
rabbitmq_consumer: Optional[RabbitMQConsumer] = None


async def get_rabbitmq_consumer() -> RabbitMQConsumer:
    """Récupère l'instance du consumer RabbitMQ"""
    global rabbitmq_consumer
    
    if rabbitmq_consumer is None:
        rabbitmq_consumer = RabbitMQConsumer()
        await rabbitmq_consumer.connect()
    
    return rabbitmq_consumer


async def start_rabbitmq_consumer() -> None:
    """Démarre le consumer RabbitMQ en arrière-plan"""
    consumer = await get_rabbitmq_consumer()
    await consumer.start_consuming()
