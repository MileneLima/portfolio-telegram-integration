import asyncio
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import select
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from loguru import logger

from config.settings import get_settings
from services.openai_service import openai_service
from services.sheets_service import sheets_service
from database.sqlite_db import get_db_session
from database.models import Transaction, UserConfig
from models.schemas import MessageInput, ProcessedTransaction, TransactionStatus, BotResponse, InterpretedTransaction


class TelegramFinanceBot:
    """Bot principal do Telegram"""

    def __init__(self):
        self.settings = get_settings()
        self.bot = None
        self.application = None

    async def setup(self):
        """Configurar bot"""
        try:
            # Criar aplicação do bot
            self.application = Application.builder().token(self.settings.telegram_bot_token).build()
            self.bot = self.application.bot

            # Configurar handlers
            await self._setup_handlers()

            # Configurar Google Sheets
            await sheets_service.setup()

            await self._setup_webhook()

            # Inicializar explicitamente para usar com webhook
            await self.application.initialize()
            logger.info("✅ Bot do Telegram configurado com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao configurar bot: {e}")
            raise

    async def _setup_handlers(self):
        """Configurar handlers do bot"""
        # Comandos
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("config", self.cmd_config))
        self.application.add_handler(CommandHandler("resumo", self.cmd_resumo))
        self.application.add_handler(CommandHandler("categoria", self.cmd_categorias))

        # Mensagens de texto (gastos)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_expense_message)
        )

        logger.info("✅ Handlers configurados")

    async def _setup_webhook(self):
        """Configurar webhook"""
        try:
            await self.bot.set_webhook(url=self.settings.telegram_webhook_url)
            logger.info(f"✅ Webhook configurado: {self.settings.telegram_webhook_url}")
        except Exception as e:
            logger.error(f"❌ Erro ao configurar webhook: {e}")
            raise

    async def process_update(self, update_data: Dict[str, Any]):
        """Processar update do webhook"""
        try:
            update = Update.de_json(update_data, self.bot)
            await self.application.process_update(update)
        except Exception as e:
            logger.error(f"❌ Erro ao processar update: {e}")
            raise

    # === COMMAND HANDLERS ===

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user_id = update.effective_user.id

        welcome_message = f"""
👋 **Olá! Eu sou seu assistente financeiro pessoal!**

💬 **Como usar:**  
Envie seus gastos em linguagem natural  
Exemplo: "gastei 25 reais no supermercado"  
Exemplo: "almoço no restaurante 35 reais"  
Exemplo: "uber 12 reais ontem"

📋 **Comandos disponíveis:**  
/resumo - Ver resumo mensal  
/categoria - Ver categorias disponíveis  
/config - Configurar planilha  
/help - Ajuda detalhada

🧠 **Eu interpreto automaticamente:**  
- Valor da compra  
- Local/descrição  
- Categoria (Alimentação, Transporte, etc.)  
- Data (hoje se não especificada)

🚀 **Vamos começar! Envie seu primeiro gasto!**
        """

        await update.message.reply_text(welcome_message, parse_mode='Markdown')

        # Salvar Configuração bÃ¡sica do usuÃ¡rio
        await self._ensure_user_config(user_id)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help"""
        help_message = """
🆘 **AJUDA - Como usar o bot:**

📝 **Enviar gastos:**  
"comprei pão na padaria 5 reais"  
"combustível no posto 80 reais"  
"farmácia remédio 25 reais"  
"cinema 30 reais sábado passado"

🎯 **Categorias automáticas:**  
• 🍔 Alimentação (comida, restaurante, mercado)  
• 🚗 Transporte (combustível, uber, ônibus)  
• 💊 Saúde (farmácia, consulta, exame)  
• 🎬 Lazer (cinema, shopping, diversão)  
• 🏠 Casa (supermercado, limpeza, contas)  
• 📦 Outros (demais gastos)

📌 **Comandos úteis:**  
• /resumo - Resumo do mês atual  
• /categoria - Ver todas as categorias  
• /config - Configurar sua planilha Google

