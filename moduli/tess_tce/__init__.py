from .routes import create_blueprint


tess_tce_bp = create_blueprint()

__all__ = ["create_blueprint", "tess_tce_bp"]