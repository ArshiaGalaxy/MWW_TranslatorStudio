"""Django models for MWW Translator Studio."""

import uuid
from django.db import models


class Project(models.Model):
    """A comic translation project (one PDF)."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        EXTRACTING = "extracting", "Extracting OCR"
        READY = "ready", "Ready"
        TRANSLATING = "translating", "Translating"
        APPLYING = "applying", "Applying / Rendering"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    class PDFType(models.TextChoices):
        MANGA = "manga", "Manga"
        MANHWA = "manhwa", "Manhwa"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    # Link-imported projects have no uploaded PDF — pages come from
    # `sources/` instead. Blank/null allowed for `uses_page_sources` mode.
    pdf_file = models.FileField(upload_to="projects/pdfs/", blank=True, null=True)
    uses_page_sources = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    pdf_type = models.CharField(max_length=10, choices=PDFType.choices, default=PDFType.MANGA)
    chapter_id = models.CharField(max_length=100, blank=True, default="")

    # Config snapshots (per-project overrides of the global config)
    ocr_config = models.JSONField(default=dict, blank=True)
    font_config = models.JSONField(default=dict, blank=True)
    inpaint_config = models.JSONField(default=dict, blank=True)
    translator_config = models.JSONField(default=dict, blank=True)
    chapter_id_config = models.JSONField(default=dict, blank=True)

    # Extraction options
    cover_pages = models.JSONField(default=list, blank=True)
    skip_pages = models.JSONField(default=list, blank=True)

    # Metadata
    total_pages = models.IntegerField(default=0)
    total_blocks = models.IntegerField(default=0)
    translated_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    detected_mode = models.CharField(max_length=30, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def progress_percent(self):
        if self.total_blocks == 0:
            return 0
        return int(self.translated_count / self.total_blocks * 100)


class Page(models.Model):
    """A single page image from the PDF."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="pages")
    page_number = models.IntegerField()
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    is_cover = models.BooleanField(default=False)
    is_skipped = models.BooleanField(default=False)

    class Meta:
        ordering = ["page_number"]
        unique_together = ["project", "page_number"]

    def __str__(self):
        return f"Page {self.page_number} - {self.project.name}"

    @property
    def image_url(self):
        return f"/media/projects/{self.project_id}/pages/page-{self.page_number}.jpg"

    @property
    def cleaned_image_url(self):
        return f"/media/projects/{self.project_id}/cleaned/page-{self.page_number}.jpg"

    @property
    def rendered_image_url(self):
        return f"/media/projects/{self.project_id}/rendered/page-{self.page_number}.jpg"


class TextBlock(models.Model):
    """A detected text region (dialog/SFX/thinking/...) on a page."""

    class BlockType(models.TextChoices):
        DIALOG = "dialog", "Dialog"
        SFX = "sfx", "Sound Effect"
        THINKING = "thinking", "Thinking"
        ACTION = "action", "Action"
        WHISPER = "whisper", "Whisper"
        NARRATION = "narration", "Narration"
        SYSTEM = "system", "System"
        CUSTOM = "custom", "Custom"

    class Orientation(models.TextChoices):
        HORIZONTAL = "horizontal", "Horizontal"
        VERTICAL = "vertical", "Vertical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="blocks")
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="blocks")
    key = models.CharField(max_length=50)  # e.g. "p1_d1"

    original_text = models.TextField(blank=True, default="")
    translation = models.TextField(blank=True, default="")
    block_type = models.CharField(max_length=15, choices=BlockType.choices, default=BlockType.DIALOG)

    # Bounding box
    x1 = models.IntegerField(default=0)
    y1 = models.IntegerField(default=0)
    x2 = models.IntegerField(default=0)
    y2 = models.IntegerField(default=0)

    # Text line polygons
    text_boxes = models.JSONField(default=list, blank=True)

    # Per-block style overrides (empty/null = inherit from config)
    color = models.CharField(max_length=9, blank=True, default="")
    stroke_color = models.CharField(max_length=9, blank=True, default="")
    stroke_size = models.IntegerField(null=True, blank=True)
    alignment = models.CharField(max_length=10, blank=True, default="")
    font_override = models.CharField(max_length=255, blank=True, default="")
    font_size_override = models.IntegerField(null=True, blank=True)
    rotation = models.FloatField(default=0)
    orientation = models.CharField(max_length=10, choices=Orientation.choices,
                                   default=Orientation.HORIZONTAL)

    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["page__page_number", "order"]

    def __str__(self):
        return f"{self.key}: {self.original_text[:30]}"

    @property
    def is_translated(self):
        return bool(self.translation.strip())

    @property
    def font_type(self):
        if self.block_type == self.BlockType.SFX:
            return "sfx"
        if self.block_type == self.BlockType.THINKING:
            return "thinking"
        return "normal"

    def to_engine_block(self):
        """Convert to the vendored comic_translator Block dataclass."""
        from comic_translator.models import Block

        return Block(
            page=self.page.page_number,
            text=self.original_text,
            x1=self.x1, y1=self.y1, x2=self.x2, y2=self.y2,
            translation_fa=self.translation,
            sfx=self.block_type == self.BlockType.SFX,
            thinking=self.block_type == self.BlockType.THINKING,
            text_boxes=self.text_boxes or [],
            text_type=self.block_type,
            color=self.color or None,
            stroke_color=self.stroke_color or None,
            stroke_size=self.stroke_size,
            alignment=self.alignment or "",
            font_override=self.font_override or None,
            font_size_override=self.font_size_override,
            orientation=self.orientation,
            rotation=self.rotation,
        )


class Job(models.Model):
    """A long-running background job (extract / translate / apply / reocr)."""

    class Kind(models.TextChoices):
        EXTRACT = "extract", "Extract OCR"
        TRANSLATE = "translate", "Translate"
        APPLY = "apply", "Apply & Render"
        CLEAN = "clean", "Clean (Inpaint)"
        RENDER = "render", "Render Text"
        REOCR = "reocr", "Re-OCR Page"
        IMPORT_PAGES = "import_pages", "Import Pages"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    progress = models.FloatField(default=0.0)  # 0..1
    stage = models.CharField(max_length=200, blank=True, default="")
    params = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    logs = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} #{self.pk} ({self.status})"


class GlossaryEntry(models.Model):
    """Consistent name/term mapping used during auto-translation."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="glossary")
    source = models.CharField(max_length=255)
    target = models.CharField(max_length=255)

    class Meta:
        unique_together = ["project", "source"]
        ordering = ["source"]

    def __str__(self):
        return f"{self.source} → {self.target}"


class MaskMark(models.Model):
    """A freehand stroke painted on a page marking a region to erase.

    Points are [[x, y], ...] in image-pixel coordinates of the standardized
    page image. Marks are erased by the clean/apply jobs together with the
    translated block regions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="mask_marks")
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="mask_marks")
    points = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Mark {self.pk} on page {self.page.page_number} ({len(self.points)} pts)"

    @property
    def region(self) -> dict:
        """Engine-ready inpaint region: bounding box + the stroke polygon."""
        xs = [p[0] for p in self.points] or [0]
        ys = [p[1] for p in self.points] or [0]
        return {
            "x1": min(xs),
            "y1": min(ys),
            "x2": max(xs),
            "y2": max(ys),
            "text_boxes": [self.points],
        }


class GlobalSetting(models.Model):
    """Singleton key/value store for global app config."""

    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key
