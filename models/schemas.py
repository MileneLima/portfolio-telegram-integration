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


# Schemas para processamento de áudio
class AudioMessage(BaseModel):
    """Mensagem de áudio do Telegram"""
    file_id: str = Field(..., description="ID do arquivo no Telegram")
    file_size: int = Field(..., description="Tamanho do arquivo em bytes")
    duration: int = Field(..., description="Duração do áudio em segundos")
    mime_type: str = Field(..., description="Tipo MIME do arquivo")
    user_id: int = Field(..., description="ID do usuário Telegram")
    message_id: int = Field(..., description="ID da mensagem")
    chat_id: int = Field(..., description="ID do chat")


class TranscriptionResult(BaseModel):
    """Resultado da transcrição de áudio"""
    text: str = Field(..., description="Texto transcrito")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confiança da transcrição")
    language: str = Field(default="pt", description="Idioma detectado")
    duration: float = Field(..., description="Duração do áudio processado")
    processing_time: float = Field(..., description="Tempo de processamento em segundos")


class TranscriptionConfirmation(BaseModel):
    """Confirmação de transcrição pelo usuário"""
    transcription_id: str = Field(..., description="ID único da transcrição")
    user_id: int = Field(..., description="ID do usuário")
    transcribed_text: str = Field(..., description="Texto transcrito")
    confirmed: bool = Field(..., description="Se foi confirmado pelo usuário")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp da confirmação")


class AudioProcessingStatus(str, Enum):
    """Status do processamento de áudio"""
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PROCESSING_EXPENSE = "processing_expense"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class GoalStatus(str, Enum):
    """Status da meta financeira"""
    DENTRO_META = "dentro_meta"
    PROXIMO_LIMITE = "proximo_limite"  # 80-100%
    LIMITE_EXCEDIDO = "limite_excedido"  # >100%


class AlertType(str, Enum):
    """Tipo de alerta de meta"""
    WARNING_80_PERCENT = "warning_80"
    EXCEEDED_100_PERCENT = "exceeded_100"


class PendingTranscription(BaseModel):
    """Transcrição pendente de confirmação"""
    id: str = Field(..., description="UUID único da transcrição")
    user_id: int = Field(..., description="ID do usuário")
    message_id: int = Field(..., description="ID da mensagem original")
    transcribed_text: str = Field(..., description="Texto transcrito")
    created_at: datetime = Field(default_factory=datetime.now, description="Data de criação")
    expires_at: datetime = Field(..., description="Data de expiração (5 minutos)")
    
    @classmethod
    def create_with_timeout(cls, user_id: int, message_id: int, transcribed_text: str, timeout_minutes: int = 5):
        """Criar transcrição pendente com timeout automático"""
        import uuid
        from datetime import timedelta
        
        now = datetime.now()
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            message_id=message_id,
            transcribed_text=transcribed_text,
            created_at=now,
            expires_at=now + timedelta(minutes=timeout_minutes)
        )


# Schemas para metas financeiras
class GoalCreate(BaseModel):
    """Schema para criação de meta"""
    categoria: ExpenseCategory = Field(..., description="Categoria da meta")
    valor_meta: Decimal = Field(..., gt=0, description="Valor da meta mensal")
    mes: int = Field(..., ge=1, le=12, description="Mês da meta (1-12)")
    ano: int = Field(..., ge=2020, le=2030, description="Ano da meta")

    @field_validator('valor_meta', mode='before')
    def validate_valor_meta(cls, v):
        if isinstance(v, str):
            import re
            v = re.sub(r'[^0-9.,]', '', v)
            v = v.replace(',', '.')
        return Decimal(str(v))


class GoalResponse(BaseModel):
    """Schema para resposta de meta"""
    id: int = Field(..., description="ID da meta")
    categoria: ExpenseCategory = Field(..., description="Categoria da meta")
    valor_meta: Decimal = Field(..., description="Valor da meta mensal")
    valor_gasto: Decimal = Field(..., description="Valor gasto no período")
    progresso_percentual: float = Field(..., description="Percentual de progresso")
    status: GoalStatus = Field(..., description="Status da meta")
    mes: int = Field(..., description="Mês da meta")
    ano: int = Field(..., description="Ano da meta")


class GoalAlert(BaseModel):
    """Schema para alerta de meta"""
    tipo: AlertType = Field(..., description="Tipo de alerta")
    categoria: ExpenseCategory = Field(..., description="Categoria da meta")
    valor_meta: Decimal = Field(..., description="Valor da meta")
    valor_atual: Decimal = Field(..., description="Valor atual gasto")
    percentual: float = Field(..., description="Percentual de progresso")
