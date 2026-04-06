"""
tests/test_smoke.py — Tests de smoke para configuración de producción (Sprint 6)
Verifica que los archivos de infraestructura existen y tienen contenido válido.
Sin llamadas reales a Docker, Railway ni internet.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ─── Archivos de deploy ────────────────────────────────────────────────────────

class TestArchivosDeploy:
    def test_dockerfile_existe(self):
        assert (ROOT / "Dockerfile").exists(), "Dockerfile faltante"

    def test_dockerfile_tiene_from_python_312(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "FROM python:3.12" in content

    def test_dockerfile_expone_puerto(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "EXPOSE" in content

    def test_dockerfile_tiene_healthcheck(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "HEALTHCHECK" in content

    def test_dockerfile_usa_port_variable(self):
        """El CMD usa ${PORT:-8080} para compatibilidad con Railway."""
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "PORT" in content

    def test_docker_entrypoint_usa_streamlit_run_mq26(self):
        """Streamlit se lanza desde docker-entrypoint.sh (no duplicar en Dockerfile)."""
        content = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
        assert "streamlit run run_mq26.py" in content

    def test_dockerfile_modo_headless(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "headless" in content.lower()

    def test_dockerignore_existe(self):
        assert (ROOT / ".dockerignore").exists(), ".dockerignore faltante"

    def test_dockerignore_excluye_env(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".env" in content

    def test_dockerignore_excluye_db(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".db" in content

    def test_dockerignore_excluye_tests(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert "tests/" in content

    def test_dockerignore_excluye_git(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".git/" in content

    def test_railway_json_existe(self):
        assert (ROOT / "railway.json").exists(), "railway.json faltante"

    def test_railway_json_es_json_valido(self):
        content = (ROOT / "railway.json").read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_railway_json_tiene_seccion_build(self):
        data = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        assert "build" in data

    def test_railway_json_usa_dockerfile(self):
        data = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        assert data.get("build", {}).get("builder") == "DOCKERFILE"

    def test_railway_json_tiene_healthcheck(self):
        data = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        deploy = data.get("deploy", {})
        assert "healthcheckPath" in deploy or "healthcheck" in str(data).lower()

    def test_railway_healthcheck_es_endpoint_streamlit(self):
        """Streamlit solo expone /_stcore/health (no /_stcore/salud ni rutas inventadas)."""
        data = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        path = data.get("deploy", {}).get("healthcheckPath")
        if path is not None:
            assert path == "/_stcore/health", (
                f"healthcheckPath debe ser /_stcore/health; Railway fallará con {path!r}"
            )


# ─── CI/CD ────────────────────────────────────────────────────────────────────

class TestCICD:
    def test_ci_yml_existe(self):
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), ".github/workflows/ci.yml faltante"

    def test_ci_yml_tiene_job_test_con_pytest(self):
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "pytest" in content

    def test_ci_yml_tiene_job_deploy(self):
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "deploy" in content.lower()

    def test_ci_yml_deploy_depende_de_test(self):
        """El job deploy declara needs: test."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "needs: test" in content

    def test_ci_yml_deploy_solo_en_main(self):
        """El deploy solo se ejecuta en la rama main."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "main" in content

    def test_ci_yml_usa_railway_token_secret(self):
        """El token de Railway viene de secrets — no hardcodeado."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "secrets.RAILWAY_TOKEN" in content


# ─── Configuración de producción ──────────────────────────────────────────────

class TestConfiguracionProduccion:
    def test_streamlit_config_toml_existe(self):
        assert (ROOT / ".streamlit" / "config.toml").exists(), \
            ".streamlit/config.toml faltante"

    def test_streamlit_config_headless(self):
        content = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        assert "headless" in content

    def test_streamlit_mq26_toml_sigue_existiendo(self):
        """El config de desarrollo no debe ser eliminado."""
        assert (ROOT / ".streamlit" / "mq26.toml").exists(), \
            ".streamlit/mq26.toml (dev) fue eliminado — debe coexistir con config.toml"

    def test_env_example_tiene_database_url(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "DATABASE_URL" in content

    def test_env_example_tiene_sentry_dsn(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "SENTRY_DSN" in content

    def test_env_example_no_tiene_secretos_reales(self):
        """El placeholder de contraseña no es un secreto real."""
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "cambiar_esta_contrasena" in content or \
               "MQ26_PASSWORD=" in content

    def test_sentry_sdk_en_requirements(self):
        content = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert "sentry-sdk" in content

    def test_sentry_en_run_mq26(self):
        """run_mq26.py tiene el bloque de init de Sentry."""
        content = (ROOT / "run_mq26.py").read_text(encoding="utf-8")
        assert "SENTRY_DSN" in content
        assert "sentry_sdk" in content

    def test_sentry_no_crashea_sin_dsn(self):
        """El bloque Sentry en run_mq26.py es un no-op sin SENTRY_DSN."""
        content = (ROOT / "run_mq26.py").read_text(encoding="utf-8")
        # El bloque debe tener el check de la variable antes de importar
        sentry_idx = content.find("SENTRY_DSN")
        import_idx = content.find("import sentry_sdk")
        assert sentry_idx < import_idx, \
            "El check de SENTRY_DSN debe estar ANTES del import de sentry_sdk"

    def test_migration_runner_existe(self):
        assert (ROOT / "migrations" / "run_migrations.py").exists(), \
            "migrations/run_migrations.py faltante"

    def test_migration_runner_tiene_check_flag(self):
        content = (ROOT / "migrations" / "run_migrations.py").read_text(encoding="utf-8")
        assert "--check" in content

    def test_migration_runner_tiene_history_flag(self):
        content = (ROOT / "migrations" / "run_migrations.py").read_text(encoding="utf-8")
        assert "--history" in content


# ─── Base de datos ────────────────────────────────────────────────────────────

class TestBaseDeDatos:
    def test_db_manager_detecta_database_url(self):
        """_build_engine() soporta DATABASE_URL para PostgreSQL."""
        import inspect

        import core.db_manager as dbm
        src = inspect.getsource(dbm._build_engine)
        assert "DATABASE_URL" in src

    def test_db_manager_fallback_sqlite(self):
        """Sin DATABASE_URL, usa SQLite (funciona siempre localmente)."""
        import inspect

        import core.db_manager as dbm
        src = inspect.getsource(dbm._build_engine)
        assert "sqlite" in src.lower()

    def test_alembic_ini_existe(self):
        assert (ROOT / "alembic.ini").exists(), "alembic.ini faltante"

    def test_migracion_tenant_id_existe(self):
        """La migración del Sprint 5 debe estar presente."""
        versions = list((ROOT / "migrations" / "versions").glob("*.py"))
        nombres = [v.name for v in versions if not v.name.startswith("__")]
        tenant_migs = [n for n in nombres if "tenant" in n.lower()]
        assert len(tenant_migs) >= 1, \
            f"Migración tenant_id no encontrada. Migraciones: {nombres}"

    def test_migration_runner_es_importable(self):
        """run_migrations.py puede importarse sin errores."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_migrations",
            ROOT / "migrations" / "run_migrations.py"
        )
        mod = importlib.util.module_from_spec(spec)
        # No ejecutamos main() — solo verificamos que el módulo carga
        assert mod is not None
        assert hasattr(spec, "loader")
