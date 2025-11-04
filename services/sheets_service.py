from typing import  Dict, Any

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

            # Criar estrutura de abas se necessário
            await self.ensure_sheet_structure()

        except Exception as e:
            logger.error(f"❌ Erro ao configurar Google Sheets: {e}")
            raise

    async def ensure_sheet_structure(self):
        """Garantir que a estrutura de abas existe"""
        try:
            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            existing_sheets = [ws.title for ws in self.spreadsheet.worksheets()]

            if "Resumo" not in existing_sheets:
                await self._create_summary_sheet()

            for mes in meses:
                if mes not in existing_sheets:
                    await self._create_monthly_sheet(mes)

            logger.info("✅ Estrutura de abas verificada e criada")

        except Exception as e:
            logger.error(f"❌ Erro ao criar estrutura de abas: {e}")

    async def _create_monthly_sheet(self, mes: str):
        """Criar aba mensal com cabeçalhos"""
        try:
            worksheet = self.spreadsheet.add_worksheet(title=mes, rows=1000, cols=10)

            headers = ["Data", "Descrição", "Categoria", "Valor", "Observações"]
            worksheet.append_row(headers)

            worksheet.format('A1:E1', {
                'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 1.0},
                'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
            })

            logger.info(f"✅ Aba '{mes}' criada com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao criar aba {mes}: {e}")

    async def _create_summary_sheet(self):
        """Criar aba de resumo"""
        try:
            worksheet = self.spreadsheet.add_worksheet(title="Resumo", rows=100, cols=10)

            headers = ["Mês", "Total Gastos", "Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros", "Transações"]
            worksheet.append_row(headers)

            meses_resumo = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            for mes in meses_resumo:
                row = [mes, 0, 0, 0, 0, 0, 0, 0, 0]
                worksheet.append_row(row)

            worksheet.format('A1:I1', {
                'backgroundColor': {'red': 0.8, 'green': 0.2, 'blue': 0.2},
                'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
            })

            logger.info("✅ Aba 'Resumo' criada com sucesso")

        except Exception as e:
            logger.error(f"❌ Erro ao criar aba resumo: {e}")

    async def add_transaction(self, transaction: InterpretedTransaction) -> int:
        """Adicionar transação na planilha"""
        try:
            mes_nomes = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_nome = mes_nomes[transaction.data.month - 1]

            worksheet = self.spreadsheet.worksheet(mes_nome)

            row_data = [
                transaction.data.strftime("%d/%m/%Y"),
                transaction.descricao,
                transaction.categoria.value,
                float(transaction.valor),
                f"Confiança: {transaction.confianca:.1%}"
            ]

            worksheet.append_row(row_data)

            row_number = len(worksheet.get_all_values())

            await self._update_summary()

            logger.info(f"✅ Transação adicionada na aba {mes_nome}, linha {row_number}")
            return row_number

        except Exception as e:
            logger.error(f"❌ Erro ao adicionar transação: {e}")
            raise

    async def _update_summary(self):
        """Atualizar aba de resumo com totais"""
        try:
            resumo_ws = self.spreadsheet.worksheet("Resumo")

            meses = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]

            categorias = ["Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros"]

            for i, mes in enumerate(meses, start=2):
                try:
                    mes_ws = self.spreadsheet.worksheet(mes)
                    all_values = mes_ws.get_all_values()

                    if len(all_values) <= 1:
                        continue

                    total_gastos = 0
                    categoria_totais = {cat: 0 for cat in categorias}
                    num_transacoes = len(all_values) - 1

                    for row in all_values[1:]:
                        if len(row) >= 4 and row[3]:
                            try:
                                valor = float(row[3])
                                categoria = row[2]

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
                        str(num_transacoes)
                    ]

                    resumo_ws.update(f'A{i}:I{i}', [row_update])

                except Exception as e:
                    logger.warning(f"Erro ao processar mês {mes}: {e}")
                    continue

            logger.info("✅ Resumo atualizado")

        except Exception as e:
            logger.error(f"❌ Erro ao atualizar resumo: {e}")

    async def get_monthly_summary(self, mes: str) -> Dict[str, Any]:
        """Obter resumo mensal"""
        try:
            worksheet = self.spreadsheet.worksheet(mes)
            all_values = worksheet.get_all_values()

            if len(all_values) <= 1:
                return {"mes": mes, "total": 0, "transacoes": 0, "categorias": {}}

            total = 0
            categorias = {}

            for row in all_values[1:]:
                if len(row) >= 4 and row[3]:
                    try:
                        valor = float(row[3])
                        categoria = row[2]

                        total += valor
                        categorias[categoria] = categorias.get(categoria, 0) + valor

                    except (ValueError, IndexError):
                        continue

            return {
                "mes": mes,
                "total": total,
                "transacoes": len(all_values) - 1,
                "categorias": categorias
            }

        except Exception as e:
            logger.error(f"Erro ao obter resumo de {mes}: {e}")
            return {"mes": mes, "total": 0, "transacoes": 0, "categorias": {}}


sheets_service = GoogleSheetsService()