"""DRF serializers for MWW Translator Studio."""

from pathlib import Path
import math
import re

from rest_framework import serializers

from .models import Project, Page, TextBlock, Job, MaskMark


def _validate_rotation(value: float) -> float:
    """Rotation in degrees, clockwise, bounded to [-180, 180]."""
    if value is None:
        return 0.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError("rotation must be a number.")
    if not math.isfinite(value):
        raise serializers.ValidationError("rotation must be finite.")
    if value < -180 or value > 180:
        raise serializers.ValidationError(
            "rotation must be between -180 and 180 degrees.")
    return value


class TextBlockSerializer(serializers.ModelSerializer):
    is_translated = serializers.BooleanField(read_only=True)
    font_type = serializers.CharField(read_only=True)
    page_number = serializers.IntegerField(source="page.page_number", read_only=True)

    class Meta:
        model = TextBlock
        fields = [
            "id", "key", "page_number", "original_text", "translation",
            "block_type", "x1", "y1", "x2", "y2", "text_boxes",
            "color", "stroke_color", "stroke_size", "alignment",
            "font_override", "font_size_override", "orientation", "rotation",
            "order", "is_translated", "font_type",
        ]

    def validate_rotation(self, value):
        return _validate_rotation(value)

    def validate_block_type(self, value):
        if value not in TextBlock.BlockType.values:
            raise serializers.ValidationError(f"Invalid block type: {value}")
        return value


class TextBlockCreateSerializer(serializers.Serializer):
    """Payload for manually adding a text block on a page."""

    page_number = serializers.IntegerField()
    original_text = serializers.CharField(required=False, allow_blank=True, default="")
    translation = serializers.CharField(required=False, allow_blank=True, default="")
    block_type = serializers.ChoiceField(
        choices=TextBlock.BlockType.choices, required=False)
    x1 = serializers.IntegerField(default=0)
    y1 = serializers.IntegerField(default=0)
    x2 = serializers.IntegerField(default=200)
    y2 = serializers.IntegerField(default=80)

    def validate(self, attrs):
        if attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError({"x2": "x2 must be greater than x1"})
        if attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError({"y2": "y2 must be greater than y1"})
        return attrs


class TextBlockUpdateSerializer(serializers.ModelSerializer):
    """Partial update for text blocks."""

    class Meta:
        model = TextBlock
        fields = [
            "translation", "block_type",
            "x1", "y1", "x2", "y2",
            "color", "stroke_color", "stroke_size", "alignment",
            "font_override", "font_size_override", "orientation", "rotation",
            "original_text",
        ]
        extra_kwargs = {f: {"required": False} for f in fields}

    def validate_rotation(self, value):
        return _validate_rotation(value)

    def validate_font_override(self, value):
        # font_override is handed straight to ImageFont.truetype by the
        # renderer — constrain it to fonts actually shipped in FONTS_DIR and
        # normalize to an absolute path so rendering keeps working.
        if not value:
            return value
        from django.conf import settings

        fonts_dir = Path(settings.FONTS_DIR).resolve()
        candidate = Path(str(value))
        name = candidate.name
        resolved = (candidate if candidate.is_absolute() else fonts_dir / name)
        try:
            resolved = resolved.resolve()
        except OSError:
            raise serializers.ValidationError("Invalid font path.")
        if not (resolved.is_file() and resolved.is_relative_to(fonts_dir)):
            raise serializers.ValidationError(
                "font_override must name a font inside the studio fonts "
                "directory.")
        return str(resolved)

    def validate(self, attrs):
        # Geometry sanity: reject inverted boxes when the PATCH supplies both
        # corners of an axis. (Don't fall back to stored values — blocks can
        # legitimately exist with default 0,0,0,0 geometry, and translation-
        # only patches must not trip geometry checks.)
        if None not in (attrs.get("x1"), attrs.get("x2")) and attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError({"x2": "x2 must be greater than x1"})
        if None not in (attrs.get("y1"), attrs.get("y2")) and attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError({"y2": "y2 must be greater than y1"})
        return attrs


class PreviewBlockSerializer(TextBlockUpdateSerializer):
    id = serializers.UUIDField()
    translation = serializers.CharField(max_length=20000, allow_blank=True, trim_whitespace=False)
    x1 = serializers.IntegerField(min_value=0, max_value=100000)
    y1 = serializers.IntegerField(min_value=0, max_value=100000)
    x2 = serializers.IntegerField(min_value=1, max_value=100000)
    y2 = serializers.IntegerField(min_value=1, max_value=100000)
    font_size_override = serializers.IntegerField(required=False, allow_null=True, min_value=6, max_value=120)

    class Meta(TextBlockUpdateSerializer.Meta):
        fields = ["id", "translation", "block_type", "x1", "y1", "x2", "y2",
                  "font_override", "font_size_override", "alignment", "rotation"]
        extra_kwargs = {f: {"required": False} for f in fields
                        if f not in ("id", "translation", "x1", "y1", "x2", "y2")}


