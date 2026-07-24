"""Configuration URL construction regression tests."""

from app.core.config import Settings


def test_connection_urls_percent_encode_credentials_and_vhost() -> None:
    settings = Settings(
        postgres_user="db@example",
        postgres_password="p@ss:/?#[]",
        postgres_db="life/os",
        rabbitmq_user="mq@example",
        rabbitmq_password="p@ss:/?#[]",
        rabbitmq_vhost="life/os",
    )

    assert settings.sqlalchemy_url == (
        "postgresql+psycopg://db%40example:p%40ss%3A%2F%3F%23%5B%5D"
        "@postgres:5432/life%2Fos"
    )
    assert settings.amqp_dsn == (
        "amqp://mq%40example:p%40ss%3A%2F%3F%23%5B%5D"
        "@rabbitmq:5672/life%2Fos"
    )
