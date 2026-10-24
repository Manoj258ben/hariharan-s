import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("STOCKSENSE_DB_PATH", str(BASE_DIR / "stocksense.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"
CUSTOMER_DB_PATH = os.getenv("STOCKSENSE_CUSTOMER_DB_PATH", str(BASE_DIR / "customers.db"))
USER_DB_PATH = os.getenv("STOCKSENSE_USER_DB_PATH", str(BASE_DIR / "users.db"))

DEFAULT_SERVICE_LEVEL_Z = 1.65  # ~95% service level
DEFAULT_FORECAST_WINDOW = 90
DEFAULT_SAFETY_STOCK_DAYS = 2
DEFAULT_EXPIRY_BUFFER_DAYS = 1
DEFAULT_AS_OF_DATE = "2026-09-30"
DEFAULT_STORE_NAME = "My Kirana Store"

# Authentication & Security
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "stocksense-super-secret-key-change-in-production-2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours

# Database Backups
BACKUP_DIR = Path(os.getenv("STOCKSENSE_BACKUP_DIR", str(BASE_DIR / "backups")))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
