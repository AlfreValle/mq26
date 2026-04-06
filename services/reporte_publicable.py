from __future__ import annotations

from datetime import date

from core.export_lineage import digest_inputs
from services.profile_proposals import build_profile_proposal

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #1F4E79; border-bottom: 2px solid #1F4E79; }}
  h2 {{ color: #1A6B3C; }}
  .perfil-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; }}
  .nota {{ background: #EBF3FB; padding: 12px; border-radius: 6px; border-left: 4px solid #1F4E79; }}
</style>
</head>
<body>{contenido}</body>
</html>"""


def generar_informe_mensual(
    mes_año: str | None = None,
    nota_asesor: str = "",
    incluir_carteras: list[str] | None = None,
) -> dict:
    """
    Genera informe mensual completo estilo BDI.
    Retorna {'html': str, 'hash_sha256': str, 'fecha': date, 'propuestas': dict}.
    """
    if not mes_año:
        from datetime import date as _d
        meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        hoy = _d.today()
        mes_año = f"{meses[hoy.month - 1]} {hoy.year}"

    perfiles   = incluir_carteras or ["conservador", "moderado", "arriesgado"]
    contenido  = [f"<h1>Informe Mensual — {mes_año}</h1>"]
    propuestas: dict = {}

    for perfil in perfiles:
        try:
            out = build_profile_proposal(perfil)
            propuestas[perfil] = out
            pesos_str = "<br>".join(
                f"<b>{t}</b>: {v*100:.1f}%"
                for t, v in sorted(out["pesos"].items(), key=lambda x: -x[1])[:5]
            )
            met = out.get("metricas", {})
            contenido.append(
                f'<div class="perfil-card">'
                f"<h2>Cartera {perfil.capitalize()}</h2>"
                f"<p>Modelo: <b>{out['modelo']}</b></p>"
                f"<p>Top posiciones:<br>{pesos_str}</p>"
                + (f"<p>Sharpe: {met.get('sharpe',0):.2f} | "
                   f"Vol: {met.get('volatilidad_anual',0)*100:.1f}%</p>" if met else "")
                + "</div>"
            )
        except Exception as e:
            contenido.append(f'<div class="perfil-card"><h2>{perfil.capitalize()}</h2>'
                             f"<p><i>No disponible: {e}</i></p></div>")

    if nota_asesor:
        contenido.append(f'<div class="nota"><b>Nota del asesor:</b> {nota_asesor}</div>')

    html = HTML_TEMPLATE.format(contenido="".join(contenido))
    hash_doc = digest_inputs(mes=mes_año, perfiles=perfiles, fecha=str(date.today()))

    return {
        "html":       html,
        "hash_sha256": hash_doc,
        "fecha":      date.today(),
        "propuestas": propuestas,
    }
