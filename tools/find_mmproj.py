"""Find mmproj files for Gemma 4 E2B-it on HuggingFace."""

import json
import urllib.request

repos = [
    "unsloth/gemma-4-E2B-it-GGUF",
    "google/gemma-4-E2B-it",
    "ggml-org/gemma-4-E2B-it-GGUF",
]

for repo in repos:
    url = f"https://huggingface.co/api/models/{repo}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            files = [f["rfilename"] for f in data.get("siblings", [])]
            mmproj_files = [f for f in files if "mmproj" in f.lower() or "projector" in f.lower()]
            if mmproj_files:
                print(f"=== {repo} ===")
                for f in mmproj_files:
                    print(f"  {f}")
            else:
                print(f"=== {repo} === (no mmproj found, {len(files)} files total)")
    except Exception as e:
        print(f"=== {repo} === ERROR: {e}")
