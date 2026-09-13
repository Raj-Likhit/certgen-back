import os
from dotenv import load_dotenv

# Load environment variables
# config.py is at backend/app/core/config.py. 
# We need 4 levels to get to project root: core -> app -> backend -> root
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(BACKEND_DIR)
backend_env = os.path.join(BACKEND_DIR, '.env')
root_env = os.path.join(BASE_DIR, '.env')

if os.path.exists(backend_env):
    load_dotenv(dotenv_path=backend_env, override=True)
if os.path.exists(root_env):
    load_dotenv(dotenv_path=root_env, override=True)
load_dotenv(override=True)

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Security
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def get_admin_password():
    if os.path.exists(backend_env):
        load_dotenv(dotenv_path=backend_env, override=True)
    if os.path.exists(root_env):
        load_dotenv(dotenv_path=root_env, override=True)
    return os.getenv("ADMIN_PASSWORD")

# Critical Check: Fail early if variables aren't found in file OR environment
missing_vars = []
if not SUPABASE_URL: missing_vars.append("SUPABASE_URL")
if not SUPABASE_KEY: missing_vars.append("SUPABASE_KEY")
if not JWT_SECRET: missing_vars.append("JWT_SECRET")
if not ADMIN_PASSWORD: missing_vars.append("ADMIN_PASSWORD")

if missing_vars:
    import logging
    logging.warning(f"CRITICAL: Missing environment variables: {', '.join(missing_vars)}. Please set them in your Vercel Project Settings.")

# Paths - Ensure consistent resolution in monorepo
# assets is in backend/assets/
ASSETS_DIR = os.path.join(BACKEND_DIR, "assets")
CONFIG_PATH = os.path.join(ASSETS_DIR, "layout_config.json")
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "template.png")

# Serverless/Vercel Support: Fallback to /tmp for writable font storage
is_serverless = os.getenv("VERCEL") or os.getenv("NOW_REGION")
if is_serverless:
    FONTS_DIR = "/tmp/fonts"
else:
    FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

os.makedirs(FONTS_DIR, exist_ok=True)
