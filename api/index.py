import os
import sys
from fastapi import FastAPI

# Add project root to sys.path for backend imports
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_path)

try:
    # Attempt to load the actual app
    from backend.app.main import app
except Exception as e:
    # Fallback to a diagnostic app if the main app crashes or can't be imported
    app = FastAPI()
    
    @app.get("/api/debug-paths")
    async def debug_paths():
        import traceback
        return {
            "status": "Import Error Recovery",
            "error_message": str(e),
            "traceback": traceback.format_exc(),
            "root_path": root_path,
            "cwd": os.getcwd(),
            "sys_path": sys.path,
            "folders_at_root": os.listdir(root_path) if os.path.exists(root_path) else "Path does not exist",
            "env_vars": {
                "VERCEL": os.getenv("VERCEL"),
                "SUPABASE_URL_PRESENT": bool(os.getenv("SUPABASE_URL")),
                "PYTHONPATH": os.getenv("PYTHONPATH")
            }
        }

    @app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def catch_all(full_path: str):
        return {
            "error": "The main application failed to load. Please check /api/debug-paths for details.",
            "error_detail": str(e),
            "requested_path": full_path
        }