💡 **Dicas:**  
• Seja natural na linguagem  
• Mencione o valor sempre  
• A data é opcional (assumo hoje)  
• Correções são bem-vindas!
        """

        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /config"""
        config_message = f"""
🛠️ **CONFIGURAÇÃO**

📊 **Planilha Google configurada:**  
ID: `{self.settings.google_sheets_spreadsheet_id[:20]}...`

✅ **Status:**  
• OpenAI: Ativo ({self.settings.openai_model})  
• Google Sheets: Conectado  
• Database: SQLite local

📋 **Estrutura da planilha:**  
• Abas mensais (Janeiro a Dezembro)  
• Aba "Resumo" com totais  
• Dados salvos automaticamente

🗂️ **Para alterar a planilha:**  
1. Configure nova planilha no arquivo .env  
2. Reinicie o bot  
3. Use /start para verificar

❓ **Precisa de ajuda?** Use /help
        """

        await update.message.reply_text(config_message, parse_mode='Markdown')

    async def cmd_resumo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /resumo - mostrar resumo mensal"""
        try:
            # Obter mês atual
            mes_atual = datetime.now().strftime("%B")  # Nome do mês em inglês
            meses_pt = {
                "January": "Janeiro", "February": "Fevereiro", "March": "Março",
                "April": "Abril", "May": "Maio", "June": "Junho",
                "July": "Julho", "August": "Agosto", "September": "Setembro",
                "October": "Outubro", "November": "Novembro", "December": "Dezembro"
            }
            mes_pt = meses_pt.get(mes_atual, "Outubro")  # Fallback para outubro

            # Obter dados do sheets
            resumo = await sheets_service.get_monthly_summary(mes_pt)

            # Montar mensagem
            if resumo['transacoes'] == 0:
                message = f" **Resumo de {mes_pt}**\n\nAinda não há transações este mês.\n\nEnvie seu primeiro gasto!"
            else:
                categorias_texto = ""
                for categoria, valor in resumo['categorias'].items():
                    if valor > 0:
                        categorias_texto += f" {categoria}: R$ {valor:.2f}\n"

                message = f"""
**Resumo de {mes_pt}**

**Total gasto:** R$ {resumo['total']:.2f}
**Transações:** {resumo['transacoes']}

**Por categoria:**
{categorias_texto}

