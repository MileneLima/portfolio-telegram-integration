"""
Sistema de controle financeiro pessoal via Telegram com IA

Author: Milene Lima
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from config.settings import get_settings
from config.logging_config import setup_logging
from bot.telegram_bot import TelegramFinanceBot
from database.sqlite_db import init_database


setup_logging()
logger = logging.getLogger(__name__)

bot_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciar lifecycle da aplicação"""
    global bot_instance

    try:
        logger.info("🔄 Iniciando Telegram Finance Bot...")

        await init_database()
        logger.info("✅ Database inicializado")

        bot_instance = TelegramFinanceBot()
        await bot_instance.setup()
        logger.info("✅ Bot configurado com sucesso")

        yield

    except Exception as e:
        logger.error(f"❌ Erro durante startup: {e}")
        raise
    finally:
        if bot_instance:
            await bot_instance.stop()
        logger.info("👋🏻 Aplicação finalizada")


settings = get_settings()
app = FastAPI(
    title="Telegram Finance Bot",
    description="Bot de controle financeiro pessoal com IA",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Endpoint de health check"""
    return {
        "message": "Telegram Finance Bot está funcionando!",
        "version": "1.0.0",
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    """Health check detalhado"""
    return {
        "status": "healthy",
        "bot_status": "active" if bot_instance else "inactive",
        "database": "connected"
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Endpoint para receber updates do Telegram"""
    try:
        if not bot_instance:
            raise HTTPException(status_code=500, detail="Bot not initialized")

        update_data = await request.json()
        logger.info(f"Received webhook update: {update_data.get('update_id')}")

        await bot_instance.process_update(update_data)

        return JSONResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )