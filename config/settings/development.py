from .base import *

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-development-key")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
DATABASES["default"].update({"NAME": os.environ.get("POSTGRES_DB", "vault67"), "USER": os.environ.get("POSTGRES_USER", "vault67"), "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "vault67"), "HOST": os.environ.get("POSTGRES_HOST", "localhost")})
