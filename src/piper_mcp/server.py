"""Serveur MCP local pour Piper TTS (français / anglais).

Il ne réimplémente rien : la synthèse passe par le binaire `piper` et la
normalisation de prononciation par le script du skill `piper-tts`
(https://github.com/STIFLEUR390/agent-skills), qui embarque les dictionnaires
de correction mesurés (dates, unités, abréviations, anglicismes, homographes).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("piper-tts")

DEFAULT_VOICES = {"fr": "fr_FR-siwis-medium", "en": "en_GB-alan-medium"}

# Emplacements où les agents installent les skills (deploy.sh du dépôt agent-skills).
SKILL_SCRIPTS = (
    "~/.agents/skills/piper-tts/scripts/piper-tts.py",
    "~/.claude/skills/piper-tts/scripts/piper-tts.py",
    "~/.config/opencode/skills/piper-tts/scripts/piper-tts.py",
    "~/.pi/agent/skills/piper-tts/scripts/piper-tts.py",
    "~/.omp/agent/skills/piper-tts/scripts/piper-tts.py",
)


def voices_dir() -> Path:
    raw = os.environ.get("PIPER_VOICES_DIR")
    path = Path(raw).expanduser() if raw else Path.home() / ".local/share/piper-voices"
    if raw and not path.is_dir():  # évite « aucune voix » quand la variable est mal recopiée
        raise ToolError(f"PIPER_VOICES_DIR ne pointe pas sur un dossier : {raw!r}")
    return path


def out_dir() -> Path:
    return Path(os.environ.get("PIPER_OUTPUT_DIR") or Path.home() / "piper-out").expanduser()


def piper_bin() -> str:
    binary = os.environ.get("PIPER_BIN") or shutil.which("piper")
    if not binary or not Path(binary).exists():
        raise ToolError(
            "binaire `piper` introuvable : `uv tool install piper-tts`, puis "
            "exporte PIPER_BIN=/chemin/vers/piper"
        )
    return binary


def skill_script() -> Path | None:
    """Script de normalisation du skill piper-tts, s'il est installé."""
    explicit = os.environ.get("PIPER_TTS_SCRIPT")
    candidates = [explicit] if explicit else list(SKILL_SCRIPTS)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"commande expirée après {timeout} s : {' '.join(cmd[:3])}…") from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ToolError(f"échec ({proc.returncode}) : " + " | ".join(detail))
    return proc


def wav_info(path: Path) -> tuple[float, int]:
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate(), path.stat().st_size


def _voice(lang: str, voice: str | None) -> str:
    if lang not in DEFAULT_VOICES:
        raise ToolError(f"langue non gérée : {lang!r} (fr ou en)")
    return voice or DEFAULT_VOICES[lang]


@mcp.tool()
def tts_generate(
    text: str,
    lang: str = "fr",
    voice: str | None = None,
    length_scale: float | None = None,
    sentence_silence: float | None = None,
    filename: str | None = None,
) -> dict:
    """Synthétise `text` en WAV sur cette machine et renvoie le chemin du fichier.

    lang: "fr" ou "en". voice: nom d'une voix installée (défaut fr_FR-siwis-medium
    / en_GB-alan-medium). length_scale > 1 ralentit. filename: nom du WAV
    (défaut horodaté) dans PIPER_OUTPUT_DIR (~/piper-out).
    """
    _voice(lang, voice)
    target = out_dir() / (filename or f"piper-{time.strftime('%Y%m%d-%H%M%S')}.wav")
    if target.suffix.lower() != ".wav":
        target = target.with_suffix(".wav")
    target.parent.mkdir(parents=True, exist_ok=True)

    script = skill_script()
    if script:
        cmd = [sys.executable, str(script), "-l", lang, "-v", _voice(lang, voice),
               "-o", str(target), "--print-text"]
        if length_scale is not None:
            cmd += ["--length-scale", str(length_scale)]
        if sentence_silence is not None:
            cmd += ["--sentence-silence", str(sentence_silence)]
        cmd += ["--", text]
    else:  # skill absent : synthèse brute, sans normalisation
        cmd = [piper_bin(), "-m", _voice(lang, voice), "--data-dir", str(voices_dir()),
               "-f", str(target)]
        if length_scale is not None:
            cmd += ["--length-scale", str(length_scale)]
        if sentence_silence is not None:
            cmd += ["--sentence-silence", str(sentence_silence)]
        cmd += ["--", text]

    proc = run(cmd)
    if not target.is_file():
        raise ToolError(f"aucun WAV produit à {target}")
    seconds, size = wav_info(target)
    normalized = next((ln for ln in proc.stdout.splitlines() if ln and not ln.startswith("✅")), None)
    return {
        "path": str(target),
        "seconds": round(seconds, 2),
        "size_bytes": size,
        "lang": lang,
        "voice": _voice(lang, voice),
        "normalized": bool(script),
        "text_normalized": normalized,
    }


@mcp.tool()
def tts_phonemes(text: str, lang: str = "fr", voice: str | None = None) -> dict:
    """Renvoie le texte corrigé et les phonèmes IPA réellement prononcés.

    Utile pour vérifier une prononciation avant de générer l'audio : la liste
    `missing` contient les symboles absents du modèle (ils seraient muets).
    """
    _voice(lang, voice)
    script = skill_script()
    if not script:
        raise ToolError(
            "normalisation indisponible : installe le skill piper-tts ou exporte "
            "PIPER_TTS_SCRIPT=/chemin/vers/piper-tts.py"
        )
    proc = run([sys.executable, str(script), "-l", lang, "-v", _voice(lang, voice),
                "--check", "--", text])
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return {
        "text_normalized": lines[0] if lines else "",
        "phonemes": " ".join(lines[1:]),
        "missing": " ".join(
            ln.split(":", 1)[1].split() for ln in proc.stderr.splitlines() if "absents" in ln
        ).split(),
    }


@mcp.tool()
def tts_voices() -> dict:
    """Liste les voix Piper installées localement et les voix par défaut par langue."""
    models = sorted(p.stem for p in voices_dir().glob("*.onnx"))
    if not models:
        raise ToolError(f"aucune voix dans {voices_dir()} : ./scripts/piper-voices.sh install …")
    return {
        "dir": str(voices_dir()),
        "default": {lang: name for lang, name in DEFAULT_VOICES.items() if name in models},
        "voices": [
            {"name": name, "lang": name.split("_")[0],
             "size_mb": round((voices_dir() / f"{name}.onnx").stat().st_size / 1e6)}
            for name in models
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
