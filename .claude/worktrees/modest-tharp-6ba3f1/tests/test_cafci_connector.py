"""
tests/test_cafci_connector.py — Tests de cafci_connector.py (Sprint 26)
Mockea urlopen donde lo usa el conector (services.cafci_connector.urlopen),
equivalente a no llamar a CAFCI ni a urllib.request real.
Las funciones puras (_score_heuristico, _rendimiento_vacio) se testean sin mock.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestRendimientoVacio:
    def test_importa_sin_error(self):
        from services.cafci_connector import _rendimiento_vacio

        assert callable(_rendimiento_vacio)

    def test_retorna_dict(self):
        from services.cafci_connector import _rendimiento_vacio

        r = _rendimiento_vacio()
        assert isinstance(r, dict)

    def test_datos_ok_false(self):
        from services.cafci_connector import _rendimiento_vacio

        assert _rendimiento_vacio()["datos_ok"] is False

    def test_claves_requeridas(self):
        from services.cafci_connector import _rendimiento_vacio

        r = _rendimiento_vacio()
        for k in (
            "cuotaparte_actual",
            "ret_1m",
            "ret_3m",
            "ret_6m",
            "ret_12m",
            "vol_mensual",
            "sharpe_proxy",
            "datos_ok",
        ):
            assert k in r, f"Clave faltante: {k}"

    def test_valores_numericos_son_cero_o_defecto(self):
        from services.cafci_connector import _rendimiento_vacio

        r = _rendimiento_vacio()
        assert r["ret_1m"] == 0
        assert r["ret_12m"] == 0
        assert r["vol_mensual"] == 10


class TestScoreHeuristico:
    def test_usd_en_nombre_da_62(self):
        from services.cafci_connector import _score_heuristico

        score, det = _score_heuristico("BALANZ CAPITAL USD")
        assert score == 62.0
        assert det["fuente"] == "heurística"

    def test_dolar_en_nombre_da_62(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("MEGAINVER DOLAR")
        assert score == 62.0

    def test_renta_fija_da_52(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("MAF RENTA FIJA ARS")
        assert score == 52.0

    def test_ahorro_da_52(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("BALANZ AHORRO")
        assert score == 52.0

    def test_acciones_da_55(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("FIMA ACCIONES")
        assert score == 55.0

    def test_mixto_da_57(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("PIONEER MIXTO")
        assert score == 57.0

    def test_infraestructura_da_60(self):
        from services.cafci_connector import _score_heuristico

        score, _ = _score_heuristico("PELLEGRINI INFRAESTR")
        assert score == 60.0

    def test_sin_coincidencia_da_50(self):
        from services.cafci_connector import _score_heuristico

        score, det = _score_heuristico("FONDO RARO SIN CLASIFICAR")
        assert score == 50.0
        assert det["motivo"] == "Sin datos"

    def test_score_en_rango_valido(self):
        from services.cafci_connector import _score_heuristico

        nombres = [
            "FONDO USD",
            "FONDO ARS",
            "RENTA FIJA",
            "MIX",
            "VARIABLE",
            "INFRAESTR",
            "DESCONOCIDO",
        ]
        for nombre in nombres:
            score, _ = _score_heuristico(nombre)
            assert 50.0 <= score <= 62.0, f"{nombre}: score={score} fuera de rango"

    def test_retorna_tuple_float_dict(self):
        from services.cafci_connector import _score_heuristico

        result = _score_heuristico("TEST")
        assert isinstance(result, tuple)
        assert isinstance(result[0], float)
        assert isinstance(result[1], dict)
        assert "fuente" in result[1]

    def test_case_insensitive(self):
        from services.cafci_connector import _score_heuristico

        s1, _ = _score_heuristico("balanz capital usd")
        s2, _ = _score_heuristico("BALANZ CAPITAL USD")
        assert s1 == s2


class TestScoreFciReal:
    def test_sin_id_usa_heuristica(self):
        """Sin ID conocido → fallback a _score_heuristico sin red."""
        from services.cafci_connector import score_fci_real

        with patch(
            "services.cafci_connector.obtener_catalogo_fondos_cacheado",
            return_value=[],
        ):
            score, det = score_fci_real("FONDO_RARO_SIN_ID_XYZ", fondo_id=None)
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0
        assert "fuente" in det
        assert det["fuente"] == "heurística"

    def test_con_nombre_usd_sin_id(self):
        from services.cafci_connector import score_fci_real

        with patch(
            "services.cafci_connector.obtener_catalogo_fondos_cacheado",
            return_value=[],
        ):
            score, _ = score_fci_real("MI FONDO USD EXTRAÑO")
        assert score == 62.0

    def test_retorna_score_en_rango(self):
        from services.cafci_connector import score_fci_real

        with patch(
            "services.cafci_connector.obtener_catalogo_fondos_cacheado",
            return_value=[],
        ):
            score, _ = score_fci_real("CUALQUIER FONDO")
        assert 0.0 <= score <= 100.0

    def test_con_rendimiento_datos_ok_false_usa_heuristica(self):
        """obtener_rendimiento retorna datos_ok=False → heurística."""
        from services.cafci_connector import _rendimiento_vacio, score_fci_real

        with patch(
            "services.cafci_connector.obtener_rendimiento",
            return_value=_rendimiento_vacio(),
        ):
            score, det = score_fci_real("BALANZ AHORRO", fondo_id=14)
        assert det["fuente"] == "heurística"


class TestGetEndpoint:
    def _make_context_manager(self, body_bytes: bytes) -> MagicMock:
        inner = MagicMock()
        inner.read.return_value = body_bytes
        cm = MagicMock()
        cm.__enter__.return_value = inner
        cm.__exit__.return_value = False
        return cm

    def test_retorna_dict_con_respuesta_ok(self):
        from services.cafci_connector import _get

        data = {"data": [{"id": 1}]}
        mock_cm = self._make_context_manager(json.dumps(data).encode("utf-8"))
        with patch("services.cafci_connector.urlopen", return_value=mock_cm):
            result = _get("/fondo")
        assert isinstance(result, dict)
        assert "data" in result

    def test_url_error_retorna_none(self):
        from urllib.error import URLError

        from services.cafci_connector import _get

        with patch("services.cafci_connector.urlopen", side_effect=URLError("timeout")):
            result = _get("/fondo")
        assert result is None

    def test_http_error_retorna_none(self):
        from urllib.error import HTTPError

        from services.cafci_connector import _get

        err = HTTPError("http://api.test/fondo", 404, "Not Found", None, None)
        with patch("services.cafci_connector.urlopen", side_effect=err):
            result = _get("/fondo/999")
        assert result is None

    def test_exception_generica_retorna_none(self):
        from services.cafci_connector import _get

        with patch("services.cafci_connector.urlopen", side_effect=RuntimeError("error")):
            result = _get("/fondo")
        assert result is None

    def test_json_invalido_retorna_none(self):
        from services.cafci_connector import _get

        mock_cm = self._make_context_manager(b"ESTO NO ES JSON {{{")
        with patch("services.cafci_connector.urlopen", return_value=mock_cm):
            result = _get("/fondo")
        assert result is None


class TestListarFondos:
    def test_retorna_lista_vacia_con_api_fallida(self):
        from services.cafci_connector import listar_fondos

        with patch("services.cafci_connector._get", return_value=None):
            result = listar_fondos()
        assert result == []

    def test_retorna_lista_vacia_sin_data_key(self):
        from services.cafci_connector import listar_fondos

        with patch("services.cafci_connector._get", return_value={"error": "x"}):
            result = listar_fondos()
        assert result == []

    def test_retorna_lista_de_dicts_con_data_ok(self):
        from services.cafci_connector import listar_fondos

        mock_resp = {
            "data": [
                {
                    "id": 14,
                    "nombre": "BALANZ AHORRO",
                    "tipoFondo": {"id": 1},
                    "gerente": {"nombre": "Balanz"},
                },
            ]
        }
        with patch("services.cafci_connector._get", return_value=mock_resp):
            result = listar_fondos()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == 14
        assert result[0]["nombre"] == "BALANZ AHORRO"

    def test_cada_fondo_tiene_claves_requeridas(self):
        from services.cafci_connector import listar_fondos

        mock_resp = {
            "data": [
                {
                    "id": 1,
                    "nombre": "TEST FCI",
                    "tipoFondo": {"id": 2},
                    "gerente": {"nombre": "Gerente"},
                },
            ]
        }
        with patch("services.cafci_connector._get", return_value=mock_resp):
            result = listar_fondos()
        if result:
            for k in ("id", "nombre", "tipo_id", "tipo", "gerente"):
                assert k in result[0]


class TestResolverFondoIdConMapa:
    def test_mapa_normalizado_sin_catalogo(self):
        from services.cafci_connector import resolver_fondo_id_con_mapa

        assert resolver_fondo_id_con_mapa("BALANZ AHORRO", catalogo=[]) == 14

    def test_fuzzy_mapa_luego_catalogo(self):
        from services import cafci_connector as m
        from services.cafci_connector import resolver_fondo_id_con_mapa

        cat = [{"id": 500, "nombre": "OTRO FONDO X", "tipo": "Otros", "gerente_cuit": ""}]
        with patch.object(m, "resolver_fondo_id", return_value=500) as mock_inner:
            rid = resolver_fondo_id_con_mapa("ZZ MAPA INEXISTENTE", catalogo=cat)
        assert rid == 500
        mock_inner.assert_called_once()


class TestResolverFondoId:
    def test_match_exacto_por_nombre(self):
        from services.cafci_connector import resolver_fondo_id

        cat = [
            {
                "id": 99,
                "nombre": "FONDO PRUEBA SA",
                "tipo_id": 1,
                "tipo": "Renta Fija ARS",
                "gerente": "G",
                "gerente_cuit": "20123456789",
            },
        ]
        assert resolver_fondo_id("fondo prueba sa", catalogo=cat) == 99

    def test_match_por_nombre_y_cuit(self):
        from services.cafci_connector import resolver_fondo_id

        cat = [
            {"id": 1, "nombre": "FONDO X", "tipo": "Otros", "gerente_cuit": "20111111111"},
            {"id": 2, "nombre": "FONDO X", "tipo": "Otros", "gerente_cuit": "20222222222"},
        ]
        assert resolver_fondo_id("FONDO X", gerente_cuit="20-22222222-2", catalogo=cat) == 2

    def test_fuzzy_cuando_no_hay_exacto(self):
        from services.cafci_connector import resolver_fondo_id

        cat = [
            {"id": 7, "nombre": "BALANZ AHORRO PLUS", "tipo": "Otros", "gerente_cuit": ""},
        ]
        rid = resolver_fondo_id("BALANZ AHORRO PLU", catalogo=cat, cutoff_similarity=0.82)
        assert rid == 7


class TestCatalogoCacheado:
    def test_obtener_catalogo_usa_cache_si_ttl_ok(self):
        from services import cafci_connector as m

        fake = [{"id": 1, "nombre": "A", "tipo_id": None, "tipo": "Otros", "gerente": "", "gerente_cuit": ""}]
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        st = MagicMock()
        st.st_mtime = 1_700_000_000.0
        mock_path.stat.return_value = st
        mock_path.read_text.return_value = json.dumps({"fondos": fake}, ensure_ascii=False)

        with patch.object(m, "_CATALOG_FILE", mock_path):
            with patch("time.time", return_value=1_700_000_100.0):
                got = m.obtener_catalogo_fondos_cacheado(force_refresh=False, ttl_seconds=86400)
        assert got == fake
