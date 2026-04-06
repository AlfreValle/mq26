"""
Entrada legacy para `streamlit run mq26_main.py`.
El código completo de la app vive en run_mq26.py (una sola copia).
"""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / "run_mq26.py"), run_name="__main__")
