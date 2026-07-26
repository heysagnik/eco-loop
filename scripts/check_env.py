
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def main() -> int:
    ok = True

    try:
        import pyenergyplus  
        print("OK: pyenergyplus importable")
    except ModuleNotFoundError:
        print(
            "MISSING: pyenergyplus not found. Install EnergyPlus 24.x from "
            "https://energyplus.net/downloads and add its install directory "
            "(containing pyenergyplus/) to PYTHONPATH."
        )
        ok = False

    idf_files = list(MODELS_DIR.glob("*.idf"))
    epw_files = list(MODELS_DIR.glob("*.epw"))

    if idf_files:
        print(f"OK: found .idf model(s): {[f.name for f in idf_files]}")
    else:
        print("MISSING: no .idf file in models/ (DOE small-office reference model)")
        ok = False

    if epw_files:
        print(f"OK: found weather file(s): {[f.name for f in epw_files]}")
    else:
        print("MISSING: no .epw weather file in models/ (TMY3)")
        ok = False

    ollama_root = OLLAMA_BASE_URL.removesuffix("/v1").rstrip("/") + "/"
    try:
        urllib.request.urlopen(ollama_root, timeout=3.0)
        print(f"OK: Ollama reachable at {ollama_root}")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(f"MISSING: Ollama not reachable at {ollama_root} ({exc}). Run `ollama serve`.")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
