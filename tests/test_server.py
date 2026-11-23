"""Aller-retour stdio réel : le serveur est lancé comme le ferait un client MCP."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

OUT = Path(os.environ.get("PIPER_OUTPUT_DIR", "/tmp/piper-mcp-test"))


def call(*requests):
    """Lance le serveur, exécute (nom, arguments) et renvoie les résultats déballés."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "piper_mcp.server"],
        env={**os.environ, "PIPER_OUTPUT_DIR": str(OUT)},
    )

    async def run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = sorted(t.name for t in (await session.list_tools()).tools)
                results = [await session.call_tool(name, args) for name, args in requests]
                # les outils renvoient du JSON en texte (pas de schema de sortie)
                return tools, [json.loads(r.content[0].text) for r in results]

    return asyncio.run(run())


def test_tools_round_trip():
    tools, (voices, phonemes, audio) = call(
        ("tts_voices", {}),
        ("tts_phonemes", {"text": "cuillère", "lang": "fr"}),
        ("tts_generate", {"text": "Bonjour le 01/02/2025.", "lang": "fr",
                          "filename": "test-mcp.wav"}),
    )
    assert tools == ["tts_generate", "tts_phonemes", "tts_voices"]

    assert voices["default"]["fr"] == "fr_FR-siwis-medium"
    assert len(voices["voices"]) >= 1

    assert phonemes["missing"] == []
    assert "ɥ" in phonemes["phonemes"]
    assert "kɥijˈɛʁ" in phonemes["text_normalized"]  # le lexique injecte l'IPA

    assert audio["normalized"] is True
    assert audio["seconds"] > 0
    assert Path(audio["path"]).is_file()
    assert audio["text_normalized"].startswith("Bonjour le premier février 2025")
