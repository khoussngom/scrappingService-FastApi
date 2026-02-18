from typing import Optional

from pydantic_settings import BaseSettings


class RabbitMQSettings(BaseSettings):

    host: str = "host.docker.internal"
    port: int = 5672
    username: str = "marakhib"
    password: str = "Marakhib"
    virtual_host: str = "/"
    publisher_confirm_type: str = "correlated"
    publisher_returns: bool = True
    template_mandatory: bool = True

    @property
    def url(self) -> str:
        return f"amqp://{self.username}:{self.password}@{self.host}:{self.port}{self.virtual_host}"


class ScrapingSettings(BaseSettings):

    discount_percentage: float = 10.0
    timeout: int = 10
    max_prices: int = 20


class Settings(BaseSettings):
    app_name: str = "Scraping & Dynamic Pricing Service"
    debug: bool = True
    
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    scraping: ScrapingSettings = ScrapingSettings()
    
    # Exchange et queues
    exchange_name: str = "catalog.exchange"  # Exchange principal du catalog service
    product_created_queue: str = "product.created.queue"
    product_updated_queue: str = "product.updated.queue"
    product_deleted_queue: str = "product.deleted.queue"
    product_price_computed_queue: str = "product.price.computed.queue"
    
    # Routing keys
    product_created_routing_key: str = "product.created"
    product_updated_routing_key: str = "product.updated"
    product_deleted_routing_key: str = "product.deleted"
    product_price_computed_routing_key: str = "product.price.computed"


settings = Settings()
