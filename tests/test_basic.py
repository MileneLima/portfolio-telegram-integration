"""
Testes básicos da aplicação
"""

import pytest
from decimal import Decimal
from datetime import date

from models.schemas import InterpretedTransaction, ExpenseCategory
from services.openai_service import OpenAIService
from utils.helpers import extract_numbers, format_currency, get_month_name


class TestSchemas:
    """Testes dos schemas Pydantic"""

    def test_interpreted_transaction_creation(self):
        """Testar criação de transação interpretada"""
        transaction = InterpretedTransaction(
            descricao="Supermercado",
            valor=Decimal("25.50"),
            categoria=ExpenseCategory.ALIMENTACAO,
            data=date.today(),
            confianca=0.9
        )

        assert transaction.descricao == "Supermercado"
        assert transaction.valor == Decimal("25.50")
        assert transaction.categoria == ExpenseCategory.ALIMENTACAO
        assert transaction.confianca == 0.9

    def test_valor_validation(self):
        """Testar validação de valor"""
        transaction = InterpretedTransaction(
            descricao="Teste",
            valor="25,50",
            categoria=ExpenseCategory.OUTROS,
            data=date.today()
        )

        assert transaction.valor == Decimal("25.50")


class TestUtils:
    """Testes das funções utilitárias"""

    def test_extract_numbers(self):
        """Testar extração de números"""
        text = "Gastei 25,50 no supermercado e 10 reais no café"
        numbers = extract_numbers(text)

        assert 25.50 in numbers
        assert 10.0 in numbers
        assert len(numbers) == 2

    def test_format_currency(self):
        """Testar formatação de moeda"""
        formatted = format_currency(25.50)
        assert formatted == "R$ 25.50"

    def test_get_month_name(self):
        """Testar nomes de meses"""
        assert get_month_name(1) == "Janeiro"
        assert get_month_name(12) == "Dezembro"
        assert get_month_name(13) == "Janeiro"


@pytest.mark.asyncio
class TestServices:
    """Testes dos serviços (necessita configuração)"""

    @pytest.mark.skip(reason="Necessita chaves de API configuradas")
    async def test_openai_service(self):
        """Testar serviço OpenAI"""
        service = OpenAIService()

        result = await service.interpret_financial_message("gastei 20 reais na padaria")

        assert result.valor > 0
        assert result.descricao
        assert result.categoria in [cat.value for cat in ExpenseCategory]


if __name__ == "__main__":
    print("Executando testes básicos...")

    test_schemas = TestSchemas()
    test_schemas.test_interpreted_transaction_creation()
    test_schemas.test_valor_validation()
    print("Testes de schemas passaram")

    test_utils = TestUtils()
    test_utils.test_extract_numbers()
    test_utils.test_format_currency()
    test_utils.test_get_month_name()
    print("Testes de utils passaram")

    print("Todos os testes básicos passaram!")