import os
import sys
import traceback

# Add project root to sys.path
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_path)

try:
    # Import the FastAPI app
    from app.main import app
    
    # Export for Vercel
    application = app
    
except Exception as e:
    # If import fails, create a minimal diagnostic app
    from fastapi import FastAPI
    
    app = FastAPI()
    
    @app.get("/")
    @app.get("/api")
    async def error_info():
        return {
            "error": "Failed to import main app",
            "message": str(e),
            "traceback": traceback.format_exc(),
            "sys_path": sys.path,
            "cwd": os.getcwd(),
            "files": os.listdir(root_path) if os.path.exists(root_path) else []
        }
    
    application = app
