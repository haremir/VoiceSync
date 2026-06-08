import os
import threading
import html
import re
import shutil
from pathlib import Path
import sherpa_onnx
from pydub import AudioSegment

# Add static ffmpeg binaries to PATH only if system ffmpeg is not present
if not shutil.which("ffmpeg") and not shutil.which("ffmpeg.exe"):
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"Warning: Failed to import or configure static_ffmpeg: {e}")

# Define root paths
ROOT_DIR = Path(__file__).resolve().parent
VOICES_DIR = ROOT_DIR / "voices"
OUTPUTS_DIR = ROOT_DIR / "outputs"

# Ensure output directory exists
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# English-to-Turkish Technical Phonetic Normalization Map
# ---------------------------------------------------------------------------
ENGLISH_PHONETIC_MAP = {
    "backgroundservice": "bekgraund servis",
    "hostedservice": "hostıd servis",
    "notificationhandler": "notifikeyşın hendlır",
    "wordpress": "vörpres",
    "fastapi": "fest ey-pi-ay",
    "api key": "ey-pi-ay ki",
    "api": "ey-pi-ay",
    "thread-safety": "tred seyfti",
    "thread safety": "tred seyfti",
    "thread": "tred",
    "scope": "skop",
    "cron": "kron",
    "poller": "polır",
    "docker": "dokır",
    "github": "githap",
    "git": "git",
    "voicesync": "voys-sink",
    "background": "bekgraund",
    "hosted": "hostıd",
    "service": "servis",
    "handler": "hendlır",
    "token": "tokın",
    "plugin": "plagin",
    "client": "klayınt",
    "server": "servır",
    "controller": "kontrolır",
    "request": "rikuest",
    "response": "rispons",
    "database": "deytabeyz",
    "web": "veb",
    "online": "onlayn",
    "offline": "oflayn",
    "software": "softver",
    "hardware": "hardver",
    "developer": "divelopır",
    "interface": "interfeyz",
    "publish": "pabliş",
    "c#": "si şarp",
    "c sharp": "si şarp",
    "c-sharp": "si şarp",
    "dotnet": "dot net",
    "sql": "es-kû-el",
    "mysql": "may-es-kû-el",
    "postgresql": "postgre-es-kû-el",
    "mongodb": "mongo-di-bi",
    "html": "ha-te-me-le",
    "css": "si-es-es",
    "js": "cey-es",
    "javascript": "cavas-kript",
    "typescript": "tayp-skript",
    "json": "ceysın",
    "xml": "iks-me-le",
    "url": "yu-ar-el",
    "uri": "yu-ar-ay",
    "http": "ha-te-te-pe",
    "https": "ha-te-te-pe-es",
    "ajax": "eyceks",
    "jquery": "cey-kueri",
    "react": "riekt",
    "vue": "vyu",
    "angular": "angulır",
    "next.js": "nekst cey-es",
    "nuxt": "nakst",
    "vite": "vayt",
    "node.js": "nod cey-es",
    "npm": "en-pi-em",
    "npx": "en-pi-eks",
    "yarn": "yarn",
    "pnpm": "pi-en-pi-em",
    "python": "paytın",
    "django": "cango",
    "flask": "flask",
    "redis": "redis",
    "docker-compose": "dokır kompoz",
    "kubernetes": "kubernetis",
    "aws": "ey-dabılyu-es",
    "azure": "ejur",
    "gcp": "ci-si-pi",
    "cloud": "klaud",
    "devops": "devops",
    "sprint": "sprint",
    "commit": "komit",
    "push": "puş",
    "pull": "pul",
    "clone": "klon",
    "branch": "birenç",
    "release": "riliys",
    "build": "bild",
    "deploy": "deploy",
    "production": "prodakşın",
    "development": "divelopmınt",
    "local": "lokal",
    "host": "host",
    "port": "port",
    "ip": "ay-pi",
    "dns": "di-en-es",
    "domain": "domeyn",
    "jwt": "cey-dabılyu-ti",
}

# Precompile regex patterns for performance and correctness using word-boundary lookbehinds/lookaheads
_compiled_patterns = []
for key in sorted(ENGLISH_PHONETIC_MAP.keys(), key=len, reverse=True):
    pattern = re.compile(
        rf"(?<![a-zA-Z0-9çğıöşüÇĞİÖŞÜ]){re.escape(key)}(?![a-zA-Z0-9çğıöşüÇĞİÖŞÜ])",
        re.IGNORECASE
    )
    _compiled_patterns.append((pattern, ENGLISH_PHONETIC_MAP[key]))

def normalize_english_words(text: str) -> str:
    """
    Normalizes common English programming/tech terms to their Turkish phonetics.
    """
    for pattern, replacement in _compiled_patterns:
        text = pattern.sub(replacement, text)
    return text

class TTSEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.device = "cpu"  # VITS runs extremely fast on CPU (onnxruntime)
        self.tts_cache = {}  # (length_scale, noise_scale, noise_scale_w) -> OfflineTts instance

    def load(self):
        """
        Loads the default Turkish VITS model configuration into cache to preheat.
        """
        with self.lock:
            # Preheat default instance (speed=1.0 -> length_scale=1.0, noise_scale=0.667, noise_scale_w=0.8)
            self.get_tts_instance(length_scale=1.0, noise_scale=0.667, noise_scale_w=0.8)

    def get_tts_instance(self, length_scale: float, noise_scale: float, noise_scale_w: float) -> sherpa_onnx.OfflineTts:
        """
        Retrieves a cached OfflineTts instance or initializes a new one.
        Maintains a maximum cache size of 8 using simple FIFO eviction to control memory usage.
        """
        key = (round(length_scale, 2), round(noise_scale, 2), round(noise_scale_w, 2))
        if key not in self.tts_cache:
            if len(self.tts_cache) >= 8:
                oldest_key = next(iter(self.tts_cache))
                del self.tts_cache[oldest_key]

            vits_cfg = sherpa_onnx.OfflineTtsVitsModelConfig(
                model="models/vits-piper-tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
                lexicon="",
                tokens="models/vits-piper-tr_TR-dfki-medium/tokens.txt",
                data_dir="models/vits-piper-tr_TR-dfki-medium/espeak-ng-data",
                noise_scale=noise_scale,
                noise_scale_w=noise_scale_w,
                length_scale=length_scale,
            )
            model_cfg = sherpa_onnx.OfflineTtsModelConfig(
                vits=vits_cfg,
                num_threads=4,
                debug=False,
                provider="cpu",
            )
            tts_cfg = sherpa_onnx.OfflineTtsConfig(
                model=model_cfg,
                max_num_sentences=100,
                silence_scale=0.2,
            )
            self.tts_cache[key] = sherpa_onnx.OfflineTts(tts_cfg)
        return self.tts_cache[key]

    def generate(self, text: str, voice_id: str, output_filename: str, language: str = "tr", 
                 speed: float = 1.0, noise_scale: float = 0.667, noise_scale_w: float = 0.8,
                 exaggeration: float = 0.05, temperature: float = 0.7) -> Path:
        """
        Generates offline VITS speech and exports it as MP3.
        """
        with self.lock:
            # Check and clean the input text
            raw_text = text.strip() if text else ""
            if not raw_text:
                raise ValueError("No valid text to generate audio from.")

            # 1. Clean HTML comments first
            clean_comments = re.sub(r'<!--.*?-->', ' ', raw_text, flags=re.DOTALL)
            # 2. Clean HTML tags
            clean_html = re.sub(r'<[^>]+>', ' ', clean_comments)
            # 3. Decode HTML entities
            clean_entities = html.unescape(clean_html)
            
            # Normalize multiple spaces and clean up text
            clean_text = re.sub(r'\s+', ' ', clean_entities).strip()
            if not clean_text:
                raise ValueError("No valid cleaned text to process.")

            # Normalize English programming/tech terms to Turkish phonetics
            normalized_text = normalize_english_words(clean_text)

            # Map speed -> length_scale (speed = 1.0 / length_scale)
            safe_speed = max(0.2, min(5.0, speed))
            length_scale = 1.0 / safe_speed

            # Retrieve model instance from cache
            tts_instance = self.get_tts_instance(length_scale, noise_scale, noise_scale_w)

            # Generate offline TTS speech
            audio = tts_instance.generate(normalized_text)
            
            # Save raw samples to a temporary WAV file
            temp_wav_path = OUTPUTS_DIR / f"_tmp_{output_filename}.wav"
            sherpa_onnx.write_wave(str(temp_wav_path), audio.samples, audio.sample_rate)

            # Export as MP3 with constant 128k bitrate using pydub
            out_mp3_path = OUTPUTS_DIR / output_filename
            sound = AudioSegment.from_wav(str(temp_wav_path))
            sound.export(str(out_mp3_path), format="mp3", bitrate="128k")

            # Clean up the temporary WAV file
            try:
                if temp_wav_path.exists():
                    os.remove(str(temp_wav_path))
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_wav_path}: {e}")

            return out_mp3_path

