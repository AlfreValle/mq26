#!/usr/bin/env python3
"""
MQ26 Demo Launcher — demo lista en 1 comando.

Uso:
    python scripts/demo_launcher.py

Hace:
  1. Carga .env
  2. Verifica MQ26_PASSWORD
  3. Genera BD demo con 3 clientes (María, Carlos, Diego)
  4. Arranca Streamlit en modo demo en puerto 8502
  5. Abre el browser automáticamente

Datos demo disponibles tras arrancar:
  - María Fernández | Ahorro Familiar   — Conservadora | 1 año
  - Carlos Rodríguez | Crecimiento     — Moderada     | 3 años
  - Diego Martínez | Alta Rentabilidad  — Agresiva     | +5 años
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from time import sleep

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    print("\nMQ26 — Demo Launcher\n" + "-" * 42)

    env_file = ROOT / ".env"
    try:
        from dotenv import load_dotenv

        if env_file.is_file():
            load_dotenv(env_file)
            print("Variables de entorno cargadas desde .env")
        else:
            print("ADVERTENCIA: .env no encontrado — usando variables del sistema")
    except ImportError:
        print("ADVERTENCIA: python-dotenv no instalado — usando variables del sistema")

    pwd = os.environ.get("MQ26_PASSWORD", "")
    if len(pwd) < 8:
        print("\nERROR: MQ26_PASSWORD no definida o menor a 8 caracteres")
        print("  Agregá MQ26_PASSWORD=tupassword en el archivo .env")
        print("  Plantilla: copiar .env.example a .env")
        sys.exit(1)
    print("MQ26_PASSWORD OK")

    demo_db = ROOT / "0_Data_Maestra" / "mq26_demo.db"
    demo_db.parent.mkdir(parents=True, exist_ok=True)
    print("\n[1/3] Generando datos demo...")
    try:
        scripts_dir = str(ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from generate_demo_data import run as run_demo

        run_demo(str(demo_db))
        print(f"BD demo lista: {demo_db.name}")
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo generar la BD demo ({e})")
        print("   La app igual arranca — podés cargar datos manualmente")

    print("\n[2/3] Iniciando MQ26...")
    env_proc = {
        **os.environ,
        "DEMO_MODE": "true",
        "DEMO_DB_PATH": str(demo_db),
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "run_mq26.py",
            "--server.port",
            "8502",
            "--server.headless",
            "false",
            "--browser.gatherUsageStats",
            "false",
            "--browser.serverAddress",
            "localhost",
        ],
        cwd=str(ROOT),
        env=env_proc,
    )

    print("[3/3] Abriendo browser...")
    sleep(4)
    webbrowser.open("http://localhost:8502")

    print("\n" + "-" * 42)
    print("Demo lista en http://localhost:8502")
    print("   Usuario: admin  |  Contraseña: tu MQ26_PASSWORD")
    print("   Clientes demo: María Fernández · Carlos Rodríguez · Diego Martínez")
    print("\n   Ctrl+C para detener la demo\n")

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nDemo detenida.")


if __name__ == "__main__":
    main()
