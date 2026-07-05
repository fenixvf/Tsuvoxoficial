# Ultimate Vocal Remover – Web Edition

A mobile-friendly web interface for AI-powered audio source separation, built on top of the [UVR](https://github.com/Anjok07/ultimatevocalremovergui) engine and [Demucs](https://github.com/facebookresearch/demucs).

## How to run

```bash
python app.py
```

Serves on port 5000. Accessible from any device (mobile, tablet, desktop) via the Replit preview URL.

## Architecture

- **`app.py`** — Flask backend. Handles file upload, job queue, Demucs subprocess, and download endpoints.
- **`templates/index.html`** — Mobile-first single-page UI.
- **`static/style.css`** — Dark-theme responsive CSS.
- **`static/app.js`** — Client-side JS: drag-and-drop, polling, results.
- **`temp/uploads/`** — Temporary uploaded audio files (auto-created).
- **`temp/outputs/`** — Separated stems per job (auto-created).

## Supported formats

MP3, WAV, FLAC, OGG, M4A, AAC, WMA, AIFF — up to 200MB.

## Separation modes

| Mode | Description |
|---|---|
| Vocal / Instrumental | Splits into vocals + no_vocals (2-stem) |
| 4 Faixas | Splits into vocals, drums, bass, other |

## Models

| Model | Notes |
|---|---|
| `htdemucs` | Default – good quality, fast |
| `htdemucs_ft` | Fine-tuned – higher quality, slower |
| `mdx_extra` | Best for vocal isolation |
| `mdx_extra_q` | Highest quality, slowest |

## User preferences

- Language: Portuguese (Brazilian)
- Mobile-first web UI preferred over desktop GUI
