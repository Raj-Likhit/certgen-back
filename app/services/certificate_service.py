import io
import asyncio
import hashlib
import os
import json
import uuid
import datetime
import random
import string
from typing import Any
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from ..core import config
import requests
import re
from ..core.supabase_client import supabase

# Asset Cache
REGISTERED_FONTS = [
    {"name": "Helvetica", "type": "system"},
    {"name": "Times-Roman", "type": "system"},
    {"name": "Courier", "type": "system"}
]
CACHE_TEMPLATE = None
CACHE_FONTS = {}
CACHE_CONFIG = None

from ..core.logging_config import logger

def register_custom_fonts():
    """Dynamically register all TTF/OTF files in assets/fonts/ with ReportLab"""
    logger.info(f"Scanning FONTS_DIR: {os.path.abspath(config.FONTS_DIR)}")
    if not os.path.exists(config.FONTS_DIR):
        logger.warning(f"FONTS_DIR does not exist: {config.FONTS_DIR}")
        return

    files = os.listdir(config.FONTS_DIR)
    logger.info(f"Found {len(files)} files in FONTS_DIR")
    for f in files:
        if f.lower().endswith((".ttf", ".otf")):
            try:
                name = os.path.splitext(f)[0]
                path = os.path.join(config.FONTS_DIR, f)
                pdfmetrics.registerFont(TTFont(name, path))
                if not any(font_dict['name'] == name for font_dict in REGISTERED_FONTS):
                    REGISTERED_FONTS.append({"name": name, "type": "custom", "filename": f})
                logger.info(f"Registered custom font: {name}")
            except Exception as e:
                logger.error(f"Failed to register font {f}: {e}")

# Initial Registration
def initialize_fonts():
    try:
        pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
        if not any(f['name'] == 'Arial' for f in REGISTERED_FONTS):
            REGISTERED_FONTS.append({"name": "Arial", "type": "system"})
    except:
        pass
    register_custom_fonts()

    register_custom_fonts()

def import_google_font(url: str):
    """
    Downloads a .ttf font from a Google Fonts URL.
    Matches CSS rules to find direct download links for truetype variants.
    """
    if not url.startswith("https://fonts.googleapis.com/css"):
        raise ValueError("Invalid Google Fonts URL")
    
    # Headers to force TTF response (Legacy Android Agents get TTF)
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 2.2; en-us; Nexus One Build/FRF91) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        css_content = response.text
        
        # Regex to find @font-face blocks and extract family, weight, style, and URL
        blocks = re.findall(r'@font-face\s*\{(.*?)\}', css_content, re.DOTALL)
        
        downloaded = []
        for block in blocks:
            family_match = re.search(r'font-family:\s*\'?([^\';]+)\'?', block)
            style_match = re.search(r'font-style:\s*([^\';]+)', block)
            weight_match = re.search(r'font-weight:\s*([^\';]+)', block)
            url_match = re.search(r'url\((https://[^\)]+\.ttf)\)', block)
            
            if family_match and url_match:
                family_name = family_match.group(1).replace(" ", "")
                ttf_url = url_match.group(1)
                style = style_match.group(1) if style_match else "normal"
                weight = weight_match.group(1) if weight_match else "400"
                
                # Suffix mapping
                suffix = ""
                if weight in ["700", "bold"]:
                    suffix = "-Bold"
                if style == "italic":
                    suffix += "Italic" if suffix else "-Italic"
                if not suffix:
                    suffix = "-Regular"
                
                filename = f"{family_name}{suffix}.ttf"
                
                # Check if already downloaded to avoid redundant work in same session
                if any(d['filename'] == filename for d in downloaded): continue

                logger.info(f"Downloading {filename} from {ttf_url}")
                font_res = requests.get(ttf_url, timeout=10)
                font_res.raise_for_status()
                
                file_path = os.path.join(config.FONTS_DIR, filename)
                with open(file_path, "wb") as f:
                    f.write(font_res.content)
                
                # Sync to Supabase Storage
                try:
                    supabase.storage.from_("fonts").upload(filename, font_res.content, {"content-type": "font/ttf", "upsert": "true"})
                except Exception as se:
                    logger.error(f"Supabase Font Sync Failed for {filename}: {se}")

                downloaded.append({"name": family_name, "filename": filename, "style": style, "weight": weight})


        # Re-register
        register_custom_fonts()
        return downloaded
    except Exception as e:
        logger.error(f"Google Font Import Failed: {e}")
        raise e

