from supabase import create_client, Client
from . import config

# Centralized Supabase Client for the entire application
# Uses credentials from core.config
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY) if (config.SUPABASE_URL and config.SUPABASE_KEY) else None
