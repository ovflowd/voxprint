"""Download the speaker model and refuse any byte that doesn't match its pinned checksum.

Usage: python3 -I fetch_model.py DEST_DIR

The model is WeSpeaker ResNet34-LM trained on VoxCeleb (CC BY 4.0), as exported to ONNX by
sherpa-onnx. NOTICE in the repository has the attribution.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import urllib.request

NAME = "wespeaker_en_voxceleb_resnet34_LM.onnx"
# The release tag's spelling is upstream's.
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/{NAME}"
SHA256 = "e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012"


def fetch(dest: Path) -> Path:
    path = dest / NAME
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256:
        return path
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    got = hashlib.sha256(data).hexdigest()
    if got != SHA256:
        raise SystemExit(f"{NAME}: sha256 {got} != pinned {SHA256}")
    dest.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    path = fetch(Path(argv[0]))
    print(f"{path}: {path.stat().st_size} bytes, sha256 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
