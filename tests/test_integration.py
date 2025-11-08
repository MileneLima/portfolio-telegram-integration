"""
Testes de integração para funcionalidades financeiras
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from models.schemas import InterpretedTransaction, ExpenseCategory, InsightsPeriod, FinancialInsights
from services.openai_service import OpenAIService
from services.sheets_service import GoogleSheetsService
from bot.telegram_bot import TelegramFinanceBot


class TestInvestmentMessageProcessing:
    """Testes para processamento de mensagens de investimento end-to-end"""

    @pytest.fixture
    def openai_service(self):
        """Fixture para OpenAI Service"""
        return OpenAIService()

    @pytest.fixture
    def sheets_service(self):
        """Fixture para Sheets Service"""
        return GoogleSheetsService()

    @pytest.fixture
    def telegram_bot(self):
        """Fixture para Telegram Bot"""
        return TelegramFinanceBot()

    @pytest.mark.asyncio
    async def test_investment_message_categorization(self, openai_service):
        """Testar se mensagens de investimento são categorizadas como 'Finanças'"""
        
        investment_messages = [
            "guardei 300 reais na conta",
            "guardei 20 reais na caixinha",
            "investi 1000 reais",
            "poupança de 500 reais",
            "aplicação de 250 reais",
            "reserva de emergência 800 reais"
        ]
        
        mock_responses = [
            '{"descricao": "Poupança conta", "valor": 300.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Caixinha", "valor": 20.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Investimento", "valor": 1000.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Poupança", "valor": 500.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Aplicação", "valor": 250.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Reserva emergência", "valor": 800.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}'
        ]
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            for i, message in enumerate(investment_messages):
                mock_response = MagicMock()
                mock_response.choices[0].message.content = mock_responses[i]
                mock_create.return_value = mock_response
                
                result = await openai_service.interpret_financial_message(message)
                
                assert result.categoria == ExpenseCategory.FINANCAS, f"Mensagem '{message}' não foi categorizada como Finanças"
                assert result.valor > 0, f"Valor inválido para mensagem '{message}'"
                assert result.descricao, f"Descrição vazia para mensagem '{message}'"
                assert result.confianca >= 0.8, f"Confiança baixa para mensagem '{message}'"

    @pytest.mark.asyncio
    async def test_investment_vs_expense_categorization(self, openai_service):
        """Testar diferenciação entre investimentos e gastos regulares"""
        
        test_cases = [
            ("guardei 100 reais na poupança", ExpenseCategory.FINANCAS),
            ("gastei 100 reais no supermercado", ExpenseCategory.ALIMENTACAO),
            ("investi 500 reais", ExpenseCategory.FINANCAS),
            ("comprei comida 50 reais", ExpenseCategory.ALIMENTACAO),
            ("aplicação de 200 reais", ExpenseCategory.FINANCAS),
            ("uber 25 reais", ExpenseCategory.TRANSPORTE)
        ]
        
        mock_responses = [
            '{"descricao": "Poupança", "valor": 100.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Supermercado", "valor": 100.00, "categoria": "Alimentação", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Investimento", "valor": 500.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Comida", "valor": 50.00, "categoria": "Alimentação", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Aplicação", "valor": 200.00, "categoria": "Finanças", "data": "2025-10-31", "confianca": 0.9}',
            '{"descricao": "Uber", "valor": 25.00, "categoria": "Transporte", "data": "2025-10-31", "confianca": 0.9}'
        ]
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            for i, (message, expected_category) in enumerate(test_cases):
                mock_response = MagicMock()
                mock_response.choices[0].message.content = mock_responses[i]
                mock_create.return_value = mock_response
                
                result = await openai_service.interpret_financial_message(message)
                
                assert result.categoria == expected_category, f"Mensagem '{message}' categorizada incorretamente. Esperado: {expected_category}, Obtido: {result.categoria}"

    @pytest.mark.asyncio
    async def test_investment_date_inference(self, openai_service):
        """Testar inferência de data para transações de investimento"""
        
        test_cases = [
            ("guardei 100 reais hoje", date.today()),
            ("investi 500 reais ontem", date.today()),
            ("poupança de 200 reais", date.today())
        ]
        
        mock_responses = [
            f'{{"descricao": "Poupança", "valor": 100.00, "categoria": "Finanças", "data": "{date.today()}", "confianca": 0.9}}',
            f'{{"descricao": "Investimento", "valor": 500.00, "categoria": "Finanças", "data": "{date.today()}", "confianca": 0.9}}',
            f'{{"descricao": "Poupança", "valor": 200.00, "categoria": "Finanças", "data": "{date.today()}", "confianca": 0.9}}'
        ]
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            for i, (message, expected_date) in enumerate(test_cases):
                mock_response = MagicMock()
                mock_response.choices[0].message.content = mock_responses[i]
                mock_create.return_value = mock_response
                
                result = await openai_service.interpret_financial_message(message)
                
                date_diff = abs((result.data - expected_date).days)
                assert date_diff <= 1, f"Data incorreta para mensagem '{message}'. Esperado: {expected_date}, Obtido: {result.data}"

    @pytest.mark.asyncio
    async def test_sheets_investment_column_structure(self, sheets_service):
        """Testar se a estrutura da planilha inclui coluna Finanças"""
        
        mock_spreadsheet = MagicMock()
        mock_worksheet = MagicMock()
        
        mock_worksheet.row_values.return_value = ["Mês", "Total Gastos", "Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros", "Transações"]
        mock_spreadsheet.worksheet.return_value = mock_worksheet
        
        sheets_service.spreadsheet = mock_spreadsheet
        
        await sheets_service.update_summary_structure()
        
        mock_worksheet.insert_cols.assert_called_once()
        mock_worksheet.update_cell.assert_called()

    @pytest.mark.asyncio
    async def test_investment_transaction_storage_and_sync(self, sheets_service):
        """Testar armazenamento e sincronização de transações de investimento"""
        
        investment_transaction = InterpretedTransaction(
            descricao="Poupança conta",
            valor=Decimal("300.00"),
            categoria=ExpenseCategory.FINANCAS,
            data=date.today(),
            confianca=0.9
        )
        
        mock_spreadsheet = MagicMock()
        mock_monthly_ws = MagicMock()
        mock_resumo_ws = MagicMock()
        
        mock_spreadsheet.worksheet.side_effect = lambda name: mock_monthly_ws if name != "Resumo" else mock_resumo_ws
        mock_monthly_ws.get_all_values.return_value = [
            ["Data", "Descrição", "Categoria", "Valor", "Observações"],
            ["31/10/2025", "Poupança conta", "Finanças", "300.0", "Confiança: 90%"]
        ]
        
        sheets_service.spreadsheet = mock_spreadsheet
        
        row_number = await sheets_service.add_transaction(investment_transaction)
        
        mock_monthly_ws.append_row.assert_called_once()
        call_args = mock_monthly_ws.append_row.call_args[0][0]
        
        assert call_args[1] == "Poupança conta"
        assert call_args[2] == "Finanças"
        assert call_args[3] == 300.0
        assert "Confiança: 90" in call_args[4]
        
        assert isinstance(row_number, int)


class TestInsightsGeneration:
    """Testes para funcionalidade de geração de insights"""

    @pytest.fixture
    def openai_service(self):
        return OpenAIService()

    @pytest.fixture
    def sheets_service(self):
        return GoogleSheetsService()

    @pytest.mark.asyncio
    async def test_monthly_insights_generation(self, openai_service):
        """Testar geração de insights mensais"""
        
        monthly_data = [
            {"descricao": "Supermercado", "valor": 150.0, "categoria": "Alimentação", "data": "2025-10-15"},
            {"descricao": "Uber", "valor": 25.0, "categoria": "Transporte", "data": "2025-10-16"},
            {"descricao": "Poupança", "valor": 200.0, "categoria": "Finanças", "data": "2025-10-17"}
        ]
        
        mock_ai_response = """