class PreviewLayoutSerializer(serializers.Serializer):
    page_number = serializers.IntegerField(min_value=1)
    blocks = PreviewBlockSerializer(many=True, max_length=100, allow_empty=False)

    def validate_blocks(self, value):
        ids = [item["id"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate block IDs.")
        return value


class PageSerializer(serializers.ModelSerializer):
    image_url = serializers.CharField(read_only=True)
    cleaned_image_url = serializers.SerializerMethodField()
    rendered_image_url = serializers.SerializerMethodField()
    block_count = serializers.SerializerMethodField()
    translated_count = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "id", "page_number", "width", "height",
            "is_cover", "is_skipped",
            "image_url", "cleaned_image_url", "rendered_image_url",
            "block_count", "translated_count",
        ]

    def _variant(self, obj: Page, subdir: str) -> str:
        import os

        from django.conf import settings

        path = (Path(settings.MEDIA_ROOT) / "projects" / str(obj.project_id)
                / subdir / f"page-{obj.page_number}.jpg")
        return (obj.cleaned_image_url if subdir == "cleaned"
                else obj.rendered_image_url) if os.path.exists(path) else ""

    def get_cleaned_image_url(self, obj):
        return self._variant(obj, "cleaned")

    def get_rendered_image_url(self, obj):
        return self._variant(obj, "rendered")

    def get_block_count(self, obj):
        annotated = getattr(obj, "block_count_annotated", None)
        return annotated if annotated is not None else obj.blocks.count()

    def get_translated_count(self, obj):
        annotated = getattr(obj, "translated_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.blocks.filter(translation__gt="").count()


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "project", "kind", "status", "progress", "stage",
            "params", "result", "logs", "error_message",
            "created_at", "updated_at", "finished_at",
        ]


class ProjectListSerializer(serializers.ModelSerializer):
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "status", "pdf_type", "chapter_id",
            "total_pages", "total_blocks", "translated_count",
            "progress_percent", "detected_mode",
            "error_message", "created_at", "updated_at", "uses_page_sources",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    pages = PageSerializer(many=True, read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    active_job = serializers.SerializerMethodField()
    class Meta:
        model = Project
        fields = [
            "id", "name", "status", "pdf_type", "chapter_id",
            "pdf_file", "total_pages", "total_blocks", "translated_count",
            "progress_percent", "detected_mode", "error_message",
            "cover_pages", "skip_pages", "uses_page_sources",
            "ocr_config", "font_config", "inpaint_config",
            "translator_config", "chapter_id_config",
            "active_job", "pages", "created_at", "updated_at",
        ]

    def get_active_job(self, obj):
        # Return the LATEST job regardless of status so the frontend can see
        # the success/failed transition (it decides what is "active").
        job = obj.jobs.first()
        return JobSerializer(job).data if job else None


class ChapterDiscoverySerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)


class ChapterImportSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500000)
    indices = serializers.ListField(child=serializers.IntegerField(min_value=0),
                                   min_length=1, max_length=300)


class PageCropSerializer(serializers.Serializer):
    """Crop rectangle in image-pixel coordinates (inclusive-exclusive)."""

    x1 = serializers.IntegerField(min_value=0, max_value=100000)
    y1 = serializers.IntegerField(min_value=0, max_value=100000)
    x2 = serializers.IntegerField(min_value=1, max_value=100000)
    y2 = serializers.IntegerField(min_value=1, max_value=100000)

    def validate(self, attrs):
        if attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError({"x2": "x2 must be greater than x1"})
        if attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError({"y2": "y2 must be greater than y1"})
        return attrs


def _safe_filename(raw: str) -> str:
    """Make a client upload name safe for storage on any OS.

    Drops path components, replaces Windows-illegal characters and control
    codes, and caps the basename at 80 chars so the full
    `projects/pdfs/<name>` value stays within the FileField max_length=100.
    """
    base = Path(str(raw or "")).name
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip()
    safe = safe.strip(".")
    if len(safe) > 80:
        stem, dot, ext = safe.rpartition(".")
        safe = (stem[:80] + dot + ext) if dot else safe[:80]
    return safe or "upload.pdf"


