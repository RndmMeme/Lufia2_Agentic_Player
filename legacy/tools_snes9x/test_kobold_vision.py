import argparse
import base64
import json
import mimetypes
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINT = "http://localhost:5001/v1/chat/completions"
DEFAULT_MODEL = "koboldcpp/Qwen3.5-4B-Q8_0"
REFERENCE_DIRS = [
    PROJECT_ROOT / "emulator" / "sprites",
    PROJECT_ROOT / "emulator" / "maps",
]


def image_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def score_reference(path: Path, keywords):
    name = path.stem.lower()
    score = 0
    for keyword in keywords:
        if keyword in name:
            score += 10
        for part in name.replace("_", " ").replace("-", " ").split():
            if keyword == part:
                score += 5
    return score


def find_reference_images(reference_keywords, limit=6):
    if not reference_keywords:
        return []

    keywords = [keyword.strip().lower() for keyword in reference_keywords if keyword.strip()]
    candidates = []

    for root in REFERENCE_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*.png"):
            score = score_reference(path, keywords)
            if score <= 0:
                continue
            candidates.append((score, path))

    candidates.sort(key=lambda item: (-item[0], item[1].name.lower()))
    seen = set()
    selected = []
    for _, path in candidates:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        selected.append(path)
        if len(selected) >= limit:
            break
    return selected


def build_prompt(object_name, strict_json):
    if strict_json:
        return (
            f"You are checking whether a {object_name} or a visually matching object is visible in the target screenshot.\n"
            "Use the reference images as examples, but do not guess.\n"
            "Return JSON only in this exact shape:\n"
            '{"visible": true_or_false, "confidence": "low|medium|high", "location": "short phrase or unknown", "reason": "short explanation"}'
        )
    return (
        f"Use the reference images to understand what '{object_name}' looks like in this game.\n"
        "Then analyze the target screenshot conservatively.\n"
        "Say whether the object is visible, where it is if visible, and keep the answer practical."
    )


def build_content(prompt, reference_paths, target_paths):
    content = [{"type": "text", "text": prompt}]
    for idx, ref_path in enumerate(reference_paths, start=1):
        content.append({"type": "text", "text": f"Reference {idx}: {ref_path.name}"})
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(ref_path)}})
    for idx, target_path in enumerate(target_paths, start=1):
        content.append({"type": "text", "text": f"Target {idx}: {target_path.name}"})
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(target_path)}})
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Send screenshots to KoboldCpp vision and optionally attach matching reference sprites from emulator assets."
    )
    parser.add_argument("image", nargs="+", help="One or more target screenshots.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--object", default="lever", dest="object_name")
    parser.add_argument(
        "--reference-keyword",
        action="append",
        default=[],
        help="Keyword used to automatically pull reference sprites from emulator/maps and emulator/sprites. Repeatable.",
    )
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        help="Explicit reference image path. Repeatable.",
    )
    parser.add_argument("--reference-limit", type=int, default=6)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--strict-json", action="store_true")
    args = parser.parse_args()

    target_paths = [Path(p) for p in args.image]
    for target_path in target_paths:
        if not target_path.exists():
            raise SystemExit(f"Target image not found: {target_path}")

    explicit_references = [Path(p) for p in args.reference]
    for ref_path in explicit_references:
        if not ref_path.exists():
            raise SystemExit(f"Reference image not found: {ref_path}")

    auto_references = find_reference_images(args.reference_keyword, limit=args.reference_limit)
    reference_paths = []
    seen = set()
    for path in explicit_references + auto_references:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        reference_paths.append(path)

    prompt = args.prompt or build_prompt(args.object_name, args.strict_json)
    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": build_content(prompt, reference_paths, target_paths),
            }
        ],
        "max_tokens": args.max_tokens,
        "temperature": 0.1,
    }

    response = requests.post(args.endpoint, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    print("=== REFERENCES USED ===")
    if reference_paths:
        for path in reference_paths:
            print(str(path))
    else:
        print("(none)")

    print("\n=== RAW JSON (trimmed) ===")
    print(json.dumps(data, indent=2)[:4000])

    print("\n=== ASSISTANT TEXT ===")
    choices = data.get("choices", [])
    if choices:
        print(choices[0].get("message", {}).get("content", ""))


if __name__ == "__main__":
    main()
