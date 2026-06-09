import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

import config
from tts_engine import TTSEngine, normalize_english_words

def test_phonetic_normalization():
    print("=== Test 1: Phonetic Normalization ===")
    test_phrase = "C# ile WordPress sitelerinde BackgroundService ve HostedService geliştirmek FastAPI ve Docker ile çok kolay."
    expected = "si şarp ile vörpres sitelerinde bekgraund servis ve hostıd servis geliştirmek fest ey-pi-ay ve dokır ile çok kolay."
    
    result = normalize_english_words(test_phrase)
    print(f"Original:  {test_phrase}")
    print(f"Normalized: {result}")
    
    assert "si şarp" in result, "C# was not normalized correctly"
    assert "vörpres" in result, "WordPress was not normalized correctly"
    assert "bekgraund servis" in result, "BackgroundService was not normalized correctly"
    assert "hostıd servis" in result, "HostedService was not normalized correctly"
    assert "fest ey-pi-ay" in result, "FastAPI was not normalized correctly"
    assert "dokır" in result, "Docker was not normalized correctly"
    print("Phonetic Normalization Test: PASSED\n")

def test_audio_generation():
    print("=== Test 2: Audio Generation with Parameters ===")
    test_text = (
        "Merhaba! VoiceSync ses klonlama sisteminin test aşamasına hoş geldiniz. "
        "BackgroundService ve WordPress entegrasyonu başarıyla çalışıyor."
    )
    
    engine = TTSEngine()
    print("Loading VITS models (preheating)...")
    engine.load()
    print("Model loaded successfully.")
    
    output_file = "test_output.mp3"
    print("Generating voice with custom speed and noise parameters...")
    
    try:
        out_path = engine.generate(
            text=test_text,
            voice_id="default",
            output_filename=output_file,
            language="tr",
            speed=1.1,
            noise_scale=0.75,
            noise_scale_w=0.85
        )
        print(f"Success! Audio successfully generated at: {out_path}")
        assert out_path.exists(), f"Error: Output file does not exist at {out_path}"
        print(f"Output file size: {out_path.stat().st_size} bytes.")
        print("Audio Generation Test: PASSED")
    except Exception as e:
        print(f"Audio Generation Test: FAILED with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_phonetic_normalization()
    test_audio_generation()

