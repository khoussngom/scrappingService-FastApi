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
    
    
    product_created_queue: str = "product.created"
    product_price_computed_queue: str = "product.price.computed"
    exchange_name: str = "catalog.exchange"


settings = Settings()