use /help para mais comandos!
                """

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"❌ Erro no comando resumo: {e}")
            await update.message.reply_text("Erro ao gerar resumo. Tente novamente.")

    async def cmd_categorias(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /categoria"""
        categorias_message = """
📂 **CATEGORIAS DISPONÍVEIS:**

🍔 **Alimentação**
Supermercado, padaria, restaurante
Lanche, comida, bebida

🚗 **Transporte** 
Uber, taxi, ônibus
Combustível, estacionamento

💊 **Saúde**
Farmácia, consulta médica
Exames, medicamentos

🎬 **Lazer**
Cinema, teatro, shows
Jogos, diversão, viagens

🏠 **Casa**
Contas, limpeza, manutenção
Móveis, decoração

📦 **Outros**
Compras diversas
Itens não categorizados

❗️**A categoria é detectada automaticamente!**
    """

        await update.message.reply_text(categorias_message, parse_mode='Markdown')

    # === MESSAGE HANDLERS ===

    async def handle_expense_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar mensagem de gasto"""
        try:
            # Extrair dados da mensagem
            message_data = MessageInput(
                text=update.message.text,
                user_id=update.effective_user.id,
                message_id=update.message.message_id,
                chat_id=update.effective_chat.id
            )

            logger.info(f"🔄 Processando mensagem: '{message_data.text[:50]}...'")

            # Enviar indicador de digitação
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )

            # Processar com IA
            interpreted = await openai_service.interpret_financial_message(message_data.text)

            # Salvar no database
            transaction = await self._save_transaction(message_data, interpreted)

            # Salvar no Google Sheets
            row_number = await sheets_service.add_transaction(interpreted)

            # Atualizar transaction com número da linha
            await self._update_transaction_sheets_info(transaction.id, row_number)

            # Enviar confirmação
            await self._send_confirmation(update, interpreted, transaction.id)

            logger.info(f"✅ Transação processada com sucesso: ID {transaction.id}")

        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem: {e}")
            await update.message.reply_text(
                "Ops! Ocorreu um erro ao processar sua mensagem.\n"
                f"{str(e)}\n\n"
                "Envie apenas uma mensagem com seu gasto e o valor.\n"
                "Tente reformular a mensagem ou use /help"
            )

    async def _save_transaction(self, message_data: MessageInput, interpreted: InterpretedTransaction) -> ProcessedTransaction:
        """Salvar transação no database"""
        try:
            async for db in get_db_session():
                transaction = Transaction(
                    original_message=message_data.text,
                    user_id=message_data.user_id,
                    message_id=message_data.message_id,
                    chat_id=message_data.chat_id,
                    descricao=interpreted.descricao,
                    valor=interpreted.valor,
                    categoria=interpreted.categoria.value,
                    data_transacao=interpreted.data,
                    confianca=interpreted.confianca,
                    status="processed"
                )

                db.add(transaction)
                await db.commit()
                await db.refresh(transaction)

                return ProcessedTransaction(
                    id=transaction.id,
                    original_message=message_data.text,
                    interpreted_data=interpreted,
                    status=TransactionStatus.PROCESSED,
                    created_at=transaction.created_at
                )

        except Exception as e:
            logger.error(f"❌ Erro ao salvar transação: {e}")
            raise

    async def _update_transaction_sheets_info(self, transaction_id: int, row_number: int):
        """Atualizar informações do Google Sheets na transação"""
        try:
            async for db in get_db_session():
                transaction = await db.get(Transaction, transaction_id)
                if transaction:
                    transaction.sheets_row_number = row_number
                    transaction.sheets_updated_at = datetime.now()
                    await db.commit()

        except Exception as e:
            logger.error(f"❌ Erro ao atualizar info do sheets: {e}")

    async def _send_confirmation(self, update: Update, interpreted: InterpretedTransaction, transaction_id: int):
        """Enviar mensagem de confirmação"""
        # Emoji por categoria
        category_emoji = {
            "Alimentação": "🍔",
            "Transporte": "🚗",
            "Saúde": "💊",
            "Lazer": "🎬",
            "Casa": "🏠",
            "Outros": "📦"
        }

        emoji = category_emoji.get(interpreted.categoria.value, "🏷️")

        confirmation = f"""
**Gasto registrado com sucesso!**

{emoji} **{interpreted.descricao}**
Valor: **R$ {interpreted.valor:.2f}**
Categoria: **{interpreted.categoria.value}**
Data: **{interpreted.data.strftime('%d/%m/%Y')}**

Confiança: {interpreted.confianca:.0%}
ID: #{transaction_id}

Salvo na planilha Google! Use /resumo para ver totais.
        """

        await update.message.reply_text(confirmation, parse_mode='Markdown')

    async def _ensure_user_config(self, user_id: int):
        """Garantir que usuário tem Configuração"""
        try:
            async for db in get_db_session():
                # Verificar se usuário jÃ¡ existe
                result = await db.execute(
                    select(UserConfig).where(UserConfig.user_id == user_id)
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    # Criar Configuração padrÃ£o
                    user_config = UserConfig(
                        user_id=user_id,
                        spreadsheet_id=self.settings.google_sheets_spreadsheet_id
                    )
                    db.add(user_config)
                    await db.commit()
                    logger.info(f"✅ Configuração criada para usuário {user_id}")

        except Exception as e:
            logger.error(f"❌ Erro ao criar configuração do usuário: {e}")

    async def stop(self):
        """Parar bot"""
        if self.application:
            await self.application.stop()
            logger.info("Bot parado")


# Instância global
telegram_bot = TelegramFinanceBot()