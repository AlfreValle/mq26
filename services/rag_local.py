"""
services/rag_local.py — recuperación local sobre los datos propios (H2, PoC).

"Memoria" consultable de MQ26 sin servicios externos ni costo: indexa texto
(docs, logs, audit) y recupera los fragmentos más relevantes a una consulta.
Usa TF-IDF + similitud coseno (scikit-learn, ya dependencia) — sin modelos
descargables, sin red, funciona en Windows.

Es la BASE de retrieval. La capa de respuesta en lenguaje natural (un LLM que
redacta usando estos fragmentos) es el chatbot de H4, que consume este índice.

Degrada con elegancia: si falta scikit-learn o el corpus está vacío, no explota.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fragmento:
    """Un trozo de texto recuperable, con su fuente (archivo / origen)."""

    fuente: str
    texto: str


@dataclass
class ResultadoRag:
    """Un fragmento recuperado con su score de relevancia [0, 1]."""

    score: float
    fragmento: Fragmento


def trocear_markdown(texto: str, fuente: str, *, min_chars: int = 40) -> list[Fragmento]:
    """Parte un texto (markdown) en fragmentos por bloques (líneas en blanco),
    descartando los muy cortos. Mantiene el encabezado más cercano como contexto."""
    bloques = re.split(r"\n\s*\n", texto or "")
    out: list[Fragmento] = []
    encabezado = ""
    for b in bloques:
        b = b.strip()
        if not b:
            continue
        if b.lstrip().startswith("#"):
            encabezado = b.splitlines()[0].lstrip("# ").strip()
        if len(b) < min_chars:
            continue
        prefijo = f"[{encabezado}] " if encabezado and not b.startswith("#") else ""
        out.append(Fragmento(fuente=fuente, texto=(prefijo + b)[:1500]))
    return out


class IndiceRag:
    """Índice TF-IDF sobre una lista de fragmentos. Inmutable tras construir."""

    def __init__(self, fragmentos: list[Fragmento]):
        self._fragmentos = fragmentos
        self._vectorizer = None
        self._matriz = None
        if not fragmentos:
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(
                lowercase=True, ngram_range=(1, 2), min_df=1, max_df=0.95
            )
            self._matriz = self._vectorizer.fit_transform([f.texto for f in fragmentos])
        except Exception:
            self._vectorizer = None
            self._matriz = None

    @property
    def n_fragmentos(self) -> int:
        return len(self._fragmentos)

    @property
    def disponible(self) -> bool:
        return self._vectorizer is not None and self._matriz is not None

    def buscar(self, consulta: str, k: int = 5) -> list[ResultadoRag]:
        """Top-k fragmentos por similitud coseno con la consulta (score>0)."""
        if not self.disponible or not str(consulta or "").strip():
            return []
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            q = self._vectorizer.transform([consulta])
            sims = cosine_similarity(q, self._matriz)[0]
        except Exception:
            return []
        idx_orden = sims.argsort()[::-1][:k]
        out: list[ResultadoRag] = []
        for i in idx_orden:
            s = float(sims[i])
            if s <= 0:
                continue
            out.append(ResultadoRag(score=round(s, 4), fragmento=self._fragmentos[i]))
        return out


def construir_indice_desde_textos(items: list[tuple[str, str]]) -> IndiceRag:
    """Construye el índice desde (fuente, texto). Trocea cada texto."""
    frags: list[Fragmento] = []
    for fuente, texto in items:
        frags.extend(trocear_markdown(texto, fuente))
    return IndiceRag(frags)


def construir_indice_docs(raiz: Path, patrones: tuple[str, ...] = ("docs/**/*.md",)) -> IndiceRag:
    """Indexa los documentos del repo (markdown) bajo `raiz`. PoC del corpus
    propio; ampliable a logs/audit trail más adelante."""
    items: list[tuple[str, str]] = []
    for patron in patrones:
        for p in sorted(Path(raiz).glob(patron)):
            try:
                items.append((str(p.relative_to(raiz)), p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return construir_indice_desde_textos(items)
