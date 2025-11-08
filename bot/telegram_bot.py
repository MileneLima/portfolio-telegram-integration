"""
Bot principal do Telegram para processamento de mensagens financeiras
"""

from datetime import datetime
from typing import Dict, Any

from sqlalchemy import select
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from loguru import logger

from config.settings import get_settings
from services.openai_service import openai_service
from services.sheets_service import sheets_service
from services.database_service import database_service
from database.sqlite_db import get_db_session
from database.models import Transaction, UserConfig
from models.schemas import MessageInput, ProcessedTransaction, TransactionStatus, InterpretedTransaction


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

                    message = f"""
📊 **Resumo {period_desc}**

💰 **Total gasto:** R$ {total_gastos:.2f}
💎 **Total investido:** R$ {total_investimentos:.2f}
📝 **Transações:** {transacoes}

**Por categoria:**
{categorias_texto}

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

                    message = f"""
📊 **Resumo {period_desc}**

💰 **Total gasto:** R$ {total_gastos:.2f}
💎 **Total investido:** R$ {total_investimentos:.2f}
📝 **Transações:** {transacoes}

**Por categoria:**
{categorias_texto}

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
            
            message = f"""
📊 **Estatísticas do Banco de Dados**

📈 **Resumo Geral:**
• Total de transações: {stats['total_transacoes']}
• Primeira transação: {stats['primeira_transacao']}
• Última transação: {stats['ultima_transacao']}
• Total gasto: R$ {stats['total_gasto']:.2f}
• Período: {stats['periodo_dias']} dias

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