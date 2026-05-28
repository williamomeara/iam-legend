"""Build the iam-legend hackathon demo video end-to-end.

Pipeline:
  1. Generate VO audio per shot via Kokoro TTS.
  2. Render Mermaid architecture diagram → PNG.
  3. Capture browser screenshots of the live demo PR via Playwright.
  4. Generate styled terminal frames via Pillow for the cold-open and MCP demo.
  5. Compose final MP4 via ffmpeg (audio + Ken-Burns image sequences + fades).

Output: docs/submission/iam-legend-demo.mp4 (1080p, ~80s, with Kokoro VO).

Run: python scripts/build_demo_video.py
"""
from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from PIL import Image, ImageDraw, ImageFont
from chatterbox.tts import ChatterboxTTS

REPO_ROOT = Path(__file__).parent.parent
BUILD = Path("/tmp/iam-legend-video")
BUILD.mkdir(exist_ok=True, parents=True)
(BUILD / "audio").mkdir(exist_ok=True)
(BUILD / "frames").mkdir(exist_ok=True)
(BUILD / "screenshots").mkdir(exist_ok=True)

OUT = REPO_ROOT / "docs" / "submission" / "iam-legend-demo.mp4"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ─── VO SCRIPT — one entry per shot ───────────────────────────────────────
# Lengths chosen so total lands ~80s at Kokoro's default 1.0 speed.
# Pacing: ~150 words/minute, deliberate.

VO_SCRIPT = [
    {
        "shot": "1_hook",
        "text": (
            "Every G C P user has lived through this. Terraform apply. "
            "Halfway through. Four oh three. "
            "Infrastructure stuck in a half applied state. "
            "Because nothing catches the permission gap before apply, "
            "against the principal that actually runs it."
        ),
    },
    {
        "shot": "2_what",
        "text": (
            "I Am Legend is the G C P I A M toolbelt that lives between plan and apply. "
            "One Python core. Three surfaces. "
            "A FastMCP server. A GitHub Action that posts A I code reviews. And a C L I. "
            "Model Context Protocol at the center. Deterministic math at the core. "
            "Gemini at the edges, for judgment and prose."
        ),
    },
    {
        "shot": "3_hero",
        "text": (
            "Every pull request push triggers I Am Legend. "
            "It runs as the actual deployer service account, via Workload Identity Federation. "
            "Hits live test I A M permissions. "
            "Picks the smallest set of predefined roles, using Gemini. "
            "And posts a code review with copy-paste ready G cloud grant commands. "
            "Notice Gemini flagging that roles slash I A M slash dev ops is broad. "
            "Surfaced in band. Not buried in a separate review."
        ),
    },
    {
        "shot": "4_mcp",
        "text": (
            "Same engine. Plug into any M C P client. "
            "Gemini C L I. Claude Code. Cursor. "
            "They all get an I A M aware partner. "
            "Without forking custom code."
        ),
    },
    {
        "shot": "5_close",
        "text": (
            "Validated against all seven official Google A D K starter templates. "
            "Zero catalog gaps on any of them. "
            "I Am Legend. "
            "Stop deploying. Start shipping."
        ),
    },
]


