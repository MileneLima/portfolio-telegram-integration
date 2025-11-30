"""
Bot principal do Telegram para processamento de mensagens financeiras
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy import select
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from loguru import logger

from config.settings import get_settings
from services.openai_service import openai_service
from services.sheets_service import sheets_service
from services.database_service import database_service
from services.audio_service import audio_service
from services.transcription_manager import transcription_manager
from database.sqlite_db import get_db_session
from database.models import Transaction, UserConfig
from models.schemas import MessageInput, ProcessedTransaction, TransactionStatus, InterpretedTransaction, AudioMessage, PendingTranscription


class TelegramFinanceBot:
    """Bot principal do Telegram"""

    def __init__(self):
        self.settings = get_settings()
        self.bot = None
        self.application = None

    async def setup(self):
        """Configurar bot"""
        try:
            self.application = Application.builder().token(self.settings.telegram_bot_token).build()
            self.bot = self.application.bot

            await self._setup_handlers()

            await sheets_service.setup()
            
            # Configurar callback de timeout para transcrições
            transcription_manager.set_timeout_notification_callback(self._notify_transcription_timeout)

            await self._setup_webhook()

            await self.application.initialize()
            logger.info("✅ Bot do Telegram configurado com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao configurar bot: {e}")
            raise

    async def _setup_handlers(self):
        """Configurar handlers do bot"""
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("config", self.cmd_config))
        self.application.add_handler(CommandHandler("resumo", self.cmd_resumo))
        self.application.add_handler(CommandHandler("categoria", self.cmd_categorias))
        self.application.add_handler(CommandHandler("insights", self.cmd_insights))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        self.application.add_handler(CommandHandler("sync", self.cmd_sync))
        self.application.add_handler(CommandHandler("meta", self.cmd_meta))
        self.application.add_handler(CommandHandler("metas", self.cmd_metas))

        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_expense_message)
        )
        
        # Handler para mensagens de áudio
        self.application.add_handler(
            MessageHandler(filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE, self.handle_audio_message)
        )
        
        # Handlers para confirmação de transcrição
        from telegram.ext import CallbackQueryHandler
        self.application.add_handler(CallbackQueryHandler(self.handle_transcription_confirmation, pattern="^confirm_yes_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_transcription_rejection, pattern="^confirm_no_"))
        
        # Handlers para confirmação de limpeza de metas
        self.application.add_handler(CallbackQueryHandler(self.handle_clear_goals_confirmation, pattern="^clear_goals_yes_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_clear_goals_cancellation, pattern="^clear_goals_no_"))

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

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user_id = update.effective_user.id

        welcome_message = f"""
👋 **Olá! Eu sou seu assistente financeiro pessoal com IA!**

💬 **Como usar:**  
Envie seus gastos em linguagem natural  
Exemplo: "gastei 25 reais no supermercado"  
Exemplo: "almoço no restaurante 35 reais"  
Exemplo: "investimento 500 reais poupança"  
Exemplo: "uber 12 reais ontem"

💻 **Comandos de Relatórios:**  
• `/resumo` - Resumo do mês atual  
• `/resumo [mês]` - Resumo de mês específico  
• `/resumo ano` - Resumo anual completo  
• `/stats` - Estatísticas detalhadas do banco  
• `/sync` - Sincronizar dados com Google Sheets

🎯 **Metas Financeiras:**  
• `/meta <categoria> <valor>` - Definir meta mensal  
• `/metas` - Ver todas as suas metas  
• Receba alertas ao atingir 80% e 100% da meta!

🧠 **Análises Inteligentes:**  
• `/insights` - Insights financeiros com IA (mês atual)  
• `/insights ano` - Análise anual completa com IA  

🛠️ **Configuração:**  
• `/categoria` - Ver todas as categorias  
• `/config` - Configurar planilha Google  
• `/sync` - Sincronizar dados com Google Sheets  
• `/help` - Ajuda completa e detalhada

🎯 **Categorias Automáticas:**  
🍔 Alimentação • 🚗 Transporte • 💊 Saúde  
🎬 Lazer • 🏠 Casa • 💰 Finanças • 📦 Outros

🚀 **Vamos começar! Envie seu primeiro gasto!**
        """

        await update.message.reply_text(welcome_message, parse_mode='Markdown')

        await self._ensure_user_config(user_id)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help"""
        help_message = """
🆘 **AJUDA COMPLETA - Assistente Financeiro com IA**

📝 **Como enviar gastos:**  
"comprei pão na padaria 5 reais"  
"combustível no posto 80 reais"  
"farmácia remédio 25 reais"  
"cinema 30 reais sábado passado"  
"investimento 500 reais poupança"

🎯 **Categorias automáticas:**  
• 🍔 **Alimentação** - comida, restaurante, mercado  
• 🚙 **Transporte** - combustível, uber, ônibus  
• 💊 **Saúde** - farmácia, consulta, exame  
• 🌊 **Lazer** - cinema, shopping, diversão  
• 🏠 **Casa** - supermercado, limpeza, contas  
• 💲 **Finanças** - investimentos, poupança  
• 📦 **Outros** - demais gastos

💻 **Comandos de Relatórios:**  
• `/resumo` - Resumo do mês atual  
• `/resumo janeiro` - Resumo de mês específico  
• `/resumo ano` - Resumo anual completo  
• `/stats` - Estatísticas detalhadas do banco  
• `/sync` - Sincronizar dados com Google Sheets

🎯 **Metas Financeiras:**  
• `/meta <categoria> <valor>` - Definir meta mensal  
• `/meta <categoria>` - Consultar meta específica  
• `/metas` - Ver todas as metas  
• `/meta limpar` - Remover todas as metas

🧠 **Análises com IA:**  
• `/insights` - Insights financeiros do mês atual  
• `/insights ano` - Análise anual completa com IA  

⚙️ ** Configuração e Ajuda:**  
• `/categoria` - Ver todas as categorias disponíveis  
• `/config` - Configurar sua planilha Google  
• `/sync` - Sincronizar dados com Google Sheets  
• `/sync clean` - Limpar dados inconsistentes  
• `/start` - Voltar ao menu inicial  
• `/help` - Esta ajuda completa

💡 **Dicas importantes:**  
• Seja natural na linguagem  
• Sempre mencione o valor  
• Data é opcional (assumo hoje)  
• Investimentos vão para categoria "Finanças"  
• Dados salvos localmente + Google Sheets
• Defina metas para controlar melhor seus gastos!
        """

        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /config"""
        config_message = f"""
🛠️ **CONFIGURAÇÃO DO SISTEMA**

📊 **Planilha Google configurada:**  
ID: `{self.settings.google_sheets_spreadsheet_id[:20]}...`

✅ **Status dos Serviços:**  
• 🤖 OpenAI: Ativo ({self.settings.openai_model})  
• 📊 Google Sheets: Conectado (visualização)  
• 💾 SQLite Database: Ativo (fonte principal)  
• ⚡ Performance: Ultra-rápida (milissegundos)

🏗️ **Estrutura da planilha:**  
• Abas mensais (Janeiro a Dezembro)  
• Aba "Resumo" com totais automáticos  
• Sincronização automática a cada transação

