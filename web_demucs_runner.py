"""
Wrapper that runs Demucs separation while:
1. Ensuring the installed demucs package (site-packages) is used, not the local folder
2. Patching torchaudio.save to use soundfile instead of torchcodec
Called by app.py as: python web_demucs_runner.py <args...>
"""
import sys
import site
from pathlib import Path

# ── Fix import order: put site-packages BEFORE the workspace root ───────────
# This prevents the local demucs/ folder from shadowing the installed package.
workspace = str(Path(__file__).parent)
site_pkgs = site.getsitepackages() + [site.getusersitepackages()]

# Remove workspace from sys.path, add site-packages at front
sys.path = [p for p in sys.path if p != workspace and p != '']
for sp in reversed(site_pkgs):
    if Path(sp).exists() and sp not in sys.path:
        sys.path.insert(0, sp)

# ── Patch torchaudio.save → soundfile (no torchcodec needed) ────────────────
import soundfile as sf

def _sf_save(path, src, sample_rate, **kwargs):
    """Save a torch tensor to audio using soundfile."""
    wav = src.numpy()
    if wav.ndim == 2:
        wav = wav.T  # (channels, frames) → (frames, channels)
    sf.write(str(path), wav, sample_rate)

import torchaudio
torchaudio.save = _sf_save

# Patch the internal reference used inside torchaudio itself
try:
    import torchaudio._torchcodec as _tc
    _tc.save_with_torchcodec = lambda path, src, sample_rate, **kw: _sf_save(path, src, sample_rate)
except Exception:
    pass

# ── Run demucs ───────────────────────────────────────────────────────────────
from demucs.separate import main
sys.exit(main())
