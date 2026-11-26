#!/usr/bin/env python3
"""Render schematics, composite PCB views, and 3D board renders into a single PDF.

Design & Maintainability Requirements
=====================================
Functional Requirements:
  FR-1  Hierarchical Schematics: Export the root schematic (``mike_rocket.kicad_sch``)
        and all child sheets into multi-page vector PDF pages.
  FR-2  Composite PCB Views: Export single-page composite PDFs for Top Assembly
        (F.Cu, F.SilkS, F.Fab, Edge.Cuts) and Bottom Assembly (B.Cu, B.SilkS,
        B.Fab, Edge.Cuts, mirrored), plus optional inner copper layers (In1.Cu,
        In2.Cu with Edge.Cuts).
  FR-3  3D Board Renders: Generate raytraced 3D PNG renders (top and bottom) via
        ``kicad-cli pcb render`` and convert them to PDF pages.
  FR-4  Single Combined Document: Merge schematics, composite PCB views, and 3D
        renders (in that order) into one PDF (default: ``build/pdfs/mike_rocket_docs.pdf``).

Non-Functional / Maintainability Requirements:
  NFR-1 Cross-Platform & CI Ready: Run identically on Windows terminals and Linux
        CI runners. Auto-discover ``kicad-cli`` via ``KICAD_CLI``, ``PATH``, or
        standard KiCad 10 installation paths.
  NFR-2 Working-Directory Independence: Resolve all project paths relative to the
        repository root so the script can be invoked from any directory.
  NFR-3 Headless/Sandboxed Safety: Ensure KiCad has a writable config directory
        when running in restricted or CI environments.
  NFR-4 Fail-Fast Validation: Validate Python dependencies, ``kicad-cli``, and
        input files before running exports; propagate non-zero exit codes.
  NFR-5 Clean Artifacts: Store intermediate files in a temporary directory by
        default (or preserve them with ``--keep-intermediates`` for debugging).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMATIC = REPO_ROOT / "mike_rocket.kicad_sch"
DEFAULT_PCB = REPO_ROOT / "mike_rocket.kicad_pcb"
DEFAULT_OUTPUT = REPO_ROOT / "build" / "pdfs" / "mike_rocket_docs.pdf"

WINDOWS_KICAD_CANDIDATES = (
    Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
)


@dataclass(frozen=True)
class CompositeView:
    """Configuration for a single composite PCB PDF page."""

    name: str
    layers: tuple[str, ...]
    mirror: bool = False


@dataclass(frozen=True)
class RenderView:
    """Configuration for a 3D PCB raytraced render."""

    name: str
    side: str


COMPOSITE_VIEWS: tuple[CompositeView, ...] = (
    CompositeView(
        name="pcb_top_composite",
        layers=("F.Cu", "F.SilkS", "F.Fab", "Edge.Cuts"),
        mirror=False,
    ),
    CompositeView(
        name="pcb_bottom_composite",
        layers=("B.Cu", "B.SilkS", "B.Fab", "Edge.Cuts"),
        mirror=True,
    ),
)

INNER_COPPER_LAYERS: tuple[str, ...] = ("In1.Cu", "In2.Cu")

RENDER_VIEWS: tuple[RenderView, ...] = (
    RenderView(name="pcb_3d_top", side="top"),
    RenderView(name="pcb_3d_bottom", side="bottom"),
)


def check_python_dependencies() -> tuple[object, object]:
    """Verify required third-party Python packages are importable."""
    missing: list[str] = []
    try:
        from pypdf import PdfWriter  # type: ignore[import-not-found]
    except ImportError:
        PdfWriter = None  # type: ignore[assignment]
        missing.append("pypdf")

    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        Image = None  # type: ignore[assignment]
        missing.append("pillow")

    if missing:
        req_file = Path(__file__).resolve().parent / "requirements.txt"
        raise RuntimeError(
            f"Missing required Python package(s): {', '.join(missing)}.\n"
            f"Install them with: pip install -r {req_file}"
        )

    return PdfWriter, Image


def find_kicad_cli() -> Path:
    """Locate the kicad-cli executable across CI and local environments."""
    env_override = os.environ.get("KICAD_CLI")
    if env_override:
        candidate = Path(env_override)
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"KICAD_CLI points to missing file: {candidate}")

    on_path = shutil.which("kicad-cli")
    if on_path:
        return Path(on_path)

    for candidate in WINDOWS_KICAD_CANDIDATES:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find 'kicad-cli'. Add KiCad's bin directory to PATH or set KICAD_CLI."
    )


def build_kicad_env(temp_dir: Path) -> dict[str, str]:
    """Return environment variables with a writable KiCad config directory if needed."""
    env = os.environ.copy()
    if "KICAD_CONFIG_HOME" not in env:
        config_dir = temp_dir / "kicad_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        env["KICAD_CONFIG_HOME"] = str(config_dir)
    return env


def run_kicad_cli(kicad_cli: Path, args: list[str], env: dict[str, str]) -> None:
    """Execute a kicad-cli subcommand and raise on non-zero exit."""
    cmd = [str(kicad_cli), *args]
    print(f"[render] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"kicad-cli exited with code {result.returncode}: {' '.join(cmd)}")


def export_schematics_pdf(
    kicad_cli: Path,
    schematic: Path,
    out_pdf: Path,
    env: dict[str, str],
    *,
    black_and_white: bool,
    theme: str | None,
    rev: str | None,
) -> Path:
    """Export the full hierarchical schematic to a multi-page PDF."""
    args = ["sch", "export", "pdf", "--output", str(out_pdf)]
    if black_and_white:
        args.append("--black-and-white")
    if theme:
        args.extend(["--theme", theme])
    if rev:
        args.extend(["--define-var", f"REV={rev}"])
    args.append(str(schematic))

    run_kicad_cli(kicad_cli, args, env)
    return out_pdf


def export_pcb_composites(
    kicad_cli: Path,
    pcb: Path,
    work_dir: Path,
    env: dict[str, str],
    *,
    black_and_white: bool,
    theme: str | None,
    rev: str | None,
    include_inner: bool,
) -> list[Path]:
    """Export composite Top/Bottom PCB PDFs and optional inner copper layers."""
    generated: list[Path] = []
    common_flags: list[str] = ["--include-border-title"]
    if black_and_white:
        common_flags.append("--black-and-white")
    if theme:
        common_flags.extend(["--theme", theme])
    if rev:
        common_flags.extend(["--define-var", f"REV={rev}"])

    for view in COMPOSITE_VIEWS:
        out_pdf = work_dir / f"{view.name}.pdf"
        args = [
            "pcb",
            "export",
            "pdf",
            "--mode-single",
            "--layers",
            ",".join(view.layers),
            *common_flags,
        ]
        if view.mirror:
            args.append("--mirror")
        args.extend(["--output", str(out_pdf), str(pcb)])
        run_kicad_cli(kicad_cli, args, env)
        generated.append(out_pdf)

    if include_inner and INNER_COPPER_LAYERS:
        inner_pdf = work_dir / "pcb_inner_layers.pdf"
        args = [
            "pcb",
            "export",
            "pdf",
            "--mode-multipage",
            "--layers",
            ",".join(INNER_COPPER_LAYERS),
            "--common-layers",
            "Edge.Cuts",
            *common_flags,
            "--output",
            str(inner_pdf),
            str(pcb),
        ]
        run_kicad_cli(kicad_cli, args, env)
        generated.append(inner_pdf)

    return generated


def export_3d_render_pdfs(
    kicad_cli: Path,
    pcb: Path,
    work_dir: Path,
    env: dict[str, str],
    image_cls: object,
    *,
    width: int,
    height: int,
    quality: str,
) -> list[Path]:
    """Render 3D board views as PNGs and convert each to a PDF page."""
    generated: list[Path] = []
    for view in RENDER_VIEWS:
        png_path = work_dir / f"{view.name}.png"
        pdf_path = work_dir / f"{view.name}.pdf"
        args = [
            "pcb",
            "render",
            "--output",
            str(png_path),
            "--side",
            view.side,
            "--quality",
            quality,
            "--width",
            str(width),
            "--height",
            str(height),
            "--background",
            "opaque",
            str(pcb),
        ]
        run_kicad_cli(kicad_cli, args, env)

        with image_cls.open(png_path) as img:  # type: ignore[attr-defined]
            rgb_img = img.convert("RGB")
            rgb_img.save(pdf_path, "PDF", resolution=300.0)
        generated.append(pdf_path)

    return generated


def merge_pdfs(pdf_writer_cls: object, pdf_paths: list[Path], output_path: Path) -> None:
    """Merge PDF files in order into a single output PDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pdf_writer_cls()  # type: ignore[operator]
    for pdf_path in pdf_paths:
        writer.append(str(pdf_path))
    with output_path.open("wb") as handle:
        writer.write(handle)
    print(f"[render] Wrote combined PDF: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render KiCad schematics, composite PCB views, and 3D renders into one PDF."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output combined PDF path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--schematic",
        type=Path,
        default=DEFAULT_SCHEMATIC,
        help=f"Root schematic file (default: {DEFAULT_SCHEMATIC})",
    )
    parser.add_argument(
        "--pcb",
        type=Path,
        default=DEFAULT_PCB,
        help=f"PCB layout file (default: {DEFAULT_PCB})",
    )
    parser.add_argument(
        "--bw",
        action="store_true",
        help="Export schematics and 2D PCB layers in black and white.",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="Optional KiCad color theme name for 2D exports.",
    )
    parser.add_argument(
        "--rev",
        default=None,
        help="Optional revision/commit string passed via '--define-var REV=...'.",
    )
    parser.add_argument(
        "--include-inner",
        action="store_true",
        help="Also include individual pages for inner copper layers (In1.Cu, In2.Cu).",
    )
    parser.add_argument(
        "--skip-3d",
        action="store_true",
        help="Skip 3D raytraced board renders.",
    )
    parser.add_argument(
        "--render-quality",
        choices=("basic", "high", "user"),
        default="high",
        help="3D raytracing quality for kicad-cli pcb render (default: high).",
    )
    parser.add_argument(
        "--render-size",
        type=int,
        nargs=2,
        metavar=("WIDTH", "HEIGHT"),
        default=(2400, 1800),
        help="3D render pixel dimensions (default: 2400 1800).",
    )
    parser.add_argument(
        "--keep-intermediates",
        type=Path,
        default=None,
        help="Optional directory to keep intermediate PDFs and 3D PNGs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pdf_writer_cls, image_cls = check_python_dependencies()
        kicad_cli = find_kicad_cli()

        schematic = args.schematic.resolve()
        pcb = args.pcb.resolve()
        output_pdf = args.output.resolve()

        if not schematic.is_file():
            raise FileNotFoundError(f"Schematic file not found: {schematic}")
        if not pcb.is_file():
            raise FileNotFoundError(f"PCB file not found: {pcb}")

        if args.keep_intermediates:
            work_dir = args.keep_intermediates.resolve()
            work_dir.mkdir(parents=True, exist_ok=True)
            temp_ctx = None
        else:
            temp_ctx = tempfile.TemporaryDirectory(prefix="kicad_render_")
            work_dir = Path(temp_ctx.name)

        try:
            env = build_kicad_env(work_dir)
            parts: list[Path] = []

            parts.append(
                export_schematics_pdf(
                    kicad_cli,
                    schematic,
                    work_dir / "01_schematics.pdf",
                    env,
                    black_and_white=args.bw,
                    theme=args.theme,
                    rev=args.rev,
                )
            )

            parts.extend(
                export_pcb_composites(
                    kicad_cli,
                    pcb,
                    work_dir,
                    env,
                    black_and_white=args.bw,
                    theme=args.theme,
                    rev=args.rev,
                    include_inner=args.include_inner,
                )
            )

            if not args.skip_3d:
                width, height = args.render_size
                parts.extend(
                    export_3d_render_pdfs(
                        kicad_cli,
                        pcb,
                        work_dir,
                        env,
                        image_cls,
                        width=width,
                        height=height,
                        quality=args.render_quality,
                    )
                )

            merge_pdfs(pdf_writer_cls, parts, output_pdf)
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()

    except Exception as exc:
        print(f"[render] ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
