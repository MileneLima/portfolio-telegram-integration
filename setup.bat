@echo off
chcp 65001 >nul
echo 🚀 Configurando Telegram Finance Bot...

echo 📦 Criando ambiente virtual...
python -m venv .venv
call .venv\Scripts\activate.bat

echo 📋 Instalando dependências...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo 📁 Criando diretórios...
if not exist "logs" mkdir logs
if not exist "credentials" mkdir credentials

if not exist ".env" (
    echo 📝 Criando arquivo .env...
    copy .env.example .env
    echo ⚠️  Configure as variáveis no arquivo .env antes de continuar!
)

if not exist "credentials\google_service_account.json" (
    echo ⚠️  Coloque as credenciais do Google em credentials\google_service_account.json
)

echo ✅ Setup concluído!
echo.
echo 📝 Próximos passos:
echo 1. Configure as variáveis no arquivo .env
echo 2. Coloque as credenciais Google em credentials\
echo 3. Execute: python main.py
echo.
echo 🔗 Links úteis:
echo • Bot Father: https://t.me/BotFather
echo • OpenAI API: https://platform.openai.com/api-keys
echo • Google Cloud Console: https://console.cloud.google.com/

pause