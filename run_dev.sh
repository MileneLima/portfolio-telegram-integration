#!/bin/bash

echo "🔄 Iniciando bot em modo desenvolvimento..."

if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✅ Ambiente virtual ativado"
else
    echo "❌ Ambiente virtual não encontrado. Execute ./setup.sh primeiro"
    exit 1
fi

if [ ! -f .env ]; then
    echo "❌ Arquivo .env não encontrado. Configure as variáveis primeiro!"
    exit 1
fi

if [ ! -f credentials/google_service_account.json ]; then
    echo "⚠️  Aviso: Credenciais Google não encontradas"
fi

echo "🚀 Iniciando aplicação..."
python main.py
