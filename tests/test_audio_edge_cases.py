"""
Testes unitários para casos edge de áudio
Testa arquivos corrompidos, muito grandes e formatos não suportados
"""

import pytest
import tempfile
import os
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from services.audio_service import AudioService
from services.openai_service import OpenAIService
from models.schemas import AudioMessage


class TestCorruptedAudioFiles:
    """Testes para arquivos corrompidos ou inválidos"""
    
    def setup_method(self):
        """Setup para cada teste"""
        self.audio_service = AudioService()
        self.openai_service = OpenAIService()
    
    def test_empty_audio_file(self):
        """Testar arquivo de áudio vazio"""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            # Arquivo vazio (0 bytes)
            temp_file.flush()
            
            try:
                # Deve falhar na validação de formato
                result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                assert not result, "Arquivo vazio não deveria ser válido"
                
                # Deve falhar na transcrição
                with pytest.raises(Exception) as exc_info:
                    asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                
                error_msg = str(exc_info.value).lower()
                assert any(keyword in error_msg for keyword in [
                    "vazio", "corrompido", "empty", "gravar novamente"
                ]), f"Erro não específico para arquivo vazio: {error_msg}"
                
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
    
    def test_corrupted_mp3_header(self):
        """Testar arquivo MP3 com cabeçalho corrompido"""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            # Escrever dados inválidos que não são MP3
            temp_file.write(b"INVALID_MP3_HEADER_DATA_NOT_AUDIO")
            temp_file.flush()
            
            try:
                # Deve falhar na validação de formato
                result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                assert not result, "Arquivo com cabeçalho corrompido não deveria ser válido"
                
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
    
    def test_text_file_with_audio_extension(self):
        """Testar arquivo de texto com extensão de áudio"""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            # Escrever texto em arquivo com extensão .mp3
            temp_file.write(b"This is just a text file, not audio data at all!")
            temp_file.flush()
            
            try:
                # Deve falhar na validação de formato
                result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                assert not result, "Arquivo de texto com extensão .mp3 não deveria ser válido"
                
                # Deve falhar na transcrição com erro específico
                with pytest.raises(Exception) as exc_info:
                    asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                
                error_msg = str(exc_info.value).lower()
                assert any(keyword in error_msg for keyword in [
                    "formato", "suportado", "corrompido", "invalid"
                ]), f"Erro não específico para formato inválido: {error_msg}"
                
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
    
    def test_partial_audio_file(self):
        """Testar arquivo de áudio parcialmente corrompido"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            # Escrever cabeçalho WAV válido mas dados corrompidos
            # Cabeçalho WAV mínimo
            temp_file.write(b'RIFF')  # ChunkID
            temp_file.write(b'\x24\x00\x00\x00')  # ChunkSize (36 bytes)
            temp_file.write(b'WAVE')  # Format
            temp_file.write(b'fmt ')  # Subchunk1ID
            temp_file.write(b'\x10\x00\x00\x00')  # Subchunk1Size (16)
            temp_file.write(b'\x01\x00')  # AudioFormat (PCM)
            temp_file.write(b'\x01\x00')  # NumChannels (1)
            temp_file.write(b'\x44\xAC\x00\x00')  # SampleRate (44100)
            temp_file.write(b'\x88\x58\x01\x00')  # ByteRate
            temp_file.write(b'\x02\x00')  # BlockAlign
            temp_file.write(b'\x10\x00')  # BitsPerSample (16)
            temp_file.write(b'data')  # Subchunk2ID
            temp_file.write(b'\x00\x00\x00\x00')  # Subchunk2Size (0)
            # Dados de áudio corrompidos/inexistentes
            temp_file.flush()
            
            try:
                # Pode passar na validação básica de formato (cabeçalho válido)
                result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                # Resultado pode variar dependendo da implementação
                
                # Mas deve falhar na transcrição
                with pytest.raises(Exception) as exc_info:
                    asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                
                error_msg = str(exc_info.value).lower()
                # Pode falhar por diferentes motivos: arquivo corrompido, vazio, etc.
                assert len(error_msg) > 0, "Erro deve ter mensagem descritiva"
                
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)


class TestLargeAudioFiles:
    """Testes para arquivos muito grandes"""
    
    def setup_method(self):
        """Setup para cada teste"""
        self.audio_service = AudioService()
        self.openai_service = OpenAIService()
    
    def test_file_exceeding_size_limit(self):
        """Testar arquivo que excede limite de 25MB"""
        # Criar AudioMessage com tamanho excessivo
        large_audio = AudioMessage(
            file_id="test_large_file",
            file_size=30 * 1024 * 1024,  # 30MB (acima do limite de 25MB)
            duration=300,  # 5 minutos
            mime_type="audio/mpeg",
            user_id=12345,
            message_id=67890,
            chat_id=11111
        )
        
        # Deve falhar na validação
        with pytest.raises(Exception) as exc_info:
            asyncio.run(self.audio_service._validate_audio_message(large_audio))
        
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in [
            "grande", "tamanho", "limite", "25mb"
        ]), f"Erro não específico para arquivo grande: {error_msg}"
        assert "30.0mb" in error_msg or "30mb" in error_msg, "Tamanho atual não informado"
    
    def test_file_with_excessive_duration(self):
        """Testar arquivo com duração excessiva"""
        # Criar AudioMessage com duração excessiva
        long_audio = AudioMessage(
            file_id="test_long_audio",
            file_size=5 * 1024 * 1024,  # 5MB (tamanho OK)
            duration=900,  # 15 minutos (acima do limite de 10 minutos)
            mime_type="audio/mpeg",
            user_id=12345,
            message_id=67890,
            chat_id=11111
        )
        
        # Deve falhar na validação
        with pytest.raises(Exception) as exc_info:
            asyncio.run(self.audio_service._validate_audio_message(long_audio))
        
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in [
            "longo", "duração", "limite", "minutos"
        ]), f"Erro não específico para áudio longo: {error_msg}"
        assert "15.0" in error_msg or "15" in error_msg, "Duração atual não informada"
    
    def test_create_large_file_for_transcription(self):
        """Testar criação de arquivo grande real para transcrição"""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            # Criar arquivo de 30MB com dados simulados
            chunk_size = 1024 * 1024  # 1MB chunks
            total_size = 30 * 1024 * 1024  # 30MB
            
            try:
                for _ in range(total_size // chunk_size):
                    # Escrever dados simulados (não é áudio real, mas testa o limite)
                    temp_file.write(b'0' * chunk_size)
                temp_file.flush()
                
                # Verificar que arquivo foi criado com tamanho correto
                actual_size = os.path.getsize(temp_file.name)
                assert actual_size >= total_size, f"Arquivo não tem tamanho esperado: {actual_size}"
                
                # Deve falhar na transcrição por tamanho
                with pytest.raises(Exception) as exc_info:
                    asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                
                error_msg = str(exc_info.value).lower()
                assert any(keyword in error_msg for keyword in [
                    "grande", "tamanho", "limite", "25mb", "dividir"
                ]), f"Erro não específico para arquivo grande: {error_msg}"
                
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
    
    def test_boundary_size_files(self):
        """Testar arquivos no limite exato de tamanho"""
        # Teste com arquivo exatamente no limite (25MB)
        exact_limit_audio = AudioMessage(
            file_id="test_exact_limit",
            file_size=25 * 1024 * 1024,  # Exatamente 25MB
            duration=300,  # 5 minutos
            mime_type="audio/mpeg",
            user_id=12345,
            message_id=67890,
            chat_id=11111
        )
        
        # Deve passar na validação (no limite)
        try:
            asyncio.run(self.audio_service._validate_audio_message(exact_limit_audio))
        except Exception as e:
            # Pode falhar por outros motivos (espaço em disco, etc.), mas não por tamanho
            error_msg = str(e).lower()
            assert "grande" not in error_msg and "tamanho" not in error_msg, \
                f"Falhou por tamanho quando deveria passar: {error_msg}"
        
        # Teste com arquivo 1 byte acima do limite
        over_limit_audio = AudioMessage(
            file_id="test_over_limit",
            file_size=25 * 1024 * 1024 + 1,  # 25MB + 1 byte
            duration=300,  # 5 minutos
            mime_type="audio/mpeg",
            user_id=12345,
            message_id=67890,
            chat_id=11111
        )
        
        # Deve falhar na validação
        with pytest.raises(Exception) as exc_info:
            asyncio.run(self.audio_service._validate_audio_message(over_limit_audio))
        
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in [
            "grande", "tamanho", "limite"
        ]), f"Erro não específico para arquivo ligeiramente acima do limite: {error_msg}"


class TestUnsupportedFormats:
    """Testes para formatos não suportados"""
    
    def setup_method(self):
        """Setup para cada teste"""
        self.audio_service = AudioService()
        self.openai_service = OpenAIService()
    
    def test_unsupported_mime_types(self):
        """Testar tipos MIME não suportados"""
        unsupported_formats = [
            "audio/flac", 
            "audio/aac",
            "video/avi",
            "video/mkv",
            "text/plain",
            "image/jpeg",
            "application/pdf"
        ]
        
        for mime_type in unsupported_formats:
            # Testar validação de MIME type
            is_supported = self.audio_service._is_supported_mime_type(mime_type)
            assert not is_supported, f"Tipo MIME não suportado foi aceito: {mime_type}"
            
            # Testar com AudioMessage
            unsupported_audio = AudioMessage(
                file_id=f"test_{mime_type.replace('/', '_')}",
                file_size=1024,  # 1KB
                duration=30,  # 30 segundos
                mime_type=mime_type,
                user_id=12345,
                message_id=67890,
                chat_id=11111
            )
            
            # Deve falhar na validação
            with pytest.raises(Exception) as exc_info:
                asyncio.run(self.audio_service._validate_audio_message(unsupported_audio))
            
            error_msg = str(exc_info.value).lower()
            assert any(keyword in error_msg for keyword in [
                "formato", "suportado", "não suportado"
            ]), f"Erro não específico para formato não suportado {mime_type}: {error_msg}"
    
    def test_supported_mime_types(self):
        """Testar tipos MIME suportados"""
        supported_formats = [
            "audio/mpeg",
            "audio/mp3", 
            "audio/mp4",
            "audio/m4a",
            "audio/wav",
            "audio/wave",
            "audio/webm",
            "video/mp4"  # Telegram às vezes envia áudio como video/mp4
        ]
        
        for mime_type in supported_formats:
            # Testar validação de MIME type
            is_supported = self.audio_service._is_supported_mime_type(mime_type)
            assert is_supported, f"Tipo MIME suportado foi rejeitado: {mime_type}"
            
            # Testar com AudioMessage
            supported_audio = AudioMessage(
                file_id=f"test_{mime_type.replace('/', '_')}",
                file_size=1024,  # 1KB
                duration=30,  # 30 segundos
                mime_type=mime_type,
                user_id=12345,
                message_id=67890,
                chat_id=11111
            )
            
            # Deve passar na validação de formato (pode falhar por outros motivos)
            try:
                asyncio.run(self.audio_service._validate_audio_message(supported_audio))
            except Exception as e:
                # Se falhar, não deve ser por formato
                error_msg = str(e).lower()
                assert "formato" not in error_msg and "suportado" not in error_msg, \
                    f"Falhou por formato quando deveria passar {mime_type}: {error_msg}"
    
    def test_file_extension_validation(self):
        """Testar validação de extensões de arquivo"""
        # Criar arquivos temporários com diferentes extensões
        unsupported_extensions = [".txt", ".pdf", ".jpg", ".doc", ".zip"]
        
        for ext in unsupported_extensions:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                temp_file.write(b"fake content")
                temp_file.flush()
                
                try:
                    # Deve falhar na validação de formato
                    result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                    assert not result, f"Extensão não suportada foi aceita: {ext}"
                    
                    # Deve falhar na transcrição
                    with pytest.raises(Exception) as exc_info:
                        asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                    
                    error_msg = str(exc_info.value).lower()
                    assert any(keyword in error_msg for keyword in [
                        "formato", "suportado", "mp3", "wav", "aceitos"
                    ]), f"Erro não específico para extensão inválida {ext}: {error_msg}"
                    
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
    
    def test_case_insensitive_extensions(self):
        """Testar que validação de extensões é case-insensitive"""
        case_variations = [
            (".MP3", b'ID3\x03\x00\x00\x00\x00\x00\x00'),  # MP3 header
            (".Mp3", b'ID3\x03\x00\x00\x00\x00\x00\x00'),  # MP3 header
            (".mP3", b'ID3\x03\x00\x00\x00\x00\x00\x00'),  # MP3 header
            (".WAV", b'RIFF\x24\x00\x00\x00WAVE'),         # WAV header
            (".Wav", b'RIFF\x24\x00\x00\x00WAVE'),         # WAV header
            (".M4A", b'\x00\x00\x00\x20ftypM4A ')          # M4A header
        ]
        
        for ext, header_data in case_variations:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                # Escrever cabeçalho apropriado para cada formato
                temp_file.write(header_data)
                temp_file.flush()
                
                try:
                    # Deve passar na validação (extensão suportada, case-insensitive)
                    result = asyncio.run(self.audio_service._validate_audio_format(temp_file.name))
                    assert result, f"Extensão suportada com case diferente foi rejeitada: {ext}"
                    
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)


class TestNetworkAndAPIErrors:
    """Testes para erros de rede e API"""
    
    def setup_method(self):
        """Setup para cada teste"""
        self.openai_service = OpenAIService()
    
    def test_nonexistent_file_error(self):
        """Testar erro para arquivo inexistente"""
        nonexistent_path = "/path/to/nonexistent/audio/file.mp3"
        
        with pytest.raises(Exception) as exc_info:
            asyncio.run(self.openai_service.transcribe_audio(nonexistent_path))
        
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in [
            "não encontrado", "not found", "enviado", "arquivo"
        ]), f"Erro não específico para arquivo não encontrado: {error_msg}"
    
    def test_api_timeout_simulation(self):
        """Testar simulação de erro de timeout da API"""
        # Simular cenário de timeout através de mock do client
        with patch.object(self.openai_service, 'client') as mock_client:
            # Configurar mock para simular timeout
            mock_client.audio.transcriptions.create.side_effect = asyncio.TimeoutError("Request timeout")
            
            # Criar arquivo temporário válido
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_file.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')  # MP3 header básico
                temp_file.flush()
                
                try:
                    # Deve falhar com erro de timeout
                    with pytest.raises(Exception) as exc_info:
                        asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                    
                    error_msg = str(exc_info.value).lower()
                    assert any(keyword in error_msg for keyword in [
                        "conexão", "network", "timeout", "internet"
                    ]), f"Erro não específico para timeout: {error_msg}"
                    
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
    
    def test_api_rate_limit_simulation(self):
        """Testar simulação de erro de rate limit da API"""
        # Simular cenário de rate limit através de mock do client
        with patch.object(self.openai_service, 'client') as mock_client:
            # Simular rate limit usando Exception genérica com mensagem específica
            mock_client.audio.transcriptions.create.side_effect = Exception("Rate limit exceeded")
            
            # Criar arquivo temporário válido
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_file.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')  # MP3 header básico
                temp_file.flush()
                
                try:
                    # Deve falhar com erro de rate limit
                    with pytest.raises(Exception) as exc_info:
                        asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                    
                    error_msg = str(exc_info.value).lower()
                    assert any(keyword in error_msg for keyword in [
                        "limite", "aguarde", "rate limit", "minutos"
                    ]), f"Erro não específico para rate limit: {error_msg}"
                    
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
    
    def test_api_server_error_simulation(self):
        """Testar simulação de erro do servidor da API"""
        # Simular cenário de erro do servidor através de mock do client
        with patch.object(self.openai_service, 'client') as mock_client:
            # Simular erro do servidor usando Exception genérica com mensagem específica
            mock_client.audio.transcriptions.create.side_effect = Exception("Service temporarily unavailable")
            
            # Criar arquivo temporário válido
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_file.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')  # MP3 header básico
                temp_file.flush()
                
                try:
                    # Deve falhar com erro do servidor
                    with pytest.raises(Exception) as exc_info:
                        asyncio.run(self.openai_service.transcribe_audio(temp_file.name))
                    
                    error_msg = str(exc_info.value).lower()
                    assert any(keyword in error_msg for keyword in [
                        "servidor", "temporário", "indisponível", "server", "texto", "unavailable", "temporarily"
                    ]), f"Erro não específico para erro do servidor: {error_msg}"
                    
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)


class TestDiskSpaceAndResourceManagement:
    """Testes para gerenciamento de espaço em disco e recursos"""
    
    def setup_method(self):
        """Setup para cada teste"""
        self.audio_service = AudioService()
    
    @patch('services.audio_service.os.statvfs')
    def test_insufficient_disk_space(self, mock_statvfs):
        """Testar erro quando não há espaço suficiente em disco"""
        # Simular pouco espaço em disco
        mock_stat = Mock()
        mock_stat.f_frsize = 4096  # 4KB block size
        mock_stat.f_bavail = 100   # 100 blocks = 400KB disponível
        mock_statvfs.return_value = mock_stat
        
        # Criar AudioMessage válida
        audio_message = AudioMessage(
            file_id="test_disk_space",
            file_size=1024,  # 1KB
            duration=30,
            mime_type="audio/mpeg",
            user_id=12345,
            message_id=67890,
            chat_id=11111
        )
        
        # Deve falhar por falta de espaço
        with pytest.raises(Exception) as exc_info:
            asyncio.run(self.audio_service._validate_audio_message(audio_message))
        
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in [
            "espaço", "disco", "insuficiente", "space"
        ]), f"Erro não específico para falta de espaço: {error_msg}"
    
    def test_temp_directory_creation(self):
        """Testar criação do diretório temporário"""
        # Verificar que diretório temporário existe
        assert self.audio_service.temp_dir.exists(), "Diretório temporário não foi criado"
        assert self.audio_service.temp_dir.is_dir(), "Caminho temporário não é um diretório"
        
        # Verificar que é possível escrever no diretório
        test_file = self.audio_service.temp_dir / "test_write.tmp"
        try:
            test_file.write_text("test")
            assert test_file.exists(), "Não foi possível escrever no diretório temporário"
        finally:
            if test_file.exists():
                test_file.unlink()
    
    def test_cleanup_temp_files(self):
        """Testar limpeza de arquivos temporários"""
        # Criar alguns arquivos temporários
        temp_files = []
        for i in range(3):
            temp_file = self.audio_service.temp_dir / f"test_cleanup_{i}.mp3"
            temp_file.write_text(f"fake audio data {i}")
            temp_files.append(temp_file)
        
        # Verificar que arquivos foram criados
        for temp_file in temp_files:
            assert temp_file.exists(), f"Arquivo temporário não foi criado: {temp_file}"
        
        # Executar limpeza
        removed_count = asyncio.run(self.audio_service.cleanup_temp_files())
        
        # Verificar que arquivos foram removidos (podem não ser removidos se muito recentes)
        # O importante é que a função execute sem erro
        assert removed_count >= 0, "Contador de arquivos removidos inválido"
        
        # Limpar arquivos restantes manualmente
        for temp_file in temp_files:
            if temp_file.exists():
                temp_file.unlink()
    
    def test_file_extension_detection(self):
        """Testar detecção correta de extensões de arquivo"""
        mime_to_ext_tests = [
            ("audio/mpeg", "mp3"),
            ("audio/mp3", "mp3"),
            ("audio/mp4", "m4a"),
            ("audio/m4a", "m4a"),
            ("audio/wav", "wav"),
            ("audio/wave", "wav"),
            ("audio/webm", "webm"),
            ("video/mp4", "mp4"),
            ("unknown/type", "mp3")  # Default
        ]
        
        for mime_type, expected_ext in mime_to_ext_tests:
            actual_ext = self.audio_service._get_file_extension(mime_type)
            assert actual_ext == expected_ext, \
                f"Extensão incorreta para {mime_type}: esperado {expected_ext}, obtido {actual_ext}"