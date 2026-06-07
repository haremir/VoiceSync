import chatterbox
from chatterbox import ChatterboxMultilingualTTS
import torch
import torchaudio

# Monkey patch torch.load to force CPU mapping if CUDA is unavailable
_orig_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    if not torch.cuda.is_available():
        kwargs["map_location"] = "cpu"
    return _orig_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from pathlib import Path
import re
import static_ffmpeg
from pydub import AudioSegment

# Add static ffmpeg binaries to PATH
static_ffmpeg.add_paths()


# Define root paths
ROOT_DIR = Path(__file__).resolve().parent
VOICES_DIR = ROOT_DIR / "voices"
OUTPUTS_DIR = ROOT_DIR / "outputs"

# Ensure output directory exists
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Pinned maximum characters per chunk
CHUNK_MAX_CHARS = 200

def chunk_text(text: str, max_chars: int = 200) -> list[str]:
    """
    Splits text by sentence boundaries (.!?). If any sentence is longer than max_chars,
    it is split at word boundaries into logical sub-blocks of at most max_chars.
    Empty chunks are filtered out.
    """
    if not text or not text.strip():
        return []

    # Split by sentence boundaries but preserve punctuation if possible or split cleanly
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []

    for sentence in raw_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        if len(sentence) <= max_chars:
            chunks.append(sentence)
        else:
            # Word-level logical splitting for long sentences
            words = sentence.split(' ')
            current_chunk = []
            current_len = 0
            for word in words:
                if not word:
                    continue
                word_len = len(word)
                # +1 represents the space between words
                added_len = word_len + (1 if current_chunk else 0)
                if current_len + added_len <= max_chars:
                    current_chunk.append(word)
                    current_len += added_len
                else:
                    if current_chunk:
                        chunks.append(" ".join(current_chunk))
                    # Handle edge case where a single word is longer than max_chars
                    if word_len > max_chars:
                        for i in range(0, word_len, max_chars):
                            chunks.append(word[i:i+max_chars])
                        current_chunk = []
                        current_len = 0
                    else:
                        current_chunk = [word]
                        current_len = word_len
            if current_chunk:
                chunks.append(" ".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]

def merge_wav_files(wav_paths: list[Path], out_path: Path) -> Path:
    """
    Merges multiple WAV files into a single audio track with a 100ms silent transition
    between chunks using pydub, and exports the final output as an MP3 with 128k bitrate.
    """
    if not wav_paths:
        raise ValueError("No WAV files provided for merging.")

    # Load the first segment
    combined = AudioSegment.from_wav(str(wav_paths[0]))
    silence = AudioSegment.silent(duration=100)

    for path in wav_paths[1:]:
        segment = AudioSegment.from_wav(str(path))
        combined += silence + segment

    # Export as MP3 with constant 128k bitrate
    combined.export(str(out_path), format="mp3", bitrate="128k")
    return out_path

class TTSEngine:
    def __init__(self):
        # Automatically detect device (CUDA GPU if available, else CPU)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None

    def load(self):
        """
        Loads the pretrained ChatterboxMultilingualTTS model once in memory.
        """
        if self.model is None:
            self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)

    def generate(self, text: str, voice_id: str, output_filename: str, language: str = "tr") -> Path:
        """
        Generates TTS audio from the provided text using the specified reference voice,
        slices text into chunks to respect model boundaries, processes them, merges the output
        into a single MP3 file, and cleans up intermediate WAVs.
        """
        if self.model is None:
            raise RuntimeError("Model is not loaded. Call load() first before generating speech.")

        # Resolve and validate reference voice path
        voice_path = VOICES_DIR / f"{voice_id}.wav"
        if not voice_path.exists():
            raise FileNotFoundError(f"Reference voice file not found at: {voice_path}")

        # Chunk the text
        text_chunks = chunk_text(text, max_chars=CHUNK_MAX_CHARS)
        if not text_chunks:
            raise ValueError("No valid text chunks to generate audio from.")

        temp_wav_paths = []
        try:
            # Generate each text chunk as a temporary WAV
            for idx, chunk in enumerate(text_chunks):
                # Using exaggeration=0.3 for natural Turkish pronunciation
                wav_tensor = self.model.generate(
                    text=chunk,
                    language_id=language,
                    audio_prompt_path=str(voice_path),
                    exaggeration=0.3
                )
                temp_path = OUTPUTS_DIR / f"temp_{voice_id}_{idx}.wav"
                torchaudio.save(str(temp_path), wav_tensor, self.model.sr)
                temp_wav_paths.append(temp_path)

            # Define final MP3 output path
            out_mp3_path = OUTPUTS_DIR / output_filename
            merge_wav_files(temp_wav_paths, out_mp3_path)
            return out_mp3_path

        finally:
            # Clean up all temporary WAV files
            for temp_path in temp_wav_paths:
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception as e:
                    print(f"Warning: Failed to delete temporary file {temp_path}: {e}")