**Resumo do Período**: Você teve um mês equilibrado com gastos de R$ 175,00 e investimentos de R$ 200,00.

**Análise por Categorias**: 
- Alimentação representa 40% dos gastos (R$ 150,00)
- Transporte representa 6,7% dos gastos (R$ 25,00)
- Finanças: R$ 200,00 em poupança

**Recomendações Práticas**:
- Continue priorizando investimentos
- Monitore gastos com alimentação
- Considere alternativas de transporte mais econômicas
        """
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = mock_ai_response
            mock_create.return_value = mock_response
            
            insights = await openai_service.generate_financial_insights(
                monthly_data, InsightsPeriod.MONTHLY, "Outubro 2025"
            )
            
            assert isinstance(insights, FinancialInsights)
            assert insights.period_type == InsightsPeriod.MONTHLY
            assert insights.period_description == "Outubro 2025"
            assert insights.total_expenses == Decimal("175.00")
            assert insights.total_investments == Decimal("200.00")
            assert insights.top_category == "Alimentação"
            assert len(insights.recommendations) > 0
            assert "Continue priorizando investimentos" in insights.insights_text

    @pytest.mark.asyncio
    async def test_yearly_insights_generation(self, openai_service):
        """Testar geração de insights anuais"""
        
        yearly_data = [
            {"descricao": "Supermercado", "valor": 1800.0, "categoria": "Alimentação", "data": "2025-01-15"},
            {"descricao": "Combustível", "valor": 600.0, "categoria": "Transporte", "data": "2025-02-16"},
            {"descricao": "Investimento", "valor": 2400.0, "categoria": "Finanças", "data": "2025-03-17"}
        ]
        
        mock_ai_response = """
**Resumo do Período**: Excelente ano financeiro com R$ 2.400,00 gastos e R$ 2.400,00 investidos.

**Análise por Categorias**:
- Alimentação: R$ 1.800,00 (75% dos gastos)
- Transporte: R$ 600,00 (25% dos gastos)
- Investimentos: R$ 2.400,00 (100% da meta)

**Recomendações Práticas**:
- Mantenha o equilíbrio entre gastos e investimentos
- Diversifique investimentos
- Otimize gastos com alimentação
        """
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = mock_ai_response
            mock_create.return_value = mock_response
            
            insights = await openai_service.generate_financial_insights(
                yearly_data, InsightsPeriod.YEARLY, "Ano 2025"
            )
            
            assert insights.period_type == InsightsPeriod.YEARLY
            assert insights.period_description == "Ano 2025"
            assert insights.total_expenses == Decimal("2400.00")  # 1800 + 600
            assert insights.total_investments == Decimal("2400.00")
            assert "Alimentação" in insights.category_breakdown
            assert insights.category_breakdown["Alimentação"] == Decimal("1800.00")

    @pytest.mark.asyncio
    async def test_insights_with_insufficient_data(self, openai_service):
        """Testar geração de insights com dados insuficientes"""
        
        empty_data = []
        
        mock_ai_response = """
**Resumo do Período**: Não há dados suficientes para análise neste período.