def generate_audio() -> dict[str, float]:
    """Generate one wav per shot using Chatterbox (Resemble AI).

    Chatterbox produces notably more natural prosody than Kokoro at the cost
    of ~real-time generation on MPS (vs <real-time on CPU for Kokoro). Model
    loads once and is reused across all shots.
    """
    durations: dict[str, float] = {}
    # Check cache first — if all WAVs exist, skip the (expensive) model load.
    cached_all = all(
        (BUILD / "audio" / f"{s['shot']}.wav").exists() for s in VO_SCRIPT
    )
    if cached_all:
        for s in VO_SCRIPT:
            out_path = BUILD / "audio" / f"{s['shot']}.wav"
            data, sr = sf.read(out_path)
            durations[s["shot"]] = len(data) / sr
            print(f"  {s['shot']}: cached ({durations[s['shot']]:.2f}s)")
        return durations

    print("== Generating VO audio with Chatterbox ==", flush=True)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"  device: {device}", flush=True)
    model = ChatterboxTTS.from_pretrained(device=device)
    print(f"  model loaded — generating {len(VO_SCRIPT)} shots", flush=True)

    for s in VO_SCRIPT:
        out_path = BUILD / "audio" / f"{s['shot']}.wav"
        if out_path.exists():
            data, sr = sf.read(out_path)
            durations[s["shot"]] = len(data) / sr
            print(f"  {s['shot']}: cached ({durations[s['shot']]:.2f}s)")
            continue
        # Chatterbox generates the whole utterance at once. For longer shots,
        # split on sentence boundaries to keep individual generations under
        # the model's preferred token horizon (~1000 tokens ~= ~30s of audio).
        sentences = [c.strip() for c in s["text"].split(". ") if c.strip()]
        chunks: list[np.ndarray] = []
        for sent in sentences:
            if not sent.endswith("."):
                sent += "."
            wav = model.generate(sent)
            arr = wav.squeeze().cpu().numpy()
            chunks.append(arr)
            # 180ms inter-sentence silence
            chunks.append(np.zeros(int(0.18 * model.sr), dtype=arr.dtype))
        if chunks:
            chunks.pop()  # drop trailing silence
        full = np.concatenate(chunks).astype(np.float32)
        sf.write(out_path, full, model.sr)
        durations[s["shot"]] = len(full) / model.sr
        print(f"  {s['shot']}: {durations[s['shot']]:.2f}s → {out_path}")
    return durations


# ─── Frame generation helpers ──────────────────────────────────────────────

W, H = 1920, 1080
BG = (15, 18, 26)
FG = (224, 230, 240)
ACCENT = (140, 200, 255)
DIM = (130, 140, 160)
RED = (255, 80, 80)
GREEN = (110, 220, 130)
YELLOW = (240, 200, 100)


def _font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"]
        if mono
        else [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Avenir Next.ttc",
            "/System/Library/Fonts/SFNS.ttf",
        ]
    )
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


FIGMA_FRAMES = BUILD / "frames-figma"


def use_figma_or_render(figma_name: str, render_fn) -> Path:
    """Prefer the Figma-exported PNG if present; otherwise fall back to Pillow."""
    figma_path = FIGMA_FRAMES / figma_name
    out = BUILD / "frames" / figma_name
    if figma_path.exists():
        # Copy/symlink the Figma version. Re-copy each run so any Figma updates flow through.
        from shutil import copyfile
        copyfile(figma_path, out)
        print(f"  [figma] {figma_name}")
        return out
    return render_fn()


def shot1_hook_frame() -> Path:
    """Cold-open terminal: a frustrated terraform apply 403."""
    out = BUILD / "frames" / "shot1_hook.png"
    img = Image.new("RGB", (W, H), (10, 12, 18))
    draw = ImageDraw.Draw(img)

    # Terminal frame chrome
    tx, ty = 160, 140
    tw, th = W - 320, H - 280
    draw.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=18, fill=(24, 28, 38))
    # window dots
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse((tx + 24 + i * 28, ty + 24, tx + 24 + i * 28 + 16, ty + 40), fill=c)
    title_font = _font(24, mono=True)
    draw.text((tx + 120, ty + 22), "ci-runner — terraform apply", fill=DIM, font=title_font)

    # terminal content
    font_lg = _font(28, mono=True)
    font_md = _font(26, mono=True)
    x, y = tx + 40, ty + 90
    lines = [
        ("$ terraform apply -auto-approve", FG),
        ("google_storage_bucket.data: Creating...", DIM),
        ("google_storage_bucket.data: Creation complete after 2s", GREEN),
        ("google_pubsub_topic.events: Creating...", DIM),
        ("google_pubsub_topic.events: Creation complete after 1s", GREEN),
        ("google_vertex_ai_endpoint.agent: Creating...", DIM),
        ("", FG),
        ("╷", RED),
        ("│  Error: 403 Permission denied: aiplatform.endpoints.create", RED),
        ("│        on plan.tf line 23, in resource \"google_vertex_ai_endpoint\" \"agent\":", DIM),
        ("│", DIM),
        ("│  The deployer service account does not have", DIM),
        ("│  permission to create Vertex AI endpoints in this project.", DIM),
        ("╵", RED),
        ("", FG),
        ("Apply failed. 2 resources created, 1 resource failed.", RED),
        ("Infrastructure is now in a half-applied state.", YELLOW),
    ]
    for text, color in lines:
        f = font_lg if "Error: 403" in text or "$ " in text else font_md
        draw.text((x, y), text, fill=color, font=f)
        y += f.size + 8

    img.save(out)
    print(f"  wrote {out}")
    return out


