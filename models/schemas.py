"""
Schemas Pydantic para validação de dados
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from enum import Enum


class ExpenseCategory(str, Enum):
    """Categorias de gastos"""
    ALIMENTACAO = "Alimentação"
    TRANSPORTE = "Transporte"
    SAUDE = "Saúde"
    LAZER = "Lazer"
    CASA = "Casa"
    FINANCAS = "Finanças"
    OUTROS = "Outros"


class TransactionStatus(str, Enum):
    """Status de processamento da transação"""
    PENDING = "pending"
    PROCESSED = "processed"
    ERROR = "error"


class InsightsPeriod(str, Enum):
    """Períodos para geração de insights"""
    MONTHLY = "monthly"
    YEARLY = "yearly"


class MessageInput(BaseModel):
    """Mensagem de entrada do usuário"""
    text: str = Field(..., min_length=1, description="Texto da mensagem")
    user_id: int = Field(..., description="ID do usuário Telegram")
    message_id: int = Field(..., description="ID da mensagem")
    chat_id: int = Field(..., description="ID do chat")
    timestamp: datetime = Field(default_factory=datetime.now)


class InterpretedTransaction(BaseModel):
    """Transação interpretada pela IA"""
    descricao: str = Field(..., description="Descrição da compra/gasto")
    valor: Decimal = Field(..., gt=0, description="Valor em reais")
    categoria: ExpenseCategory = Field(..., description="Categoria do gasto")
    data: date = Field(..., description="Data da transação")
    confianca: float = Field(default=1.0, ge=0.0, le=1.0, description="Nível de confiança da interpretação")

    @field_validator('valor', mode='before')
    def validate_valor(cls, v):
        if isinstance(v, str):
            import re
            v = re.sub(r'[^0-9.,]', '', v)
            v = v.replace(',', '.')
        return Decimal(str(v))


class ProcessedTransaction(BaseModel):
    """Transação processada e salva"""
    id: Optional[int] = None
    original_message: str
    interpreted_data: InterpretedTransaction
    status: TransactionStatus
    error_message: Optional[str] = None
    sheets_row: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class BotResponse(BaseModel):
    """Resposta do bot"""
    message: str
    success: bool = True
    transaction_id: Optional[int] = None
    data: Optional[Dict[str, Any]] = None


class FinancialInsights(BaseModel):
    """Insights financeiros gerados pela IA"""
    period_type: InsightsPeriod = Field(..., description="Tipo de período analisado")
    period_description: str = Field(..., description="Descrição do período (ex: 'Outubro 2025', 'Ano 2025')")
    total_expenses: Decimal = Field(..., description="Total de gastos no período")
    total_investments: Decimal = Field(default=Decimal('0'), description="Total de investimentos no período")
    category_breakdown: Dict[str, Decimal] = Field(..., description="Gastos por categoria")
    top_category: str = Field(..., description="Categoria com maior gasto")
    insights_text: str = Field(..., description="Análise textual gerada pela IA")
    recommendations: List[str] = Field(default_factory=list, description="Recomendações da IA")


class InsightRequest(BaseModel):
    """Solicitação de insights"""
    tipo: str = Field(..., description="Tipo de insight (mensal, categoria, tendencia)")
    periodo: Optional[str] = Field(None, description="Período (YYYY-MM, YYYY-Q1, etc)")


class MonthlyInsight(BaseModel):
    """Insight mensal"""
    mes: str
    total_gastos: Decimal
    gastos_por_categoria: Dict[str, Decimal]
    transacoes_count: int
    categoria_mais_gasta: str
    media_diaria: Decimal
    insight_text: str