**Recomendações Práticas**:
- Comece a registrar seus gastos diários
- Estabeleça um orçamento mensal
- Defina metas de poupança
        """
        
        with patch.object(openai_service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = mock_ai_response
            mock_create.return_value = mock_response
            
            insights = await openai_service.generate_financial_insights(
                empty_data, InsightsPeriod.MONTHLY, "Outubro 2025"
            )
            
            assert isinstance(insights, FinancialInsights)
            assert insights.total_expenses == Decimal("0")
            assert insights.total_investments == Decimal("0")
            assert len(insights.category_breakdown) == 0
            assert "Não há dados suficientes" in insights.insights_text or "dados" in insights.insights_text.lower()

    @pytest.mark.asyncio
    async def test_insights_data_formatting(self, openai_service):
        """Testar formatação de dados para IA"""
        
        test_data = [
            {"descricao": "Padaria", "valor": 15.0, "categoria": "Alimentação", "data": "2025-10-15"},
            {"descricao": "Farmácia", "valor": 45.0, "categoria": "Saúde", "data": "2025-10-16"},
            {"descricao": "Poupança", "valor": 100.0, "categoria": "Finanças", "data": "2025-10-17"}
        ]
        
        formatted = openai_service._format_transactions_for_ai(test_data)
        
        assert "RESUMO FINANCEIRO:" in formatted
        assert "Total de Gastos: R$ 60.00" in formatted
        assert "Total de Investimentos/Poupança: R$ 100.00" in formatted
        assert "Alimentação:" in formatted
        assert "Saúde:" in formatted
        assert "Finanças:" in formatted
        assert "Padaria: R$ 15.00" in formatted


class TestEnhancedSummaryCommand:
    """Testes para comando de resumo aprimorado"""

    @pytest.fixture
    def telegram_bot(self):
        return TelegramFinanceBot()

    def test_resumo_parameter_parsing_valid_months(self, telegram_bot):
        """Testar parsing de parâmetros válidos para meses"""
        
        valid_months = [
            ("janeiro", ("monthly", "Janeiro")),
            ("fevereiro", ("monthly", "Fevereiro")),
            ("março", ("monthly", "Março")),
            ("dezembro", ("monthly", "Dezembro"))
        ]
        
        for input_month, expected in valid_months:
            result = telegram_bot._parse_resumo_parameters([input_month])
            assert result == expected, f"Parsing incorreto para mês '{input_month}'"

    def test_resumo_parameter_parsing_yearly(self, telegram_bot):
        """Testar parsing de parâmetro anual"""
        
        result = telegram_bot._parse_resumo_parameters(["ano"])
        assert result == ("yearly", None)

    def test_resumo_parameter_parsing_no_params(self, telegram_bot):
        """Testar parsing sem parâmetros (comportamento original)"""
        
        result = telegram_bot._parse_resumo_parameters([])
        assert result == ("monthly", None)

    def test_resumo_parameter_parsing_invalid(self, telegram_bot):
        """Testar parsing de parâmetros inválidos"""
        
        invalid_params = ["mes_invalido", "13", "abc", ""]
        
        for invalid_param in invalid_params:
            with pytest.raises(ValueError) as exc_info:
                telegram_bot._parse_resumo_parameters([invalid_param])
            
            error_msg = str(exc_info.value)
            assert "Parâmetro inválido" in error_msg
            assert "Uso correto" in error_msg
            assert "janeiro" in error_msg

    @pytest.mark.asyncio
    async def test_yearly_summary_aggregation(self, telegram_bot):
        """Testar agregação de dados para resumo anual"""
        
        mock_yearly_data = {
            "periodo": "anual",
            "total_gastos": 2400.0,
            "total_financas": 1200.0,
            "total_transacoes": 24,
            "categorias_totais": {
                "Alimentação": 1200.0,
                "Transporte": 600.0,
                "Saúde": 300.0,
                "Lazer": 300.0
            }
        }
        
        with patch('bot.telegram_bot.sheets_service') as mock_sheets:
            mock_sheets.get_transactions_for_period = AsyncMock(return_value=[
                {"descricao": "Supermercado", "valor": 1200.0, "categoria": "Alimentação", "data": "2025-01-15"},
                {"descricao": "Combustível", "valor": 600.0, "categoria": "Transporte", "data": "2025-02-16"},
                {"descricao": "Investimento", "valor": 1200.0, "categoria": "Finanças", "data": "2025-03-17"}
            ])
            
            result = await telegram_bot._get_insights_data("yearly")
            
            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]["categoria"] == "Alimentação"
            assert result[1]["categoria"] == "Transporte"
            assert result[2]["categoria"] == "Finanças"

    @pytest.mark.asyncio
    async def test_backward_compatibility_resumo(self, telegram_bot):
        """Testar compatibilidade com uso anterior do /resumo"""
        
        mock_monthly_data = {
            "mes": "Outubro",
            "total": 450.0,
            "transacoes": 12,
            "categorias": {
                "Alimentação": 200.0,
                "Transporte": 100.0,
                "Finanças": 150.0
            }
        }
        
        with patch('bot.telegram_bot.sheets_service') as mock_sheets:
            mock_sheets.get_period_data = AsyncMock(return_value=mock_monthly_data)
            
            period_type, period_value = telegram_bot._parse_resumo_parameters([])
            
            assert period_type == "monthly"
            assert period_value is None


if __name__ == "__main__":
    print("🧪 Executando testes de integração...")
    
    bot = TelegramFinanceBot()
    
    try:
        result = bot._parse_resumo_parameters(["janeiro"])
        assert result == ("monthly", "Janeiro")
        print("✅ Teste de parsing de mês passou")
        
        result = bot._parse_resumo_parameters(["ano"])
        assert result == ("yearly", None)
        print("✅ Teste de parsing anual passou")
        
        result = bot._parse_resumo_parameters([])
        assert result == ("monthly", None)
        print("✅ Teste sem parâmetros passou")
        
    except Exception as e:
        print(f"❌ Erro nos testes básicos: {e}")
    
    print("🎉 Testes de integração básicos concluídos!")