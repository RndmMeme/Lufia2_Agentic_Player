import argparse
import json
from pathlib import Path

from test_kobold_vision import DEFAULT_ENDPOINT, DEFAULT_MODEL, build_content, build_prompt, find_reference_images
from test_kobold_vision import image_to_data_url  # noqa: F401

import requests


def call_model(endpoint: str, model: str, content, max_tokens: int):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    response = requests.post(endpoint, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def parse_result(response_json):
    text = ""
    choices = response_json.get("choices", [])
    if choices:
        text = choices[0].get("message", {}).get("content", "") or ""
    text = text.strip()
    if "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(text)
    except Exception:
        data = {
            "visible": None,
            "confidence": "low",
            "location": "unknown",
            "reason": f"unparsed response: {text[:200]}",
        }
    return data, text


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark KoboldCpp multimodal detection on paired screenshots with optional auto-selected reference sprites."
    )
    parser.add_argument("manifest", help="JSON list of benchmark cases.")
    parser.add_argument("--object", default="lever", dest="object_name")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=120)
    parser.add_argument("--output", default="data/debug/vision_benchmark_report.json")
    parser.add_argument(
        "--reference-keyword",
        action="append",
        default=[],
        help="Keyword used to automatically pull reference sprites from emulator/maps and emulator/sprites. Repeatable.",
    )
    parser.add_argument("--reference-limit", type=int, default=6)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    cases = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise SystemExit("Manifest must be a JSON list.")

    reference_paths = find_reference_images(args.reference_keyword, limit=args.reference_limit)
    prompt = build_prompt(args.object_name, strict_json=True)

    results = []
    summary = {"tp": 0, "tn": 0, "fp": 0, "fn": 0, "unknown": 0}

    for idx, case in enumerate(cases, start=1):
        image_path = Path(case["image"])
        expected = bool(case["expected"])
        label = case.get("label", f"case_{idx}")
        pair_id = case.get("pair_id")

        if not image_path.exists():
            results.append({
                "label": label,
                "pair_id": pair_id,
                "image": str(image_path),
                "expected": expected,
                "error": "image_not_found",
            })
            summary["unknown"] += 1
            continue

        content = build_content(prompt, reference_paths, [image_path])
        response_json = call_model(args.endpoint, args.model, content, args.max_tokens)
        parsed, raw_text = parse_result(response_json)
        predicted = parsed.get("visible")

        bucket = "unknown"
        if predicted is True and expected is True:
            bucket = "tp"
        elif predicted is False and expected is False:
            bucket = "tn"
        elif predicted is True and expected is False:
            bucket = "fp"
        elif predicted is False and expected is True:
            bucket = "fn"

        summary[bucket] += 1
        results.append({
            "label": label,
            "pair_id": pair_id,
            "image": str(image_path),
            "expected": expected,
            "predicted": predicted,
            "bucket": bucket,
            "confidence": parsed.get("confidence", "low"),
            "location": parsed.get("location", "unknown"),
            "reason": parsed.get("reason", ""),
            "raw_response": raw_text,
        })

        print(f"[{idx}/{len(cases)}] {label}: expected={expected} predicted={predicted} bucket={bucket}")

    total_known = summary["tp"] + summary["tn"] + summary["fp"] + summary["fn"]
    metrics = {
        "accuracy": ((summary["tp"] + summary["tn"]) / total_known) if total_known else None,
        "precision": (summary["tp"] / (summary["tp"] + summary["fp"])) if (summary["tp"] + summary["fp"]) else None,
        "recall": (summary["tp"] / (summary["tp"] + summary["fn"])) if (summary["tp"] + summary["fn"]) else None,
    }

    report = {
        "object": args.object_name,
        "reference_images": [str(path) for path in reference_paths],
        "summary": summary,
        "metrics": metrics,
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nReference images:")
    for path in reference_paths:
        print(str(path))

    print("\nSummary:")
    print(json.dumps(report["summary"], indent=2))
    print("\nMetrics:")
    print(json.dumps(report["metrics"], indent=2))
    print(f"\nSaved report to: {output_path}")


if __name__ == "__main__":
    main()
