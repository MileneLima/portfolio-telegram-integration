import json
import hashlib
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional
from decimal import Decimal

from loguru import logger

from config.settings import get_settings
from models.schemas import InterpretedTransaction, ExpenseCategory
from database.sqlite_db import get_db_session
from database.models import AIPromptCache
from sqlalchemy import select
from openai import AsyncOpenAI


class OpenAIService:
    """Serviço para processamento de IA"""

    def __init__(self):
        self.settings = get_settings()
        self.model = self.settings.openai_model
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def interpret_financial_message(self, message: str) -> InterpretedTransaction:
        """Interpretar mensagem financeira usando IA"""
        try:
            cached_result = await self._get_cached_result(message)
            if cached_result:
                logger.info(f"Usando resultado do cache para mensagem")
                return self._parse_ai_response(cached_result)

            prompt = self._create_financial_prompt(message)

            logger.info(f"Processando mensagem com {self.model}")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um assistente especializado em interpretar mensagens sobre gastos pessoais em português brasileiro. Sempre retorne JSON válido."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Baixa temperatura para consistÃªncia
                max_tokens=200
            )

            ai_response = response.choices[0].message.content.strip()
            logger.info(f"âœ… Resposta da IA recebida: {len(ai_response)} caracteres")

            await self._save_to_cache(message, ai_response)

            return self._parse_ai_response(ai_response)

        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")
            raise Exception(f"Erro na interpretação: {str(e)}")

    def _create_financial_prompt(self, message: str) -> str:
        """Criar prompt otimizado para interpretação financeira"""
        today = date.today().strftime("%Y-%m-%d")
        categories = [cat.value for cat in ExpenseCategory]

        prompt = f"""
Interprete esta mensagem sobre gasto pessoal em português brasileiro:
"{message}"

Extraia as informações e retorne APENAS um JSON válido com os campos:

- "descricao": nome do estabelecimento/item comprado (string)
- "valor": valor numérico em reais (número decimal, ex: 15.50)
- "categoria": uma das opções exatas: {', '.join(categories)}
- "data": formato YYYY-MM-DD (se não especificada, use hoje: {today})
- "confianca": número de 0.0 a 1.0 indicando certeza da interpretação

Sobre o campo "data":
Caso não seja específicada uma exata (mês e dia), porém for especificado um mês, você vai trazer a data do primeiro dia daquele mês em específico.
Caso a data seja um feriado, por exemplo, "natal", você vai trazer a data referente ao natal deste ano (2025-12-25).

Exemplos:
Input: "gastei 20 reais na padaria"
Output: {{"descricao": "Padaria", "valor": 20.00, "categoria": "Alimentação", "data": "{today}", "confianca": 0.9}}

Input: "uber para o trabalho 15 reais ontem" 
Output: {{"descricao": "Uber trabalho", "valor": 15.00, "categoria": "Transporte", "data": "{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}", "confianca": 0.8}}

Input: "lanche no mcdonalds mes passado 30 reais" 
Output: {{"descricao": "McDonalds", "valor": 30.00, "categoria": "Alimentação", "data": "{(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}", "confianca": 0.8}}

Input: "comprei uma blusa em agosto de 100 reais" 
Output: {{"descricao": "Blusa", "valor": 100.00, "categoria": "Outros", "data": "2025-08-01", "confianca": 0.8}}

Retorne APENAS o JSON, sem texto adicional:
"""
        return prompt

    def _parse_ai_response(self, ai_response: str) -> InterpretedTransaction:
        """Parsear resposta da IA em objeto estruturado"""
        try:
            ai_response = ai_response.strip()
            if ai_response.startswith("```json"):
                ai_response = ai_response[7:]
            if ai_response.endswith("```"):
                ai_response = ai_response[:-3]

            data = json.loads(ai_response)

            categoria = data.get("categoria")
            if categoria not in [cat.value for cat in ExpenseCategory]:
                logger.warning(f"Categoria inválida '{categoria}', usando 'Outros'")
                categoria = ExpenseCategory.OUTROS.value

            return InterpretedTransaction(
                descricao=data["descricao"],
                valor=Decimal(str(data["valor"])),
                categoria=ExpenseCategory(categoria),
                data=datetime.strptime(data["data"], "%Y-%m-%d").date(),
                confianca=float(data.get("confianca", 0.8))
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Erro ao parsear resposta da IA: {ai_response} - {str(e)}")
            raise Exception(f"Resposta inválida da IA.")

    async def _get_cached_result(self, message: str) -> Optional[str]:
        """Buscar resultado no cache"""
        try:
            message_hash = hashlib.sha256(message.encode()).hexdigest()

            async for db in get_db_session():
                result = await db.execute(
                    select(AIPromptCache).where(
                        AIPromptCache.input_hash == message_hash,
                        AIPromptCache.expires_at > datetime.now()
                    )
                )
                cached = result.scalar_one_or_none()

                if cached:
                    return cached.output_json

        except Exception as e:
            logger.warning(f"Erro ao buscar cache: {e}")

        return None

    async def _save_to_cache(self, message: str, ai_response: str):
        """Salvar resultado no cache"""
        try:
            message_hash = hashlib.sha256(message.encode()).hexdigest()
            expires_at = datetime.now() + timedelta(days=7)  # Cache por 7 dias

            async for db in get_db_session():
                cache_entry = AIPromptCache(
                    input_hash=message_hash,
                    input_text=message,
                    output_json=ai_response,
                    model_used=self.model,
                    expires_at=expires_at
                )

                db.add(cache_entry)
                await db.commit()

        except Exception as e:
            logger.warning(f"Erro ao salvar cache: {e}")


openai_service = OpenAIService()