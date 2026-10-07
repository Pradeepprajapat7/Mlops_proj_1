import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pymongo
import certifi

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


def _mongo_username(mongo_db_url: str) -> str:
    parsed = urlparse(mongo_db_url)
    return parsed.username or ""


def _load_env_file() -> None:
    file_values = _parse_env_file()
    for key, value in file_values.items():
        os.environ.setdefault(key, value)

    # A leftover session URI with the placeholder user "USER" must not win over .env.
    session_url = os.getenv(MONGODB_URL_KEY, "")
    file_url = file_values.get(MONGODB_URL_KEY)
    if file_url and (not session_url or _mongo_username(session_url) == "USER"):
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
                mongo_db_url = os.getenv(MONGODB_URL_KEY)  # Retrieve MongoDB URL from environment variables
                if mongo_db_url is None:
                    raise Exception(f"Environment variable '{MONGODB_URL_KEY}' is not set.")
                
                # Establish a new MongoDB client connection
                MongoDBClient.client = pymongo.MongoClient(mongo_db_url, tlsCAFile=ca)
                
            # Use the shared MongoClient for this instance
            self.client = MongoDBClient.client
            self.database = self.client[database_name]  # Connect to the specified database
            self.database_name = database_name
            self.client.admin.command("ping")
            logging.info("MongoDB connection successful.")
            
        except Exception as e:
            # Raise a custom exception with traceback details if connection fails
            raise MyException(e, sys)