"""Point d'accès unique à MySQL et SQLAlchemy pour les écrans et les scripts."""

from app.config import database_settings

try:
    import mysql.connector as _driver
    DatabaseError = _driver.Error
except ImportError:
    _driver = None

    class DatabaseError(RuntimeError):
        """Le pilote MySQL n'est pas disponible."""


def connect():
    if _driver is None:
        raise DatabaseError("Installez les dépendances : python -m pip install -r requirements.txt")
    return _driver.connect(**database_settings(), connection_timeout=5, charset="utf8mb4")


def create_engine():
    from sqlalchemy import create_engine as sqlalchemy_engine
    from sqlalchemy.engine import URL
    config = database_settings()
    url = URL.create("mysql+pymysql", username=config["user"], password=config["password"],
                     host=config["host"], port=config["port"], database=config["database"],
                     query={"charset": "utf8mb4"})
    return sqlalchemy_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
