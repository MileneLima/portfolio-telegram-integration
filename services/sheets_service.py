"""
Serviço de integração com Google Sheets
"""

import gspread
from google.oauth2.service_account import Credentials
from loguru import logger

from config.settings import get_settings
from models.schemas import InterpretedTransaction


class GoogleSheetsService:
    """Serviço para integração com Google Sheets"""

    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self.spreadsheet = None
        self.spreadsheet_id = self.settings.google_sheets_spreadsheet_id

    async def setup(self):
        """Configurar cliente Google Sheets"""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            credentials = Credentials.from_service_account_file(
                self.settings.google_credentials_file,
                scopes=scopes
            )

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)

            logger.info("✅ Google Sheets configurado com sucesso")

            await self.ensure_sheet_structure()

        except Exception as e:
            logger.error(f"❌ Erro ao configurar Google Sheets: {e}")
            raise

    async def ensure_sheet_structure(self, always_sync: bool = False):
        """Garantir que a estrutura de abas existe e sincronizar dados iniciais"""
        try:
            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            existing_sheets = [ws.title for ws in self.spreadsheet.worksheets()]
            new_sheets_created = False
            missing_sheets = []

            if "Resumo" not in existing_sheets:
                await self._create_summary_sheet()
                new_sheets_created = True
                missing_sheets.append("Resumo")

            for mes in meses:
                if mes not in existing_sheets:
                    await self._create_monthly_sheet(mes)
                    new_sheets_created = True
                    missing_sheets.append(mes)

            if missing_sheets:
                logger.info(f"✅ Abas criadas: {', '.join(missing_sheets)}")
            else:
                logger.info("✅ Estrutura de abas verificada - todas existem")

            sync_needed = new_sheets_created or always_sync or await self._check_if_sync_needed()
            
            if sync_needed:
                logger.info("🔄 Sincronização necessária - iniciando...")
                await self._initial_sync_from_database()
            else:
                logger.info("ℹ️ Planilha já sincronizada - pulando sincronização inicial")

            return {
                "new_sheets_created": new_sheets_created,
                "missing_sheets": missing_sheets,
                "sync_executed": sync_needed
            }

        except Exception as e:
            logger.error(f"❌ Erro ao criar estrutura de abas: {e}")
            raise

    async def _create_monthly_sheet(self, mes: str):
        """Criar aba mensal com cabeçalhos"""
        try:
            worksheet = self.spreadsheet.add_worksheet(title=mes, rows=1000, cols=10)

            headers = ["ID", "Data", "Descrição", "Categoria", "Valor", "Observações"]
            worksheet.append_row(headers)

            worksheet.format('A1:F1', {
                'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 1.0},
                'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
            })

            logger.info(f"✅ Aba '{mes}' criada com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao criar aba {mes}: {e}")

    async def _create_summary_sheet(self):
        """Criar aba de resumo"""
        try:
            worksheet = self.spreadsheet.add_worksheet(title="Resumo", rows=100, cols=11)

            headers = ["Mês", "Total Gastos", "Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros", "Transações", "Finanças"]
            worksheet.append_row(headers)

            meses_resumo = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            for mes in meses_resumo:
                row = [mes, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                worksheet.append_row(row)

            worksheet.format('A1:J1', {
                'backgroundColor': {'red': 0.8, 'green': 0.2, 'blue': 0.2},
                'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
            })

            logger.info("✅ Aba 'Resumo' criada com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao criar aba resumo: {e}")

    async def add_transaction(self, transaction: InterpretedTransaction, transaction_id: int = None) -> int:
        """Adicionar transação na planilha"""
        try:
            mes_nomes = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_nome = mes_nomes[transaction.data.month - 1]

            worksheet = self.spreadsheet.worksheet(mes_nome)

            if transaction_id:
                logger.info(f"🔍 Verificando se transação ID {transaction_id} já existe na aba {mes_nome}")
                existing_row = await self._find_transaction_by_id(worksheet, transaction_id)
                if existing_row:
                    logger.info(f"⚠️ Transação ID {transaction_id} já existe na linha {existing_row}, pulando...")
                    return existing_row
                else:
                    logger.info(f"✅ Transação ID {transaction_id} não existe, adicionando...")

            row_data = [
                transaction_id if transaction_id else "",
                transaction.data.strftime("%d/%m/%Y"),
                transaction.descricao,
                transaction.categoria.value,
                float(transaction.valor),
                f"Confiança: {transaction.confianca:.1%}"
            ]

            logger.info(f"📝 Adicionando transação à aba {mes_nome}: {row_data}")

            worksheet.append_row(row_data)

            row_number = len(worksheet.get_all_values())

            await self._update_summary()

            logger.info(f"✅ Transação adicionada na aba {mes_nome}, linha {row_number}")
            return row_number

        except Exception as e:
            logger.error(f"❌ Erro ao adicionar transação: {e}")
            raise

    async def _find_transaction_by_id(self, worksheet, transaction_id: int) -> int:
        """Encontrar transação por ID na planilha"""
        try:
            all_values = worksheet.get_all_values()
            
            if len(all_values) <= 1:
                return None
            
            for row_index, row in enumerate(all_values[1:], start=2):  # Começar da linha 2 (pular cabeçalho)
                if len(row) > 0 and str(row[0]) == str(transaction_id):
                    return row_index
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao procurar transação por ID: {e}")
            return None

    async def _update_summary(self):
        """Atualizar aba de resumo com totais"""
        try:
            resumo_ws = self.spreadsheet.worksheet("Resumo")

            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            categorias = ["Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros", "Finanças"]

            for i, mes in enumerate(meses, start=2):
                try:
                    mes_ws = self.spreadsheet.worksheet(mes)
                    all_values = mes_ws.get_all_values()

                    if len(all_values) <= 1:
                        continue

                    total_gastos = 0
                    total_financas = 0
                    categoria_totais = {cat: 0 for cat in categorias}
                    num_transacoes = len(all_values) - 1

                    for row in all_values[1:]:
                        if len(row) >= 5 and row[4]:
                            try:
                                valor = float(row[4])
                                categoria = row[3]

                                if categoria == "Finanças":
                                    total_financas += valor
                                else:
                                    total_gastos += valor
                                
                                if categoria in categoria_totais:
                                    categoria_totais[categoria] += valor

                            except (ValueError, IndexError):
                                continue

                    row_update = [
                        mes,
                        f"R$ {total_gastos:.2f}",
                        f"R$ {categoria_totais['Alimentação']:.2f}",
                        f"R$ {categoria_totais['Transporte']:.2f}",
                        f"R$ {categoria_totais['Saúde']:.2f}",
                        f"R$ {categoria_totais['Lazer']:.2f}",
                        f"R$ {categoria_totais['Casa']:.2f}",
                        f"R$ {categoria_totais['Outros']:.2f}",
                        str(num_transacoes),
                        f"R$ {categoria_totais['Finanças']:.2f}"
                    ]

                    resumo_ws.update(f'A{i}:J{i}', [row_update])

                except Exception as e:
                    logger.warning(f"Erro ao processar mês {mes}: {e}")
                    continue

            logger.info("✅ Resumo atualizado")

        except Exception as e:
            logger.error(f"❌ Erro ao atualizar resumo: {e}")

    async def _initial_sync_from_database(self):
        """Sincronização inicial otimizada: SQLite → Google Sheets"""
        try:
            from services.database_service import database_service
            from database.sqlite_db import get_db_session
            from database.models import Transaction
            from sqlalchemy import select
            import asyncio
            
            logger.info("🔄 Iniciando sincronização inicial do banco para planilha...")
            
            await self._clean_inconsistent_data()
            
            async for db in get_db_session():
                result = await db.execute(
                    select(Transaction)
                    .where(Transaction.status == 'processed')
                    .order_by(Transaction.data_transacao.asc())
                )
                
                all_transactions = result.scalars().all()
                
                if not all_transactions:
                    logger.info("ℹ️ Nenhuma transação encontrada no banco para sincronizar")
                    return
                
                logger.info(f"📊 Encontradas {len(all_transactions)} transações para sincronizar")
                
                monthly_data = {}
                meses_pt = [
                    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
                ]
                
                for transaction in all_transactions:
                    month_name = meses_pt[transaction.data_transacao.month - 1]
                    
                    if month_name not in monthly_data:
                        monthly_data[month_name] = []
                    
                    row_data = [
                        str(transaction.id),
                        transaction.data_transacao.strftime("%d/%m/%Y"),
                        transaction.descricao,
                        transaction.categoria,
                        float(transaction.valor),
                        f"Confiança: {transaction.confianca:.0%}"
                    ]
                    monthly_data[month_name].append(row_data)
                
                total_synced = 0
                months_with_data = len([m for m in monthly_data.values() if m])
                current_month = 0
                
                for month_name, transactions_data in monthly_data.items():
                    if transactions_data:
                        current_month += 1
                        logger.info(f"📅 Sincronizando {month_name} ({current_month}/{months_with_data}): {len(transactions_data)} transações")
                        
                        synced_count = await self._batch_insert_transactions(month_name, transactions_data)
                        total_synced += synced_count
                        
                        await asyncio.sleep(0.5)
                
                logger.info(f"✅ Sincronização inicial concluída: {total_synced} transações sincronizadas")
                
                await self._mark_transactions_as_synced(all_transactions)
                
                await self._update_summary()
                
        except Exception as e:
            logger.error(f"❌ Erro na sincronização inicial: {e}")

    async def _batch_insert_transactions(self, month_name: str, transactions_data: list) -> int:
        """Inserir transações em lote para otimizar performance"""
        try:
            worksheet = self.spreadsheet.worksheet(month_name)
            
            existing_values = worksheet.get_all_values()
            if len(existing_values) > 1:
                logger.info(f"⚠️ Aba {month_name} já contém dados - pulando sincronização")
                return 0
            
            if transactions_data:
                start_row = 2
                end_row = start_row + len(transactions_data) - 1
                range_name = f"A{start_row}:F{end_row}"
                
                worksheet.update(range_name, transactions_data)
                
                logger.info(f"✅ {month_name}: {len(transactions_data)} transações sincronizadas em lote")
                return len(transactions_data)
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Erro ao sincronizar lote para {month_name}: {e}")
            return 0

    async def _check_if_sync_needed(self) -> bool:
        """Verificar se sincronização inicial é necessária"""
        try:
            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            
            for mes in meses:
                try:
                    worksheet = self.spreadsheet.worksheet(mes)
                    values = worksheet.get_all_values()
                    
                    if len(values) <= 1:
                        return True
                        
                except Exception:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar necessidade de sincronização: {e}")
            return True

    async def _mark_transactions_as_synced(self, transactions):
        """Marcar transações como sincronizadas no banco"""
        try:
            from database.sqlite_db import get_db_session
            from datetime import datetime
            
            async for db in get_db_session():
                for transaction in transactions:
                    transaction.sheets_row_number = 999  # Valor fictício indicando sincronização
                    transaction.sheets_updated_at = datetime.now()
                
                await db.commit()
                logger.info(f"✅ {len(transactions)} transações marcadas como sincronizadas no banco")
                
        except Exception as e:
            logger.error(f"❌ Erro ao marcar transações como sincronizadas: {e}")

    async def _clean_inconsistent_data(self):
        """Limpar dados inconsistentes da planilha (dados inseridos manualmente)"""
        try:
            from database.sqlite_db import get_db_session
            from database.models import Transaction
            from sqlalchemy import select
            import asyncio
            
            logger.info("🧹 Iniciando limpeza de dados inconsistentes...")
            
            async for db in get_db_session():
                result = await db.execute(
                    select(Transaction.id)
                    .where(Transaction.status == 'processed')
                )
                valid_ids = {str(row.id) for row in result}
                
            logger.info(f"📊 IDs válidos no banco: {len(valid_ids)}")
            
            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            
            total_removed = 0
            
            for i, mes in enumerate(meses):
                try:
                    if i > 0:
                        await asyncio.sleep(0.3)
                    
                    worksheet = self.spreadsheet.worksheet(mes)
                    all_values = worksheet.get_all_values()
                    
                    if len(all_values) <= 1:
                        continue
                    
                    rows_to_delete = []
                    inconsistent_count = 0
                    
                    for row_index, row in enumerate(all_values[1:], start=2):
                        if len(row) == 0 or not row[0]:
                            rows_to_delete.append(row_index)
                            inconsistent_count += 1
                        elif row[0] not in valid_ids:
                            rows_to_delete.append(row_index)
                            inconsistent_count += 1
                    
                    if rows_to_delete:
                        logger.info(f"🗑️ {mes}: Removendo {len(rows_to_delete)} linhas inconsistentes")
                        
                        for row_index in reversed(rows_to_delete):
                            worksheet.delete_rows(row_index)
                            total_removed += 1
                            
                            await asyncio.sleep(0.1)
                    
                    if inconsistent_count == 0:
                        logger.info(f"✅ {mes}: Nenhum dado inconsistente encontrado")
                    
                except Exception as e:
                    logger.error(f"❌ Erro ao limpar dados de {mes}: {e}")
                    continue
            
            if total_removed > 0:
                logger.info(f"🧹 Limpeza concluída: {total_removed} linhas inconsistentes removidas")
            else:
                logger.info("✅ Nenhum dado inconsistente encontrado na planilha")
                
        except Exception as e:
            logger.error(f"❌ Erro na limpeza de dados inconsistentes: {e}")

    async def _validate_sheet_data_integrity(self) -> dict:
        """Validar integridade dos dados na planilha"""
        try:
            from database.sqlite_db import get_db_session
            from database.models import Transaction
            from sqlalchemy import select
            
            async for db in get_db_session():
                result = await db.execute(
                    select(Transaction.id)
                    .where(Transaction.status == 'processed')
                )
                valid_ids = {str(row.id) for row in result}
            
            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            
            total_rows = 0
            valid_rows = 0
            invalid_rows = 0
            empty_rows = 0
            
            for mes in meses:
                try:
                    worksheet = self.spreadsheet.worksheet(mes)
                    all_values = worksheet.get_all_values()
                    
                    for row in all_values[1:]:
                        if len(row) == 0 or not row[0]:
                            empty_rows += 1
                        elif row[0] in valid_ids:
                            valid_rows += 1
                        else:
                            invalid_rows += 1
                        
                        total_rows += 1
                        
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao validar {mes}: {e}")
                    continue
            
            return {
                "total_rows": total_rows,
                "valid_rows": valid_rows,
                "invalid_rows": invalid_rows,
                "empty_rows": empty_rows,
                "integrity_ok": invalid_rows == 0 and empty_rows == 0
            }
            
        except Exception as e:
            logger.error(f"❌ Erro na validação de integridade: {e}")
            return {"error": str(e)}


sheets_service = GoogleSheetsService()