🔧 **Para alterar configurações:**  
1. Edite o arquivo .env para nova planilha  
2. Reinicie o bot completamente  
3. Use /start para verificar funcionamento  
4. Use /stats para ver estatísticas do banco

❓ **Precisa de ajuda?** Use /help
        """

        await update.message.reply_text(config_message, parse_mode='Markdown')

    async def cmd_resumo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /resumo - mostrar resumo mensal com parâmetros opcionais"""
        try:
            # NOTA: Não passa user_id pois o sistema é compartilhado entre usuários
            args = context.args
            period_type, period_value = self._parse_resumo_parameters(args)
            
            if period_type == "yearly":
                resumo = await database_service.get_yearly_summary()
                period_desc = "Anual"
                
                if not resumo or resumo.get('total_transacoes', 0) == 0:
                    message = f"📊 **Resumo {period_desc}**\n\nAinda não há transações neste período.\n\nEnvie seu primeiro gasto!"
                else:
                    categorias_texto = ""
                    for categoria, valor in resumo.get('categorias_totais', {}).items():
                        if valor > 0:
                            categorias_texto += f"• {categoria}: R$ {valor:.2f}\n"

                    total_gastos = resumo.get('total_gastos', 0)
                    total_investimentos = resumo.get('total_financas', 0)
                    transacoes = resumo.get('total_transacoes', 0)
                    
                    # Adicionar informação de origem se houver áudios
                    source_stats = resumo.get('source_stats', {})
                    source_info = ""
                    if source_stats.get('audio_transcribed', 0) > 0:
                        text_count = source_stats.get('text', 0)
                        audio_count = source_stats.get('audio_transcribed', 0)
                        source_info = f"\n\n📱 **Por tipo de entrada:**\n• 💬 Texto: {text_count} • 🎵 Áudio: {audio_count}"

                    message = f"""
📊 **Resumo {period_desc}**

💰 **Total gasto:** R$ {total_gastos:.2f}
💎 **Total investido:** R$ {total_investimentos:.2f}
📝 **Transações:** {transacoes}

**Por categoria:**
{categorias_texto}{source_info}

Use /help para mais comandos!
                    """
            else:
                if period_value:
                    meses_pt_to_num = {
                        "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
                        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
                        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
                    }
                    month = meses_pt_to_num.get(period_value.lower(), datetime.now().month)
                    year = datetime.now().year
                    period_desc = f"de {period_value}"
                else:
                    now = datetime.now()
                    month = now.month
                    year = now.year
                    meses_pt = [
                        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
                    ]
                    period_desc = f"de {meses_pt[month - 1]}"
                
                # NOTA: Não passa user_id pois o sistema é compartilhado entre usuários
                resumo = await database_service.get_monthly_summary(month, year)

                if not resumo or resumo.get('transacoes', 0) == 0:
                    message = f"📊 **Resumo {period_desc}**\n\nAinda não há transações neste período.\n\nEnvie seu primeiro gasto!"
                else:
                    categorias_texto = ""
                    for categoria, valor in resumo.get('categorias', {}).items():
                        if valor > 0:
                            categorias_texto += f"• {categoria}: R$ {valor:.2f}\n"

                    total_gastos = resumo.get('total', 0)
                    total_investimentos = resumo.get('categorias', {}).get('Finanças', 0)
                    transacoes = resumo.get('transacoes', 0)
                    
                    # Adicionar informação de origem se houver áudios
                    source_stats = resumo.get('source_stats', {})
                    source_info = ""
                    if source_stats.get('audio_transcribed', 0) > 0:
                        text_count = source_stats.get('text', 0)
                        audio_count = source_stats.get('audio_transcribed', 0)
                        source_info = f"\n\n📱 **Por tipo de entrada:**\n• 💬 Texto: {text_count} • 🎵 Áudio: {audio_count}"

                    message = f"""
📊 **Resumo {period_desc}**

💰 **Total gasto:** R$ {total_gastos:.2f}
💎 **Total investido:** R$ {total_investimentos:.2f}
📝 **Transações:** {transacoes}

**Por categoria:**
{categorias_texto}{source_info}

Use /help para mais comandos!
                    """

            await update.message.reply_text(message, parse_mode='Markdown')

        except ValueError as e:
            await update.message.reply_text(str(e), parse_mode='Markdown')
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

💰 **Finanças**
Investimentos, poupança
Aplicações financeiras

📦 **Outros**
Compras diversas
Itens não categorizados

❗️**A categoria é detectada automaticamente!**
    """

        await update.message.reply_text(categorias_message, parse_mode='Markdown')

    async def cmd_insights(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /insights - gerar insights financeiros com IA"""
        try:
            args = context.args
            period_type = "monthly"
            
            if args and args[0].lower() == "ano":
                period_type = "yearly"
            
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            transactions_data = await self._get_insights_data(period_type)
            
            if not transactions_data or len(transactions_data) == 0:
                period_desc = "do ano" if period_type == "yearly" else "do mês atual"
                await update.message.reply_text(
                    f"📊 **Insights Financeiros**\n\n"
                    f"Não há dados suficientes {period_desc} para gerar insights.\n\n"
                    f"Envie alguns gastos primeiro e tente novamente!"
                )
                return
            
            from models.schemas import InsightsPeriod
            period_desc = "Ano 2025" if period_type == "yearly" else f"{datetime.now().strftime('%B')} 2025"
            insights_period = InsightsPeriod.YEARLY if period_type == "yearly" else InsightsPeriod.MONTHLY
            insights_obj = await openai_service.generate_financial_insights(
                transactions_data, insights_period, period_desc
            )
            
            period_display = "Anual" if period_type == "yearly" else "Mensal"
            
            insights_text = insights_obj.insights_text
            if len(insights_text) > 2500:
                insights_text = insights_text[:2500] + "..."
            
            message = f"""🧠 **Insights Financeiros - {period_display}**

{insights_text}

💡 *Análise gerada por IA com base nos seus dados financeiros*"""
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"❌ Erro no comando insights: {e}")
            await update.message.reply_text(
                "Ops! Ocorreu um erro ao gerar insights.\n"
                "Tente novamente em alguns instantes.\n\n"
                "Use: /insights (mês atual) ou /insights ano (ano completo)"
            )

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /stats - mostrar estatísticas do banco de dados"""
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            stats = await database_service.get_database_stats()
            
            if not stats:
                await update.message.reply_text("❌ Erro ao obter estatísticas do banco de dados.")
                return
            
            category_analysis = await database_service.get_category_analysis()
            
            # Preparar estatísticas por tipo de entrada
            source_stats = stats.get('source_stats', {})
            text_count = source_stats.get('text', 0)
            audio_count = source_stats.get('audio_transcribed', 0)
            
            source_info = ""
            if audio_count > 0:
                source_info = f"""

📱 **Por tipo de entrada:**
• 💬 Mensagens de texto: {text_count}
• 🎵 Áudios transcritos: {audio_count}"""

            message = f"""
📊 **Estatísticas do Banco de Dados**

📈 **Resumo Geral:**
• Total de transações: {stats['total_transacoes']}
• Primeira transação: {stats['primeira_transacao']}
• Última transação: {stats['ultima_transacao']}
• Total gasto: R$ {stats['total_gasto']:.2f}
• Período: {stats['periodo_dias']} dias{source_info}

