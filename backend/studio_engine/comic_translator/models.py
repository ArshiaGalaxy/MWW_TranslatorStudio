"""Data models for block dictionaries used throughout the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OCRItem:
    """Raw output from PaddleOCR for a single text line."""

    text: str
    box: list[list[int]]
    cx: float
    cy: float
    height: int
    confidence: float = 1.0
    page: int | None = None
    orientation: str = "horizontal"


@dataclass
class OCRDialog:
    """A clustered dialog region detected by OCR (before page assignment)."""

    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    sfx: bool
    text_boxes: list[list[tuple[int, int]]]
    orientation: str = "horizontal"


@dataclass
class Block:
    """Canonical block representing a single dialog/SFX on a page."""

    page: int
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    translation_fa: str = ""
    cover: bool = False
    sfx: bool = False
    thinking: bool = False
    text_boxes: list[list[tuple[int, int]]] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    continuation_page: int = 0

    text_type: str = "dialog"
    color: str | None = None
    stroke_color: str | None = None
    stroke_size: int | None = None
    alignment: str = "center"
    font_override: str | None = None
    font_size_override: int | None = None
    rotation: float = 0.0
    orientation: str = "horizontal"

    def __post_init__(self) -> None:
        if not self.pages:
            self.pages = [self.page]
        # Backward compat: derive text_type from legacy booleans
        if self.text_type == "dialog":
            if self.sfx:
                self.text_type = "sfx"
            elif self.thinking:
                self.text_type = "think"
        # Sync legacy booleans from text_type
        self.sfx = self.text_type == "sfx"
        self.thinking = self.text_type == "think"

    @property
    def font_type(self) -> str:
        return _FONT_TYPE_MAP.get(self.text_type, "normal")

    @property
    def is_sfx(self) -> bool:
        return self.text_type == "sfx"

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "text": self.text,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "translation_fa": self.translation_fa,
            "cover": self.cover,
            "sfx": self.sfx,
            "thinking": self.thinking,
            "text_boxes": self.text_boxes,
            "pages": self.pages,
            "continuation_page": self.continuation_page,
            "text_type": self.text_type,
            "color": self.color,
            "stroke_color": self.stroke_color,
            "stroke_size": self.stroke_size,
            "alignment": self.alignment,
            "font_override": self.font_override,
            "font_size_override": self.font_size_override,
            "orientation": self.orientation,
            "rotation": self.rotation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Block:
        blk = cls(
            page=d["page"],
            text=d["text"],
            x1=d["x1"],
            y1=d["y1"],
            x2=d["x2"],
            y2=d["y2"],
            translation_fa=d.get("translation_fa", ""),
            cover=d.get("cover", False),
            sfx=d.get("sfx", False),
            thinking=d.get("thinking", False),
            text_boxes=d.get("text_boxes", []),
            pages=d.get("pages", []),
            continuation_page=d.get("continuation_page", 0),
            text_type=d.get("text_type", "dialog"),
            color=d.get("color"),
            stroke_color=d.get("stroke_color"),
            stroke_size=d.get("stroke_size"),
            alignment=d.get("alignment", "center"),
            font_override=d.get("font_override"),
            font_size_override=d.get("font_size_override"),
            orientation=d.get("orientation", "horizontal"),
            rotation=d.get("rotation", 0.0),
        )
        if not blk.pages:
            blk.pages = [blk.page]
        # Backward compat
        if blk.text_type == "dialog":
            if blk.sfx:
                blk.text_type = "sfx"
            elif blk.thinking:
                blk.text_type = "think"
        # Sync legacy booleans
        blk.sfx = blk.text_type == "sfx"
        blk.thinking = blk.text_type == "think"
        return blk

    @classmethod
    def from_ocr(cls, page: int, dialog: OCRDialog | dict) -> Block:
        if isinstance(dialog, dict):
            dialog = OCRDialog(**dialog)
        return cls(
            page=page,
            text=dialog.text,
            x1=dialog.x1,
            y1=dialog.y1,
            x2=dialog.x2,
            y2=dialog.y2,
            translation_fa=dialog.text if dialog.sfx else "",
            cover=False,
            sfx=dialog.sfx,
            thinking=False,
            text_boxes=dialog.text_boxes,
            text_type="sfx" if dialog.sfx else "dialog",
            orientation=dialog.orientation,
        )

    @property
    def region(self) -> dict:
        """Return the subset dict expected by inpaint batch functions."""
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "text_boxes": self.text_boxes,
        }


_FONT_TYPE_MAP: dict[str, str] = {
    "dialog": "normal",
    "sfx": "sfx",
    "think": "thinking",
    "action": "normal",
    "whisper": "normal",
    "narration": "normal",
    "system": "normal",
    "custom": "normal",
}
