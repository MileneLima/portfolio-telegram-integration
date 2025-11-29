"""
Serviço de integração com OpenAI para processamento de mensagens
"""

import json
import hashlib
from datetime import datetime, timedelta, date
from typing import Optional
from decimal import Decimal

from loguru import logger

from config.settings import get_settings
from models.schemas import InterpretedTransaction, ExpenseCategory, FinancialInsights, InsightsPeriod, TranscriptionResult
from database.sqlite_db import get_db_session
from database.models import AIPromptCache
from sqlalchemy import select
from openai import AsyncOpenAI
from utils.error_handler import AudioErrorHandler, audio_metrics


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

            logger.info(f"🧠 Processando mensagem com {self.model}")
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
                temperature=0.1,
                max_tokens=200
            )

            ai_response = response.choices[0].message.content.strip()
            logger.info(f"Resposta da IA recebida: {len(ai_response)} caracteres")

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
Interprete esta mensagem sobre gasto pessoal ou investimento em português brasileiro:
"{message}"

Extraia as informações e retorne APENAS um JSON válido com os campos:

- "descricao": nome do estabelecimento/item comprado/investimento (string)
- "valor": valor numérico em reais (número decimal, ex: 15.50)
- "categoria": uma das opções exatas: {', '.join(categories)}
- "data": formato YYYY-MM-DD (se não especificada, use hoje: {today})
- "confianca": número de 0.0 a 1.0 indicando certeza da interpretação

IMPORTANTE - Detecção de Investimentos/Poupança:
Se a mensagem contém palavras como "guardei", "investi", "caixinha", "poupança", "investimento", "aplicação", "reserva", use a categoria "Finanças".

Sobre o campo "data":
Caso não seja específicada uma exata (mês e dia), porém for especificado um mês, você vai trazer a data do primeiro dia daquele mês em específico.
Caso a data seja um feriado, por exemplo, "natal", você vai trazer a data referente ao natal deste ano (2025-12-25).

Exemplos:
Input: "gastei 20 reais na padaria"
Output: {{"descricao": "Padaria", "valor": 20.00, "categoria": "Alimentação", "data": "{today}", "confianca": 0.9}}

Input: "uber para o trabalho 15 reais ontem" 
Output: {{"descricao": "Uber trabalho", "valor": 15.00, "categoria": "Transporte", "data": "{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}", "confianca": 0.8}}

Input: "guardei 300 reais na conta"
Output: {{"descricao": "Poupança conta", "valor": 300.00, "categoria": "Finanças", "data": "{today}", "confianca": 0.9}}

Input: "guardei 20 reais na caixinha"
Output: {{"descricao": "Caixinha", "valor": 20.00, "categoria": "Finanças", "data": "{today}", "confianca": 0.9}}

Input: "investi 1000 reais"
Output: {{"descricao": "Investimento", "valor": 1000.00, "categoria": "Finanças", "data": "{today}", "confianca": 0.9}}

Input: "lanche no mcdonalds mes passado 30 reais" 
Output: {{"descricao": "McDonalds", "valor": 30.00, "categoria": "Alimentação", "data": "{(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}", "confianca": 0.8}}

Input: "comprei uma blusa em agosto de 100 reais" 
Output: {{"descricao": "Blusa", "valor": 100.00, "categoria": "Outros", "data": "2025-08-01", "confianca": 0.8}}