🏆 **Top 3 Categorias:**"""
            
            if category_analysis:
                sorted_categories = sorted(category_analysis.items(), key=lambda x: x[1]['total'], reverse=True)
                for i, (categoria, dados) in enumerate(sorted_categories[:3], 1):
                    message += f"\n{i}. {categoria}: R$ {dados['total']:.2f} ({dados['transacoes']} transações)"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Erro no comando stats: {e}")
            await update.message.reply_text("Erro ao obter estatísticas. Tente novamente.")

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /sync - sincronizar dados entre SQLite e Google Sheets"""
        try:
            args = context.args
            clean_mode = len(args) > 0 and args[0].lower() == "clean"
            
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            stats = await database_service.get_database_stats()
            
            if stats['total_transacoes'] == 0:
                await update.message.reply_text(
                    "ℹ️ **Nenhuma transação para sincronizar**\n\n"
                    "O banco de dados está vazio.\n"
                    "Envie alguns gastos primeiro e tente novamente."
                )
                return
            
            mode_text = " (LIMPEZA)" if clean_mode else ""
            
            initial_message = f"""
🔄 **Iniciando Sincronização{mode_text}**

📊 **Dados no banco:**
• {stats['total_transacoes']} transações
• Período: {stats['primeira_transacao']} a {stats['ultima_transacao']}
• Total: R$ {stats['total_gasto']:.2f}

⏳ Verificando necessidade de sincronização...
            """
            
            message = await update.message.reply_text(initial_message, parse_mode='Markdown')
            
            if clean_mode:
                await message.edit_text(
                    f"{initial_message}\n🧹 Executando limpeza de dados inconsistentes...",
                    parse_mode='Markdown'
                )
                
                integrity_before = await sheets_service._validate_sheet_data_integrity()
                
                await sheets_service._clean_inconsistent_data()
                
                integrity_after = await sheets_service._validate_sheet_data_integrity()
                
                removed_invalid = integrity_before.get('invalid_rows', 0) - integrity_after.get('invalid_rows', 0)
                removed_empty = integrity_before.get('empty_rows', 0) - integrity_after.get('empty_rows', 0)
                total_removed = removed_invalid + removed_empty
                
                clean_message = f"""
🧹 **Limpeza de Dados Concluída!**

📊 **Antes da limpeza:**
• Total de linhas: {integrity_before.get('total_rows', 0)}
• Linhas válidas: {integrity_before.get('valid_rows', 0)}
• Linhas inválidas: {integrity_before.get('invalid_rows', 0)}
• Linhas vazias: {integrity_before.get('empty_rows', 0)}

📊 **Após a limpeza:**
• Total de linhas: {integrity_after.get('total_rows', 0)}
• Linhas válidas: {integrity_after.get('valid_rows', 0)}
• Linhas removidas: {total_removed}

✅ **Integridade:** {'OK' if integrity_after.get('integrity_ok', False) else 'Problemas detectados'}

💡 **Apenas dados inseridos pelo bot permanecem na planilha!**
                """
                
                await message.edit_text(clean_message, parse_mode='Markdown')
                return
            
            if not clean_mode:
                sync_needed = await sheets_service._check_if_sync_needed()
                if not sync_needed:
                    await message.edit_text(
                        "✅ **Sincronização Desnecessária**\n\n"
                        "A planilha já está sincronizada com o banco de dados.\n\n"
                        "💡 **Opção disponível:**\n"
                        "• `/sync clean` - Limpar dados inconsistentes",
                        parse_mode='Markdown'
                    )
                    return
            
            await message.edit_text(
                f"{initial_message}\n🚀 Executando sincronização...",
                parse_mode='Markdown'
            )
            
            sync_result = await sheets_service.ensure_sheet_structure(always_sync=clean_mode)
            
            final_stats = await database_service.get_database_stats()
            
            sheets_info = ""
            if sync_result["new_sheets_created"]:
                sheets_info = f"\n🆕 **Abas criadas:** {', '.join(sync_result['missing_sheets'])}"
            
            sync_status = "✅ Executada" if sync_result["sync_executed"] else "ℹ️ Não necessária"
            
            success_message = f"""
✅ **Sincronização Concluída com Sucesso!**

📊 **Resultados:**
• {final_stats['total_transacoes']} transações processadas
• Período: {final_stats['primeira_transacao']} a {final_stats['ultima_transacao']}
• Total: R$ {final_stats['total_gasto']:.2f}
• Sincronização: {sync_status}{sheets_info}

🎯 **Otimizações aplicadas:**
• Inserção em lote por mês
• Verificação de duplicações
• Pausas para evitar rate limit
• Atualização automática do resumo

📋 **Planilha Google Sheets atualizada!**
Use `/resumo` para ver os dados organizados.
            """
            
            await message.edit_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Erro no comando sync: {e}")
            
            error_message = f"""
❌ **Erro na Sincronização**

Detalhes: {str(e)}

🔧 **Possíveis soluções:**
• Verifique sua conexão com a internet
• Confirme se a planilha Google está acessível
• Tente novamente em alguns minutos
• Use `/sync clean` para limpar dados inconsistentes

💡 **Seus dados estão seguros no banco local!**
            """
            
            try:
                await update.message.reply_text(error_message, parse_mode='Markdown')
            except:
                await update.message.reply_text("❌ Erro na sincronização. Tente novamente.")

    def _parse_resumo_parameters(self, args):
        """Parse e validação dos parâmetros do comando /resumo"""
        if not args:
            return "monthly", None
        
        param = args[0].lower()
        
        if param == "ano":
            return "yearly", None
        
        meses_validos = {
            "janeiro": "Janeiro", "fevereiro": "Fevereiro", "março": "Março",
            "abril": "Abril", "maio": "Maio", "junho": "Junho",
            "julho": "Julho", "agosto": "Agosto", "setembro": "Setembro",
            "outubro": "Outubro", "novembro": "Novembro", "dezembro": "Dezembro"
        }
        
        if param in meses_validos:
            return "monthly", meses_validos[param]
        
        meses_lista = ", ".join(meses_validos.keys())
        raise ValueError(
            f"❌ **Parâmetro inválido:** `{args[0]}`\n\n"
            f"**Uso correto:**\n"
            f"• `/resumo` - mês atual\n"
            f"• `/resumo ano` - resumo anual\n"
            f"• `/resumo [mês]` - mês específico\n\n"
            f"**Meses válidos:**\n{meses_lista}"
        )

    async def _get_insights_data(self, period_type: str):
        """Obter dados de transações para geração de insights"""
        try:
            if period_type == "yearly":
                return await database_service.get_transactions_for_period("yearly")
            else:
                return await database_service.get_transactions_for_period("monthly")
                
        except Exception as e:
            logger.error(f"❌ Erro ao obter dados para insights: {e}")
            return []

    async def cmd_meta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /meta - definir, consultar ou remover meta"""
        try:
            from services.goal_service import goal_service
            from models.schemas import ExpenseCategory
            from decimal import Decimal, InvalidOperation
            from datetime import datetime
            
            user_id = update.effective_user.id
            args = context.args
            
            logger.info(f"📝 Comando /meta recebido: user={user_id}, args={args}")
            
            # Caso 1: /meta limpar - remover todas as metas
            if args and args[0].lower() == "limpar":
                logger.info(f"🧹 Solicitação de limpeza de metas: user={user_id}")
                await self._handle_clear_all_goals(update, context, user_id)
                return
            
            # Caso 2: /meta <categoria> - consultar meta específica
            if len(args) == 1:
                await self._handle_query_goal(update, context, user_id, args[0])
                return
            
            # Caso 3: /meta <categoria> <valor> - definir ou atualizar meta
            if len(args) == 2:
                await self._handle_set_goal(update, context, user_id, args[0], args[1])
                return
            
            # Caso 4: Argumentos demais - formato inválido
            if len(args) > 2:
                logger.warning(f"⚠️ Formato de comando inválido: muitos argumentos ({len(args)}) por usuário {user_id}")
                await update.message.reply_text(
                    "❌ **Formato de comando inválido**\n\n"
                    "Você forneceu muitos argumentos.\n\n"
                    "**Formatos válidos:**\n"
                    "• `/meta <categoria> <valor>` - Definir meta\n"
                    "• `/meta <categoria>` - Consultar meta\n"
                    "• `/meta limpar` - Limpar todas\n\n"
                    "**Exemplo:** `/meta Alimentação 500`",
                    parse_mode='Markdown'
                )
                return
            
            # Caso 5: Sem argumentos - mostrar ajuda
            logger.info(f"ℹ️ Ajuda de /meta solicitada por usuário {user_id}")
            await self._show_meta_help(update)
            
        except Exception as e:
            logger.error(f"❌ Erro inesperado no comando /meta: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ **Erro inesperado ao processar comando**\n\n"
                "Tente novamente ou use `/meta` sem argumentos para ver a ajuda.",
                parse_mode='Markdown'
            )
    
    async def _handle_set_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                              user_id: int, categoria_input: str, valor_input: str):
        """Definir ou atualizar uma meta"""
        from services.goal_service import goal_service
        from models.schemas import ExpenseCategory
        from decimal import Decimal, InvalidOperation
        from datetime import datetime
        
        try:
            # Log da tentativa de criação de meta
            logger.info(f"🎯 Tentativa de definir meta: user={user_id}, categoria='{categoria_input}', valor='{valor_input}'")
            
            # Normalizar categoria
            categoria = goal_service.normalize_category(categoria_input)
            
            if not categoria:
                # Categoria inválida - mostrar lista de categorias com sugestões
                logger.warning(f"⚠️ Categoria inválida fornecida: '{categoria_input}' por usuário {user_id}")
                
                categorias_list = "\n".join([f"• {cat.value}" for cat in ExpenseCategory])
                
                # Tentar sugerir categorias similares
                sugestoes = self._get_category_suggestions(categoria_input)
                sugestoes_text = ""
                if sugestoes:
                    sugestoes_text = f"\n\n💡 **Você quis dizer:**\n" + "\n".join([f"• {s}" for s in sugestoes])
                
                await update.message.reply_text(
                    f"❌ **Categoria inválida:** `{categoria_input}`\n\n"
                    f"**Categorias disponíveis:**\n{categorias_list}{sugestoes_text}\n\n"
                    f"**Exemplo:** `/meta Alimentação 500`",
                    parse_mode='Markdown'
                )
                return
            
            # Validar valor
            try:
                # Remover espaços e validar string vazia
                valor_input_clean = valor_input.strip()
                if not valor_input_clean:
                    logger.warning(f"⚠️ Valor vazio fornecido por usuário {user_id}")
                    await update.message.reply_text(
                        "❌ **Valor não fornecido**\n\n"
                        "Você precisa especificar um valor para a meta.\n\n"
                        "**Formato:** `/meta <categoria> <valor>`\n"
                        "**Exemplo:** `/meta Alimentação 500`",
                        parse_mode='Markdown'
                    )
                    return
                
                valor = Decimal(valor_input_clean.replace(',', '.'))
                
                # Validar valores especiais (infinity, NaN)
                if valor.is_infinite() or valor.is_nan():
                    logger.warning(f"⚠️ Valor especial inválido fornecido: '{valor_input}' por usuário {user_id}")
                    await update.message.reply_text(
                        "❌ **Valor inválido**\n\n"
                        "O valor deve ser um número finito.\n\n"
                        "**Exemplos válidos:**\n"
                        "• `/meta Alimentação 500`\n"
                        "• `/meta Transporte 300.50`",
                        parse_mode='Markdown'
                    )
                    return
                
                if valor < 0:
                    logger.warning(f"⚠️ Valor negativo fornecido: {valor} por usuário {user_id}")
                    await update.message.reply_text(
                        "❌ **Valor inválido**\n\n"
                        "O valor deve ser um número positivo.\n\n"
                        "**Exemplos válidos:**\n"
                        "• `/meta Alimentação 500`\n"
                        "• `/meta Transporte 300.50`",
                        parse_mode='Markdown'
                    )
                    return
                
                # Caso especial: valor 0 = remover meta
                if valor == 0:
                    logger.info(f"🗑️ Remoção de meta solicitada: user={user_id}, categoria={categoria.value}")
                    await self._handle_remove_goal(update, context, user_id, categoria)
                    return
                
            except (InvalidOperation, ValueError) as e:
                logger.warning(f"⚠️ Formato de valor inválido: '{valor_input}' por usuário {user_id} - {e}")
                await update.message.reply_text(
                    "❌ **Valor inválido**\n\n"
                    "O valor deve ser um número.\n\n"
                    "**Exemplos válidos:**\n"
                    "• `/meta Alimentação 500`\n"
                    "• `/meta Transporte 300.50`",
                    parse_mode='Markdown'
                )
                return
            
            # Criar ou atualizar meta
            now = datetime.now()
            goal = await goal_service.create_or_update_goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor,
                mes=now.month,
                ano=now.year
            )
            
            # Obter progresso atual
            progress = await goal_service.get_goal_progress(
                user_id=user_id,
                categoria=categoria,
                mes=now.month,
                ano=now.year
            )
            
            # Montar mensagem de confirmação
            category_emoji = {
                "Alimentação": "🍔",
                "Transporte": "🚗",
                "Saúde": "💊",
                "Lazer": "🎬",
                "Casa": "🏠",
                "Finanças": "💲",
                "Outros": "📦"
            }
            
            emoji = category_emoji.get(categoria.value, "🎯")
            status_emoji = "✅" if progress.status.value == "dentro_meta" else "⚠️" if progress.status.value == "proximo_limite" else "🚨"
            
            # Nomes dos meses em português
            meses_pt = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_nome = meses_pt[now.month - 1]
            
            confirmation = f"""
{emoji} **Meta definida com sucesso!**

