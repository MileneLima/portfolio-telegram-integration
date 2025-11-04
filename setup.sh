#!/bin/bash

echo "🚀 Configurando Telegram Finance Bot..."

echo "📦 Criando ambiente virtual..."
python3 -m venv .venv
source .venv/bin/activate

echo "📋 Instalando dependências..."
pip install --upgrade pip
pip install -r requirements.txt

echo "📁 Criando diretórios..."
mkdir -p logs
mkdir -p credentials

if [ ! -f .env ]; then
    echo "📝 Criando arquivo .env..."
    cp .env.example .env
    echo "⚠️  Configure as variáveis no arquivo .env antes de continuar!"
fi

if [ ! -f credentials/google_service_account.json ]; then
    echo "⚠️  Coloque as credenciais do Google em credentials/google_service_account.json"
fi

echo "✅ Setup concluído!"
echo ""
echo "📝 Próximos passos:"
echo "1. Configure as variáveis no arquivo .env"
echo "2. Coloque as credenciais Google em credentials/"
echo "3. Execute: python main.py"
echo ""
echo "🔗 Links úteis:"
echo "• Bot Father: https://t.me/BotFather"
echo "• OpenAI API: https://platform.openai.com/api-keys"
echo "• Google Cloud Console: https://console.cloud.google.com/"
