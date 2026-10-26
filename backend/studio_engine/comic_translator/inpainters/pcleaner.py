"""PanelCleaner subprocess inpainting backend.

Delegates the full cleaning pipeline (text detection + masking + inpainting)
to PanelCleaner (pcleaner) via CLI subprocess. Requires `pcleaner` to be
installed separately: pip install pcleaner
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from comic_translator.inpainters.base import InpainterBackend

logger = logging.getLogger(__name__)

_OUTPUT_DIR_NAME = "cleaned"


class PcleanerBackend(InpainterBackend):
    """PanelCleaner inpainting via CLI subprocess.

    Runs the full PanelCleaner pipeline (text detection, masking, inpainting)
    on each image using the `pcleaner clean` command. Best for CPU use since
    PanelCleaner manages its own model loading and torch resources.
    """

    @property
    def name(self) -> str:
        return "pcleaner"

    @property
    def is_neural(self) -> bool:
        return False

    def load(self, cli_path: str | None = None, **kwargs) -> None:
        """Verify that the pcleaner CLI is available."""
        self._cli_path = self._find_cli(cli_path)

    @staticmethod
    def _find_cli(cli_path: str | None = None) -> str:
        """Locate the pcleaner CLI executable."""
        if cli_path and Path(cli_path).is_file():
            return cli_path

        # Try PATH lookup
        found = shutil.which("pcleaner")
        if found:
            return found

        # Try python -m pcleaner as fallback
        try:
            subprocess.run(
                [shutil.which("python") or "python", "-m", "pcleaner", "--version"],
                capture_output=True,
                timeout=15,
                check=True,
            )
            return "__python_module__"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        raise FileNotFoundError(
            "PanelCleaner CLI not found. Install it with:\n"
            "  pip install pcleaner\n"
            "Or specify the path in config: \"pcleaner_cli_path\": \"/path/to/pcleaner\""
        )

    def _run_clean(self, image_path: Path, output_dir: Path, profile: str | None) -> Path:
        """Run `pcleaner clean` on a single image, return path to cleaned output."""
        cmd = [self._cli_path]

        if self._cli_path == "__python_module__":
            cmd = [shutil.which("python") or "python", "-m", "pcleaner"]

        cmd.extend([
            "clean",
            str(image_path),
            "-c",  # --save-only-cleaned
            "-o", str(output_dir),
            "-a",  # hide analytics
        ])

        if profile:
            cmd.extend(["-p", profile])

        logger.info("Running PanelCleaner: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                check=True,
            )
            if result.stderr:
                logger.debug("PanelCleaner stderr: %s", result.stderr[:2000])
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "PanelCleaner timed out after 600s. "
                "The image may be too large or the system too slow."
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"PanelCleaner failed (exit code {e.returncode}):\n"
                f"{e.stderr[:1000] if e.stderr else 'No error output'}"
            ) from e

        # Find the output file — PanelCleaner puts it in output_dir/cleaned/
        cleaned_dir = output_dir / _OUTPUT_DIR_NAME
        if not cleaned_dir.exists():
            # PanelCleaner may output directly to output_dir
            cleaned_dir = output_dir

        stem = image_path.stem
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"):
            candidate = cleaned_dir / f"{stem}{ext}"
            if candidate.exists():
                return candidate

        # Try any file in the cleaned directory
        if cleaned_dir.exists():
            files = list(cleaned_dir.iterdir())
            if files:
                return files[0]

        raise FileNotFoundError(
            f"PanelCleaner did not produce output for {image_path.name}. "
            f"Checked: {cleaned_dir}"
        )

    def inpaint_single(
        self,
        image: Image.Image,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        text_boxes: list | None = None,
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        pcleaner_profile: str | None = None,
        **kwargs,
    ) -> Image.Image:
        """Inpaint a single region via PanelCleaner.

        PanelCleaner runs its own text detection + masking + inpainting pipeline,
        so the coordinates (x1, y1, x2, y2) are noted but PanelCleaner decides
        what to clean based on its own detection.
        """
        with tempfile.TemporaryDirectory(prefix="pcleaner_") as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.png"
            output_path = tmp_path / "output"
            output_path.mkdir()

            # Convert to RGB if needed (PanelCleaner expects standard formats)
            img = image.convert("RGB")
            img.save(str(input_path), "PNG")

            cleaned_path = self._run_clean(input_path, output_path, pcleaner_profile)
            cleaned = Image.open(cleaned_path).convert("RGB")

            # Resize to match original in case PanelCleaner changed dimensions
            if cleaned.size != image.size:
                cleaned = cleaned.resize(image.size, Image.LANCZOS)

            # Restore alpha channel if original had one
            if image.mode == "RGBA":
                cleaned = cleaned.convert("RGBA")
                cleaned.putalpha(image.split()[3])

            return cleaned

    def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[dict],
        pad: int = 30,
        pad_x: int = 30,
        pad_y: int = 30,
        pcleaner_profile: str | None = None,
        **kwargs,
    ) -> Image.Image:
        """Inpaint multiple regions via PanelCleaner.

        PanelCleaner processes the entire image at once (detecting and cleaning
        all text), so we pass the full image and let it handle everything.
        """
        with tempfile.TemporaryDirectory(prefix="pcleaner_") as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.png"
            output_path = tmp_path / "output"
            output_path.mkdir()

            img = image.convert("RGB")
            img.save(str(input_path), "PNG")

            cleaned_path = self._run_clean(input_path, output_path, pcleaner_profile)
            cleaned = Image.open(cleaned_path).convert("RGB")

            if cleaned.size != image.size:
                cleaned = cleaned.resize(image.size, Image.LANCZOS)

            if image.mode == "RGBA":
                cleaned = cleaned.convert("RGBA")
                cleaned.putalpha(image.split()[3])

            return cleaned
