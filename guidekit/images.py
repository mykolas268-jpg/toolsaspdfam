"""Image pipeline helpers for /images: prompt building, batch contact sheets, crops,
and bookkeeping in images.yaml. Generation itself happens in Claude Code (Higgsfield MCP).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .loader import GuideData, dump_model, write_yaml
from .model import ImageJob, ImagesFile, ImageSlot

DEFAULT_STYLE_LOCK = (
    "Flat painterly editorial illustration, gouache texture with fine grain, warm golden-hour light, "
    "limited palette of warm cream, deep teal, terracotta and sage green, soft gradients, simple clean shapes, "
    "calm aspirational mood, no text, no letters, no numbers, no logos, no watermark."
)
# v2 lesson: these words produced grids and triptychs.
BANNED_PROMPT_WORDS = re.compile(r"\b(every image|series|set|sets)\b", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def subject_noun(character: str) -> str:
    c = f" {character.lower()} "
    if " woman " in c or " girl " in c:
        return "woman"
    if " man " in c or " guy " in c:
        return "man"
    return "person"


def build_prompt(slot: ImageSlot, character: str, style_lock: str, *, cover: bool) -> str:
    noun = subject_noun(character)
    action = slot.action.strip().rstrip(".") or "shown mid-movement"
    scene = slot.scene.strip().rstrip(".")
    view = slot.view.strip().rstrip(".")
    body = (f"One single illustration (not a grid, not panels): {scene}. The {character} is {action}. "
            f"{view}, full body in frame, face small, plain warm cream background. "
            f"Anatomically correct: two arms, two hands, five fingers each. {style_lock}")
    if cover:
        return body.replace(f"The {character} is", f"A {character} is", 1)
    return f"Use the {noun} from the reference image and the same illustration style. " + body


def prompt_problems(slot: ImageSlot) -> list[str]:
    probs = []
    for field_name in ("scene", "action", "view"):
        m = BANNED_PROMPT_WORDS.search(getattr(slot, field_name))
        if m:
            probs.append(f"slot {slot.id}: {field_name} uses {m.group(0)!r}, which produced grids in v2. Rephrase.")
    return probs


def save_images(data: GuideData) -> None:
    write_yaml(data.root / "images.yaml", dump_model(data.images) or {"slots": []})


def write_prompts(data: GuideData) -> tuple[list[str], list[str]]:
    style = data.images.style_lock or data.theme.tokens.get("images", {}).get("style_lock") or DEFAULT_STYLE_LOCK
    problems: list[str] = []
    for slot in data.images.slots:
        problems += prompt_problems(slot)
        slot.prompt = build_prompt(slot, data.guide.character, style, cover=slot.id == "cover")
    if not problems:
        save_images(data)
    return [f"{s.id}: {s.prompt}" for s in data.images.slots], problems


def slot_files(data: GuideData, slot_id: str) -> list[Path]:
    raw = data.root / "images" / "raw"
    files = [p for p in sorted(raw.glob(f"{slot_id}*")) if p.suffix.lower() in IMAGE_EXT] if raw.exists() else []
    for job in data.slot_by_id[slot_id].jobs:
        if job.file:
            p = data.root / job.file
            if p.exists() and p not in files:
                files.append(p)
    return files


def batch_sheet(data: GuideData, slot_id: str, thumb_w: int = 600) -> Path | None:
    from PIL import Image, ImageDraw

    files = slot_files(data, slot_id)
    if not files:
        return None
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        thumbs.append((f, im.resize((thumb_w, round(im.height * thumb_w / im.width)), Image.LANCZOS)))
    gap, label = 24, 40
    th = max(t.height for _, t in thumbs)
    sheet = Image.new("RGB", (gap + len(thumbs) * (thumb_w + gap), gap + label + th + gap), (50, 50, 50))
    draw = ImageDraw.Draw(sheet)
    for i, (f, t) in enumerate(thumbs):
        x = gap + i * (thumb_w + gap)
        draw.text((x, gap + 6), f"{f.name}  {Image.open(f).size[0]}x{Image.open(f).size[1]}", fill=(235, 235, 235))
        sheet.paste(t, (x, gap + label))
    out = data.out / "qa" / "images"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slot_id}.jpg"
    sheet.save(path, quality=90)
    return path


def crop(src: Path, box: tuple[float, float, float, float], out_dir: Path, scale: int = 2) -> Path:
    """box = x, y, w, h as fractions (0-1) or pixels (>1). For hand/equipment close checks."""
    from PIL import Image

    im = Image.open(src).convert("RGB")
    x, y, w, h = box
    if max(box) <= 1:
        x, y, w, h = x * im.width, y * im.height, w * im.width, h * im.height
    region = im.crop((int(x), int(y), int(x + w), int(y + h)))
    region = region.resize((region.width * scale, region.height * scale), Image.LANCZOS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{src.stem}-crop-{int(x)}-{int(y)}.png"
    region.save(path)
    return path


def fetch(data: GuideData, slot_id: str, job_id: str, url: str, variant: int | None, credits: float | None) -> Path:
    """Download a generation result into images/raw/<slot>-<variant>.<ext> and record the job."""
    import urllib.request

    raw = data.root / "images" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    slot = data.slot_by_id[slot_id]
    variant = variant or len(slot.jobs) + 1
    ext = Path(url.split("?")[0]).suffix.lower() or ".png"
    dest = raw / f"{slot_id}-{variant}{ext}"
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (MYKO-supplied generation URL)
        dest.write_bytes(resp.read())
    existing = next((j for j in slot.jobs if j.id == job_id), None)
    if existing:
        existing.file = dest.relative_to(data.root).as_posix()
        save_images(data)
    else:
        add_job(data, slot_id, job_id, dest.relative_to(data.root).as_posix(), credits, variant)
    return dest


def add_job(data: GuideData, slot_id: str, job_id: str, file: str | None, credits: float | None,
            variant: int | None) -> None:
    slot = data.slot_by_id[slot_id]
    slot.jobs.append(ImageJob(id=job_id, file=file, credits=credits, variant=variant))
    if credits:
        data.images.credits_used += credits
    if slot.status == "todo":
        slot.status = "generated"
    save_images(data)


def set_verdict(data: GuideData, slot_id: str, job_id: str, verdict: str, reason: str | None) -> Path | None:
    slot = data.slot_by_id[slot_id]
    job = next((j for j in slot.jobs if j.id == job_id), None)
    if job is None:
        raise KeyError(f"no job {job_id!r} on slot {slot_id!r}")
    job.verdict, job.reason = verdict, reason  # type: ignore[assignment]
    final = None
    if verdict == "pick":
        if not job.file:
            raise ValueError("picked job has no file")
        src = data.root / job.file
        final = data.root / "images" / f"{slot_id}{src.suffix.lower()}"
        shutil.copy2(src, final)
        slot.file, slot.status = final.relative_to(data.root).as_posix(), "picked"
        if slot_id == "cover":
            data.images.cover_ref = slot.file
    save_images(data)
    return final


def status_rows(images: ImagesFile) -> list[str]:
    rows = []
    for s in images.slots:
        picks = sum(1 for j in s.jobs if j.verdict == "pick")
        rejects = sum(1 for j in s.jobs if j.verdict == "reject")
        rows.append(f"{s.id:<16} {s.status:<11} jobs={len(s.jobs)} picked={picks} rejected={rejects} file={s.file or '-'}")
    rows.append(f"credits used: {images.credits_used:g}")
    return rows