Input: "padaria 10 reais dia 1" 
Output: {{"descricao": "Padaria", "valor": 10.00, "categoria": "Alimentação", "data": "2025-{(datetime.now().month)}-01", "confianca": 0.8}}

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
                logger.warning(f"🚨 Categoria inválida '{categoria}', usando 'Outros'")
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
            logger.warning(f"❌ Erro ao buscar cache: {e}")

        return None

    async def _save_to_cache(self, message: str, ai_response: str):
        """Salvar resultado no cache"""
        try:
            message_hash = hashlib.sha256(message.encode()).hexdigest()
            expires_at = datetime.now() + timedelta(days=7)

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
            logger.warning(f"❌ Erro ao salvar cache: {e}")


    async def transcribe_audio(self, audio_file_path: str) -> TranscriptionResult:
        """Transcrever áudio usando API Whisper da OpenAI"""
        import os
        import time
        import asyncio
        from pathlib import Path
        
        try:
            # Validar se arquivo existe
            if not os.path.exists(audio_file_path):
                raise Exception("Arquivo de áudio não encontrado. Verifique se o arquivo foi enviado corretamente.")
            
            # Validar tamanho do arquivo
            file_size = os.path.getsize(audio_file_path)
            max_size = 25 * 1024 * 1024  # 25MB
            if file_size > max_size:
                raise Exception(f"Arquivo muito grande ({file_size / 1024 / 1024:.1f}MB). O limite máximo é 25MB. Tente dividir o áudio em partes menores.")
            
            if file_size == 0:
                raise Exception("Arquivo de áudio vazio ou corrompido. Tente gravar novamente.")
            
            # Validar formato do arquivo
            file_extension = Path(audio_file_path).suffix.lower()
            supported_formats = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg', '.oga', '.opus']
            if file_extension not in supported_formats:
                formats_str = ', '.join(supported_formats)
                raise Exception(f"Formato de áudio não suportado ({file_extension}). Formatos aceitos: {formats_str}")
            
            start_time = time.time()
            
            # Implementar retry com backoff exponencial
            max_retries = 2
            base_delay = 1.0
            
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"🎵 Transcrevendo áudio (tentativa {attempt + 1}/{max_retries + 1}): {audio_file_path}")
                    
                    # Abrir arquivo para transcrição
                    with open(audio_file_path, 'rb') as audio_file:
                        response = await self.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="pt",  # Português brasileiro
                            response_format="json"
                        )
                    
                    processing_time = time.time() - start_time
                    
                    # Validar qualidade da transcrição
                    transcribed_text = response.text.strip()
                    if not transcribed_text:
                        raise Exception("Áudio muito baixo ou com ruído excessivo. Tente gravar em ambiente mais silencioso e fale mais próximo do microfone.")
                    
                    # Calcular confiança baseada no comprimento e qualidade
                    confidence = self._calculate_transcription_confidence(transcribed_text, file_size, processing_time)
                    
                    # Obter duração do áudio (estimativa baseada no tamanho)
                    estimated_duration = self._estimate_audio_duration(file_size, file_extension)
                    
                    logger.info(f"✅ Transcrição concluída: {len(transcribed_text)} caracteres em {processing_time:.2f}s")
                    
                    # Registrar sucesso nas métricas
                    audio_metrics.record_success(processing_time)
                    
                    return TranscriptionResult(
                        text=transcribed_text,
                        confidence=confidence,
                        language="pt",
                        duration=estimated_duration,
                        processing_time=processing_time
                    )
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    logger.error(f"❌ Erro na tentativa {attempt + 1} de transcrição: {str(e)}")
                    
                    # Verificar se é um erro recuperável
                    recoverable_errors = [
                        "timeout", "network", "connection", "rate limit", 
                        "server error", "503", "502", "500", "429",
                        "internal server error", "bad gateway", "service unavailable"
                    ]
                    
                    is_recoverable = any(err in error_msg for err in recoverable_errors)
                    
                    if attempt < max_retries and is_recoverable:
                        # Calcular delay com backoff exponencial
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"⚠️ Erro recuperável na tentativa {attempt + 1}: {str(e)}. Tentando novamente em {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Erro não recuperável ou esgotaram-se as tentativas
                        # Fornecer mensagens de erro específicas e orientações claras
                        if "rate limit" in error_msg or "429" in error_msg:
                            raise Exception("Limite de requisições excedido. Aguarde alguns minutos antes de tentar novamente.")
                        elif "timeout" in error_msg or "network" in error_msg or "connection" in error_msg:
                            raise Exception("Erro de conexão. Verifique sua internet e tente novamente.")
                        elif any(server_err in error_msg for server_err in ["server", "503", "502", "500", "unavailable"]):
                            raise Exception("Serviço temporariamente indisponível. Tente novamente em alguns minutos ou use mensagem de texto.")
                        elif any(corrupt_err in error_msg for corrupt_err in ["corrupted", "invalid", "malformed"]):
                            raise Exception("Arquivo de áudio corrompido ou ilegível. Tente gravar novamente.")
                        elif "permission" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
                            raise Exception("Erro de autenticação. Verifique as configurações da API.")
                        elif "quota" in error_msg or "billing" in error_msg:
                            raise Exception("Cota da API excedida. Verifique sua conta OpenAI.")
                        elif "unsupported" in error_msg or "format" in error_msg:
                            raise Exception("Formato de áudio não suportado. Use MP3, WAV, M4A ou WebM.")
                        else:
                            # Usar error handler para tratamento robusto
                            context = {
                                'file_path': audio_file_path,
                                'attempt': attempt + 1,
                                'operation': 'transcription'
                            }
                            
                            # Registrar erro nas métricas
                            audio_metrics.record_error(e)
                            
                            # Obter mensagem amigável
                            user_friendly_msg = AudioErrorHandler.handle_audio_error(e, context=context)
                            raise Exception(user_friendly_msg)
            
        except Exception as e:
            logger.error(f"❌ Erro ao transcrever áudio: {str(e)}")
            raise
    
    def _calculate_transcription_confidence(self, text: str, file_size: int, processing_time: float) -> float:
        """Calcular confiança da transcrição baseada em métricas"""
        confidence = 0.8  # Base
        
        # Ajustar baseado no comprimento do texto
        if len(text) > 50:
            confidence += 0.1
        elif len(text) < 10:
            confidence -= 0.2
        
        # Ajustar baseado na qualidade do áudio (tamanho vs tempo)
        if file_size > 1024 * 1024:  # > 1MB
            confidence += 0.05
        
        # Ajustar baseado no tempo de processamento
        if processing_time < 5.0:
            confidence += 0.05
        
        # Garantir que está no range válido
        return max(0.0, min(1.0, confidence))
    
    def _estimate_audio_duration(self, file_size: int, file_extension: str) -> float:
        """Estimar duração do áudio baseada no tamanho do arquivo"""
        # Estimativas aproximadas baseadas em bitrates típicos
        bitrate_estimates = {
            '.mp3': 128,  # kbps
            '.m4a': 128,
            '.mp4': 128,
            '.wav': 1411,  # PCM 16-bit 44.1kHz
            '.webm': 96,
            '.ogg': 64,   # Opus típico do Telegram
            '.oga': 64,
            '.opus': 64,
            '.mpeg': 128,
            '.mpga': 128
        }
        
        bitrate = bitrate_estimates.get(file_extension, 128)  # Default 128 kbps
        
        # Calcular duração: (file_size_bits) / (bitrate_bits_per_second)
        file_size_bits = file_size * 8
        bitrate_bits_per_second = bitrate * 1000
        
        estimated_duration = file_size_bits / bitrate_bits_per_second
        
        # Aplicar fator de correção (arquivos têm overhead)
        correction_factor = 0.9
        return estimated_duration * correction_factor

    async def generate_financial_insights(self, transactions_data: list, period_type: InsightsPeriod, period_description: str) -> FinancialInsights:
        """Gerar insights financeiros usando IA"""
        try:
            formatted_data = self._format_transactions_for_ai(transactions_data)
            
            prompt = self._create_insights_prompt(formatted_data, period_type, period_description)
            
            logger.info(f"🧠 Gerando insights financeiros para {period_description}")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um consultor financeiro especializado em análise de gastos pessoais. Forneça insights práticos e acionáveis em português brasileiro. IMPORTANTE: Não use formatação markdown (# ## * -). Use apenas texto simples com emojis para destacar seções. Limite sua resposta a 2500 caracteres."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=600
            )

            ai_response = response.choices[0].message.content.strip()
            
            ai_response = self._clean_and_limit_response(ai_response, 2500)
            
            logger.info(f"✅ Insights gerados: {len(ai_response)} caracteres")

            total_expenses = sum(t['valor'] for t in transactions_data if t['categoria'] != 'Finanças')
            total_investments = sum(t['valor'] for t in transactions_data if t['categoria'] == 'Finanças')
            
            category_breakdown = {}
            for transaction in transactions_data:
                categoria = transaction['categoria']
                if categoria != 'Finanças':
                    category_breakdown[categoria] = category_breakdown.get(categoria, Decimal('0')) + Decimal(str(transaction['valor']))
            
            top_category = max(category_breakdown.keys(), key=lambda k: category_breakdown[k]) if category_breakdown else "Nenhuma"
            
            recommendations = []
            lines = ai_response.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('- ') or line.startswith('• ') or (line and line[0].isdigit() and '. ' in line):
                    recommendations.append(line.lstrip('- •').split('. ', 1)[-1])
            
            return FinancialInsights(
                period_type=period_type,
                period_description=period_description,
                total_expenses=Decimal(str(total_expenses)),
                total_investments=Decimal(str(total_investments)),
                category_breakdown=category_breakdown,
                top_category=top_category,
                insights_text=ai_response,
                recommendations=recommendations[:5]  # Limitar a 5 recomendações
            )

        except Exception as e:
            logger.error(f"Erro ao gerar insights: {e}")
            raise Exception(f"Erro na geração de insights: {str(e)}")

    def _create_insights_prompt(self, formatted_data: str, period_type: InsightsPeriod, period_description: str) -> str:
        """Criar prompt otimizado para geração de insights financeiros"""
        
        period_text = "mensal" if period_type == InsightsPeriod.MONTHLY else "anual"
        
        prompt = f"""
Analise os dados financeiros do período {period_description} e forneça insights práticos:

{formatted_data}

Forneça uma análise concisa incluindo:

📊 RESUMO: Visão geral dos gastos e investimentos
🏷️ CATEGORIAS: Principais categorias de gastos
📈 PADRÕES: Tendências observadas
⚠️ ATENÇÃO: Gastos que merecem revisão
💡 DICAS: 3 recomendações práticas específicas

REGRAS IMPORTANTES:
- A categoria 'Finanças' se trata de investimentos e dinheiro guardado, não é um gasto, leve isso em consideração sempre
- Use apenas texto simples com emojis (sem markdown # ## * -)
- Seja específico com valores e percentuais
- Linguagem acessível e motivadora
- Máximo 2500 caracteres
- Foque em insights acionáveis
- Reconheça bons hábitos (investimentos)

Estruture com emojis para destacar seções, não use formatação markdown.
"""
        return prompt

    def _clean_and_limit_response(self, response: str, max_chars: int = 2500) -> str:
        """Limpar formatação markdown e limitar caracteres da resposta"""
        try:
            cleaned = response
            
            import re
            cleaned = re.sub(r'^#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
            
            cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
            cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
            
            cleaned = re.sub(r'^[\-\*]\s+', '• ', cleaned, flags=re.MULTILINE)
            
            cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
            
            cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
            
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            
            if len(cleaned) > max_chars:
                truncated = cleaned[:max_chars]
                
                last_period = truncated.rfind('.')
                last_newline = truncated.rfind('\n')
                
                cut_point = max(last_period, last_newline)
                
                if cut_point > max_chars * 0.8:
                    cleaned = truncated[:cut_point + 1]
                else:
                    cleaned = truncated + "..."
            
            return cleaned.strip()
            
        except Exception as e:
            logger.error(f"Erro ao limpar resposta: {e}")
            return response[:max_chars] + ("..." if len(response) > max_chars else "")

    def _format_transactions_for_ai(self, transactions_data: list) -> str:
        """Formatar dados de transações para consumo da IA"""
        if not transactions_data:
            return "Nenhuma transação encontrada para o período."
        
        categories = {}
        total_geral = Decimal('0')
        total_investimentos = Decimal('0')
        
        for transaction in transactions_data:
            categoria = transaction['categoria']
            valor = Decimal(str(transaction['valor']))
            
            if categoria == 'Finanças':
                total_investimentos += valor
            else:
                total_geral += valor
            
            if categoria not in categories:
                categories[categoria] = {
                    'total': Decimal('0'),
                    'count': 0,
                    'transactions': []
                }
            
            categories[categoria]['total'] += valor
            categories[categoria]['count'] += 1
            categories[categoria]['transactions'].append({
                'descricao': transaction['descricao'],
                'valor': valor,
                'data': transaction['data']
            })
        
        formatted = f"RESUMO FINANCEIRO:\n"
        formatted += f"Total de Gastos: R$ {total_geral:.2f}\n"
        formatted += f"Total de Investimentos/Poupança: R$ {total_investimentos:.2f}\n"
        formatted += f"Total de Transações: {sum(cat['count'] for cat in categories.values())}\n\n"
        
        formatted += "DETALHAMENTO POR CATEGORIA:\n"
        
        sorted_categories = sorted(categories.items(), key=lambda x: x[1]['total'], reverse=True)
        
        for categoria, data in sorted_categories:
            percentage = (data['total'] / (total_geral + total_investimentos)) * 100 if (total_geral + total_investimentos) > 0 else 0
            formatted += f"\n{categoria}: R$ {data['total']:.2f} ({percentage:.1f}%) - {data['count']} transações\n"
            
            main_transactions = sorted(data['transactions'], key=lambda x: x['valor'], reverse=True)[:3]
            for trans in main_transactions:
                formatted += f"  • {trans['descricao']}: R$ {trans['valor']:.2f} ({trans['data']})\n"
        
        return formatted


openai_service = OpenAIService()