**Categoria:** {categoria.value}
**Valor da meta:** R$ {valor:.2f}
**Período:** {mes_nome}/{now.year}

📊 **Progresso atual:**
• Gasto: R$ {progress.valor_gasto:.2f}
• Progresso: {progress.progresso_percentual:.1f}%
• Status: {status_emoji} {progress.status.value.replace('_', ' ').title()}

Use /metas para ver todas as suas metas!
            """
            
            await update.message.reply_text(confirmation, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Erro ao definir meta: {e}")
            await update.message.reply_text(
                "❌ Erro ao definir meta. Tente novamente."
            )
    
    async def _handle_query_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                 user_id: int, categoria_input: str):
        """Consultar meta específica"""
        from services.goal_service import goal_service
        from models.schemas import ExpenseCategory
        from datetime import datetime
        
        try:
            logger.info(f"🔍 Consulta de meta: user={user_id}, categoria='{categoria_input}'")
            
            # Normalizar categoria
            categoria = goal_service.normalize_category(categoria_input)
            
            if not categoria:
                logger.warning(f"⚠️ Categoria inválida na consulta: '{categoria_input}' por usuário {user_id}")
                
                categorias_list = "\n".join([f"• {cat.value}" for cat in ExpenseCategory])
                
                # Tentar sugerir categorias similares
                sugestoes = self._get_category_suggestions(categoria_input)
                sugestoes_text = ""
                if sugestoes:
                    sugestoes_text = f"\n\n💡 **Você quis dizer:**\n" + "\n".join([f"• {s}" for s in sugestoes])
                
                await update.message.reply_text(
                    f"❌ **Categoria inválida:** `{categoria_input}`\n\n"
                    f"**Categorias disponíveis:**\n{categorias_list}{sugestoes_text}\n\n"
                    f"**Exemplo:** `/meta Alimentação`",
                    parse_mode='Markdown'
                )
                return
            
            # Buscar meta
            now = datetime.now()
            progress = await goal_service.get_goal_progress(
                user_id=user_id,
                categoria=categoria,
                mes=now.month,
                ano=now.year
            )
            
            if not progress:
                await update.message.reply_text(
                    f"ℹ️ **Nenhuma meta definida para {categoria.value}**\n\n"
                    f"Para criar uma meta, use:\n"
                    f"`/meta {categoria.value} <valor>`\n\n"
                    f"**Exemplo:** `/meta {categoria.value} 500`",
                    parse_mode='Markdown'
                )
                return
            
            # Mostrar detalhes da meta
            category_emoji = {
                "Alimentação": "🍔",
                "Transporte": "🚗",
                "Saúde": "💊",
                "Lazer": "🎬",
                "Casa": "🏠",
                "Finanças": "💲",
                "Outros": "📦"
            }
            
            emoji = category_emoji.get(categoria.value, "🎯")
            status_emoji = "✅" if progress.status.value == "dentro_meta" else "⚠️" if progress.status.value == "proximo_limite" else "🚨"
            
            # Calcular quanto falta
            falta = progress.valor_meta - progress.valor_gasto
            
            # Nomes dos meses em português
            meses_pt = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_nome = meses_pt[now.month - 1]
            
            message = f"""
{emoji} **Meta de {categoria.value}**