def shot4_mcp_frame() -> Path:
    """Gemini CLI talking to the iam-legend MCP."""
    out = BUILD / "frames" / "shot4_mcp.png"
    img = Image.new("RGB", (W, H), (10, 12, 18))
    draw = ImageDraw.Draw(img)
    tx, ty = 160, 140
    tw, th = W - 320, H - 280
    draw.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=18, fill=(24, 28, 38))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse((tx + 24 + i * 28, ty + 24, tx + 24 + i * 28 + 16, ty + 40), fill=c)
    draw.text(
        (tx + 120, ty + 22),
        "gemini-cli — iam-legend MCP connected",
        fill=DIM,
        font=_font(24, mono=True),
    )

    font_lg = _font(28, mono=True)
    font_md = _font(26, mono=True)
    x, y = tx + 40, ty + 90
    lines = [
        ("> what IAM perms does this Vertex agent deploy need?", FG),
        ("", FG),
        ("▸ calling tool: lookup_permissions_for", DIM),
        ("    target = vertex.agent_engine_create", DIM),
        ("", FG),
        ("✓ vertex.agent_engine_create (create)", GREEN),
        ("    - aiplatform.reasoningEngines.create", FG),
        ("    - aiplatform.reasoningEngines.deploy", FG),
        ("    - storage.objects.create", FG),
        ("    - storage.objects.get", FG),
        ("", FG),
        ("▸ calling tool: recommend_roles", DIM),
        ("    permissions = [4 perms]", DIM),
        ("", FG),
        ("✓ Gemini picked bundle 0 (per-service prefix match):", GREEN),
        ("    roles/aiplatform.user", ACCENT),
        ("    reasoning: Best match for Vertex Agent Engine deploy.", DIM),
        ("               Avoids broader roles/aiplatform.admin.", DIM),
    ]
    for text, color in lines:
        f = font_lg if text.startswith(("> ", "✓ ")) and ":" in text else font_md
        draw.text((x, y), text, fill=color, font=f)
        y += f.size + 6
    img.save(out)
    print(f"  wrote {out}")
    return out


