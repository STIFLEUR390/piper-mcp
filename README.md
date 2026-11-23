# piper-mcp

Serveur [MCP](https://modelcontextprotocol.io) local pour **Piper TTS** : synthèse vocale
française et anglaise hors ligne, avec correction de prononciation.

Le serveur n'embarque aucun modèle et aucun moteur : il pilote le binaire `piper` déjà
installé et s'appuie sur le skill [`piper-tts`](https://github.com/STIFLEUR390/agent-skills)
pour normaliser le texte avant de le prononcer — dates, unités, abréviations, sigles,
anglicismes et homographes anglais.

```
"Le 01/02/2025, M. Dupont a payé 12,50 €."
        │
        ├─ normalisation  →  "premier février 2025, Monsieur Dupont a payé 12 euros 50"
        └─ piper          →  ~/piper-out/piper-20260201-101500.wav
```

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-6f42c1.svg)](https://modelcontextprotocol.io)

## Pourquoi pas un générateur OpenAPI

Piper expose un mode HTTP (`python -m piper.http_server`), donc les générateurs type
`openapi-mcp-generator` ou `API-to-MCP-Generator` savent le transformer en MCP. Ils ont été
écartés :

- l'API HTTP de Piper, ce sont trois routes (`/synthesize`, `/voices`, `/info`) : le serveur
  écrit à la main fait 200 lignes, sans code généré à maintenir ni dépendance `requests` ;
- le mode HTTP **garde un modèle en mémoire par processus** : il faut le démarrer, le
  surveiller, choisir un port et le relancer à chaque changement de voix. En stdio, un appel
  = un sous-processus `piper` (~0,8 s de chargement), sans processus à gérer ;
- surtout, un générateur ne fait que relayer le texte tel quel. La valeur ici est la
  normalisation de prononciation, qui doit s'exécuter **avant** `piper` et ne rentre dans
  aucune spécification OpenAPI.

## Prérequis

```bash
# 1. le moteur (une fois)
uv tool install --python 3.13 piper-tts

# 2. des voix (dans ~/.local/share/piper-voices)
git clone https://github.com/STIFLEUR390/agent-skills
cd agent-skills && bash skills/piper-voices/scripts/piper-voices.sh bootstrap

# 3. le skill de normalisation (optionnel mais fortement conseillé)
bash skills/skill-creator/scripts/deploy.sh piper-tts skills
```

Sans le skill, `tts_generate` fonctionne toujours (le champ `normalized` passe à `false`) et
`tts_phonemes` répond par une erreur explicite.

## Installation

```bash
git clone https://github.com/STIFLEUR390/piper-mcp
cd piper-mcp
uv sync
uv run piper-mcp          # stdio, prêt pour un client MCP
```

Avec `pipx` :

```bash
pipx install git+https://github.com/STIFLEUR390/piper-mcp
```

## Déclaration dans un client MCP

```json
{
  "mcpServers": {
    "piper-tts": {
      "command": "uv",
      "args": ["run", "--directory", "/home/moi/Projects/mcp/piper-mcp", "piper-mcp"],
      "env": {
        "PIPER_VOICES_DIR": "/home/moi/.local/share/piper-voices",
        "PIPER_OUTPUT_DIR": "/home/moi/piper-out"
      }
    }
  }
}
```

- **Claude Desktop / Code** : `~/.claude.json` ou `.mcp.json` du projet.
- **Pi** : `~/.pi/agent/mcp.json` (même schéma `mcpServers`).
- **OpenCode** : `~/.config/opencode/opencode.json`, section `mcp`.

## Outils

| Outil | Rôle | Renvoie |
|---|---|---|
| `tts_generate` | synthétise un texte en WAV | `path`, `seconds`, `size_bytes`, `text_normalized`, `normalized` |
| `tts_phonemes` | texte corrigé + IPA réellement prononcés, symboles absents du modèle | `text_normalized`, `phonemes`, `missing` |
| `tts_voices` | voix installées, tailles, voix par défaut | `dir`, `default`, `voices[]` |

```text
tts_generate("Le 01/02/2025, M. Dupont a payé 12,50 €. Il aime le week-end.", lang="fr")
→ {"path": "~/piper-out/piper-20260201-101500.wav", "seconds": 7.4, "size_bytes": 326654,
   "normalized": true,
   "text_normalized": "premier février 2025, Monsieur Dupont a payé 12 euros 50. Il aime le [[wikˈɛnd]]."}

tts_generate("Ms. Smith, on 10/12/2025.", lang="en", voice="en_US-lessac-medium")
tts_phonemes("cuillère", lang="fr")
→ {"text_normalized": "[[kɥijˈɛʁ]]", "phonemes": "k ɥ i j ˈ ɛ ʁ", "missing": []}
```

Le serveur ne télécharge pas de voix : installer des modèles ONNX est le travail de
`piper-voices.sh install <nom>`, qui vérifie les md5 de l'index Hugging Face. Un outil
`tts_install_model` a été volontairement laissé de côté pour ne pas dupliquer ce script.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `PIPER_VOICES_DIR` | `~/.local/share/piper-voices` | modèles `.onnx` + `.onnx.json` |
| `PIPER_OUTPUT_DIR` | `~/piper-out` | dossier des WAV produits |
| `PIPER_BIN` | `piper` dans le `PATH` | binaire Piper |
| `PIPER_TTS_SCRIPT` | skill détecté automatiquement | script de normalisation |

## Dépannage

| Symptôme | Cause |
|---|---|
| `binaire piper introuvable` | `uv tool install piper-tts`, puis `PIPER_BIN` |
| `aucune voix dans …` | `piper-voices.sh install fr_FR-siwis-medium` |
| `normalisation indisponible` | skill non déployé, ou `PIPER_TTS_SCRIPT` non défini |
| `absents du modèle : […]` dans `missing` | symbole absent de la voix choisie : changer de voix (`en_GB-alan-medium` vs `en_US-lessac-medium` n'ont pas le même inventaire) |

## Tests

```bash
uv run pytest -q      # aller-retour stdio réel : list_tools + 3 appels
```

## Licence

MIT — voir [LICENSE](LICENSE). Le moteur Piper est GPL-3.0 ; les voix ont chacune leur
`MODEL_CARD` (voir la [politique de licences de Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md)).
