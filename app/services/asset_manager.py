from .certificate_service import load_assets_to_cache as initialize_assets

# This module acts as a bridge for asset management functions 
# which have been integrated into the certificate_service.
__all__ = ["initialize_assets"]
