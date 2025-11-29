"""
Serviço para processamento de arquivos de áudio
"""

import os
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from loguru import logger
import aiofiles
from telegram import File

from config.settings import get_settings
from models.schemas import AudioMessage, AudioProcessingStatus
from utils.error_handler import AudioErrorHandler, audio_metrics


class AudioService:
    """Serviço para download e processamento de arquivos de áudio"""
    
    # Formatos suportados pela API Whisper
    SUPPORTED_FORMATS = ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm', 'ogg', 'oga', 'opus']
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
    MAX_DURATION = 600  # 10 minutos
    
    def __init__(self):
        self.settings = get_settings()
        self.temp_dir = Path(tempfile.gettempdir()) / "audio_files"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Sistema de fila para processamento sequencial
        self._processing_queue: Dict[int, List[AudioMessage]] = {}  # user_id -> lista de áudios
        self._queue_locks: Dict[int, asyncio.Lock] = {}  # user_id -> lock
        self._processing_status: Dict[str, AudioProcessingStatus] = {}  # file_id -> status
        
        # Configurações de rate limiting
        self.MAX_QUEUE_SIZE = 10  # Por usuário
        self.MAX_REQUESTS_PER_MINUTE = 5  # Por usuário
        self._user_request_counts: Dict[int, List[datetime]] = {}  # user_id -> timestamps
        
        # Configurações de limpeza
        self.CLEANUP_INTERVAL = 3600  # 1 hora
        self.MAX_TEMP_FILE_AGE = 1800  # 30 minutos
        self.MIN_FREE_SPACE = 1024 * 1024 * 1024  # 1GB
        
        # Iniciar tarefa de limpeza automática
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Iniciar tarefa de limpeza automática"""
        try:
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        except RuntimeError:
            # Não há loop de eventos rodando, cleanup será iniciado quando necessário
            pass
    
    async def _periodic_cleanup(self):
        """Limpeza periódica de arquivos temporários"""
        while True:
            try:
                await self.cleanup_temp_files()
                await asyncio.sleep(self.CLEANUP_INTERVAL)
            except Exception as e:
                logger.error(f"Erro na limpeza periódica: {e}")
                await asyncio.sleep(60)  # Tentar novamente em 1 minuto
    
    async def download_audio_file(self, telegram_file: File, audio_message: AudioMessage) -> str:
        """
        Baixar arquivo de áudio do Telegram
        
        Args:
            telegram_file: Objeto File do Telegram
            audio_message: Dados da mensagem de áudio
            
        Returns:
            Caminho do arquivo baixado
            
        Raises:
            Exception: Se houver erro no download ou validação
        """
        try:
            # Verificar rate limiting
            if not self._check_rate_limit(audio_message.user_id):
                raise Exception("Limite de requisições por minuto excedido. Tente novamente em alguns instantes.")
            
            # Validar arquivo antes do download
            await self._validate_audio_message(audio_message)
            
            # Gerar nome único para o arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = self._get_file_extension(audio_message.mime_type)
            filename = f"audio_{audio_message.user_id}_{timestamp}_{audio_message.file_id[:8]}.{file_extension}"
            file_path = self.temp_dir / filename
            
            # Atualizar status
            self._processing_status[audio_message.file_id] = AudioProcessingStatus.DOWNLOADING
            
            logger.info(f"📥 Baixando áudio: {filename} ({audio_message.file_size} bytes)")
            
            # Baixar arquivo
            await telegram_file.download_to_drive(str(file_path))
            
            # Verificar se o arquivo foi baixado corretamente
            if not file_path.exists():
                raise Exception("Falha no download do arquivo")
            
            # Verificar tamanho do arquivo baixado
            actual_size = file_path.stat().st_size
            if actual_size != audio_message.file_size:
                await self.cleanup_temp_file(str(file_path))
                raise Exception(f"Tamanho do arquivo inconsistente: esperado {audio_message.file_size}, obtido {actual_size}")
            
            # Validar formato do arquivo baixado
            if not await self._validate_audio_format(str(file_path)):
                await self.cleanup_temp_file(str(file_path))
                raise Exception("Formato de áudio não suportado ou arquivo corrompido")
            
            logger.info(f"✅ Áudio baixado com sucesso: {filename}")
            return str(file_path)
            
        except Exception as e:
            self._processing_status[audio_message.file_id] = AudioProcessingStatus.FAILED
            
            # Usar error handler para tratamento robusto
            context = {
                'file_id': audio_message.file_id,
                'file_size': audio_message.file_size,
                'operation': 'download'
            }
            
            # Registrar erro nas métricas
            audio_metrics.record_error(e)
            
            # Obter mensagem amigável e logar
            user_friendly_msg = AudioErrorHandler.handle_audio_error(
                e, audio_message.user_id, audio_message.file_id, context
            )
            
            raise Exception(user_friendly_msg)
    
    async def _validate_audio_message(self, audio_message: AudioMessage) -> None:
        """Validar mensagem de áudio antes do processamento"""
        
        # Verificar se os dados básicos são válidos
        if not audio_message.file_id or len(audio_message.file_id.strip()) == 0:
            raise Exception("ID do arquivo inválido. Tente enviar o áudio novamente.")
        
        if audio_message.file_size <= 0:
            raise Exception("Tamanho do arquivo inválido. Tente enviar o áudio novamente.")
        
        if audio_message.duration <= 0:
            raise Exception("Duração do áudio inválida. Certifique-se de que o áudio não está vazio.")
        
        # Verificar tamanho do arquivo
        if audio_message.file_size > self.MAX_FILE_SIZE:
            size_mb = audio_message.file_size / (1024 * 1024)
            max_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            raise Exception(f"Arquivo muito grande ({size_mb:.1f}MB). Limite máximo: {max_mb}MB. Tente dividir o áudio em partes menores.")
        
        # Verificar duração
        if audio_message.duration > self.MAX_DURATION:
            duration_min = audio_message.duration / 60
            max_min = self.MAX_DURATION / 60
            raise Exception(f"Áudio muito longo ({duration_min:.1f} min). Limite máximo: {max_min} minutos. Tente gravar um áudio mais curto.")
        
        # Verificar formato MIME
        if not audio_message.mime_type or not self._is_supported_mime_type(audio_message.mime_type):
            supported_formats_str = ', '.join(self.SUPPORTED_FORMATS)
            raise Exception(f"Formato não suportado: {audio_message.mime_type or 'desconhecido'}. Formatos aceitos: {supported_formats_str}")
        
        # Verificar espaço em disco
        if not self._check_disk_space():
            raise Exception("Espaço em disco insuficiente no servidor. Tente novamente mais tarde.")
        
        # Verificar se a duração é razoável em relação ao tamanho
        # Áudios muito pequenos para a duração podem indicar problemas
        min_expected_size = audio_message.duration * 1000  # ~1KB por segundo (muito conservador)
        if audio_message.file_size < min_expected_size:
            logger.warning(f"⚠️ Áudio suspeito: {audio_message.file_size} bytes para {audio_message.duration}s")
            # Não bloquear, apenas logar o aviso
    
    async def _validate_audio_format(self, file_path: str) -> bool:
        """Validar formato do arquivo de áudio baixado"""
        try:
            # Verificar se o arquivo existe
            if not os.path.exists(file_path):
                return False
            
            # Verificar extensão do arquivo
            file_extension = Path(file_path).suffix.lower().lstrip('.')
            if file_extension not in self.SUPPORTED_FORMATS:
                return False
            
            # Verificar se o arquivo não está vazio
            if os.path.getsize(file_path) == 0:
                return False
            
            # Verificação rigorosa de cabeçalho do arquivo
            async with aiofiles.open(file_path, 'rb') as f:
                header = await f.read(16)  # Ler mais bytes para validação
                
                # Verificar assinaturas de arquivo conhecidas
                if len(header) < 4:
                    return False
                
                # MP3 - verificação mais rigorosa
                if file_extension in ['mp3', 'mpeg', 'mpga']:
                    # ID3v2 header ou MPEG frame sync
                    if header[:3] == b'ID3':
                        # Verificar versão ID3 válida
                        if len(header) >= 5 and header[3] <= 4 and header[4] <= 9:
                            return True
                    elif header[:2] == b'\xff\xfb' or header[:2] == b'\xff\xfa':
                        # MPEG frame sync válido
                        return True
                    else:
                        return False
                
                # WAV - verificação mais rigorosa
                elif file_extension in ['wav', 'wave']:
                    if (header[:4] == b'RIFF' and 
                        len(header) >= 12 and 
                        header[8:12] == b'WAVE'):
                        return True
                    else:
                        return False
                
                # MP4/M4A - verificação mais rigorosa
                elif file_extension in ['mp4', 'm4a']:
                    # Procurar por 'ftyp' box em posições válidas
                    if (len(header) >= 8 and 
                        (header[4:8] == b'ftyp' or b'ftyp' in header[:12])):
                        return True
                    else:
                        return False
                
                # WebM - verificação mais rigorosa
                elif file_extension == 'webm':
                    if header[:4] == b'\x1a\x45\xdf\xa3':
                        return True
                    else:
                        return False
                
                # OGG/Opus - verificação mais rigorosa
                elif file_extension in ['ogg', 'oga', 'opus']:
                    if header[:4] == b'OggS':
                        return True
                    else:
                        return False
                
                # Se chegou aqui, formato não reconhecido
                return False
                
        except Exception as e:
            logger.error(f"Erro ao validar formato de áudio: {e}")
            return False
    
    def _is_supported_mime_type(self, mime_type: str) -> bool:
        """Verificar se o tipo MIME é suportado"""
        supported_mimes = [
            'audio/mpeg', 'audio/mp3',
            'audio/mp4', 'audio/m4a',
            'audio/wav', 'audio/wave',
            'audio/webm',
            'audio/ogg', 'audio/opus',  # Mensagens de voz do Telegram
            'video/mp4'  # Telegram às vezes envia áudio como video/mp4
        ]
        return mime_type.lower() in supported_mimes
    
    def _get_file_extension(self, mime_type: str) -> str:
        """Obter extensão de arquivo baseada no tipo MIME"""
        mime_to_ext = {
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/mp4': 'm4a',
            'audio/m4a': 'm4a',
            'audio/wav': 'wav',
            'audio/wave': 'wav',
            'audio/webm': 'webm',
            'audio/ogg': 'ogg',
            'audio/opus': 'ogg',
            'video/mp4': 'mp4'
        }
        return mime_to_ext.get(mime_type.lower(), 'mp3')
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Verificar limite de requisições por usuário"""
        try:
            now = datetime.now()
            
            # Inicializar lista se não existir
            if user_id not in self._user_request_counts:
                self._user_request_counts[user_id] = []
            
            # Remover requisições antigas (mais de 1 minuto)
            cutoff_time = now - timedelta(minutes=1)
            old_count = len(self._user_request_counts[user_id])
            self._user_request_counts[user_id] = [
                timestamp for timestamp in self._user_request_counts[user_id]
                if timestamp > cutoff_time
            ]
            new_count = len(self._user_request_counts[user_id])
            
            if old_count != new_count:
                logger.debug(f"🧹 Limpeza rate limit usuário {user_id}: {old_count} -> {new_count} requisições")
            
            # Verificar se excedeu o limite
            current_requests = len(self._user_request_counts[user_id])
            if current_requests >= self.MAX_REQUESTS_PER_MINUTE:
                logger.warning(f"⚠️ Rate limit excedido para usuário {user_id}: {current_requests}/{self.MAX_REQUESTS_PER_MINUTE}")
                return False
            
            # Adicionar requisição atual
            self._user_request_counts[user_id].append(now)
            logger.debug(f"✅ Rate limit OK para usuário {user_id}: {current_requests + 1}/{self.MAX_REQUESTS_PER_MINUTE}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar rate limit para usuário {user_id}: {e}")
            # Em caso de erro, permitir a requisição (fail-safe)
            return True
    
    def _check_disk_space(self) -> bool:
        """Verificar espaço disponível em disco"""
        try:
            statvfs = os.statvfs(self.temp_dir)
            free_space = statvfs.f_frsize * statvfs.f_bavail
            return free_space > self.MIN_FREE_SPACE
        except Exception:
            # Se não conseguir verificar, assumir que há espaço
            return True
    
    async def add_to_queue(self, audio_message: AudioMessage) -> int:
        """
        Adicionar áudio à fila de processamento
        
        Returns:
            Posição na fila (0 = processando agora)
        """
        user_id = audio_message.user_id
        
        try:
            # Inicializar estruturas se necessário
            if user_id not in self._processing_queue:
                self._processing_queue[user_id] = []
                logger.debug(f"📋 Criada nova fila para usuário {user_id}")
            if user_id not in self._queue_locks:
                self._queue_locks[user_id] = asyncio.Lock()
            
            async with self._queue_locks[user_id]:
                # Verificar limite da fila
                current_queue_size = len(self._processing_queue[user_id])
                if current_queue_size >= self.MAX_QUEUE_SIZE:
                    logger.warning(f"⚠️ Fila cheia para usuário {user_id}: {current_queue_size}/{self.MAX_QUEUE_SIZE}")
                    raise Exception(f"Fila de processamento cheia ({current_queue_size}/{self.MAX_QUEUE_SIZE}). Aguarde o processamento dos áudios anteriores.")
                
                # Adicionar à fila
                self._processing_queue[user_id].append(audio_message)
                position = len(self._processing_queue[user_id]) - 1
                
                logger.info(f"📋 Áudio {audio_message.file_id[:8]}... adicionado à fila do usuário {user_id}. Posição: {position}")
                return position
                
        except Exception as e:
            logger.error(f"❌ Erro ao adicionar áudio à fila do usuário {user_id}: {e}")
            raise
    
    async def process_queue(self, user_id: int) -> None:
        """Processar fila de áudios de um usuário"""
        if user_id not in self._queue_locks:
            return
        
        async with self._queue_locks[user_id]:
            while self._processing_queue.get(user_id, []):
                audio_message = self._processing_queue[user_id].pop(0)
                
                try:
                    # Aqui seria chamado o processamento real do áudio
                    # Por enquanto, apenas simular o processamento
                    self._processing_status[audio_message.file_id] = AudioProcessingStatus.TRANSCRIBING
                    
                    logger.info(f"🎵 Processando áudio {audio_message.file_id} do usuário {user_id}")
                    
                    # Simular tempo de processamento
                    await asyncio.sleep(0.1)
                    
                    self._processing_status[audio_message.file_id] = AudioProcessingStatus.COMPLETED
                    
                except Exception as e:
                    logger.error(f"❌ Erro ao processar áudio {audio_message.file_id}: {e}")
                    self._processing_status[audio_message.file_id] = AudioProcessingStatus.FAILED
    
    def get_queue_position(self, user_id: int, file_id: str) -> Optional[int]:
        """Obter posição na fila de um áudio específico"""
        if user_id not in self._processing_queue:
            return None
        
        for i, audio_message in enumerate(self._processing_queue[user_id]):
            if audio_message.file_id == file_id:
                return i
        
        return None
    
    def get_processing_status(self, file_id: str) -> Optional[AudioProcessingStatus]:
        """Obter status de processamento de um áudio"""
        return self._processing_status.get(file_id)
    
    async def cleanup_temp_file(self, file_path: str) -> None:
        """Limpar arquivo temporário específico"""
        try:
            if os.path.exists(file_path):
                # Verificar se o arquivo não está sendo usado
                try:
                    # Tentar abrir o arquivo para verificar se está em uso
                    with open(file_path, 'r+b'):
                        pass
                except (PermissionError, OSError) as e:
                    logger.warning(f"⚠️ Arquivo em uso, tentando novamente: {file_path}")
                    await asyncio.sleep(0.1)  # Aguardar um pouco
                
                os.remove(file_path)
                logger.debug(f"🗑️ Arquivo temporário removido: {file_path}")
        except PermissionError as e:
            logger.warning(f"⚠️ Sem permissão para remover arquivo temporário {file_path}: {e}")
        except FileNotFoundError:
            # Arquivo já foi removido, não é um erro
            logger.debug(f"📁 Arquivo temporário já removido: {file_path}")
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao remover arquivo temporário {file_path}: {e}")
    
    async def cleanup_temp_files(self) -> int:
        """
        Limpar arquivos temporários antigos
        
        Returns:
            Número de arquivos removidos
        """
        removed_count = 0
        cutoff_time = datetime.now() - timedelta(seconds=self.MAX_TEMP_FILE_AGE)
        
        try:
            for file_path in self.temp_dir.glob("audio_*"):
                try:
                    # Verificar idade do arquivo
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    if file_mtime < cutoff_time:
                        file_path.unlink()
                        removed_count += 1
                        logger.debug(f"🗑️ Arquivo antigo removido: {file_path.name}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao processar arquivo {file_path}: {e}")
            
            if removed_count > 0:
                logger.info(f"🧹 Limpeza automática: {removed_count} arquivos temporários removidos")
                
        except Exception as e:
            logger.error(f"❌ Erro na limpeza de arquivos temporários: {e}")
        
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do serviço"""
        total_queued = sum(len(queue) for queue in self._processing_queue.values())
        
        status_counts = {}
        for status in self._processing_status.values():
            status_counts[status.value] = status_counts.get(status.value, 0) + 1
        
        temp_files_count = len(list(self.temp_dir.glob("audio_*")))
        
        return {
            "total_queued_audios": total_queued,
            "active_users": len(self._processing_queue),
            "processing_status_counts": status_counts,
            "temp_files_count": temp_files_count,
            "temp_dir_path": str(self.temp_dir),
            "cleanup_task_running": self._cleanup_task and not self._cleanup_task.done()
        }
    
    async def shutdown(self) -> None:
        """Encerrar o serviço de áudio"""
        # Cancelar tarefa de limpeza
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Limpar filas
        self._processing_queue.clear()
        self._processing_status.clear()
        self._user_request_counts.clear()
        
        # Limpeza final de arquivos temporários
        await self.cleanup_temp_files()
        
        logger.info("🔌 AudioService encerrado")


# Instância global do serviço
audio_service = AudioService()