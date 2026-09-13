import os
from fastapi import APIRouter
from ..core.config import BASE_DIR, ASSETS_DIR

router = APIRouter()

@router.get("/debug-paths")
async def debug_paths():
    return {
        "CWD": os.getcwd(),
        "FILE": __file__,
        "BASE_DIR": BASE_DIR,
        "ASSETS_DIR": ASSETS_DIR,
        "ASSETS_EXISTS": os.path.exists(ASSETS_DIR),
        "ENV_VARS": {
            "VERCEL": os.getenv("VERCEL"),
            "SUPABASE_URL_SET": bool(os.getenv("SUPABASE_URL")),
            "SUPABASE_KEY_SET": bool(os.getenv("SUPABASE_KEY")),
        },
        "FOLDER_LIST": os.listdir() if os.path.exists(".") else []
    }
