# =============================================================================
# 1_Scripts_Motor/config.py — Reexporta todo desde el config.py raíz (G1)
# No duplicar constantes: usar el config.py del directorio raíz como fuente única.
# =============================================================================
import sys
from pathlib import Path

# Agregar el directorio raíz al path para importar el config principal
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Reexportar todo desde el config raíz
from config import *  # noqa: F401, F403

# Compatibilidad: aliases que algunos scripts del motor usan con nombres distintos
try:
    from config import (
        CCL_FALLBACK,  # noqa: F401
        RISK_FREE_RATE,  # noqa: F401
    )
    from config import PESO_MAX_OPT as PESO_MAX_ALTO  # noqa: F401
    from config import PESO_MIN_OPT as PESO_MIN_DEFAULT  # noqa: F401
    PESO_MAX_MEDIO = PESO_MAX_OPT * 0.6  # noqa: F841 — perfil moderado = 15%
    PESO_MAX_BAJO  = PESO_MAX_OPT * 0.4  # noqa: F841 — perfil bajo = 10%
    UMBRAL_ORDEN   = 0.05                # solo genera orden si desviación ≥ 5%
    RSI_MIN = RSI_COMPRA                 # noqa: F821
    RSI_MAX = RSI_VENTA                  # noqa: F821
    NOTA_VENTA = NOTA_ALERTA             # noqa: F821
except ImportError:
    pass