💰 **Valor da meta:** R$ {progress.valor_meta:.2f}
📊 **Gasto atual:** R$ {progress.valor_gasto:.2f}
📈 **Progresso:** {progress.progresso_percentual:.1f}%
{status_emoji} **Status:** {progress.status.value.replace('_', ' ').title()}

{'💚 **Disponível:** R$ ' + f'{falta:.2f}' if falta > 0 else '🚨 **Excedido em:** R$ ' + f'{abs(falta):.2f}'}

**Período:** {mes_nome}/{now.year}

💡 **Dica:** Use `/meta {categoria.value} 0` para remover esta meta
            """
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Erro ao consultar meta: {e}")
            await update.message.reply_text(
                "❌ Erro ao consultar meta. Tente novamente."
            )
    
    async def _handle_remove_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  user_id: int, categoria: 'ExpenseCategory'):
        """Remover uma meta específica"""
        from services.goal_service import goal_service
        from datetime import datetime
        
        try:
            now = datetime.now()
            success = await goal_service.delete_goal(
                user_id=user_id,
                categoria=categoria,
                mes=now.month,
                ano=now.year
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ **Meta de {categoria.value} removida com sucesso!**\n\n"
                    f"O sistema não calculará mais o progresso para esta categoria.\n\n"
                    f"Use /metas para ver suas metas restantes.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ **Nenhuma meta encontrada para {categoria.value}**\n\n"
                    f"Use /metas para ver suas metas ativas.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"❌ Erro ao remover meta: {e}")
            await update.message.reply_text(
                "❌ Erro ao remover meta. Tente novamente."
            )
    
    async def _handle_clear_all_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     user_id: int):
        """Remover todas as metas com confirmação"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        try:
            # Criar botões de confirmação
            keyboard = [
                [
                    InlineKeyboardButton("✅ Sim, limpar tudo", callback_data=f"clear_goals_yes_{user_id}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"clear_goals_no_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ **Confirmar limpeza de metas**\n\n"
                "Você tem certeza que deseja remover **TODAS** as suas metas?\n\n"
                "Esta ação não pode ser desfeita.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar limpeza de metas: {e}")
            await update.message.reply_text(
                "❌ Erro ao processar comando. Tente novamente."
            )
    
    def _get_category_suggestions(self, input_text: str) -> list:
        """Obter sugestões de categorias similares"""
        from models.schemas import ExpenseCategory
        from services.goal_service import goal_service
        
        if not input_text or len(input_text.strip()) < 2:
            return []
        
        suggestions = []
        input_lower = input_text.lower().strip()
        
        # Buscar categorias que contenham o texto ou vice-versa
        for category in ExpenseCategory:
            category_lower = category.value.lower()
            
            # Substring match
            if input_lower in category_lower or category_lower in input_lower:
                suggestions.append(category.value)
                continue
            
            # Levenshtein distance (similaridade)
            distance = goal_service._levenshtein_distance(input_lower, category_lower)
            threshold = max(len(input_lower), len(category_lower)) * 0.4
            
            if distance <= threshold:
                suggestions.append(category.value)
        
        return suggestions[:3]  # Máximo 3 sugestões
    
    async def _show_meta_help(self, update: Update):
        """Mostrar ajuda do comando /meta"""
        from models.schemas import ExpenseCategory
        
        categorias_list = "\n".join([f"• {cat.value}" for cat in ExpenseCategory])
        
        help_message = f"""
🎯 **Comando /meta - Gerenciar Metas Financeiras**

**Definir ou atualizar meta:**
`/meta <categoria> <valor>`
Exemplo: `/meta Alimentação 500`

**Consultar meta específica:**
`/meta <categoria>`
Exemplo: `/meta Alimentação`

**Remover meta:**
`/meta <categoria> 0`
Exemplo: `/meta Alimentação 0`

**Limpar todas as metas:**
`/meta limpar`

**Categorias disponíveis:**
{categorias_list}

💡 **Dicas:**
• As metas são mensais e reiniciam automaticamente
• Você receberá alertas ao atingir 80% e 100% da meta
• Use /metas para ver todas as suas metas
• Não se preocupe com acentos ou maiúsculas/minúsculas
        """
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def cmd_metas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /metas - listar todas as metas"""
        try:
            from services.goal_service import goal_service
            from datetime import datetime
            
            user_id = update.effective_user.id
            now = datetime.now()
            
            logger.info(f"📊 Listagem de metas solicitada: user={user_id}, mes={now.month}, ano={now.year}")
            
            # Buscar todas as metas do usuário
            goals = await goal_service.get_user_goals(
                user_id=user_id,
                mes=now.month,
                ano=now.year
            )
            
            if not goals:
                logger.info(f"ℹ️ Nenhuma meta encontrada para usuário {user_id}")
                await update.message.reply_text(
                    "ℹ️ **Você ainda não tem metas definidas**\n\n"
                    "Para criar uma meta, use:\n"
                    "`/meta <categoria> <valor>`\n\n"
                    "**Exemplo:** `/meta Alimentação 500`\n\n"
                    "💡 **Dica:** As metas ajudam você a controlar seus gastos mensais!",
                    parse_mode='Markdown'
                )
                return
            
            logger.info(f"✅ {len(goals)} meta(s) encontrada(s) para usuário {user_id}")
            
            # Montar mensagem com todas as metas
            category_emoji = {
                "Alimentação": "🍔",
                "Transporte": "🚗",
                "Saúde": "💊",
                "Lazer": "🎬",
                "Casa": "🏠",
                "Finanças": "💲",
                "Outros": "📦"
            }
            
            metas_text = ""
            total_meta = Decimal('0')
            total_gasto = Decimal('0')
            
            for goal in goals:
                emoji = category_emoji.get(goal.categoria.value, "🎯")
                status_emoji = "✅" if goal.status.value == "dentro_meta" else "⚠️" if goal.status.value == "proximo_limite" else "🚨"
                
                metas_text += f"\n{emoji} **{goal.categoria.value}**\n"
                metas_text += f"   Meta: R$ {goal.valor_meta:.2f} | Gasto: R$ {goal.valor_gasto:.2f}\n"
                metas_text += f"   {status_emoji} {goal.progresso_percentual:.1f}%\n"
                
                total_meta += goal.valor_meta
                total_gasto += goal.valor_gasto
            
            # Calcular progresso geral
            progresso_geral = float((total_gasto / total_meta) * 100) if total_meta > 0 else 0
            
            # Nomes dos meses em português
            meses_pt = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_nome = meses_pt[now.month - 1]
            
            message = f"""
📊 **Suas Metas - {mes_nome}/{now.year}**
{metas_text}
━━━━━━━━━━━━━━━━━━━━
💰 **Total:** R$ {total_meta:.2f}
📈 **Gasto:** R$ {total_gasto:.2f}
📊 **Progresso geral:** {progresso_geral:.1f}%

💡 Use `/meta <categoria>` para ver detalhes
            """
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Erro no comando /metas: {e}")
            await update.message.reply_text(
                "❌ Erro ao listar metas. Tente novamente."
            )

    async def handle_expense_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar mensagem de gasto"""
        try:
            message_data = MessageInput(
                text=update.message.text,
                user_id=update.effective_user.id,
                message_id=update.message.message_id,
                chat_id=update.effective_chat.id
            )

            logger.info(f"🔄 Processando mensagem: '{message_data.text[:50]}...'")

            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )

            interpreted = await openai_service.interpret_financial_message(message_data.text)

            transaction = await self._save_transaction(message_data, interpreted)

            row_number = await sheets_service.add_transaction(interpreted, transaction.id)

            await self._update_transaction_sheets_info(transaction.id, row_number)

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

    async def _save_transaction(self, message_data: MessageInput, interpreted: InterpretedTransaction, 
                               source_type: str = "text", transcribed_text: str = None) -> ProcessedTransaction:
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
                    status="processed",
                    source_type=source_type,
                    transcribed_text=transcribed_text
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

    async def _send_confirmation(self, update: Update, interpreted: InterpretedTransaction, transaction_id: int, 
                                source_type: str = "text", transcribed_text: str = None):
        """Enviar mensagem de confirmação"""
        from services.goal_service import goal_service
        from datetime import datetime
        
        category_emoji = {
            "Alimentação": "🍔",
            "Transporte": "🚗",
            "Saúde": "💊",
            "Lazer": "🎬",
            "Casa": "🏠",
            "Finanças": "💲",
            "Outros": "📦"
        }

        emoji = category_emoji.get(interpreted.categoria.value, "🏷️")

        # Adicionar informação de origem se for áudio
        origin_info = ""
        if source_type == "audio_transcribed" and transcribed_text:
            origin_info = f'\n📝 **Texto transcrito:** "{transcribed_text}"\n🔊 **Origem:** Áudio transcrito'

        # Verificar se há meta para esta categoria e calcular progresso
        goal_info = ""
        progress = None
        user_id = update.effective_user.id
        now = datetime.now()
        
        try:
            progress = await goal_service.get_goal_progress(
                user_id=user_id,
                categoria=interpreted.categoria,
                mes=now.month,
                ano=now.year
            )
            
            if progress:
                status_emoji = "✅" if progress.status.value == "dentro_meta" else "⚠️" if progress.status.value == "proximo_limite" else "🚨"
                falta = progress.valor_meta - progress.valor_gasto
                
                goal_info = f"\n\n🎯 **Meta de {interpreted.categoria.value}:**\n"
                goal_info += f"   {status_emoji} R$ {progress.valor_gasto:.2f} / R$ {progress.valor_meta:.2f} ({progress.progresso_percentual:.1f}%)"
                
                if falta > 0:
                    goal_info += f"\n   💚 Disponível: R$ {falta:.2f}"
                else:
                    goal_info += f"\n   🚨 Excedido em: R$ {abs(falta):.2f}"
        except Exception as e:
            logger.error(f"❌ Erro ao obter informações de meta: {e}")

        confirmation = f"""
**Gasto registrado com sucesso!**

{emoji} **{interpreted.descricao}**
Valor: **R$ {interpreted.valor:.2f}**
Categoria: **{interpreted.categoria.value}**
Data: **{interpreted.data.strftime('%d/%m/%Y')}**{origin_info}

Confiança: {interpreted.confianca:.0%}
ID: #{transaction_id}{goal_info}

Salvo na planilha Google! Use /resumo para ver totais.
        """

        await update.message.reply_text(confirmation, parse_mode='Markdown')
        
        # Verificar e enviar alertas de meta se necessário
        try:
            if progress:
                alert = await goal_service.check_goal_alerts(
                    user_id=user_id,
                    categoria=interpreted.categoria,
                    current_spending=progress.valor_gasto
                )
                
                if alert:
                    await self._send_goal_alert(update, alert)
        except Exception as e:
            logger.error(f"❌ Erro ao verificar alertas de meta: {e}")

    async def _send_goal_alert(self, update: Update, alert: 'GoalAlert'):
        """Enviar alerta de meta"""
        from models.schemas import AlertType
        
        category_emoji = {
            "Alimentação": "🍔",
            "Transporte": "🚗",
            "Saúde": "💊",
            "Lazer": "🎬",
            "Casa": "🏠",
            "Finanças": "💲",
            "Outros": "📦"
        }
        
        emoji = category_emoji.get(alert.categoria.value, "🎯")
        
        if alert.tipo == AlertType.WARNING_80_PERCENT:
            message = f"""
⚠️ **Alerta de Meta - {alert.categoria.value}**

{emoji} Você atingiu **{alert.percentual:.1f}%** da sua meta!

💰 **Meta:** R$ {alert.valor_meta:.2f}
📊 **Gasto:** R$ {alert.valor_atual:.2f}
💚 **Disponível:** R$ {(alert.valor_meta - alert.valor_atual):.2f}

💡 **Dica:** Fique atento aos seus gastos para não ultrapassar a meta!
            """
        else:  # EXCEEDED_100_PERCENT
            message = f"""
🚨 **ALERTA: Meta Ultrapassada - {alert.categoria.value}**

{emoji} Você ultrapassou sua meta em **{(alert.percentual - 100):.1f}%**!

💰 **Meta:** R$ {alert.valor_meta:.2f}
📊 **Gasto:** R$ {alert.valor_atual:.2f}
🚨 **Excedido em:** R$ {(alert.valor_atual - alert.valor_meta):.2f}

💡 **Dica:** Considere revisar seus gastos ou ajustar sua meta.
            """
        
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_audio_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar mensagem de áudio"""
        try:
            # Detectar tipo de áudio e extrair informações
            audio_message = await self._extract_audio_info(update)
            if not audio_message:
                await update.message.reply_text("❌ Não foi possível processar este tipo de áudio. Tente enviar um arquivo de áudio válido.")
                return

            logger.info(f"🎵 Processando áudio do usuário {audio_message.user_id}: {audio_message.file_id}")

            # Enviar feedback inicial
            processing_message = await update.message.reply_text(
                f"🎵 **Processando áudio...** ({audio_message.duration}s)\n\n"
                f"⏳ Baixando e transcrevendo...",
                parse_mode='Markdown'
            )

            # Mostrar indicador de digitação
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )

            try:
                # Baixar arquivo de áudio
                telegram_file = await context.bot.get_file(audio_message.file_id)
                file_path = await audio_service.download_audio_file(telegram_file, audio_message)

                # Transcrever áudio
                transcription_result = await openai_service.transcribe_audio(file_path)

                # Limpar arquivo temporário
                await audio_service.cleanup_temp_file(file_path)

                # Exibir transcrição para confirmação
                await self._show_transcription_confirmation(update, context, transcription_result.text, processing_message)

            except Exception as e:
                logger.error(f"❌ Erro ao processar áudio: {e}")
                
                # Atualizar mensagem com erro específico
                error_message = self._get_audio_error_message(str(e))
                await processing_message.edit_text(
                    f"❌ **Erro ao processar áudio**\n\n{error_message}",
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"❌ Erro geral no handler de áudio: {e}")
            await update.message.reply_text(
                "❌ Ocorreu um erro inesperado ao processar o áudio.\n"
                "Tente novamente ou envie uma mensagem de texto."
            )

    async def _extract_audio_info(self, update: Update) -> Optional[AudioMessage]:
        """Extrair informações da mensagem de áudio"""
        message = update.message
        
        # Verificar diferentes tipos de áudio
        if message.audio:
            # Arquivo de áudio regular
            audio = message.audio
            return AudioMessage(
                file_id=audio.file_id,
                file_size=audio.file_size or 0,
                duration=audio.duration or 0,
                mime_type=audio.mime_type or "audio/mpeg",
                user_id=update.effective_user.id,
                message_id=message.message_id,
                chat_id=update.effective_chat.id
            )
        
        elif message.voice:
            # Mensagem de voz (Telegram usa Opus em container OGG)
            voice = message.voice
            return AudioMessage(
                file_id=voice.file_id,
                file_size=voice.file_size or 0,
                duration=voice.duration or 0,
                mime_type=voice.mime_type or "audio/ogg",  # Telegram voice messages são audio/ogg
                user_id=update.effective_user.id,
                message_id=message.message_id,
                chat_id=update.effective_chat.id
            )
        
        elif message.video_note:
            # Video note (mensagem de vídeo circular)
            video_note = message.video_note
            return AudioMessage(
                file_id=video_note.file_id,
                file_size=video_note.file_size or 0,
                duration=video_note.duration or 0,
                mime_type="video/mp4",
                user_id=update.effective_user.id,
                message_id=message.message_id,
                chat_id=update.effective_chat.id
            )
        
        return None

    async def _show_transcription_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                             transcribed_text: str, processing_message):
        """Exibir transcrição para confirmação do usuário"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # Adicionar transcrição ao gerenciador
        transcription_id = transcription_manager.add_pending_transcription(
            user_id=update.effective_user.id,
            message_id=update.message.message_id,
            transcribed_text=transcribed_text
        )
        
        # Criar botões de confirmação
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim, está correto", callback_data=f"confirm_yes_{transcription_id}"),
                InlineKeyboardButton("❌ Não, enviar novamente", callback_data=f"confirm_no_{transcription_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Atualizar mensagem com transcrição
        confirmation_text = f"""
🎵 **Transcrição concluída!**

📝 **Texto transcrito:**
"{transcribed_text}"

**Esta transcrição está correta?**
• ✅ **Sim** - Processar como gasto
• ❌ **Não** - Enviar áudio novamente

⏰ *Esta confirmação expira em 1 minuto*
        """
        
        await processing_message.edit_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    def _get_audio_error_message(self, error: str) -> str:
        """Obter mensagem de erro específica para problemas de áudio"""
        error_lower = error.lower()
        
        if "não encontrado" in error_lower or "not found" in error_lower:
            return ("📁 **Arquivo não encontrado**\n"
                   "Verifique se o arquivo foi enviado corretamente e tente novamente.")
        
        elif "muito grande" in error_lower or "large" in error_lower:
            return ("📏 **Arquivo muito grande**\n"
                   "O limite é de 25MB. Tente dividir o áudio em partes menores.")
        
        elif "muito longo" in error_lower or "long" in error_lower:
            return ("⏱️ **Áudio muito longo**\n"
                   "O limite é de 10 minutos. Tente dividir em áudios menores.")
        
        elif "formato" in error_lower or "format" in error_lower:
            return ("🎵 **Formato não suportado**\n"
                   "Formatos aceitos: MP3, MP4, WAV, WebM, M4A.\n"
                   "Tente converter o arquivo ou gravar novamente.")
        
        elif "vazio" in error_lower or "empty" in error_lower:
            return ("🔇 **Áudio vazio ou corrompido**\n"
                   "Tente gravar novamente com fala mais clara.")
        
        elif "ruído" in error_lower or "noise" in error_lower:
            return ("🔊 **Qualidade de áudio baixa**\n"
                   "Tente gravar em ambiente mais silencioso e próximo ao microfone.")
        
        elif "limite" in error_lower or "rate limit" in error_lower:
            return ("⏳ **Limite de requisições excedido**\n"
                   "Aguarde alguns minutos antes de tentar novamente.")
        
        elif "conexão" in error_lower or "network" in error_lower:
            return ("🌐 **Erro de conexão**\n"
                   "Verifique sua internet e tente novamente.")
        
        elif "servidor" in error_lower or "server" in error_lower:
            return ("🔧 **Serviço temporariamente indisponível**\n"
                   "Tente novamente em alguns minutos ou use mensagem de texto.")
        
        else:
            return ("❌ **Erro no processamento**\n"
                   "Tente novamente ou envie uma mensagem de texto com seu gasto.")

    async def handle_transcription_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar confirmação da transcrição"""
        try:
            query = update.callback_query
            await query.answer()
            
            # Extrair ID da transcrição
            transcription_id = query.data.replace("confirm_yes_", "")
            
            # Obter transcrição pendente
            pending_transcription = transcription_manager.get_pending_transcription(transcription_id)
            if not pending_transcription:
                await query.edit_message_text(
                    "⏰ **Confirmação expirada**\n\n"
                    "Esta transcrição expirou. Envie o áudio novamente.",
                    parse_mode='Markdown'
                )
                return
            
            # Processar texto transcrito como gasto
            await query.edit_message_text(
                "✅ **Confirmado!** Processando gasto...",
                parse_mode='Markdown'
            )
            
            # Mostrar indicador de digitação
            await context.bot.send_chat_action(
                chat_id=query.message.chat_id,
                action="typing"
            )
            
            try:
                # Interpretar texto transcrito
                interpreted = await openai_service.interpret_financial_message(pending_transcription.transcribed_text)
                
                # Criar dados da mensagem para salvar
                message_data = MessageInput(
                    text=f"[ÁUDIO TRANSCRITO] {pending_transcription.transcribed_text}",
                    user_id=pending_transcription.user_id,
                    message_id=pending_transcription.message_id,
                    chat_id=query.message.chat_id
                )
                
                # Salvar transação com origem de áudio
                transaction = await self._save_transaction(
                    message_data, 
                    interpreted, 
                    source_type="audio_transcribed", 
                    transcribed_text=pending_transcription.transcribed_text
                )
                
                # Adicionar à planilha
                row_number = await sheets_service.add_transaction(interpreted, transaction.id)
                await self._update_transaction_sheets_info(transaction.id, row_number)
                
                # Enviar confirmação
                await self._send_audio_confirmation(query, interpreted, transaction.id, pending_transcription.transcribed_text)
                
                # Remover transcrição pendente
                transcription_manager.remove_pending_transcription(transcription_id)
                
                logger.info(f"✅ Transação de áudio processada com sucesso: ID {transaction.id}")
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar gasto de áudio: {e}")
                await query.edit_message_text(
                    f"❌ **Erro ao processar gasto**\n\n"
                    f"Detalhes: {str(e)}\n\n"
                    f"Tente reformular o áudio ou envie uma mensagem de texto.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"❌ Erro no handler de confirmação: {e}")
            await query.edit_message_text(
                "❌ Erro inesperado. Tente novamente.",
                parse_mode='Markdown'
            )

    async def handle_transcription_rejection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar rejeição da transcrição"""
        try:
            query = update.callback_query
            await query.answer()
            
            # Extrair ID da transcrição
            transcription_id = query.data.replace("confirm_no_", "")
            
            # Remover transcrição pendente
            transcription_manager.remove_pending_transcription(transcription_id)
            
            # Informar que foi rejeitado
            await query.edit_message_text(
                "❌ **Transcrição rejeitada**\n\n"
                "Envie um novo áudio ou digite seu gasto manualmente.\n\n"
                "💡 **Dicas para melhor transcrição:**\n"
                "• Fale claramente e devagar\n"
                "• Grave em ambiente silencioso\n"
                "• Mantenha o microfone próximo\n"
                "• Mencione o valor e descrição do gasto",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Erro no handler de rejeição: {e}")
            await query.edit_message_text(
                "❌ Erro inesperado. Tente novamente.",
                parse_mode='Markdown'
            )



    async def _send_audio_confirmation(self, query, interpreted: InterpretedTransaction, transaction_id: int, transcribed_text: str):
        """Enviar mensagem de confirmação para transação de áudio"""
        category_emoji = {
            "Alimentação": "🍔",
            "Transporte": "🚗",
            "Saúde": "💊",
            "Lazer": "🎬",
            "Casa": "🏠",
            "Finanças": "💲",
            "Outros": "📦"
        }

        emoji = category_emoji.get(interpreted.categoria.value, "🏷️")

        confirmation = f"""
🎵 **Gasto de áudio registrado com sucesso!**

{emoji} **{interpreted.descricao}**
Valor: **R$ {interpreted.valor:.2f}**
Categoria: **{interpreted.categoria.value}**
Data: **{interpreted.data.strftime('%d/%m/%Y')}**

📝 **Texto transcrito:** "{transcribed_text}"
🔊 **Origem:** Áudio transcrito
Confiança: {interpreted.confianca:.0%}
ID: #{transaction_id}

Salvo na planilha Google! Use /resumo para ver totais.
        """

        await query.edit_message_text(confirmation, parse_mode='Markdown')

    async def handle_clear_goals_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar confirmação de limpeza de metas"""
        try:
            from services.goal_service import goal_service
            
            query = update.callback_query
            await query.answer()
            
            # Extrair user_id do callback_data
            user_id = int(query.data.replace("clear_goals_yes_", ""))
            
            # Verificar se é o usuário correto
            if user_id != update.effective_user.id:
                await query.edit_message_text(
                    "❌ Você não pode confirmar esta ação.",
                    parse_mode='Markdown'
                )
                return
            
            # Limpar todas as metas
            count = await goal_service.clear_all_goals(user_id)
            
            if count > 0:
                await query.edit_message_text(
                    f"✅ **Metas removidas com sucesso!**\n\n"
                    f"{count} meta(s) foram removidas.\n\n"
                    f"Use `/meta <categoria> <valor>` para criar novas metas.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    "ℹ️ **Nenhuma meta encontrada**\n\n"
                    "Você não tinha metas definidas.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"❌ Erro ao confirmar limpeza de metas: {e}")
            await query.edit_message_text(
                "❌ Erro ao limpar metas. Tente novamente.",
                parse_mode='Markdown'
            )
    
    async def handle_clear_goals_cancellation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar cancelamento de limpeza de metas"""
        try:
            query = update.callback_query
            await query.answer()
            
            await query.edit_message_text(
                "✅ **Operação cancelada**\n\n"
                "Suas metas foram mantidas.\n\n"
                "Use /metas para ver suas metas ativas.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Erro ao cancelar limpeza de metas: {e}")
            await query.edit_message_text(
                "❌ Erro ao processar cancelamento.",
                parse_mode='Markdown'
            )

    async def _notify_transcription_timeout(self, transcription: 'PendingTranscription'):
        """Notificar usuário sobre timeout de transcrição"""
        try:
            timeout_message = (
                "⏰ **Confirmação expirada**\n\n"
                "Sua transcrição de áudio expirou após 1 minuto sem resposta.\n\n"
                "💡 **Para continuar:**\n"
                "• Envie o áudio novamente\n"
                "• Ou digite seu gasto manualmente\n\n"
                "**Dica:** Responda mais rapidamente às confirmações para evitar expirações."
            )
            
            await self.bot.send_message(
                chat_id=transcription.user_id,  # Assumindo que user_id é o chat_id para mensagens privadas
                text=timeout_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"✅ Notificação de timeout enviada para usuário {transcription.user_id}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar notificação de timeout para usuário {transcription.user_id}: {e}")

    async def _ensure_user_config(self, user_id: int):
        """Garantir que usuário tem Configuração"""
        try:
            async for db in get_db_session():
                result = await db.execute(
                    select(UserConfig).where(UserConfig.user_id == user_id)
                )
                existing = result.scalar_one_or_none()

                if not existing:
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


telegram_bot = TelegramFinanceBot()