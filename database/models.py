"""
Modelos SQLAlchemy para o banco de dados
"""

from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Text, Boolean
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Transaction(Base):
    """Modelo de transação financeira"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    original_message = Column(Text, nullable=False, comment="Mensagem original do usuário")
    user_id = Column(Integer, nullable=False, comment="ID do usuário Telegram")
    message_id = Column(Integer, nullable=False, comment="ID da mensagem Telegram")
    chat_id = Column(Integer, nullable=False, comment="ID do chat")

    descricao = Column(String(255), nullable=False, comment="Descrição interpretada")
    valor = Column(Numeric(10, 2), nullable=False, comment="Valor da transação")
    categoria = Column(String(50), nullable=False, comment="Categoria do gasto")
    data_transacao = Column(Date, nullable=False, comment="Data da transação")
    confianca = Column(Numeric(3, 2), default=1.0, comment="Nível de confiança da IA")

    status = Column(String(20), default="pending", comment="Status do processamento")
    error_message = Column(Text, nullable=True, comment="Mensagem de erro se houver")

    sheets_row_number = Column(Integer, nullable=True, comment="Número da linha na planilha")
    sheets_updated_at = Column(DateTime, nullable=True, comment="Última atualização na planilha")

    created_at = Column(DateTime, default=func.now(), comment="Data de criação")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="Última atualização")

    def __repr__(self):
        return f"<Transaction(id={self.id}, descricao='{self.descricao}', valor={self.valor})>"


class AIPromptCache(Base):
    """Cache de prompts da IA para otimizar custos"""
    __tablename__ = "ai_prompt_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    input_hash = Column(String(64), unique=True, nullable=False, comment="SHA256 do input")
    input_text = Column(Text, nullable=False, comment="Texto original")
    output_json = Column(Text, nullable=False, comment="Resposta da IA em JSON")
    model_used = Column(String(50), nullable=False, comment="Modelo de IA usado")

    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False, comment="Data de expiração do cache")

    def __repr__(self):
        return f"<AIPromptCache(id={self.id}, hash={self.input_hash[:8]}...)>"


class UserConfig(Base):
    """Configurações do usuário"""
    __tablename__ = "user_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, comment="ID do usuário Telegram")

    spreadsheet_id = Column(String(255), nullable=False, comment="ID da planilha Google")
    timezone = Column(String(50), default="America/Sao_Paulo", comment="Timezone do usuário")
    default_currency = Column(String(3), default="BRL", comment="Moeda padrão")

    auto_categorize = Column(Boolean, default=True, comment="Categorização automática")
    send_daily_summary = Column(Boolean, default=False, comment="Enviar resumo diário")
    send_monthly_insights = Column(Boolean, default=True, comment="Enviar insights mensais")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<UserConfig(user_id={self.user_id}, spreadsheet_id={self.spreadsheet_id})>"