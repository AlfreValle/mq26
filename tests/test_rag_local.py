"""Tests del retrieval local TF-IDF (H2 RAG, PoC)."""
from __future__ import annotations

from pathlib import Path

from services.rag_local import (
    construir_indice_desde_textos,
    construir_indice_docs,
    construir_indice_local,
    fragmentos_desde_auditoria,
    trocear_markdown,
)

_CORPUS = [
    ("riesgo.md", "# Riesgo\n\nEl VaR mide la pérdida esperada en un horizonte dado.\n\n"
                  "Cuando el VIX supera 40 el mercado está en pánico y conviene reducir riesgo."),
    ("perfiles.md", "# Perfiles\n\nUn perfil conservador prioriza renta fija y baja volatilidad.\n\n"
                    "El perfil arriesgado acepta más volatilidad por mayor retorno."),
    ("cedears.md", "# CEDEARs\n\nUn CEDEAR es un certificado que representa una acción extranjera "
                   "y cotiza en pesos en BYMA."),
]


def test_trocear_descarta_cortos_y_marca_encabezado():
    frags = trocear_markdown("# Titulo\n\nEste es un parrafo suficientemente largo para indexar.\n\nok",
                             "x.md", min_chars=40)
    assert any("Titulo" in f.texto for f in frags)
    # "ok" (corto) se descarta
    assert all(len(f.texto) >= 5 for f in frags)


def test_buscar_rankea_el_fragmento_relevante_primero():
    idx = construir_indice_desde_textos(_CORPUS)
    assert idx.disponible and idx.n_fragmentos >= 3
    res = idx.buscar("qué pasa cuando el VIX supera 40", k=3)
    assert res, "debería recuperar algo"
    assert "VIX" in res[0].fragmento.texto
    assert res[0].fragmento.fuente == "riesgo.md"
    assert 0.0 < res[0].score <= 1.0


def test_buscar_perfil_conservador():
    idx = construir_indice_desde_textos(_CORPUS)
    res = idx.buscar("perfil conservador renta fija", k=2)
    assert res and res[0].fragmento.fuente == "perfiles.md"


def test_consulta_vacia_o_sin_match_no_explota():
    idx = construir_indice_desde_textos(_CORPUS)
    assert idx.buscar("") == []
    assert isinstance(idx.buscar("zzzzz palabra inexistente qwerty"), list)


def test_corpus_vacio_no_explota():
    idx = construir_indice_desde_textos([])
    assert not idx.disponible
    assert idx.buscar("algo") == []


def test_fragmentos_desde_auditoria_y_busqueda():
    import pandas as pd

    df_reco = pd.DataFrame([
        {"evento": "SIMULACION", "cliente_nombre": "Ana", "perfil": "Arriesgado",
         "cartera": "Ana | Principal", "capital_ars": 5_000_000, "filas": 8,
         "actor": "estudio", "timestamp": "2026-06-20"},
    ])
    df_ord = pd.DataFrame([
        {"tipo": "COMPRA", "ticker": "AAPL", "cantidad": 3, "precio_ars": 100000,
         "cartera": "Ana | Principal", "modelo": "elite", "timestamp": "2026-06-20"},
    ])
    frags = fragmentos_desde_auditoria(df_reco=df_reco, df_ordenes=df_ord)
    assert len(frags) == 2
    assert any(f.fuente == "audit:recomendaciones" for f in frags)
    idx = construir_indice_desde_textos([(f.fuente, f.texto) for f in frags])
    res = idx.buscar("qué recomendé para perfil arriesgado", k=2)
    assert res and "Arriesgado" in res[0].fragmento.texto


def test_fragmentos_auditoria_vacios_no_explota():
    assert fragmentos_desde_auditoria(None, None) == []


def test_construir_indice_local_degrada_sin_audit():
    # Indexa docs reales + audit best-effort; nunca rompe.
    idx = construir_indice_local(Path(__file__).resolve().parents[1], incluir_audit=True)
    assert idx.n_fragmentos >= 0  # no explota aunque la BD no esté


def test_construir_indice_docs_del_repo():
    # Smoke: indexa los docs reales del repo y recupera algo coherente.
    raiz = Path(__file__).resolve().parents[1]
    idx = construir_indice_docs(raiz)
    # El repo tiene docs/; si por algún motivo no, el test no debe romper.
    if idx.n_fragmentos == 0:
        return
    res = idx.buscar("usabilidad para la venta", k=3)
    assert isinstance(res, list)
