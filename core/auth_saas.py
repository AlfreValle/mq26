"""
core/auth_saas.py — Autenticación multi-asesor para modo SaaS (Sprint 5)
MQ26-DSS | Detecta AUTH_CONFIG en variables de entorno.

Si AUTH_CONFIG está definida: usa streamlit-authenticator (login individual).
Si NO está definida: retorna None → el caller usa el auth legacy (check_password).
Compatibilidad total: la app local actual funciona sin cambios.

Formato de AUTH_CONFIG (YAML serializado, para Railway / variables de entorno):
    credentials:
      usernames:
        alfredo:
          email: alfredo@example.com
          name: Alfredo Vallejos
          password: $2b$12$hash_bcrypt
    cookie:
      expiry_days: 30
      key: clave_secreta_aleatoria_larga
      name: mq26_auth_cookie

Generar hash de contraseña (streamlit-authenticator >= 0.4):
    import streamlit_authenticator as stauth
    print(stauth.Hasher.hash_passwords({"u": {"password": "mi_password"}}))
    # (en 0.2/0.3 era: stauth.Hasher(["mi_password"]).generate())
"""
from __future__ import annotations

import os
from typing import Any


def get_authenticator() -> Any | None:
    """
    Retorna un objeto Authenticate de streamlit-authenticator si AUTH_CONFIG
    está definida en las variables de entorno. Retorna None en modo local.

    El caller comprueba: if auth is None → usar check_password() legacy.
    Nunca lanza excepción — siempre degrada a None de forma silenciosa.
    """
    raw = os.environ.get("AUTH_CONFIG", "").strip()
    if not raw:
        return None
    try:
        import streamlit_authenticator as stauth
        import yaml
        config = yaml.safe_load(raw)
        # Argumentos POSICIONALES (robusto entre versiones): el 3er parámetro es
        # la cookie key — en 0.4 se llama `cookie_key` y en 0.2/0.3 `key`. Pasarlo
        # posicional evita el TypeError por el cambio de nombre del keyword.
        return stauth.Authenticate(
            config["credentials"],
            config["cookie"]["name"],
            config["cookie"]["key"],
            config["cookie"]["expiry_days"],
        )
    except ImportError as e:
        import warnings
        warnings.warn(
            f"AUTH_CONFIG definida pero streamlit-authenticator no instalado: {e}. "
            "Usando auth legacy. Instalar: pip install streamlit-authenticator pyyaml",
            stacklevel=2,
        )
        return None
    except Exception as e:
        import warnings
        warnings.warn(
            f"AUTH_CONFIG inválida o error al parsear: {e}. Usando auth legacy.",
            stacklevel=2,
        )
        return None


def get_tenant_id(authenticator: Any | None) -> str:
    """
    Retorna el email del asesor autenticado como tenant_id.
    Si authenticator es None (modo local), retorna 'default'.
    Invariante: nunca retorna string vacío — siempre retorna al menos 'default'.
    """
    if authenticator is None:
        return "default"
    try:
        import streamlit as st
        username = st.session_state.get("username", "")
        if not username:
            return "default"
        # Intentar obtener el email desde la config del authenticator
        credentials = getattr(authenticator, "_credentials", {})
        usernames = credentials.get("usernames", {})
        user_data = usernames.get(username, {})
        email = user_data.get("email", "")
        # Usar email si está disponible, sino usar el username como tenant_id
        return email if email else username
    except Exception:
        return "default"


def login_saas(authenticator: Any) -> tuple[str | None, bool | None, str | None]:
    """
    Ejecuta el widget de login de streamlit-authenticator.
    Retorna (name, authentication_status, username).
    authentication_status: True=ok, False=fallo, None=sin intentar.

    Compatible con 0.4.x y con 0.2/0.3:
    - 0.4: login() NO devuelve tupla — escribe en st.session_state
      ('name', 'authentication_status', 'username'). Se lee de ahí.
    - 0.2/0.3: login(form_name, location) devolvía la tupla; si una versión
      vieja la devuelve, se usa directamente.

    Invariante: no lanza excepción al caller — cualquier fallo devuelve (None, None, None).
    """
    try:
        import streamlit as st

        result = None
        try:
            # API 0.4.x (también 0.3.2+): keyword `location`.
            result = authenticator.login(location="main")
        except TypeError:
            try:
                # API 0.2/0.3 posicional (form_name, location).
                result = authenticator.login("Ingresar", "main")
            except Exception:
                result = None

        # Versiones viejas devuelven la tupla; usarla si vino.
        if isinstance(result, (tuple, list)) and len(result) == 3:
            return result[0], result[1], result[2]

        # 0.4: los valores viven en session_state.
        return (
            st.session_state.get("name"),
            st.session_state.get("authentication_status"),
            st.session_state.get("username"),
        )
    except Exception:
        return None, None, None
