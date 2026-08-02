import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageOps


def is_content(pixel, black_threshold):
    if isinstance(pixel, int):
        return pixel > black_threshold
    if len(pixel) >= 3:
        r, g, b = pixel[:3]
        return r > black_threshold or g > black_threshold or b > black_threshold
    return any(channel > black_threshold for channel in pixel)


def find_components(image, black_threshold):
    img = image.convert("RGB")
    w, h = img.size
    pixels = img.load()
    visited = [[False] * w for _ in range(h)]
    components = []

    for y in range(h):
        for x in range(w):
            if visited[y][x] or not is_content(pixels[x, y], black_threshold):
                continue
            queue = deque([(x, y)])
            visited[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while queue:
                cx, cy = queue.popleft()
                count += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                        visited[ny][nx] = True
                        if is_content(pixels[nx, ny], black_threshold):
                            queue.append((nx, ny))
            components.append({
                "pixel_count": count,
                "bbox": {
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                    "width": max_x - min_x + 1,
                    "height": max_y - min_y + 1,
                },
            })
    return components


def crop_component(image, component, padding):
    bbox = component["bbox"]
    min_x = max(0, bbox["min_x"] - padding)
    min_y = max(0, bbox["min_y"] - padding)
    max_x = min(image.size[0] - 1, bbox["max_x"] + padding)
    max_y = min(image.size[1] - 1, bbox["max_y"] + padding)
    crop = image.crop((min_x, min_y, max_x + 1, max_y + 1))
    return crop, {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}


def main():
    parser = argparse.ArgumentParser(description="Split a dungeon map sheet into connected room/segment images.")
    parser.add_argument("image", help="Path to dungeon map PNG.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to <image_dir>/rooms")
    parser.add_argument("--black-threshold", type=int, default=8)
    parser.add_argument("--min-pixels", type=int, default=5000)
    parser.add_argument("--padding", type=int, default=8)
    parser.add_argument("--scale", type=int, default=2, help="Integer upscale factor for exported room images.")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    output_dir = Path(args.output_dir) if args.output_dir else image_path.parent / "rooms"
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(image_path).convert("RGB")
    components = find_components(image, args.black_threshold)
    components = [c for c in components if c["pixel_count"] >= args.min_pixels]
    components.sort(key=lambda c: (c["bbox"]["min_y"], c["bbox"]["min_x"]))

    manifest = {
        "source_image": str(image_path),
        "image_size": {"width": image.size[0], "height": image.size[1]},
        "black_threshold": args.black_threshold,
        "min_pixels": args.min_pixels,
        "padding": args.padding,
        "scale": args.scale,
        "segments": [],
    }

    for idx, component in enumerate(components, start=1):
        crop, padded_bbox = crop_component(image, component, args.padding)
        export = crop
        if args.scale > 1:
            export = ImageOps.scale(crop, args.scale, resample=Image.Resampling.NEAREST)
        filename = f"segment_{idx:02d}.png"
        export_path = output_dir / filename
        export.save(export_path)
        manifest["segments"].append({
            "id": f"segment_{idx:02d}",
            "file": filename,
            "pixel_count": component["pixel_count"],
            "bbox": component["bbox"],
            "padded_bbox": padded_bbox,
        })

    manifest_path = output_dir / "segments_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Saved {len(components)} segments to {output_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
