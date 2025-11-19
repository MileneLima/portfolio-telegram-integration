@echo off
chcp 65001 >nul
echo 🔄 Iniciando bot em modo desenvolvimento...

if exist ".venv" (
    call .venv\Scripts\activate.bat
    echo ✅ Ambiente virtual ativado
) else (
    echo ❌ Ambiente virtual não encontrado. Execute setup.bat primeiro
    pause
    exit /b 1
)

if not exist ".env" (
    echo ❌ Arquivo .env não encontrado. Configure as variáveis primeiro!
    pause
    exit /b 1
)

if not exist "credentials\google_service_account.json" (
    echo ⚠️  Aviso: Credenciais Google não encontradas
)

echo 🚀 Iniciando aplicação...
python main.py

pause