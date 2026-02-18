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
            
            # Déclarer l'exchange principal (topic exchange)
            await self.channel.declare_exchange(
                settings.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Déclarer les queues avec dead-letter
            # Queue pour product.created
            await self.channel.declare_queue(
                settings.product_created_queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "catalog.exchange.dlx",
                    "x-dead-letter-routing-key": "product.created.dlq"
                }
            )
            
            # Queue pour product.updated
            await self.channel.declare_queue(
                settings.product_updated_queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "catalog.exchange.dlx",
                    "x-dead-letter-routing-key": "product.updated.dlq"
                }
            )
            
            # Queue pour product.deleted
            await self.channel.declare_queue(
                settings.product_deleted_queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "catalog.exchange.dlx",
                    "x-dead-letter-routing-key": "product.deleted.dlq"
                }
            )
            
            logger.info("Connecté à RabbitMQ - Prêt à recevoir les événements du catalog service")
            
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
            
            message_body = json.dumps(event.model_dump(mode='json', by_alias=True)).encode()
            
            await exchange.publish(
                aio_pika.Message(
                    body=message_body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=settings.product_price_computed_routing_key
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
        Il gère les événements:
        - PRODUCT_CREATED: déclenche le scraping et calcule le prix
        - PRODUCT_UPDATED: re-calcule le prix si le prix owner a changé
        - PRODUCT_DELETED: supprime les données de scraping locales (optionnel)
        
        Args:
            message: Message reçu
        """
        async with message.process():
            try:
                # Parser le message
                event_data = json.loads(message.body.decode())
                
                # Déterminer le type d'événement à partir du routing key
                routing_key = message.routing_key or ""
                event_type = "PRODUCT_CREATED"
                
                if "updated" in routing_key:
                    event_type = "PRODUCT_UPDATED"
                elif "deleted" in routing_key:
                    event_type = "PRODUCT_DELETED"
                
                logger.info(f"Message reçu (routing key: {routing_key}, type: {event_type})")
                logger.info(f"Données brutes: {event_data}")
                
                # Traiter selon le type d'événement
                if event_type == "PRODUCT_DELETED":
                    await self._handle_product_deleted(event_data)
                    return
                
                # Pour PRODUCT_CREATED et PRODUCT_UPDATED, extraire les données produit
                product_data = self._extract_product_data(event_data)
                
                logger.info(f"Données extraites: {product_data}")
                product_event = ProductCreatedEvent(**product_data)
                
                if event_type == "PRODUCT_CREATED":
                    logger.info(
                        f"Reçu ProductCreatedEvent pour: {product_event.product_name} "
                        f"(ID: {product_event.product_id}, prix: {product_event.owner_price})"
                    )
                    
                    # Traiter l'événement - calculer le prix
                    price_computed_event = await process_product_created_event(product_data)
                    
                    logger.info(
                        f"Prix calculé pour '{price_computed_event.product_name}': "
                        f"computed_price={price_computed_event.computed_price}, "
                        f"strategy={price_computed_event.strategy}, "
                        f"profitable={price_computed_event.profitable}, "
                        f"alert_supplier={price_computed_event.alert_supplier}"
                    )
                    
                    # Publier le résultat vers product.price.computed.queue
                    publish_success = await self.publish_price_computed(price_computed_event)
                    
                    if not publish_success:
                        logger.error(
                            f"Échec de la publication pour le produit {price_computed_event.product_id}"
                        )
                        
                elif event_type == "PRODUCT_UPDATED":
                    logger.info(
                        f"Reçu ProductUpdatedEvent pour: {product_event.product_name} "
                        f"(ID: {product_event.product_id}, prix: {product_event.owner_price})"
                    )
                    
                    # Re-calculer le prix pour le produit mis à jour
                    price_computed_event = await process_product_created_event(product_data)
                    
                    logger.info(
                        f"Prix re-calculé pour '{price_computed_event.product_name}': "
                        f"computed_price={price_computed_event.computed_price}, "
                        f"strategy={price_computed_event.strategy}"
                    )
                    
                    # Publier le résultat
                    publish_success = await self.publish_price_computed(price_computed_event)
                    
                    if not publish_success:
                        logger.error(
                            f"Échec de la publication pour le produit mis à jour {price_computed_event.product_id}"
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
    
    def _extract_product_data(self, event_data: dict) -> dict:
        """
        Extrait les données du produit depuis l'événement.
        
        Supporte plusieurs formats:
        - format direct: {"product_id": ..., "product_name": ..., "owner_price": ...}
        - format wrapper: {"eventId": ..., "eventType": "PRODUCT_CREATED", "data": {...}}
        - format Java: {"produitId": ..., "nom": ..., "prix": ...}
        """
        # Essayer d'extraire les données du format wrapper
        if "data" in event_data:
            product_data = event_data["data"]
        elif "eventId" in event_data:
            # Pour le format Java, utiliser les noms de champs corrects
            # priorité: produitId > productId > eventId > id
            product_id = event_data.get("produitId") or event_data.get("productId") or event_data.get("eventId") or event_data.get("id")
            
            # nom du produit: nom > productName > product_name > name > title
            product_name = event_data.get("nom") or event_data.get("productName") or event_data.get("product_name") or event_data.get("name") or event_data.get("title")
            
            # prix owner: prix > ownerPrice > sellingPrice > owner_price > price
            owner_price = event_data.get("prix") or event_data.get("ownerPrice") or event_data.get("sellingPrice") or event_data.get("owner_price") or event_data.get("price")
            
            product_data = {
                "product_id": product_id,
                "product_name": product_name,
                "owner_price": owner_price
            }
            
            # Si owner_price est None ou 0, chercher plus profondément
            if not product_data["owner_price"]:
                # Chercher dans un objet imbriqué
                for key in ["payload", "body", "content"]:
                    if key in event_data and isinstance(event_data[key], dict):
                        product_data["owner_price"] = event_data[key].get("prix") or event_data[key].get("ownerPrice") or event_data[key].get("sellingPrice") or event_data[key].get("price")
                        if product_data["owner_price"]:
                            break
        else:
            product_data = event_data
        
        return product_data
    
    async def _handle_product_deleted(self, event_data: dict) -> None:
        """
        Gère l'événement de suppression de produit.
        
        Supprime les données de scraping locales associées au produit.
        """
        # Extraire l'ID du produit
        product_id = event_data.get("produitId") or event_data.get("productId") or event_data.get("id") or event_data.get("eventId")
        
        if product_id:
            logger.info(f"Reçu ProductDeletedEvent pour le produit ID: {product_id}")
            # Ici on pourrait supprimer les données locales de scraping
            # Pour l'instant, on log juste l'événement
            logger.info(f"Événement de suppression traité pour le produit {product_id}")
        else:
            logger.warning("ProductDeletedEvent reçu sans ID de produit")
    
    async def start_consuming(self) -> None:
        """Démarre la consommation des messages sur toutes les queues"""
        if not self.channel:
            raise RuntimeError("Pas de canal RabbitMQ disponible")
        
        # Déclarer et binder les queues
        
        # Queue product.created
        queue_created = await self.channel.declare_queue(
            settings.product_created_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "catalog.exchange.dlx",
                "x-dead-letter-routing-key": "product.created.dlq"
            }
        )
        await queue_created.bind(
            settings.exchange_name,
            routing_key=settings.product_created_routing_key
        )
        
        # Queue product.updated
        queue_updated = await self.channel.declare_queue(
            settings.product_updated_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "catalog.exchange.dlx",
                "x-dead-letter-routing-key": "product.updated.dlq"
            }
        )
        await queue_updated.bind(
            settings.exchange_name,
            routing_key=settings.product_updated_routing_key
        )
        
        # Queue product.deleted
        queue_deleted = await self.channel.declare_queue(
            settings.product_deleted_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "catalog.exchange.dlx",
                "x-dead-letter-routing-key": "product.deleted.dlq"
            }
        )
        await queue_deleted.bind(
            settings.exchange_name,
            routing_key=settings.product_deleted_routing_key
        )
        
        # Consommer sur les 3 queues
        await queue_created.consume(self.on_message)
        await queue_updated.consume(self.on_message)
        await queue_deleted.consume(self.on_message)
        
        self._consuming = True
        logger.info(f"En attente de messages sur:")
        logger.info(f"  - {settings.product_created_queue} (product.created)")
        logger.info(f"  - {settings.product_updated_queue} (product.updated)")
        logger.info(f"  - {settings.product_deleted_queue} (product.deleted)")
        
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
