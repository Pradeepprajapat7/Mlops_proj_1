import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

import pymongo
import certifi
from pymongo.errors import OperationFailure, ConfigurationError

from src.exception import MyException
from src.logger import logging
from src.constants import DATABASE_NAME, MONGODB_URL_KEY

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _parse_env_file() -> dict[str, str]:
    """Load KEY=VALUE pairs from project-root .env without extra packages."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.match(key):
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def _encode_mongo_url(mongo_db_url: str) -> str:
    """Percent-encode user and password so special characters do not break auth."""
    parsed = urlparse(mongo_db_url)
    if not parsed.hostname or parsed.username is None:
        return mongo_db_url
    user = quote_plus(parsed.username)
    password = quote_plus(parsed.password or "")
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=f"{user}:{password}@{host}"))


def _load_env_file() -> None:
    file_values = _parse_env_file()
    for key, value in file_values.items():
        os.environ.setdefault(key, value)

    # Project .env is the source of truth so a stale PowerShell MONGODB_URL cannot win.
    file_url = file_values.get(MONGODB_URL_KEY)
    if file_url:
        os.environ[MONGODB_URL_KEY] = file_url


_load_env_file()

# Load the certificate authority file to avoid timeout errors when connecting to MongoDB
ca = certifi.where()

class MongoDBClient:
    """
    MongoDBClient is responsible for establishing a connection to the MongoDB database.

    Attributes:
    ----------
    client : MongoClient
        A shared MongoClient instance for the class.
    database : Database
        The specific database instance that MongoDBClient connects to.

    Methods:
    -------
    __init__(database_name: str) -> None
        Initializes the MongoDB connection using the given database name.
    """

    client = None  # Shared MongoClient instance across all MongoDBClient instances

    def __init__(self, database_name: str = DATABASE_NAME) -> None:
        """
        Initializes a connection to the MongoDB database. If no existing connection is found, it establishes a new one.

        Parameters:
        ----------
        database_name : str, optional
            Name of the MongoDB database to connect to. Default is set by DATABASE_NAME constant.

        Raises:
        ------
        MyException
            If there is an issue connecting to MongoDB or if the environment variable for the MongoDB URL is not set.
        """
        try:
            # Check if a MongoDB client connection has already been established; if not, create a new one
            if MongoDBClient.client is None:
                mongo_db_url = os.getenv(MONGODB_URL_KEY)
                if mongo_db_url is None:
                    raise Exception(f"Environment variable '{MONGODB_URL_KEY}' is not set.")

                MongoDBClient.client = pymongo.MongoClient(
                    _encode_mongo_url(mongo_db_url),
                    tlsCAFile=ca,
                    serverSelectionTimeoutMS=20000,
                )

            self.client = MongoDBClient.client
            self.database = self.client[database_name]
            self.database_name = database_name
            self.client.admin.command("ping")
            logging.info("MongoDB connection successful.")

        except (OperationFailure, ConfigurationError) as e:
            MongoDBClient.client = None
            raise MyException(
                "MongoDB authentication failed. Update MONGODB_URL in the project .env "
                "with a current Atlas database user and password, then restart the app.",
                sys,
            ) from e
        except Exception as e:
            MongoDBClient.client = None
            raise MyException(e, sys)