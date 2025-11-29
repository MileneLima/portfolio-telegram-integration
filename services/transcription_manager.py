"""
Gerenciador de transcrições pendentes
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Awaitable
from models.schemas import PendingTranscription


class TranscriptionManager:
    """Gerenciador de transcrições pendentes em memória"""
    
    def __init__(self):
        self._pending_transcriptions: Dict[str, PendingTranscription] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_started = False
        self._timeout_notification_callback: Optional[Callable[[PendingTranscription], Awaitable[None]]] = None
    
    def _start_cleanup_task(self):
        """Iniciar tarefa de limpeza automática"""
        if not self._cleanup_started:
            try:
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._cleanup_expired())
                    self._cleanup_started = True
            except RuntimeError:
                # Não há loop de eventos rodando, cleanup será iniciado quando necessário
                pass
    
    async def _cleanup_expired(self):
        """Limpar transcrições expiradas periodicamente"""
        while True:
            try:
                now = datetime.now()
                expired_transcriptions = [
                    transcription for transcription in self._pending_transcriptions.values()
                    if transcription.expires_at <= now
                ]
                
                # Notificar usuários sobre expiração antes de remover
                for transcription in expired_transcriptions:
                    if self._timeout_notification_callback:
                        try:
                            await self._timeout_notification_callback(transcription)
                        except Exception as e:
                            print(f"Erro ao notificar timeout para usuário {transcription.user_id}: {e}")
                    
                    # Remover transcrição expirada
                    if transcription.id in self._pending_transcriptions:
                        del self._pending_transcriptions[transcription.id]
                
                if expired_transcriptions:
                    print(f"Limpeza automática: {len(expired_transcriptions)} transcrições expiradas removidas")
                
                # Aguardar 1 minuto antes da próxima limpeza
                await asyncio.sleep(60)
                
            except Exception as e:
                print(f"Erro na limpeza automática de transcrições: {e}")
                await asyncio.sleep(60)
    
    def add_pending_transcription(self, user_id: int, message_id: int, transcribed_text: str, timeout_minutes: int = 5) -> str:
        """Adicionar transcrição pendente"""
        # Tentar iniciar cleanup se ainda não foi iniciado
        if not self._cleanup_started:
            self._start_cleanup_task()
            
        transcription = PendingTranscription.create_with_timeout(
            user_id=user_id,
            message_id=message_id,
            transcribed_text=transcribed_text,
            timeout_minutes=timeout_minutes
        )
        
        self._pending_transcriptions[transcription.id] = transcription
        return transcription.id
    
    def get_pending_transcription(self, transcription_id: str) -> Optional[PendingTranscription]:
        """Obter transcrição pendente por ID"""
        transcription = self._pending_transcriptions.get(transcription_id)
        
        # Verificar se não expirou
        if transcription and transcription.expires_at <= datetime.now():
            del self._pending_transcriptions[transcription_id]
            return None
        
        return transcription
    
    def remove_pending_transcription(self, transcription_id: str) -> bool:
        """Remover transcrição pendente"""
        if transcription_id in self._pending_transcriptions:
            del self._pending_transcriptions[transcription_id]
            return True
        return False
    
    def get_user_pending_transcriptions(self, user_id: int) -> list[PendingTranscription]:
        """Obter todas as transcrições pendentes de um usuário"""
        now = datetime.now()
        user_transcriptions = []
        
        for transcription in self._pending_transcriptions.values():
            if transcription.user_id == user_id and transcription.expires_at > now:
                user_transcriptions.append(transcription)
        
        return user_transcriptions
    
    def cleanup_user_transcriptions(self, user_id: int) -> int:
        """Limpar todas as transcrições pendentes de um usuário"""
        removed_count = 0
        transcription_ids_to_remove = []
        
        for transcription_id, transcription in self._pending_transcriptions.items():
            if transcription.user_id == user_id:
                transcription_ids_to_remove.append(transcription_id)
        
        for transcription_id in transcription_ids_to_remove:
            del self._pending_transcriptions[transcription_id]
            removed_count += 1
        
        return removed_count
    
    def get_stats(self) -> dict:
        """Obter estatísticas do gerenciador"""
        now = datetime.now()
        active_count = sum(1 for t in self._pending_transcriptions.values() if t.expires_at > now)
        expired_count = sum(1 for t in self._pending_transcriptions.values() if t.expires_at <= now)
        
        return {
            "total_pending": len(self._pending_transcriptions),
            "active": active_count,
            "expired": expired_count,
            "cleanup_task_running": self._cleanup_task and not self._cleanup_task.done()
        }
    
    def set_timeout_notification_callback(self, callback: Callable[[PendingTranscription], Awaitable[None]]):
        """Definir callback para notificação de timeout"""
        self._timeout_notification_callback = callback
    
    async def shutdown(self):
        """Encerrar o gerenciador"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self._pending_transcriptions.clear()


# Instância global do gerenciador
transcription_manager = TranscriptionManager()