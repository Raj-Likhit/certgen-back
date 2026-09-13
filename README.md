# CertGen Backend API

FastAPI backend for certificate generation and management.

## 🚀 Deployment

This backend is deployed as a Vercel serverless function.

### Environment Variables Required

Set these in Vercel Project Settings:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
JWT_SECRET=your-jwt-secret
ADMIN_PASSWORD=your-admin-password
JWT_ALGORITHM=HS256
```

## 🏗️ Structure

```
certgen-backend/
├── api/
│   ├── index.py          # Vercel entry point
│   └── requirements.txt  # Python dependencies
├── app/
│   ├── main.py          # FastAPI application
│   ├── api/             # API routes
│   ├── core/            # Configuration
│   ├── models/          # Pydantic schemas
│   └── services/        # Business logic
├── assets/              # Fonts and templates
└── vercel.json          # Vercel configuration
```

## 🔧 Local Development

```bash
# Install dependencies
pip install -r api/requirements.txt

# Run development server
cd app
python -m uvicorn main:app --reload
```

## 📝 API Documentation

Once deployed, visit:
- Swagger UI: `https://your-backend.vercel.app/docs`
- ReDoc: `https://your-backend.vercel.app/redoc`

## 🔐 CORS Configuration

Update `app/main.py` with your frontend URL:

```python
allowed_origins = [
    "http://localhost:5173",
    "https://your-frontend.vercel.app",
]
```
