"""
Utilitário para tratamento robusto de erros do sistema de transcrição de áudio
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger


class AudioErrorHandler:
    """Classe para tratamento centralizado de erros de áudio"""
    
    # Categorias de erro
    ERROR_CATEGORIES = {
        'NETWORK': 'network',
        'FILE_FORMAT': 'file_format',
        'FILE_SIZE': 'file_size',
        'API_LIMIT': 'api_limit',
        'PERMISSION': 'permission',
        'DISK_SPACE': 'disk_space',
        'CORRUPTION': 'corruption',
        'VALIDATION': 'validation',
        'UNKNOWN': 'unknown'
    }
    
    # Mapeamento de palavras-chave para categorias
    ERROR_KEYWORDS = {
        'NETWORK': [
            'network', 'connection', 'timeout', 'internet', 'connectivity',
            'dns', 'socket', 'unreachable', 'refused'
        ],
        'FILE_FORMAT': [
            'format', 'extension', 'mime', 'type', 'unsupported',
            'invalid format', 'not supported'
        ],
        'FILE_SIZE': [
            'file too large', 'file size', 'size limit', 'maximum file size',
            'too big', 'too large', 'file is too big'
        ],
        'API_LIMIT': [
            'rate limit', 'quota', 'billing', 'rate limit exceeded',
            '429', 'too many requests'
        ],
        'PERMISSION': [
            'permission', 'access', 'denied', 'unauthorized', 'forbidden',
            '401', '403', 'authentication'
        ],
        'DISK_SPACE': [
            'disk', 'space', 'storage', 'full', 'no space',
            'insufficient space'
        ],
        'CORRUPTION': [
            'corrupt', 'corrupted', 'invalid', 'malformed', 'damaged',
            'broken', 'unreadable'
        ],
        'VALIDATION': [
            'validation', 'invalid', 'missing', 'empty', 'null',
            'required', 'mandatory'
        ]
    }
    
    # Mensagens de erro amigáveis
    ERROR_MESSAGES = {
        'NETWORK': "Erro de conexão. Verifique sua internet e tente novamente.",
        'FILE_FORMAT': "Formato de áudio não suportado. Use MP3, WAV, M4A ou WebM.",
        'FILE_SIZE': "Arquivo muito grande. O limite é 25MB. Tente dividir o áudio em partes menores.",
        'API_LIMIT': "Limite de requisições excedido. Aguarde alguns minutos antes de tentar novamente.",
        'PERMISSION': "Erro de permissão. Tente enviar o áudio novamente.",
        'DISK_SPACE': "Espaço em disco insuficiente no servidor. Tente novamente mais tarde.",
        'CORRUPTION': "Arquivo de áudio corrompido ou ilegível. Tente gravar novamente.",
        'VALIDATION': "Dados do áudio inválidos. Tente enviar o áudio novamente.",
        'UNKNOWN': "Erro inesperado. Tente novamente ou use mensagem de texto."
    }
    
    @classmethod
    def categorize_error(cls, error: Exception) -> str:
        """Categorizar erro baseado na mensagem"""
        error_msg = str(error).lower()
        
        # Verificar categorias em ordem de prioridade (mais específicas primeiro)
        priority_order = ['API_LIMIT', 'NETWORK', 'FILE_FORMAT', 'FILE_SIZE', 
                         'PERMISSION', 'DISK_SPACE', 'CORRUPTION', 'VALIDATION']
        
        for category in priority_order:
            keywords = cls.ERROR_KEYWORDS[category]
            if any(keyword in error_msg for keyword in keywords):
                return cls.ERROR_CATEGORIES[category]
        
        return cls.ERROR_CATEGORIES['UNKNOWN']
    
    @classmethod
    def get_user_friendly_message(cls, error: Exception, context: Optional[Dict[str, Any]] = None) -> str:
        """Obter mensagem amigável para o usuário"""
        category = cls.categorize_error(error)
        base_message = cls.ERROR_MESSAGES.get(category.upper(), cls.ERROR_MESSAGES['UNKNOWN'])
        
        # Adicionar contexto específico se disponível
        if context:
            if category == 'file_size' and 'actual_size' in context:
                actual_mb = context['actual_size'] / (1024 * 1024)
                base_message = f"Arquivo muito grande ({actual_mb:.1f}MB). O limite é 25MB. Tente dividir o áudio em partes menores."
            elif category == 'file_format' and 'mime_type' in context:
                base_message = f"Formato não suportado: {context['mime_type']}. Use MP3, WAV, M4A ou WebM."
        
        return base_message
    
    @classmethod
    def log_error(cls, error: Exception, context: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None):
        """Logar erro com contexto detalhado"""
        category = cls.categorize_error(error)
        
        log_data = {
            'error_category': category,
            'error_message': str(error),
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        # Log com nível apropriado baseado na categoria
        if category in ['network', 'api_limit']:
            logger.warning(f"⚠️ [{category.upper()}] {str(error)} | User: {user_id} | Context: {context}")
        elif category in ['corruption', 'validation', 'file_format']:
            logger.info(f"ℹ️ [{category.upper()}] {str(error)} | User: {user_id} | Context: {context}")
        else:
            logger.error(f"❌ [{category.upper()}] {str(error)} | User: {user_id} | Context: {context}")
    
    @classmethod
    def handle_audio_error(cls, error: Exception, user_id: Optional[int] = None, 
                          file_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> str:
        """Tratamento completo de erro de áudio"""
        
        # Preparar contexto
        full_context = context or {}
        if file_id:
            full_context['file_id'] = file_id
        
        # Logar erro
        cls.log_error(error, full_context, user_id)
        
        # Retornar mensagem amigável
        return cls.get_user_friendly_message(error, full_context)
    
    @classmethod
    def is_recoverable_error(cls, error: Exception) -> bool:
        """Verificar se o erro é recuperável (pode tentar novamente)"""
        category = cls.categorize_error(error)
        
        # Erros recuperáveis: network, api_limit, disk_space
        recoverable_categories = ['network', 'api_limit', 'disk_space']
        return category in recoverable_categories
    
    @classmethod
    def get_retry_delay(cls, error: Exception, attempt: int) -> float:
        """Calcular delay para retry baseado no tipo de erro"""
        category = cls.categorize_error(error)
        
        base_delays = {
            'network': 1.0,
            'api_limit': 5.0,
            'disk_space': 2.0,
            'unknown': 1.0
        }
        
        base_delay = base_delays.get(category, 1.0)
        
        # Backoff exponencial
        return base_delay * (2 ** attempt)


class AudioProcessingMetrics:
    """Classe para coletar métricas de processamento de áudio"""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.processing_times: Dict[str, float] = {}
        self.success_count = 0
        self.total_attempts = 0
    
    def record_error(self, error: Exception):
        """Registrar erro nas métricas"""
        category = AudioErrorHandler.categorize_error(error)
        self.error_counts[category] = self.error_counts.get(category, 0) + 1
        self.total_attempts += 1
    
    def record_success(self, processing_time: float):
        """Registrar sucesso nas métricas"""
        self.success_count += 1
        self.total_attempts += 1
        
        # Registrar tempo de processamento
        if processing_time > 0:
            times = self.processing_times.get('transcription', [])
            times.append(processing_time)
            self.processing_times['transcription'] = times[-100:]  # Manter últimas 100
    
    def get_success_rate(self) -> float:
        """Calcular taxa de sucesso"""
        if self.total_attempts == 0:
            return 0.0
        return self.success_count / self.total_attempts
    
    def get_average_processing_time(self) -> float:
        """Calcular tempo médio de processamento"""
        times = self.processing_times.get('transcription', [])
        if not times:
            return 0.0
        return sum(times) / len(times)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Obter resumo de erros"""
        return {
            'total_attempts': self.total_attempts,
            'success_count': self.success_count,
            'success_rate': self.get_success_rate(),
            'error_counts': self.error_counts.copy(),
            'avg_processing_time': self.get_average_processing_time()
        }


# Instância global para métricas
audio_metrics = AudioProcessingMetrics()