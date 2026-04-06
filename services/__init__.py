"""services — Lógica de dominio sin dependencias de Streamlit."""
from services.data_bridge import leer_ccl, publicar_ccl

__all__ = ["publicar_ccl", "leer_ccl"]