class ProjectCreateSerializer(serializers.ModelSerializer):
    uses_page_sources = serializers.BooleanField(required=False, default=False)
    source_url = serializers.URLField(required=False, max_length=2048, allow_blank=True)

    class Meta:
        model = Project
        fields = ["name", "pdf_file", "pdf_type", "chapter_id", "uses_page_sources", "source_url"]

    def to_internal_value(self, data):
        # Sanitize the client filename BEFORE field validators run: the
        # FileField's max_length=100 counts the whole `projects/pdfs/<name>`
        # value, and Django's storage does not strip Windows-illegal
        # characters (`:`, `?`, … — common in manga chapter titles), which
        # used to fail the upload (400 on length, OSError/500 on save).
        try:
            pdf = data.get("pdf_file")
        except Exception:
            pdf = None
        if pdf is not None and getattr(pdf, "name", None):
            pdf.name = _safe_filename(pdf.name)
        return super().to_internal_value(data)

    def validate(self, attrs):
        uses_page_sources = attrs.get("uses_page_sources", False)
        pdf_file = attrs.get("pdf_file")

        if uses_page_sources:
            # When using page sources (link), pdf_file is not required
            if not pdf_file:
                attrs["pdf_file"] = None
        else:
            # Traditional PDF upload requires a PDF file
            if not pdf_file:
                raise serializers.ValidationError({"pdf_file": "PDF file is required."})

        return attrs

    def create(self, validated_data):
        # `source_url` is write-only transport for the view (stored into
        # chapter_id_config there) — it is not a Project model field.
        validated_data.pop("source_url", None)
        return super().create(validated_data)

    def validate_pdf_file(self, value):
        """Only real PDFs: uploaded files are later served from /media and
        must never be HTML/SVG (stored XSS) or arbitrary executables.

        The declared Content-Type is client-controlled and adds nothing, so
        the gate is the .pdf extension plus the %PDF- magic bytes.
        (Filename safety is handled earlier in to_internal_value.)
        """
        if value is None:
            return value
        value.name = _safe_filename(value.name)
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError(
                "Only .pdf files are accepted.")
        header = b""
        try:
            pos = value.tell()
            value.seek(0)
            header = value.read(5)
            value.seek(pos)
        except (OSError, ValueError):
            pass
        if header and header != b"%PDF-":
            raise serializers.ValidationError(
                "File content is not a valid PDF.")
        return value


class ProjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["name", "chapter_id", "cover_pages", "skip_pages"]


class MaskMarkSerializer(serializers.ModelSerializer):
    page_number = serializers.IntegerField(source="page.page_number", read_only=True)

    class Meta:
        model = MaskMark
        fields = ["id", "page_number", "points", "created_at"]


class MaskMarkCreateSerializer(serializers.ModelSerializer):
    """Create payload: page_number + stroke points in image-pixel coords."""

    page_number = serializers.IntegerField()

    class Meta:
        model = MaskMark
        fields = ["page_number", "points"]

    def validate_points(self, value):
        MAX_POINTS = 2000
        MAX_COORD = 100_000
        if (
            not isinstance(value, list)
            or len(value) < 3
            or len(value) > MAX_POINTS
            or not all(
                isinstance(p, (list, tuple))
                and len(p) == 2
                and all(isinstance(c, int) for c in p)
                and all(-MAX_COORD <= c <= MAX_COORD for c in p)
                for p in value
            )
        ):
            raise serializers.ValidationError(
                f"points must be a list of 3..{MAX_POINTS} [x, y] integer "
                f"pairs with coordinates within ±{MAX_COORD}"
            )
        return value


class ExtractParamsSerializer(serializers.Serializer):
    covers = serializers.ListField(child=serializers.IntegerField(), required=False, default=None)
    skip_pages = serializers.ListField(child=serializers.IntegerField(), required=False, default=None)
    pdf_type = serializers.ChoiceField(choices=Project.PDFType.choices, required=False)
    standard_max_side = serializers.IntegerField(required=False)
    ocr_version = serializers.ChoiceField(
        choices=["PP-OCRv6", "PP-OCRv5", "PP-OCRv4", "PP-OCRv3"], required=False
    )


class TranslateParamsSerializer(serializers.Serializer):
    block_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    force = serializers.BooleanField(required=False, default=False)
    provider = serializers.ChoiceField(
        choices=["gemini", "openrouter", "custom"], required=False
    )


class ApplyParamsSerializer(serializers.Serializer):
    chapter_id = serializers.CharField(required=False, allow_blank=True, default="")
    formats = serializers.ListField(
        child=serializers.ChoiceField(choices=["pdf", "zip", "psd"]),
        required=False,
    )