def shot5_close_frame() -> Path:
    """Validation table + end card with URLs."""
    out = BUILD / "frames" / "shot5_close.png"
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    title_font = _font(64)
    subtitle_font = _font(36)
    table_h = _font(28, mono=True)
    url_font = _font(34, mono=True)

    draw.text((W // 2, 110), "iam-legend", fill=ACCENT, font=title_font, anchor="mm")
    draw.text(
        (W // 2, 175),
        "Validated against ALL 7 official Google ADK starter templates",
        fill=FG,
        font=subtitle_font,
        anchor="mm",
    )

    # Validation table
    headers = ["Template", "Resources", "Catalog gaps"]
    rows = [
        ("adk", "44", "0"),
        ("agentic_rag", "51", "0"),
        ("adk_live", "44", "0"),
        ("adk_a2a", "44", "0"),
        ("adk_go", "44", "0"),
        ("adk_java", "44", "0"),
        ("adk_ts", "44", "0"),
    ]
    col_x = [W // 2 - 320, W // 2, W // 2 + 320]
    y = 270
    for i, h in enumerate(headers):
        draw.text((col_x[i], y), h, fill=DIM, font=table_h, anchor="mm")
    y += 28
    draw.line((W // 2 - 480, y, W // 2 + 480, y), fill=DIM, width=2)
    y += 28
    for r in rows:
        for i, cell in enumerate(r):
            color = GREEN if cell == "0" else FG
            draw.text((col_x[i], y), cell, fill=color, font=table_h, anchor="mm")
        y += 44

    # Closing tagline
    y_tag = H - 280
    draw.text((W // 2, y_tag), "Stop deploying. Start shipping.", fill=FG, font=_font(48), anchor="mm")

    # URLs
    y_url = H - 180
    urls = [
        "github.com/williamomeara/iam-legend",
        "iam-legend-935195616837.us-central1.run.app",
        "github.com/williamomeara/iam-legend-validation-demo/pull/1",
    ]
    for u in urls:
        draw.text((W // 2, y_url), u, fill=ACCENT, font=url_font, anchor="mm")
        y_url += 44

    img.save(out)
    print(f"  wrote {out}")
    return out


# ─── Mermaid → PNG ────────────────────────────────────────────────────────


def render_mermaid_diagram() -> Path:
    """Extract the Mermaid diagram from docs/architecture.md and render to PNG."""
    out = BUILD / "frames" / "shot2_architecture.png"
    if out.exists():
        return out
    arch = (REPO_ROOT / "docs" / "architecture.md").read_text()
    m = re.search(r"```mermaid\n(.+?)\n```", arch, re.DOTALL)
    if not m:
        raise RuntimeError("no mermaid block found in docs/architecture.md")
    mmd_path = BUILD / "frames" / "arch.mmd"
    mmd_path.write_text(m.group(1))
    # Render via mmdc with dark theme to match our colour palette
    subprocess.run(
        [
            "mmdc",
            "-i",
            str(mmd_path),
            "-o",
            str(out),
            "-t",
            "dark",
            "-b",
            "transparent",
            "--width",
            "1800",
            "--height",
            "1000",
        ],
        check=True,
        capture_output=True,
    )
    # Pad the diagram onto a 1920x1080 canvas with a title/subtitle. Crop
    # the rendered diagram tightly to its non-transparent bounds first so it
    # fills more of the frame (mmdc adds significant whitespace padding).
    diagram = Image.open(out).convert("RGBA")
    bbox = diagram.getbbox()
    if bbox:
        diagram = diagram.crop(bbox)
    diagram.thumbnail((1800, 880))
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((W // 2, 60), "iam-legend — Architecture", fill=ACCENT, font=_font(48), anchor="mm")
    draw.text(
        (W // 2, 110),
        "One core. Three surfaces. MCP at the centre.",
        fill=DIM,
        font=_font(28),
        anchor="mm",
    )
    dx = (W - diagram.width) // 2
    canvas.paste(diagram, (dx, 150), diagram)
    canvas.save(out)
    print(f"  wrote {out}")
    return out


# ─── Browser screenshot of the live PR ─────────────────────────────────────


def capture_pr_screenshot() -> Path:
    """Headless Chromium → screenshot the latest iam-legend bot review.

    Uses the GitHub REST API to find the most recent review's id, then opens
    the PR page at that review's anchor (#pullrequestreview-<id>) and
    screenshots just the review's DOM element.
    """
    out = BUILD / "frames" / "shot3_pr.png"
    if out.exists():
        out.unlink()  # force re-capture

    # 1. Get the latest review id via the GH API
    api = subprocess.check_output(
        [
            "gh",
            "api",
            "repos/williamomeara/iam-legend-validation-demo/pulls/1/reviews",
            "--jq",
            "[.[] | select(.user.login == \"github-actions[bot]\")] | last | .id",
        ],
        text=True,
    ).strip()
    print(f"  latest bot review id: {api}")
    anchor = f"pullrequestreview-{api}"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Larger viewport + 2x device scale → ~4800x3600 raw → crisp downscale.
        page = browser.new_page(viewport={"width": 2400, "height": 1800}, device_scale_factor=2)
        url = f"https://github.com/williamomeara/iam-legend-validation-demo/pull/1#{anchor}"
        # GitHub pages have continual background activity (auto-refresh,
        # analytics) and rarely hit `networkidle`. Wait for DOM + an
        # explicit settle window instead.
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        # Locate the review's container by id and screenshot just that element
        elem = page.locator(f"#{anchor}").first
        try:
            elem.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            elem.screenshot(path=str(out))
        except Exception as e:
            print(f"  WARN: element capture failed ({e}); falling back to viewport screenshot")
            page.screenshot(path=str(out))
        browser.close()

    # Pad onto 1920x1080 with title. Lanczos resampling for sharp downscale.
    pr = Image.open(out).convert("RGB")
    pr.thumbnail((1700, 900), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (W // 2, 55),
        "Live PR review on Google's agent-starter-pack project",
        fill=ACCENT,
        font=_font(38),
        anchor="mm",
    )
    draw.text(
        (W // 2, 110),
        "github.com/williamomeara/iam-legend-validation-demo/pull/1",
        fill=DIM,
        font=_font(24, mono=True),
        anchor="mm",
    )
    canvas.paste(pr, ((W - pr.width) // 2, 150))
    canvas.save(out)
    print(f"  wrote {out}")
    return out


# ─── Assemble final video ──────────────────────────────────────────────────


def compose_video(durations: dict[str, float]) -> Path:
    """ffmpeg compositing: each shot is one image w/ ken-burns slow zoom + audio."""
    shots = [
        ("1_hook", "shot1_hook.png", durations["1_hook"]),
        ("2_what", "shot2_architecture.png", durations["2_what"]),
        ("3_hero", "shot3_pr.png", durations["3_hero"]),
        ("4_mcp", "shot4_mcp.png", durations["4_mcp"]),
        ("5_close", "shot5_close.png", durations["5_close"]),
    ]

    # 1) Render each shot to a video clip. Each clip is the audio length plus
    #    a TAIL_GAP seconds of held image + silence — gives the viewer a beat
    #    between shots so the cuts don't feel jittery.
    TAIL_GAP = 1.0
    clips: list[Path] = []
    for name, frame, dur in shots:
        clip = BUILD / f"clip_{name}.mp4"
        frame_path = BUILD / "frames" / frame
        total = dur + TAIL_GAP
        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-framerate", "30",
            "-t", f"{total:.3f}",
            "-i", str(frame_path),
            "-i", str(BUILD / "audio" / f"{name}.wav"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-vf",
            # Fade in over the first 15 frames; fade out over the last 15.
            # The fade-out sits inside the TAIL_GAP silence so it doesn't bite
            # into the spoken audio.
            f"fade=in:0:15,fade=out:{int(total * 30) - 15}:15",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            # Pad the audio with TAIL_GAP seconds of silence at the end so it
            # matches the image's extended duration.
            "-af", f"apad=pad_dur={TAIL_GAP}",
            str(clip),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        clips.append(clip)
        print(f"  clip {name}: {dur:.2f}s + {TAIL_GAP:.1f}s gap = {total:.2f}s")

    # 2) Concat the clips
    concat_list = BUILD / "concat.txt"
    concat_list.write_text("\n".join(f"file '{c}'" for c in clips))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(OUT),
        ],
        check=True,
        capture_output=True,
    )
    print(f"  wrote {OUT}")
    return OUT


# ─── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    durations = generate_audio()
    print()
    print("== Rendering visuals ==")
    # Prefer Figma-designed PNGs from /tmp/iam-legend-video/frames-figma/;
    # fall back to Pillow renders if a Figma export is missing.
    use_figma_or_render("shot1_hook.png", shot1_hook_frame)
    use_figma_or_render("shot2_architecture.png", render_mermaid_diagram)
    capture_pr_screenshot()
    use_figma_or_render("shot4_mcp.png", shot4_mcp_frame)
    use_figma_or_render("shot5_close.png", shot5_close_frame)
    print()
    print("== Composing video ==")
    out = compose_video(durations)
    total = sum(durations.values())
    print()
    print(f"== Done: {out} ({total:.1f}s) ==")


if __name__ == "__main__":
    main()
