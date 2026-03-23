from .routes import create_blueprint


tpf_bp = create_blueprint()

__all__ = ["create_blueprint", "tpf_bp"]