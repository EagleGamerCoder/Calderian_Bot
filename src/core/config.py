'''
loads .env
'''

from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass(frozen=True)
class Config:
    TOKEN: str
    DATABASE_URL: str
    ROBLOX_COOKIE: str | None
    PORT: int
    DEBUG: bool

config = Config(
    TOKEN=os.getenv("TOKEN", ""),
    DATABASE_URL=os.getenv("DATABASE_URL", ""),
    ROBLOX_COOKIE=os.getenv("ROBLOX_COOKIE"),
    PORT=int(os.getenv("PORT", 8080)),
    DEBUG=os.getenv("DEBUG", "false").lower() == "true"
)