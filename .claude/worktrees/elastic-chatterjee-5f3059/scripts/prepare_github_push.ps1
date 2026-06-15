# MQ26 — Preparar repo local para el primer push a GitHub (Windows PowerShell)
# No ejecuta push: solo init, add, commit sugerido y recordatorios.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
    Write-Host "OK: git init + rama main"
} else {
    Write-Host "INFO: ya existe .git"
}

# Asegurar que .env no se commitea (.gitignore)
if (Test-Path ".env") {
    Write-Host "AVISO: .env presente — debe permanecer ignorado por .gitignore (no subir secretos)."
}

git add -A
git status

Write-Host ""
Write-Host "Siguiente (manual):"
Write-Host "  1. Crear repo vacio en GitHub (ej. mq26)"
Write-Host "  2. git remote add origin https://github.com/TU_USUARIO/mq26.git"
Write-Host "  3. git commit -m \"feat: MQ26 — deploy-ready\""
Write-Host "  4. git push -u origin main"
Write-Host ""
Write-Host "Deploy: ver docs/DEPLOY_RAILWAY.md"