def sync_font_to_storage(filename: str, content: bytes):
    """Sync a locally uploaded font to Supabase Storage"""
    try:
        supabase.storage.from_("fonts").upload(
            filename, 
            content, 
            {"content-type": "font/ttf", "upsert": "true"}
        )
        logger.info(f"Supabase Font Sync Success: {filename}")
    except Exception as e:
        logger.error(f"Supabase Font Sync Failed: {e}")

def get_template_bytes():
    """Fetches the certificate template as bytes. Fallback chain: Memory -> Supabase -> Local File."""
    global CACHE_TEMPLATE
    if CACHE_TEMPLATE:
        return CACHE_TEMPLATE

    # 1. Try Supabase Storage
    try:
        data = supabase.storage.from_("assets").download("template.png")
        if data:
            CACHE_TEMPLATE = data
            return data
    except Exception as e:
        logger.warning(f"Failed to fetch template from Supabase: {e}")

    # 2. Try Local Filesystem (Initial load or local dev)
    if os.path.exists(config.TEMPLATE_PATH):
        try:
            with open(config.TEMPLATE_PATH, "rb") as f:
                data = f.read()
                CACHE_TEMPLATE = data
                return data
        except:
            pass
    
    return None

def sync_fonts_from_storage():
    """Ensures all fonts in Supabase are available in FONTS_DIR (Stateless compatibility)"""
    try:
        res = supabase.storage.from_("fonts").list()
        for f_item in res:
            f_name = f_item['name']
            if f_name.startswith('.'): continue 
            local_path = os.path.join(config.FONTS_DIR, f_name)
            if not os.path.exists(local_path):
                logger.info(f"Downloading missing font from cloud: {f_name}")
                data = supabase.storage.from_("fonts").download(f_name)
                with open(local_path, "wb") as f:
                    f.write(data)
    except Exception as e:
        logger.error(f"Stateless font sync failed: {e}")

def load_assets_to_cache():
    """Industrial Optimization: Pre-loads assets to RAM to eliminate Disk I/O latency."""
    global CACHE_TEMPLATE, CACHE_FONTS, CACHE_CONFIG
    logger.info("Initializing Stateless Asset Cache...")
    
    # NEW: Sync fonts from cloud to local (/tmp or assets)
    sync_fonts_from_storage()
    register_custom_fonts()
    
    # Cache Config
    CACHE_CONFIG = load_config()
    print("Config Cached")

    # Cache Template
    get_template_bytes()
    
    # Cache Base Fonts (Pillow objects)
    # We pre-cache common sizes to avoid repeated FreeType initialization
    common_sizes = [32, 48, 52, 64]
    for size in common_sizes:
        CACHE_FONTS[f"Helvetica-{size}-Regular"] = get_pil_font("Helvetica", size)
        CACHE_FONTS[f"Helvetica-{size}-Bold"] = get_pil_font("Helvetica", size, weight="Bold")
    
    print(f"Pre-loaded {len(CACHE_FONTS)} font variants to RAM")


