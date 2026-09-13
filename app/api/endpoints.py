import io
import os
import datetime
import jwt
from pydantic import BaseModel
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from supabase import create_client, Client
from PIL import Image
from ..core import config
from ..models import schemas
from ..services import certificate_service as service
from ..core.limiter import limiter
from ..core.logging_config import logger
from ..core.supabase_client import supabase

router = APIRouter()

# JWT Security
def verify_jwt(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not an admin")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/")
def read_root():
    return {"status": "ok", "service": "Cert-Gen-V2 (Modular)"}

@router.post("/admin/login")
def admin_login(req: schemas.LoginRequest):
    import secrets
    target_pwd = config.get_admin_password() or config.ADMIN_PASSWORD
    if target_pwd and secrets.compare_digest(req.password, target_pwd):
        expiration = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        token = jwt.encode(
            {"role": "admin", "exp": expiration},
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM
        )
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid password")

@router.get("/admin/config")
def get_layout_config():
    return {"config": service.load_config()}

@router.post("/admin/save-config", dependencies=[Depends(verify_jwt)])
async def save_layout_config(req: schemas.ConfigRequest):
    try:
        cfg = service.load_config()
        cfg['name_pos'] = {'x': req.name_x, 'y': req.name_y}
        cfg['font_family'] = req.font_family
        cfg['text_color'] = req.text_color
        cfg['event_name'] = req.event_name
        cfg['is_centered'] = req.is_centered
        cfg['font_weight'] = req.font_weight
        cfg['is_italic'] = req.is_italic
        cfg['stroke_width'] = req.stroke_width
        cfg['stroke_color'] = req.stroke_color
        cfg['font_size'] = req.font_size
        cfg['font_url'] = req.font_url
        cfg['font_filename'] = req.font_filename
        service.save_config(cfg)
        return {"status": "saved", "config": cfg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/auto-detect", dependencies=[Depends(verify_jwt)])
def auto_detect_layout():
    if not os.path.exists(config.TEMPLATE_PATH):
        raise HTTPException(status_code=404, detail="Template not found.")
    with Image.open(config.TEMPLATE_PATH) as img:
        coords = service.detect_name_line_cv2(img)
        if coords:
            return {"found": True, "x": coords[0], "y": coords[1]}
        return {"found": False, "message": "No horizontal line detected."}


@router.post("/admin/upload-template")
async def upload_template(request: Request, file: UploadFile = File(...)):
    verify_jwt(request)
    try:
        if not file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            raise HTTPException(status_code=400, detail="Invalid file type. Only PNG and JPG are allowed.")
        
        content = await file.read()
        
        # 1. Sync to Supabase Storage (Stateless Priority)
        try:
            supabase.storage.from_("assets").upload(
                "template.png", 
                content, 
                {"content-type": "image/png", "upsert": "true"}
            )
        except Exception as se:
            logger.error(f"Supabase Template Sync Failed: {se}")
            # If we aren't in serverless, we can still rely on local, 
            # but usually Supabase is our source of truth now.

        # 2. Sync to Local (For legacy/dev support, optional in serverless)
        try:
            if not os.path.exists("assets"): os.makedirs("assets")
            with open(config.TEMPLATE_PATH, "wb") as f:
                f.write(content)
        except Exception as le:
            logger.warning(f"Local template write skipped/failed (normal in serverless): {le}")

        # Clear Cache
        import app.services.certificate_service as service
        service.CACHE_TEMPLATE = content

        return {"status": "success", "filename": "template.png"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/upload-font")
async def upload_font(request: Request, file: UploadFile = File(...)):
    verify_jwt(request)
    try:
        if not file.filename.lower().endswith((".ttf", ".otf")):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .ttf and .otf are allowed.")
        
        content = await file.read()
        
        # 1. Sync to Local (Best effort for immediate registration)
        try:
            if not os.path.exists(config.FONTS_DIR):
                os.makedirs(config.FONTS_DIR)
            file_path = os.path.join(config.FONTS_DIR, file.filename)
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as le:
            logger.warning(f"Local font write skipped/failed: {le}")

        # 2. Sync to Supabase Storage (Stateless Priority)
        service.sync_font_to_storage(file.filename, content)
        
        # 3. Register
        service.register_custom_fonts()
        
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin/fonts/{filename}", dependencies=[Depends(verify_jwt)])
def delete_font(filename: str):
    try:
        if filename.endswith(".ttf") or filename.endswith(".otf"):
            file_path = os.path.join(config.FONTS_DIR, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
            font_name = os.path.splitext(filename)[0]
            service.REGISTERED_FONTS = [f for f in service.REGISTERED_FONTS if f.get('name') != font_name]
            try:
                supabase.storage.from_("fonts").remove([filename])
            except:
                pass
            return {"status": "deleted"}
        raise HTTPException(status_code=400, detail="Invalid font filename")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class GoogleFontRequest(BaseModel):
    url: str

@router.post("/admin/font-import-google", dependencies=[Depends(verify_jwt)])
async def import_google_font(req: GoogleFontRequest):
    try:
        fonts = service.import_google_font(req.url)
        if not fonts:
            raise ValueError("Success connection but no compatible .ttf font variants found in this URL. Try a different Google Font link.")
        return {"status": "success", "imported": fonts}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/admin/fonts")
def get_fonts():
    return {"fonts": service.REGISTERED_FONTS}

@router.delete("/admin/template", dependencies=[Depends(verify_jwt)])
def delete_template():
    try:
        if os.path.exists(config.TEMPLATE_PATH):
            os.remove(config.TEMPLATE_PATH)
        if os.path.exists(config.CONFIG_PATH):
            os.remove(config.CONFIG_PATH) 
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
def check_health():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

# Helper to sanitize database exceptions
def handle_db_error(e: Exception):
    err_str = str(e)
    # Check for Supabase restoration markers (Cloudflare 521, getaddrinfo, etc)
    if "521" in err_str or "getaddrinfo" in err_str or "connection" in err_str.lower():
        return HTTPException(
            status_code=503, 
            detail="Database is currently waking up or unreachable. Please wait a minute and refresh."
        )
    return HTTPException(status_code=500, detail=f"Database error: {err_str[:200]}")

@router.get("/admin/teams", dependencies=[Depends(verify_jwt)])
async def get_teams():
    try:
        res = supabase.table("Teams").select("*").execute()
        return res.data
    except Exception as e:
        raise handle_db_error(e)


@router.get("/participants/names")
async def get_all_participant_names():
    try:
        res = supabase.table("Teams").select("*").execute()
        names = set()
        for row in res.data:
            for k, v in row.items():
                if k != "id" and v and isinstance(v, str) and v.strip():
                    names.add(v.strip())
        return sorted(list(names))
    except Exception as e:
        raise handle_db_error(e)

@router.post("/claim")
@limiter.limit("20/minute")
async def claim_certificate(req: schemas.ClaimRequest, request: Request):
    try:
        result, error = await service.process_claim(req.name, req.frontend_url, supabase)
        if error:
            if error == "No participant found":
                raise HTTPException(status_code=404, detail=error)
            if error == "Template not configured":
                raise HTTPException(status_code=404, detail=error)
            # Check if service.process_claim error string looks like a DB connection issue
            if "521" in error or "connection" in error.lower():
                 raise HTTPException(status_code=503, detail="Database is waking up, please try again.")
            raise HTTPException(status_code=500, detail=error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_db_error(e)
@router.post("/admin/batch-import", dependencies=[Depends(verify_jwt)])
async def batch_import_participants(req: schemas.BatchImportRequest):
    try:
        items = req.teams or req.participants or []
        results = await service.process_batch_import(items, supabase)
        return {
            "summary": f"Processed {len(results)} records", 
            "details": results,
            "success_count": len([r for r in results if r['status'] == 'success']),
            "error_count": len([r for r in results if r['status'] == 'error'])
        }
    except Exception as e:
        raise handle_db_error(e)
