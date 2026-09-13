import os
import sys

# Add project root to sys.path
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_path)

# Import the FastAPI app
from app.main import app

# Vercel Python runtime expects 'app' or 'handler'
# FastAPI app works directly with ASGI servers
# For Vercel, we don't need to wrap it - just export the app
# The app is already defined above

# This makes the FastAPI app available to Vercel's Python runtime
application = app
