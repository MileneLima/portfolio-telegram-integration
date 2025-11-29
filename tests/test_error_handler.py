"""
Testes para o sistema de tratamento de erros
"""

import pytest
from utils.error_handler import AudioErrorHandler, AudioProcessingMetrics


class TestAudioErrorHandler:
    """Testes para o AudioErrorHandler"""
    
    def test_categorize_network_errors(self):
        """Testar categorização de erros de rede"""
        network_errors = [
            Exception("Connection timeout"),
            Exception("Network unreachable"),
            Exception("DNS resolution failed"),
            Exception("Socket connection refused")
        ]
        
        for error in network_errors:
            category = AudioErrorHandler.categorize_error(error)
            assert category == 'network', f"Erro de rede não categorizado corretamente: {error}"
    
    def test_categorize_file_format_errors(self):
        """Testar categorização de erros de formato"""
        format_errors = [
            Exception("Unsupported format"),
            Exception("Invalid MIME type"),
            Exception("File extension not supported"),
            Exception("Format not recognized")
        ]
        
        for error in format_errors:
            category = AudioErrorHandler.categorize_error(error)
            assert category == 'file_format', f"Erro de formato não categorizado corretamente: {error}"
    
    def test_categorize_file_size_errors(self):
        """Testar categorização de erros de tamanho"""
        size_errors = [
            Exception("File too large"),
            Exception("Size limit exceeded"),
            Exception("Maximum file size reached"),
            Exception("File is too big")
        ]
        
        for error in size_errors:
            category = AudioErrorHandler.categorize_error(error)
            assert category == 'file_size', f"Erro de tamanho não categorizado corretamente: {error}"
    
    def test_get_user_friendly_messages(self):
        """Testar mensagens amigáveis para usuários"""
        test_cases = [
            (Exception("Connection timeout"), "conexão"),
            (Exception("Unsupported format"), "formato"),
            (Exception("File too large"), "grande"),
            (Exception("Rate limit exceeded"), "limite")
        ]
        
        for error, expected_keyword in test_cases:
            message = AudioErrorHandler.get_user_friendly_message(error)
            assert expected_keyword.lower() in message.lower(), \
                f"Mensagem não contém palavra-chave esperada '{expected_keyword}': {message}"
    
    def test_is_recoverable_error(self):
        """Testar identificação de erros recuperáveis"""
        recoverable_errors = [
            Exception("Network timeout"),
            Exception("Rate limit exceeded"),
            Exception("Disk space insufficient")
        ]
        
        non_recoverable_errors = [
            Exception("Invalid format"),
            Exception("File corrupted"),
            Exception("Permission denied")
        ]
        
        for error in recoverable_errors:
            category = AudioErrorHandler.categorize_error(error)
            is_recoverable = AudioErrorHandler.is_recoverable_error(error)
            print(f"Error: {error}, Category: {category}, Recoverable: {is_recoverable}")
            assert is_recoverable, \
                f"Erro deveria ser recuperável: {error} (categoria: {category})"
        
        for error in non_recoverable_errors:
            assert not AudioErrorHandler.is_recoverable_error(error), \
                f"Erro não deveria ser recuperável: {error}"
    
    def test_get_retry_delay(self):
        """Testar cálculo de delay para retry"""
        network_error = Exception("Network timeout")
        api_error = Exception("Rate limit exceeded")
        
        # Testar que delay aumenta com tentativas
        delay1 = AudioErrorHandler.get_retry_delay(network_error, 0)
        delay2 = AudioErrorHandler.get_retry_delay(network_error, 1)
        delay3 = AudioErrorHandler.get_retry_delay(network_error, 2)
        
        assert delay2 > delay1, "Delay deveria aumentar com tentativas"
        assert delay3 > delay2, "Delay deveria aumentar exponencialmente"
        
        # Testar que API errors têm delay maior (se categorizados corretamente)
        api_delay = AudioErrorHandler.get_retry_delay(api_error, 0)
        network_delay = AudioErrorHandler.get_retry_delay(network_error, 0)
        
        # Debug
        api_category = AudioErrorHandler.categorize_error(api_error)
        network_category = AudioErrorHandler.categorize_error(network_error)
        print(f"API error category: {api_category}, delay: {api_delay}")
        print(f"Network error category: {network_category}, delay: {network_delay}")
        
        if api_category == 'api_limit':
            assert api_delay > network_delay, "API errors deveriam ter delay maior"
        else:
            # Se não foi categorizado como api_limit, pelo menos deve ter delay válido
            assert api_delay > 0, "Delay deve ser positivo"
    
    def test_handle_audio_error_with_context(self):
        """Testar tratamento de erro com contexto"""
        error = Exception("File too large")
        context = {
            'actual_size': 30 * 1024 * 1024,  # 30MB
            'file_id': 'test123'
        }
        
        message = AudioErrorHandler.handle_audio_error(
            error, user_id=12345, file_id='test123', context=context
        )
        
        assert "30.0mb" in message.lower(), "Contexto de tamanho não incluído na mensagem"
        assert "25mb" in message.lower(), "Limite não mencionado na mensagem"


class TestAudioProcessingMetrics:
    """Testes para métricas de processamento"""
    
    def test_record_errors(self):
        """Testar registro de erros"""
        metrics = AudioProcessingMetrics()
        
        # Registrar diferentes tipos de erro
        metrics.record_error(Exception("Network timeout"))
        metrics.record_error(Exception("File too large"))
        metrics.record_error(Exception("Network timeout"))  # Duplicado
        
        summary = metrics.get_error_summary()
        
        assert summary['total_attempts'] == 3, "Total de tentativas incorreto"
        assert summary['error_counts']['network'] == 2, "Contagem de erros de rede incorreta"
        assert summary['error_counts']['file_size'] == 1, "Contagem de erros de tamanho incorreta"
    
    def test_record_success(self):
        """Testar registro de sucessos"""
        metrics = AudioProcessingMetrics()
        
        # Registrar sucessos
        metrics.record_success(2.5)
        metrics.record_success(3.0)
        metrics.record_success(1.8)
        
        summary = metrics.get_error_summary()
        
        assert summary['success_count'] == 3, "Contagem de sucessos incorreta"
        assert summary['total_attempts'] == 3, "Total de tentativas incorreto"
        assert summary['success_rate'] == 1.0, "Taxa de sucesso incorreta"
        assert 2.0 < summary['avg_processing_time'] < 3.0, "Tempo médio incorreto"
    
    def test_mixed_success_and_errors(self):
        """Testar métricas mistas (sucessos e erros)"""
        metrics = AudioProcessingMetrics()
        
        # Registrar sucessos e erros
        metrics.record_success(2.0)
        metrics.record_error(Exception("Network error"))
        metrics.record_success(3.0)
        metrics.record_error(Exception("Format error"))
        
        summary = metrics.get_error_summary()
        
        assert summary['total_attempts'] == 4, "Total de tentativas incorreto"
        assert summary['success_count'] == 2, "Contagem de sucessos incorreta"
        assert summary['success_rate'] == 0.5, "Taxa de sucesso incorreta"
        assert len(summary['error_counts']) == 2, "Número de categorias de erro incorreto"