def px_to_pt(px):
    return px * 0.75

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def detect_name_line_cv2(pil_image):
    try:
        import numpy as np
        import cv2
        open_cv_image = np.array(pil_image.convert('RGB')) 
        open_cv_image = open_cv_image[:, :, ::-1].copy() 
        h, w = open_cv_image.shape[:2]
        
        # Focus on the likely name zone (middle 40-75% vertical)
        roi_start_y = int(h * 0.35)
        roi_end_y = int(h * 0.8)
        roi = open_cv_image[roi_start_y:roi_end_y, :]
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Target horizontal lines (underlines)
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 20, 1))
        detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        cnts, _ = cv2.findContours(detect_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best_line = None
        max_score = -1
        
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            # Line must be at least 10% of image width
            if cw > (w * 0.10) and cw > 2 * ch:
                line_center_x = x + cw / 2
                dist_from_v_center = abs(line_center_x - (w / 2))
                
                # Higher score for wider lines and lines closer to the horizontal center
                # Width bonus: (cw/w) * 1000
                # Center penalty: -(dist_from_v_center/w) * 2000 (penalty is high to force centering)
                score = (cw / w) * 1000 - (dist_from_v_center / w) * 2000
                
                if score > max_score:
                    max_score = score
                    best_line = (x, y, cw, ch)
                    
        if best_line:
            lx, ly, lcw, lch = best_line
            # Precise Center of the detected line
            target_x = lx + lcw // 2
            
            # If the best line is close enough to the absolute center, just snap to absolute center
            if abs(target_x - (w // 2)) < (w * 0.05):
                target_x = w // 2
                
            # Vertical: place exactly on the line (new baseline anchor handles the rest)
            target_y = roi_start_y + ly 
            return (int(target_x), int(target_y))
            
        return None
    except Exception as e:
        print(f"CV2 Enhanced Error: {e}")
        return None

def get_pil_font(family, size, weight='Regular', is_italic=False):
    variant = weight
    if is_italic:
        variant = "Bold Italic" if weight == "Bold" else "Italic"
    suffixes = {
        "Regular": ["", "-Regular", "Reg"],
        "Bold": ["-Bold", "bd", "b"],
        "Italic": ["-Italic", "i", "-Ital"],
        "Bold Italic": ["-BoldItalic", "bi", "-BoldItal"]
    }
    search_names = []
    for s in suffixes.get(variant, [""]):
        search_names.extend([f"{family}{s}.ttf", f"{family}{s}.otf"])
    if os.path.exists(family): return ImageFont.truetype(family, size)
    for name in search_names:
        path = os.path.join(config.FONTS_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    sys_paths = ["C:\\Windows\\Fonts\\", "/usr/share/fonts/truetype/liberation/", "/System/Library/Fonts/"]
    for sp in sys_paths:
        for name in search_names:
            full_p = os.path.join(sp, name)
            if os.path.exists(full_p):
                return ImageFont.truetype(full_p, size)
    try:
        if weight == "Bold": return ImageFont.truetype("arialbd.ttf", size)
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

def generate_certificate_png(name, cfg):
    """Generate PNG certificate with name overlay using PIL"""
    template_data = get_template_bytes()
    if not template_data:
        return None, "Template not found"
    
    try:
        # Load template image
        img = Image.open(io.BytesIO(template_data))
        draw = ImageDraw.Draw(img)
        
        # Get config
        name_pos = cfg.get('name_pos', {'x': img.width/2, 'y': img.height/2})
        font_fam = cfg.get('font_family', 'Helvetica')
        text_color = cfg.get('text_color', '#000000')
        font_size = cfg.get('font_size', 48) or 48
        weight = cfg.get('font_weight', 'Regular')
        is_italic = cfg.get('is_italic', False)
        is_centered = cfg.get('is_centered', False)
        stroke_w = cfg.get('stroke_width', 0)
        stroke_c = cfg.get('stroke_color', '#000000')
        
        # Get PIL font
        pil_font = get_pil_font(font_fam, font_size, weight, is_italic)
        
        # Get text bbox for positioning calculations
        # Use anchor='ls' (left-baseline) to match PDF baseline positioning
        x = name_pos['x']
        
        # In PDF: name_y_raw_px is from top, then converted to bottom for ReportLab
        # For PIL with top-origin, we use name_pos['y'] directly
        # BUT: PIL's draw.text with anchor='lt' starts at TOP of text
        # We need anchor='ls' (left-baseline) or anchor='la' (left-ascender) to match PDF
        y_from_top_px = name_pos['y']
        
        # PIL anchor='ls' means: x,y point to left edge of baseline
        # This matches what PDF does (baseline positioning)
        anchor = 'ls'  # left-baseline
        
        if is_centered:
            anchor = 'ms'  # middle-baseline for centered text
        
        # Convert hex colors to RGB
        rgb_color = hex_to_rgb(text_color)
        
        # Draw text with stroke if needed
        if stroke_w > 0:
            stroke_rgb = hex_to_rgb(stroke_c)
            # Draw stroke by offsetting in all directions
            for offset_x in range(-stroke_w, stroke_w + 1):
                for offset_y in range(-stroke_w, stroke_w + 1):
                    if offset_x != 0 or offset_y != 0:
                        draw.text(
                            (x + offset_x, y_from_top_px + offset_y), 
                            name, 
                            font=pil_font, 
                            fill=stroke_rgb,
                            anchor=anchor
                        )
        
        # Draw main text with baseline anchor
        draw.text((x, y_from_top_px), name, font=pil_font, fill=rgb_color, anchor=anchor)
        
        # Save to buffer
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        
        return buffer, None
        
    except Exception as e:
        logger.error(f"PNG generation error: {str(e)}")
        return None, str(e)

def generate_certificate_pdf(template_bytes_io, name, cfg, base_url="https://certgen.io"):
    # --- Background Loading ---
    template_data = get_template_bytes()
    if not template_data:
        # Fallback to provided BytesIO if it exists (for legacy/custom paths)
        actual_content = template_bytes_io if template_bytes_io and template_bytes_io.getbuffer().nbytes > 0 else None
        if not actual_content:
            return None, "Template not found. Please upload one in the designer."
    else:
        actual_content = io.BytesIO(template_data)

    buffer = io.BytesIO()
    img_reader = ImageReader(actual_content)
    iw_px, ih_px = img_reader.getSize()
    iw_pt, ih_pt = px_to_pt(iw_px), px_to_pt(ih_px)
    c = canvas.Canvas(buffer, pagesize=(iw_pt, ih_pt))
    c.drawImage(img_reader, 0, 0, width=iw_pt, height=ih_pt)
    name_pos = cfg.get('name_pos', {'x': iw_px/2, 'y': ih_px/2})
    font_fam = cfg.get('font_family', 'Helvetica')
    text_color = cfg.get('text_color', '#000000')
    name_x_pt = px_to_pt(name_pos['x'])
    name_y_raw_px = name_pos['y']
    name_y_pt = ih_pt - px_to_pt(name_y_raw_px)
    weight = cfg.get('font_weight', 'Regular')
    is_italic = cfg.get('is_italic', False)
    # --- Robust Font Resolution ---
    pdf_font = 'Helvetica'
    weight = cfg.get('font_weight', 'Regular')
    is_italic = cfg.get('is_italic', False)
    
    # Standard 14/Common Aliases Mapping
    family_map = {
        "times new roman": "Times",
        "times-roman": "Times",
        "serif": "Times",
        "arial": "Helvetica",
        "sans-serif": "Helvetica",
        "courier new": "Courier",
        "mono": "Courier"
    }
    
    base_family = family_map.get(font_fam.lower(), font_fam)
    
    # Determine Variant Suffix
    variant = "Regular"
    if weight == "Bold" and is_italic: variant = "BoldItalic"
    elif weight == "Bold": variant = "Bold"
    elif is_italic: variant = "Italic"

    # Greedy Search in Registered Fonts
    registered_fonts = pdfmetrics.getRegisteredFontNames()
    font_lookup_lower = {f.lower(): f for f in registered_fonts}
    
    # Try 1: Exact Family-Variant (e.g., SpaceGrotesk-Bold)
    targets = [
        f"{base_family}-{variant}",
        f"{base_family}{variant}",
        f"{base_family}_{variant}",
        f"{base_family} {variant}",
        base_family if variant == "Regular" else None
    ]
    
    found = False
    for t in filter(None, targets):
        if t.lower() in font_lookup_lower:
            pdf_font = font_lookup_lower[t.lower()]
            found = True
            break
            
    # Try 2: Standard Fallbacks if custom fails
    if not found:
        # Check if the base family itself is registered (synthetic fallback)
        if base_family.lower() in font_lookup_lower:
            pdf_font = font_lookup_lower[base_family.lower()]
            found = True
            logger.info(f"Using synthetic fallback for {base_family}-{variant} via base font {pdf_font}")
        elif base_family.lower() in ["times", "helvetica", "courier"]:
            # ReportLab standard font naming: Helvetica-Bold, Times-Italic, etc.
            sep = "-" if base_family.lower() != "times" or variant != "Regular" else ""
            if base_family.lower() == "times" and variant == "Regular": 
                pdf_font = "Times-Roman"
            else:
                pdf_font = f"{base_family.capitalize()}{sep}{variant}"
            # Final sanity check for standard names
            if pdf_font not in registered_fonts:
                # Last resort standard mapping
                mapping = {"Bold": "Bold", "Italic": "Oblique", "BoldItalic": "BoldOblique"}
                pdf_font = f"{base_family.capitalize()}-{mapping.get(variant, '')}".strip('-')
        else:
            logger.warning(f"Font variant '{base_family}-{variant}' not found. Falling back to Helvetica.")
            pdf_font = 'Helvetica-Bold' if weight == "Bold" else 'Helvetica'
    
    logger.info(f"Resolved PDF Font: {pdf_font} for requested {font_fam} ({weight})")
    # --- End Font Resolution ---

    base_font_size = cfg.get('font_size', 48) or 48
    # Scaling Factor: Align with px_to_pt (0.75) to match Browser (96dpi) vs PDF (72dpi)
    font_size = px_to_pt(base_font_size) 
    
    # Calculate text width and handle wrapping/scaling
    text_w = c.stringWidth(name, pdf_font, font_size)
    
    # Allow 90% of page width instead of hardcoded 400pt
    available_w = iw_pt * 0.9
    
    while text_w > available_w and font_size > 12:
        font_size -= 2
        text_w = c.stringWidth(name, pdf_font, font_size)
        
    c.setFont(pdf_font, font_size)
    r, g, b = hex_to_rgb(text_color)
    c.setFillColorRGB(r/255.0, g/255.0, b/255.0)
    is_centered = cfg.get('is_centered', False)
    # ReportLab y uses bottom-left origin.
    # name_y_pt is the distance from BOTTOM of page in points.
    
    # Calculate more accurate baseline offset using font metrics
    try:
        face = pdfmetrics.getFont(pdf_font).face
        # face.ascent is based on 1000 units per em
        ascent = (face.ascent * font_size) / 1000.0
    except:
        # Fallback if font metrics missing
        ascent = font_size * 0.8

    # Handle Outline (Stroke)
    stroke_w = cfg.get('stroke_width', 0)
    stroke_c = cfg.get('stroke_color', '#000000')
    if stroke_w > 0:
        sr, sg, sb = hex_to_rgb(stroke_c)
        c.setStrokeColorRGB(sr/255.0, sg/255.0, sb/255.0)
        c.setLineWidth(px_to_pt(stroke_w))
        c._code.append("2 Tr") # Fill and Stroke
    else:
        c._code.append("0 Tr") # Fill only

    # --- Apply Synthetic Styles if needed ---
    needs_synthetic_italic = is_italic and "italic" not in pdf_font.lower() and "oblique" not in pdf_font.lower()
    needs_synthetic_bold = weight == "Bold" and "bold" not in pdf_font.lower()

    if needs_synthetic_italic or needs_synthetic_bold:
        c.saveState()
        if needs_synthetic_italic:
            # Skew the coordinate system for italics (approx 0.2 radians)
            c.transform(1, 0, 0.2, 1, 0, 0)
        
        if needs_synthetic_bold:
            # Embolden using a small stroke
            c._code.append("2 Tr") # Fill and Stroke
            c.setStrokeColorRGB(r/255.0, g/255.0, b/255.0)
            c.setLineWidth(font_size * 0.03) # 3% of font size for moderate bolding

    if is_centered:
        c.drawCentredString(name_x_pt, name_y_pt, name)
    else:
        c.drawString(name_x_pt, name_y_pt, name)
    
    if needs_synthetic_italic or needs_synthetic_bold:
        c.restoreState()

    
    # Reset render mode for following prints
    c._code.append("0 Tr")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer




# Global semaphores for resource throttling - Increased for event-grade throughput
RENDER_SEMAPHORE = asyncio.Semaphore(15)
STORAGE_SEMAPHORE = asyncio.Semaphore(20)

async def process_claim(name: str, frontend_url: str, supabase: Any):
    name = name.strip()
    logger.info(f"Processing claim for name: {name}")
    
    res = supabase.table("Teams").select("*").execute()
    
    matched_name = None
    target_clean = name.strip().lower()
    
    cols = [
        "Team Lead Name", 
        "Team Member 1 Name", 
        "Team Member 2 Name", 
        "Team Member 3 Name", 
        "Team Member 4 Name", 
        "Team Member 5 Name"
    ]
    
    for row in res.data or []:
        for col in cols:
            val = row.get(col)
            if val and isinstance(val, str) and val.strip().lower() == target_clean:
                matched_name = val.strip()
                break
        if matched_name:
            break
            
    if not matched_name:
        logger.warning(f"Claim failed: No participant found for {name}")
        return None, "No participant found"
        
    name = matched_name
        
    base_url = frontend_url.rstrip('/')
    
    template_io = io.BytesIO(CACHE_TEMPLATE) if CACHE_TEMPLATE else None
    if not template_io:
        if not os.path.exists(config.TEMPLATE_PATH):
            return None, "Template not configured"
        with open(config.TEMPLATE_PATH, "rb") as f:
            template_io = io.BytesIO(f.read())

    cfg = load_config()
    loop = asyncio.get_event_loop()
    
    try:
        def render_pdf_job():
            tio = io.BytesIO(template_io.getvalue())
            return generate_certificate_pdf(tio, name, cfg, base_url)
        
        def render_png_job():
            return generate_certificate_png(name, cfg)
            
        async with RENDER_SEMAPHORE:
            # Generate both PDF and PNG in parallel
            pdf_task = loop.run_in_executor(None, render_pdf_job)
            png_task = loop.run_in_executor(None, render_png_job)
            
            pdf_buffer = await pdf_task
            png_result = await png_task
            
            if png_result[1]:  # Error in PNG generation
                logger.error(f"PNG generation failed: {png_result[1]}")
                png_buffer = None
            else:
                png_buffer = png_result[0]
        
        def upload_f(fname, data, ctype):
             supabase.storage.from_("certificates").upload(path=fname, file=data, file_options={"content-type": ctype, "upsert": "true"})
             return supabase.storage.from_("certificates").get_public_url(fname)

        async with STORAGE_SEMAPHORE:
            base_filename = str(uuid.uuid4())
            
            # Upload PDF
            pdf_fname = f"{base_filename}.pdf"
            pdf_fut = loop.run_in_executor(None, upload_f, pdf_fname, pdf_buffer.getvalue(), "application/pdf")
            pdf_public_url = await pdf_fut
            
            # Upload PNG if generated successfully
            png_public_url = None
            if png_buffer:
                png_fname = f"{base_filename}.png"
                png_fut = loop.run_in_executor(None, upload_f, png_fname, png_buffer.getvalue(), "image/png")
                png_public_url = await png_fut
        
        logger.info(f"Successfully processed claim for {name} (PDF + PNG)")
        return {
            "cert_url": pdf_public_url,
            "cert_png_url": png_public_url,
            "name": name
        }, None

    except Exception as e:
        logger.error(f"Claim generation error for {name}: {str(e)}")
        return None, str(e)

async def process_batch_import(teams: list, supabase: Any):
    import asyncio
    sem = asyncio.Semaphore(5)
    
    try:
        supabase.table("Teams").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    except Exception:
        pass
        
    async def process_t(t):
        async with sem:
            try:
                loop = asyncio.get_event_loop()
                def db_op():
                    lead = t.get("team_lead_name") if isinstance(t, dict) else getattr(t, "team_lead_name", None)
                    m1 = t.get("team_member_1_name") if isinstance(t, dict) else getattr(t, "team_member_1_name", None)
                    m2 = t.get("team_member_2_name") if isinstance(t, dict) else getattr(t, "team_member_2_name", None)
                    m3 = t.get("team_member_3_name") if isinstance(t, dict) else getattr(t, "team_member_3_name", None)
                    m4 = t.get("team_member_4_name") if isinstance(t, dict) else getattr(t, "team_member_4_name", None)
                    m5 = t.get("team_member_5_name") if isinstance(t, dict) else getattr(t, "team_member_5_name", None)
                    
                    data = {
                        "Team Lead Name": lead,
                        "Team Member 1 Name": m1,
                        "Team Member 2 Name": m2,
                        "Team Member 3 Name": m3,
                        "Team Member 4 Name": m4,
                        "Team Member 5 Name": m5,
                    }
                    supabase.table("Teams").insert(data).execute()
                await loop.run_in_executor(None, db_op)
                lead_name = t.get("team_lead_name") if isinstance(t, dict) else getattr(t, "team_lead_name", None)
                return {"name": lead_name, "status": "success"}
            except Exception as e:
                logger.error(f"Batch import error: {str(e)}")
                lead_name = t.get("team_lead_name") if isinstance(t, dict) else getattr(t, "team_lead_name", None)
                return {"name": lead_name, "status": "error", "error": str(e)}

    results = await asyncio.gather(*(process_t(t) for t in teams))
    return results

def load_config():
    global CACHE_CONFIG
    if CACHE_CONFIG:
        return CACHE_CONFIG

    # Primary: Load from Supabase
    try:
        res = supabase.table("LayoutConfig").select("config").limit(1).execute()
        if res.data and res.data[0].get("config"):
            cfg = res.data[0]["config"]
            # Sync to local for resilience
            save_config_local(cfg)
            CACHE_CONFIG = cfg
            return cfg
    except Exception as e:
        err_msg = str(e)
        if "521" in err_msg or "getaddrinfo" in err_msg:
            logger.warning("Supabase project is offline/restoring. Falling back to local configuration.")
        else:
            logger.warning(f"Supabase Config Load Failed, falling back to local: {err_msg[:100]}")

    # Fallback: Load from local file
    if os.path.exists(config.CONFIG_PATH):
        try:
            with open(config.CONFIG_PATH, "r") as f:
                cfg = json.load(f)
                CACHE_CONFIG = cfg
                return cfg
        except:
            pass
    
    return {
        'name_pos': {'x': 500, 'y': 400, 'max_width': 400},
        'page_size': [1000, 800],
        'font_family': 'Helvetica',
        'text_color': '#000000',
        'event_name': 'Certificate of Participation',
        'is_centered': True,
        'font_weight': 'Regular',
        'is_italic': False,
        'stroke_width': 0,
        'stroke_color': '#000000',
        'font_size': 48
    }

def save_config_local(cfg):
    with open(config.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)

def save_config(cfg):
    global CACHE_CONFIG
    CACHE_CONFIG = cfg
    
    # 1. Save Local
    save_config_local(cfg)
    
    # 2. Sync to Supabase
    try:
        res = supabase.table("LayoutConfig").select("id").limit(1).execute()
        if res.data:
            supabase.table("LayoutConfig").update({"config": cfg}).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("LayoutConfig").insert({"config": cfg}).execute()
        logger.info("Supabase Config Synced")
    except Exception as e:
        logger.error(f"Supabase Config Sync Failed: {e}")

# Industrial Initialization
initialize_fonts()
load_assets_to_cache()
# Trigger Reload
# Trigger Reload 2
# Final Fix Trigger
# QR Decommissioned 
