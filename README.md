# MQ26 — Terminal de Inversiones

**Optimizador cuantitativo de carteras BYMA · Argentina**

---

## Demo en 1 comando

```bash
git clone https://github.com/TU_USUARIO/mq26.git && cd mq26
pip install -r requirements.txt
cp .env.example .env          # editar con tu contraseña
python scripts/demo_launcher.py
```

Abre el browser automáticamente con 3 carteras de ejemplo precargadas.

---

## Instalación completa (5 minutos)

### 1. Requisitos

- Python 3.12+
- Windows / Mac / Linux

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar contraseñas

```bash
cp .env.example .env
```

Editar `.env` con al menos:

```env
MQ26_PASSWORD=tu_password_seguro    # admin — mínimo 8 caracteres
MQ26_VIEWER_PASSWORD=para_estudio   # rol asesor/estudio (opcional)
MQ26_INVESTOR_PASSWORD=para_cliente # rol inversor (opcional)
```

### 4. Verificar entorno

```bash
python scripts/mvp_preflight.py
```

Debe decir: `Preflight MVP: sin errores bloqueantes.`

### 5. Arrancar

```bash
streamlit run run_mq26.py --server.port 8502
```

Abrir `http://localhost:8502`

---

## Los 4 roles de usuario

| Rol | Usuario | Contraseña en `.env` | Qué ve |
|-----|---------|----------------------|--------|
| **Admin** | `admin` | `MQ26_PASSWORD` | Todo + panel Admin |
| **Asesor** | `asesor` | `MQ26_ADVISOR_PASSWORD` | Cartera, Optimización, Reporte |
| **Estudio** | `estudio` | `MQ26_VIEWER_PASSWORD` | Clientes, Cartera, Reportes |
| **Inversor** | `inversor` | `MQ26_INVESTOR_PASSWORD` | Mi Cartera (varios clientes vinculados posibles) |

Para crear usuarios con login propio por asesor/inversor: **Admin → Usuarios BD → Alta de usuario**.

---

## Importar cartera desde tu broker

Soporta: **Balanz** · **Bull Market Brokers** · **IOL**

En la app: **Mi Cartera → Agregar activo → Importar desde mi broker**

---

## Deploy en la nube (Railway)

- Guía completa: [`docs/DEPLOY_RAILWAY.md`](docs/DEPLOY_RAILWAY.md) (checklist rápido al inicio).
- Smoke HTTP tras el deploy: [`docs/SMOKE_PRODUCCION.md`](docs/SMOKE_PRODUCCION.md) y `python scripts/smoke_produccion.py --base-url https://TU-URL`.
- Backup y monitoreo: [`docs/OPS_BACKUP_Y_MONITOREO.md`](docs/OPS_BACKUP_Y_MONITOREO.md).
- Primer push desde Windows: `powershell -ExecutionPolicy Bypass -File scripts/prepare_github_push.ps1`

## Comercial (interno)

- Demo 30 min: [`docs/commercial/GUIA_DEMO_30MIN.md`](docs/commercial/GUIA_DEMO_30MIN.md)

---

## Tests

```bash
MQ26_PASSWORD=test pytest tests/ -q --tb=short
```

1562 tests, 0 failures (ajustar `MQ26_PASSWORD` si tu entorno lo exige; verificación Sprint 11 con `test_password_123`).

---

## Arquitectura

```
MQ26/
├── run_mq26.py              ← Entry point principal
├── config.py                ← Variables de entorno
├── .env                     ← Contraseñas (NO subir a git)
├── 0_Data_Maestra/          ← BD SQLite + CSV transaccional
├── 1_Scripts_Motor/         ← Motores cuantitativos (9 modelos)
├── core/                    ← Lógica de negocio (auth, BD, diagnóstico)
├── services/                ← Orquestación y reportes
├── ui/                      ← Interfaz Streamlit (1 archivo por tab)
├── scripts/                 ← Herramientas: demo, backup, preflight
└── docs/product/            ← Guías operativas
```
