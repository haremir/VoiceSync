import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

import config
from tts_engine import chunk_text, TTSEngine

def test_text_chunking():
    print("=== Test 1: Text Chunking ===")
    long_text = (
        "Ses sentezleme teknolojisi, yapay zeka alanında son yıllarda inanılmaz bir gelişme gösterdi. "
        "Artık modeller, sadece birkaç saniyelik referans ses kayıtlarını kullanarak son derece doğal, "
        "insansı ve akıcı konuşmalar üretebiliyor. Bu proje kapsamında geliştirdiğimiz VoiceSync, "
        "kullanıcılara bu gelişmiş ses klonlama yeteneğini modern API standartlarında sunmayı hedefliyor. "
        "Bölme işleminin 200 karakter sınırına uyup uymadığını kontrol etmek için bu çok uzun cümleyi bilerek buraya ekledik."
    )
    
    print(f"Original Text Length: {len(long_text)} characters.")
    chunks = chunk_text(long_text, max_chars=200)
    print(f"Generated Chunks count: {len(chunks)}")
    
    for idx, chunk in enumerate(chunks):
        print(f"  Chunk {idx + 1} ({len(chunk)} chars): {chunk}")
        assert len(chunk) <= 200, f"Error: Chunk {idx + 1} exceeds 200 characters limit!"
    
    print("Text Chunking Test: PASSED\n")

def test_audio_generation():
    print("=== Test 2: Audio Generation ===")
    test_text = (
        "Merhaba! VoiceSync ses klonlama sisteminin test aşamasına hoş geldiniz. "
        "Şu an Chatterbox TTS motoru aktif olarak çalışıyor ve Türkçe ses sentezleme testi gerçekleştiriyor. "
        "Her şey yolunda görünüyor."
    )
    
    engine = TTSEngine()
    print("Loading TTS model into memory (this may take a moment on first run)...")
    engine.load()
    print("Model loaded successfully.")
    
    output_file = "test_output.mp3"
    print(f"Generating voice for text using reference 'default' voice ID...")
    
    try:
        out_path = engine.generate(
            text=test_text,
            voice_id="default",
            output_filename=output_file,
            language="tr"
        )
        print(f"Success! Audio successfully generated and saved at: {out_path}")
        assert out_path.exists(), f"Error: Output file does not exist at {out_path}"
        print(f"Output file size: {out_path.stat().st_size} bytes.")
        print("Audio Generation Test: PASSED")
    except Exception as e:
        print(f"Audio Generation Test: FAILED with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_text_chunking()
    test_audio_generation()
