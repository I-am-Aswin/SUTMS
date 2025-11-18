"""
Configuration for DB connection. Uses environment variables by default.
Edit values here to change defaults, or set env vars for production.
"""
import os

MYSQL_USER = os.getenv("MYSQL_USER", "taxii_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "taxii_pass")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB = os.getenv("MYSQL_DB", "taxii_db")

# SQLAlchemy connection URL
SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

# For small deployments
SQLALCHEMY_ECHO = False
