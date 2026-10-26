"""Centralized typography rules specification for the rendered-text subsystem.

STATUS: SPECIFICATION ONLY.

This module defines the *rules and recommended defaults* for how translated
text will be typeset by the future renderer.  It deliberately contains NO
rendering logic: no layout search, no font-size optimization, no image
drawing, no OCR, no translation, no inpainting and no SFX handling.

The rules are isolated so the future renderer can consume a single
:class:`TypographyRules` object produced by :func:`build_typography_rules`.

SFX / sound effects / onomatopoeia are entirely OUTSIDE this specification.
An OCR item classified as SFX must be ignored by the translated-text rendering
pipeline, so the style table below contains NO SFX style and the legacy
``"sfx"`` text type is explicitly mapped to ``None`` (must not be rendered).

Core principle enforced throughout::

    READABILITY > BUBBLE OCCUPANCY > DECORATIVE STYLE

The renderer must never make text unreadably small simply to force it into a
bubble.  Font-size reduction is one of the LAST adjustments; the renderer
should first improve wrapping and spacing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

# ── Enumerations ─────────────────────────────────────────────────────────────


class TextStyle(str, Enum):
    """The text styles supported by the translated-text rendering pipeline.

    NOTE: there is deliberately no ``SFX`` style here.  SFX is outside the
    rendering system and must be ignored by the pipeline.
    """

    NORMAL_DIALOGUE = "normal_dialogue"
    SHOUT = "shout"
    WHISPER = "whisper"
    THOUGHT = "thought"
    NARRATION = "narration"
    CAPTION = "caption"
    SYSTEM_MESSAGE = "system_message"
    MONSTER_VOICE = "monster_voice"
    EMPHASIS = "emphasis"


ALL_TEXT_STYLES: tuple[TextStyle, ...] = tuple(TextStyle)


class BubbleShape(str, Enum):
    """Classification of the region the text must be rendered inside."""

    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    ROUNDED_RECT = "rounded_rect"
    RECT = "rect"
    IRREGULAR = "irregular"


class HorizontalAlign(str, Enum):
    CENTER = "center"
    RIGHT = "right"
    LEFT = "left"


class VerticalAlign(str, Enum):
    """Vertical alignment applies to the ENTIRE multiline block, never per line."""

    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"


class FittingStep(str, Enum):
    """Ordered steps the renderer must follow when fitting text into a region."""

    PRESERVE_MEANING = "preserve_meaning"
    PRESERVE_READABILITY = "preserve_readability"
    CORRECT_RTL = "correct_rtl_ltr"
    SELECT_STYLE = "select_style"
    SAFE_AREA = "safe_area"
    CHOOSE_FONT = "choose_font"
    FONT_SIZE = "font_size"
    WRAP = "wrap"
    BALANCE = "balance"
    LINE_SPACING = "line_spacing"
    PADDING = "padding"
    FONT_SIZE_AGAIN = "font_size_again"
    REJECT = "reject_for_review"


class PriorityLevel(str, Enum):
    """Strict priority hierarchy for typography decisions."""

    MEANING = "meaning_preservation"
    READABILITY = "readability"
    RTL = "rtl_ltr_correctness"
    SHAPING = "text_shaping"
    WRAPPING = "natural_wrapping"
    BUBBLE_BALANCE = "bubble_balance"
    FONT_CONSISTENCY = "font_consistency"
    VISUAL_STYLE = "visual_style"
    DECORATION = "decorative_effects"


class BadRender(str, Enum):
    """Conditions that make a render unacceptable."""

    TEXT_TOUCHES_BORDER = "text_touches_bubble_border"
    TEXT_CROSSES_BOUNDARY = "text_crosses_bubble_boundary"
    CLIPPING = "text_clipping"
    OVERFLOW = "text_overflow"
    UNREADABLY_SMALL = "unreadably_small_font"
    EXCESSIVELY_LARGE = "excessively_large_font"
    EXCESSIVE_EMPTY_SPACE = "excessive_empty_space"
    EXCESSIVE_DENSITY = "excessive_text_density"
    AWKWARD_LINE_BREAK = "awkward_line_break"
    ISOLATED_FINAL_WORD = "isolated_final_word"
    UNEVEN_LINES = "extremely_uneven_lines"
    WRONG_RTL_ORDER = "incorrect_rtl_order"
    WRONG_PUNCTUATION = "incorrect_punctuation_placement"
    EXCESSIVE_LINE_SPACING = "excessive_line_spacing"
    EXCESSIVE_LETTER_SPACING = "excessive_letter_spacing"
    EXCESSIVE_OUTLINE = "excessive_outline"
    EXCESSIVE_SHADOW = "excessive_shadow"
    MISSING_GLYPHS = "missing_glyphs"
    INCONSISTENT_FONT = "inconsistent_font_usage"


class GoodRender(str, Enum):
    """Conditions that describe a professional, typeset-looking render."""

    COMFORTABLE_MARGINS = "comfortable_margins"
    READABLE_TEXT = "readable_text"
    NATURAL_LINE_BREAKS = "natural_line_breaks"
    BALANCED_LINES = "balanced_lines"
    VISUALLY_CENTERED = "visually_centered"
    CONSISTENT_TYPOGRAPHY = "consistent_typography"
    CORRECT_PERSIAN_SHAPING = "correct_persian_shaping"
    CORRECT_RTL_LTR = "correct_rtl_ltr_behavior"
    APPROPRIATE_WEIGHT = "appropriate_font_weight"
    APPROPRIATE_DENSITY = "appropriate_text_density"


# ── General typography ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FontRole:
    """Font selection for a text role (glob patterns + fallback file)."""

    family_patterns: tuple[str, ...] = ("*Mikhak*",)
    fallback_file: str = "Vazir.ttf"


@dataclass(frozen=True)
class GeneralTypography:
    """Font family, sizing bounds and overall typographic behaviour.

    ``min_font_size`` / ``max_font_size`` are seeded from the existing
    ``FontConfig`` (backward compatibility) and may be overridden by the
    ``typography`` config section.
    """

    font_roles: dict[str, FontRole] = field(default_factory=dict)
    min_font_size: int = 15
    max_font_size: int = 60
    hard_min_readable_size: int = 12
    default_line_height_ratio: float = 1.15
    default_letter_spacing_em: float = 0.0
    text_density_min: float = 0.55
    text_density_max: float = 0.85
    readability_first: bool = True
    text_scaling_enabled: bool = True


# ── Speech bubble rules ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BubbleShapeRules:
    """Typography rules for a single bubble shape.

    All values are ratios relative to the region box (x2-x1, y2-y1) unless
    stated otherwise.  Ratios are the *recommended defaults*; the renderer may
    adjust them within the occupancy bounds according to bubble size and text
    length.  Text must never visually touch the bubble border.
    """

    safe_inset_ratio_x: float = 0.06
    safe_inset_ratio_y: float = 0.07
    padding_ratio_x: float = 0.05
    padding_ratio_y: float = 0.05
    max_usable_width_ratio: float = 0.88
    max_usable_height_ratio: float = 0.86
    min_safe_margin_ratio: float = 0.03
    occupancy_min: float = 0.60
    occupancy_ideal: float = 0.72
    occupancy_max: float = 0.85


@dataclass(frozen=True)
class BubbleRules:
    """Safe-area rules for every bubble shape.

    The general principle: the renderer must preserve enough empty space
    around the text that the bubble feels natural — avoiding both excessive
    empty space and excessive text density.
    """

    default_shape: BubbleShape = BubbleShape.ELLIPSE
    shapes: dict[BubbleShape, BubbleShapeRules] = field(default_factory=dict)


# ── Text occupancy ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OccupancyRules:
    """How much of the usable bubble area the text should occupy.

    The text should occupy a comfortable portion of the usable area — not too
    small (excessive empty space) and not filling the entire bubble or
    touching its edges.  Values are configurable targets, not immutable
    constants; the renderer may adjust them dynamically by bubble size and
    text length.
    """

    target_occupancy_min: float = 0.55
    target_occupancy_ideal: float = 0.70
    target_occupancy_max: float = 0.85
    dynamic_adjustment: bool = True


# ── Font-size rules ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FontSizeRules:
    """Dynamic font sizing (never one fixed size for every region)."""

    initial_height_ratio: float = 0.55
    max_chars_per_line_hint: int = 14
    max_reasonable_size_ratio: float = 0.60
    reduction_step_px: int = 1
    growth_allowed: bool = True
    cap_relative_to_bubble: bool = True
    long_text_length_threshold: int = 40
    long_text_scale: float = 0.90
    very_long_text_threshold: int = 60
    very_long_text_scale: float = 0.80
    min_after_reduction: int = 12


# ── Word-wrapping rules ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class WrappingRules:
    """Professional line-breaking rules.

    Wrapping MUST be based on the actual rendered width (not character count),
    must preserve complete words whenever possible and must avoid awkward
    breaks, unnecessary line counts, extremely short final lines and
    one-word lines.  Punctuation must remain attached to its word.
    """

    measure_by_rendered_width: bool = True
    max_line_count: int = 6
    preserve_words: bool = True
    allow_hyphen_break: bool = False
    avoid_orphan_lines: bool = True
    avoid_one_word_lines: bool = True
    final_line_min_ratio: float = 0.40
    prefer_balanced_breaks: bool = True
    punctuation_cling: bool = True
    preserve_zwnj_tokens: bool = True


# ── Line balance ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LineBalanceRules:
    """Visually balanced multiline text.

    Balanced line widths, natural sentence grouping, fewer unnecessary lines,
    reasonable final-line length and consistent visual rhythm are important
    typography rules.  Extremely uneven lines, 4-5 line layouts that could be
    fewer, very short final lines, isolated words and awkward sentence
    splitting must be avoided.
    """

    enabled: bool = True
    max_width_variance: float = 0.25
    prefer_fewer_lines: bool = True
    max_lines_before_shrink: int = 4
    final_line_min_ratio: float = 0.40
    avoid_isolated_word_lines: bool = True
    reflow_pass: bool = True


# ── Line spacing ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LineSpacingRules:
    """Line-height rules for compact, professional manga/manhwa typesetting.

    Vertical gaps must stay compact — never excessive.  Persian text and mixed
    Persian/English text may need slightly more room than pure Latin.
    """

    base_ratio: float = 1.15
    small_bubble_ratio: float = 1.08
    large_bubble_ratio: float = 1.30
    min_ratio: float = 1.05
    max_ratio: float = 1.50
    persian_ratio: float = 1.20
    mixed_language_ratio: float = 1.25
    compact_preferred: bool = True


# ── Letter spacing ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LetterSpacingRules:
    """Per-style letter spacing (in em, relative to the current font size).

    Default dialogue must use natural letter spacing.  Text must NOT be
    artificially stretched to fill a bubble unless a style rule explicitly
    requires it.
    """

    normal_dialogue_em: float = 0.00
    emphasis_em: float = 0.02
    shout_em: float = 0.04
    whisper_em: float = -0.01
    special_style_em: float = 0.00
    max_em: float = 0.10
    no_artificial_stretching: bool = True


# ── RTL / Persian typography ────────────────────────────────────────────────


@dataclass(frozen=True)
class RTLRules:
    """Requirements for correct Persian / Arabic rendering.

    The renderer MUST use the Unicode Bidirectional Algorithm and proper
    Arabic/Persian glyph shaping.  It MUST NEVER manually reverse Persian
    strings: the logical text order stays intact while visual rendering
    handles RTL correctly.
    """

    use_unicode_bidi: bool = True
    use_arabic_shaping: bool = True
    never_manually_reverse: bool = True
    preserve_logical_order: bool = True
    preserve_zwnj: bool = True
    persian_digits_supported: bool = True
    arabic_digits_supported: bool = True
    western_digits_supported: bool = True
    do_not_convert_digits: bool = True
    bidi_mirror_punctuation: bool = True
    shaping_backend: str = "arabic_reshaper + python_bidi"


# ── Mixed RTL / LTR text ────────────────────────────────────────────────────


@dataclass(frozen=True)
class MixedLanguageRules:
    """Rules for sentences mixing Persian (RTL) with English / numbers (LTR).

    Examples that must render correctly::

        "HP شما فقط 20٪ باقی مونده!"
        "Chapter 20 رو بخون."
        "این مرحله فقط 10% پیشرفت داره."

    English words stay correctly ordered, numbers stay correctly positioned,
    punctuation stays visually correct and RTL/LTR segments never scramble.
    """

    enabled: bool = True
    english_words_ordered: bool = True
    numbers_positioned_correctly: bool = True
    english_abbreviations_kept_integral: bool = True
    punctuation_visual_placement: bool = True
    base_embedding_level_rtl: bool = True
    no_manual_segment_rewriting: bool = True


# ── Alignment ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlignmentRules:
    """Default horizontal + vertical alignment per style and context.

    Speech bubbles prefer CENTER when geometry supports it.  Rectangular /
    narrative text may prefer RIGHT or CENTER depending on style.  One global
    alignment must NOT be forced.  Vertical alignment applies to the whole
    multiline block (each line is not independently centered).
    """

    bubble_default_h: HorizontalAlign = HorizontalAlign.CENTER
    bubble_default_v: VerticalAlign = VerticalAlign.CENTER
    narration_h: HorizontalAlign = HorizontalAlign.RIGHT
    caption_h: HorizontalAlign = HorizontalAlign.RIGHT
    system_h: HorizontalAlign = HorizontalAlign.CENTER
    style_defaults_h: dict[str, HorizontalAlign] = field(default_factory=dict)
    style_defaults_v: dict[str, VerticalAlign] = field(default_factory=dict)


# ── Text styles ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextStyleRules:
    """Complete typography rules for a single text style.

    ``line_height_ratio`` / ``letter_spacing_em`` of ``None`` mean "use the
    general default".  ``color_policy`` is one of:

    - ``"match_original"`` — take the color of the original text when it can
      be sampled (see :class:`TextColorRules`);
    - ``"inherit"`` — use the surrounding default color logic;
    - ``"fixed"`` — always use ``fixed_color``.
    """

    style: TextStyle
    font_weight: int = 400
    relative_size: float = 1.0
    line_height_ratio: float | None = None
    letter_spacing_em: float | None = None
    align_h: HorizontalAlign = HorizontalAlign.CENTER
    align_v: VerticalAlign = VerticalAlign.CENTER
    outline_enabled: bool = False
    outline_ratio: float = 0.04
    shadow_enabled: bool = False
    shadow_opacity: float = 0.20
    opacity: float = 1.0
    color_policy: str = "match_original"
    fixed_color: str | None = None
    characteristics: tuple[str, ...] = ()


@dataclass(frozen=True)
class StyleRuleSet:
    """The complete style table.  Deliberately contains NO SFX style."""

    default_style: TextStyle = TextStyle.NORMAL_DIALOGUE
    rules: dict[TextStyle, TextStyleRules] = field(default_factory=dict)


# ── Outline ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OutlineRules:
    """Text stroke / outline rules.

    Normal dialogue inside clean speech bubbles uses little or no outline.
    Excessive cartoon-like outlines are avoided unless a style requires them.
    Outline thickness scales with font size.
    """

    default_enabled: bool = False
    relative_thickness: float = 0.04
    min_thickness_px: int = 1
    max_thickness_px: int = 4
    scale_with_font_size: bool = True
    cartoon_max_ratio: float = 0.08
    readability_requirement: bool = True
    allowed_styles: tuple[TextStyle, ...] = ()


# ── Shadow ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShadowRules:
    """Text shadow rules.

    Normal dialogue has no shadow or only a very subtle one.  A shadow must
    never reduce readability.
    """

    default_enabled: bool = False
    opacity_range_min: float = 0.0
    opacity_range_max: float = 0.35
    default_opacity: float = 0.20
    offset_x_ratio: float = 0.015
    offset_y_ratio: float = 0.03
    blur_px: int = 0
    scale_with_font_size: bool = True
    never_reduce_readability: bool = True
    allowed_styles: tuple[TextStyle, ...] = ()


# ── Font fallback ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FontFallbackRules:
    """Missing-glyph handling.

    The renderer must: detect missing glyphs, attempt an appropriate fallback
    font, preserve visual consistency and support mixed-font rendering when
    necessary.  Missing-glyph boxes (e.g. ``□ □ □``) are NEVER acceptable.
    """

    detect_missing_glyphs: bool = True
    fallback_chain: tuple[str, ...] = (
        "persian",
        "arabic",
        "latin",
        "numbers",
        "punctuation",
        "symbols",
    )
    required_scripts: tuple[str, ...] = ("persian", "arabic", "latin", "numbers")
    mixed_font_rendering: bool = True
    never_tofu_boxes: bool = True
    mark_for_review_on_failure: bool = True
    recommended_fonts: tuple[str, ...] = ("Mikhak", "Vazir", "IRYekan")


# ── Text color (match original) ─────────────────────────────────────────────


@dataclass(frozen=True)
class TextColorRules:
    """Translated text should look like the ORIGINAL text color.

    The renderer should sample the original text color from the artwork BEFORE
    the region is erased/inpainted (dominant high-contrast color of the text
    strokes inside the OCR text boxes), and use it for the translated text.

    Precedence for the final color:

    1. per-block explicit color override;
    2. style ``fixed`` color (e.g. whisper gray / system blue);
    3. original-text color match (when readable);
    4. black/white contrast fallback against the background.

    Readability always wins: if the matched color has insufficient contrast on
    the cleaned background, only its luminance is adjusted toward black or
    white (hue is preserved where possible).
    """

    match_original_text_color: bool = True
    sampling_source: str = "pre_inpaint_text_strokes"
    contrast_min_ratio: float = 3.0
    adjust_luminance_on_low_contrast: bool = True
    preserve_hue: bool = True
    fallback_black_white: bool = True
    ink_color_distance_threshold: float = 90.0
    ink_quantization_step: int = 16
    ink_min_sample_count: int = 10


# ── Text orientation (horizontal / vertical) ────────────────────────────────


@dataclass(frozen=True)
class OrientationRules:
    """Handling of vertical (top-to-bottom / bottom-to-top) text, common in
    manga/manhwa "name boxes" and Japanese/Chinese captions.

    Detection is performed at OCR time using the aspect ratio of the detected
    text-line box.  The actual rotation of the rendered translation for a
    vertical source is the renderer's responsibility; these rules only define
    the *detection* thresholds and the *policy* (rotate-for-ocr / rotate-rendered
    text).  True vertical Persian typesetting (column RTL) is intentionally
    out of scope here — see ``rotate_translated_text``.
    """

    detect_vertical: bool = True
    vertical_aspect_ratio: float = 2.0
    rotate_for_ocr: bool = True
    rotate_translated_text: bool = True
    vertical_text_align_h: HorizontalAlign = HorizontalAlign.CENTER
    vertical_text_align_v: VerticalAlign = VerticalAlign.CENTER


@dataclass(frozen=True)
class FittingRules:
    """Order in which the renderer must make adjustments.

    Font-size reduction is one of the LAST adjustments.  The renderer must NOT
    immediately shrink the font whenever text does not fit.
    """

    steps: tuple[FittingStep, ...] = tuple(FittingStep)


@dataclass(frozen=True)
class OverflowRules:
    """What happens when text does not fit.

    Prefer better wrapping, better line balance, reasonable spacing
    adjustment and safe-area adjustment before aggressively reducing font
    size.  If the text still cannot fit while remaining readable, mark the
    item for manual review instead of producing unreadably tiny text.
    """

    escalation_order: tuple[str, ...] = (
        "re_wrap",
        "re_balance",
        "adjust_line_spacing",
        "adjust_padding",
        "reduce_font_size",
        "reject_for_review",
    )
    min_readable_size_gate: bool = True
    mark_for_review: bool = True
    never_produce_unreadable_text: bool = True


@dataclass(frozen=True)
class QualityRules:
    """Definition of BAD and GOOD renders."""

    bad_renders: tuple[BadRender, ...] = tuple(BadRender)
    good_renders: tuple[GoodRender, ...] = tuple(GoodRender)


@dataclass(frozen=True)
class PriorityRules:
    """Strict typography priority hierarchy.

    Decorative effects must NEVER override readability.
    """

    hierarchy: tuple[PriorityLevel, ...] = tuple(PriorityLevel)


# ── Root specification ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TypographyRules:
    """The complete, centralized typography rule set.

    This mirrors the conceptual structure::

        TypographyRules
        ├── general
        ├── bubble
        ├── occupancy
        ├── font_size
        ├── wrapping
        ├── line_balance
        ├── line_spacing
        ├── letter_spacing
        ├── rtl
        ├── mixed_language
        ├── alignment
        ├── styles
        ├── outline
        ├── shadow
        ├── font_fallback
        ├── text_color
        ├── orientation
        ├── fitting
        ├── overflow
        ├── quality
        └── priority
    """

    general: GeneralTypography = field(default_factory=GeneralTypography)
    bubble: BubbleRules = field(default_factory=BubbleRules)
    occupancy: OccupancyRules = field(default_factory=OccupancyRules)
    font_size: FontSizeRules = field(default_factory=FontSizeRules)
    wrapping: WrappingRules = field(default_factory=WrappingRules)
    line_balance: LineBalanceRules = field(default_factory=LineBalanceRules)
    line_spacing: LineSpacingRules = field(default_factory=LineSpacingRules)
    letter_spacing: LetterSpacingRules = field(default_factory=LetterSpacingRules)
    rtl: RTLRules = field(default_factory=RTLRules)
    mixed_language: MixedLanguageRules = field(default_factory=MixedLanguageRules)
    alignment: AlignmentRules = field(default_factory=AlignmentRules)
    styles: StyleRuleSet = field(default_factory=StyleRuleSet)
    outline: OutlineRules = field(default_factory=OutlineRules)
    shadow: ShadowRules = field(default_factory=ShadowRules)
    font_fallback: FontFallbackRules = field(default_factory=FontFallbackRules)
    text_color: TextColorRules = field(default_factory=TextColorRules)
    orientation: OrientationRules = field(default_factory=OrientationRules)
    fitting: FittingRules = field(default_factory=FittingRules)
    overflow: OverflowRules = field(default_factory=OverflowRules)
    quality: QualityRules = field(default_factory=QualityRules)
    priority: PriorityRules = field(default_factory=PriorityRules)


# ── Recommended defaults ────────────────────────────────────────────────────


def _default_font_roles() -> dict[str, FontRole]:
    return {
        "normal": FontRole(("*Mikhak*",), "Vazir.ttf"),
        "shout": FontRole(("*Mikhak*",), "Vazir.ttf"),
        "whisper": FontRole(("Vazir*",), "Vazir.ttf"),
        "thought": FontRole(("*AFSANEH*",), "Vazir.ttf"),
        "narration": FontRole(("*Mikhak*",), "Vazir.ttf"),
        "caption": FontRole(("*Mikhak*",), "Vazir.ttf"),
        "system": FontRole(("Vazir*",), "Vazir.ttf"),
        "monster_voice": FontRole(("*Mikhak*",), "Vazir.ttf"),
        "emphasis": FontRole(("*Mikhak*",), "Vazir.ttf"),
    }


def _default_bubble_shapes() -> dict[BubbleShape, BubbleShapeRules]:
    return {
        BubbleShape.CIRCLE: BubbleShapeRules(
            safe_inset_ratio_x=0.08,
            safe_inset_ratio_y=0.10,
            padding_ratio_x=0.06,
            padding_ratio_y=0.06,
            max_usable_width_ratio=0.84,
            max_usable_height_ratio=0.80,
            min_safe_margin_ratio=0.04,
            occupancy_min=0.55,
            occupancy_ideal=0.68,
            occupancy_max=0.82,
        ),
        BubbleShape.ELLIPSE: BubbleShapeRules(
            safe_inset_ratio_x=0.07,
            safe_inset_ratio_y=0.09,
            padding_ratio_x=0.06,
            padding_ratio_y=0.06,
            max_usable_width_ratio=0.86,
            max_usable_height_ratio=0.82,
            min_safe_margin_ratio=0.04,
            occupancy_min=0.55,
            occupancy_ideal=0.68,
            occupancy_max=0.82,
        ),
        BubbleShape.ROUNDED_RECT: BubbleShapeRules(
            safe_inset_ratio_x=0.06,
            safe_inset_ratio_y=0.07,
            padding_ratio_x=0.05,
            padding_ratio_y=0.05,
            max_usable_width_ratio=0.88,
            max_usable_height_ratio=0.86,
            min_safe_margin_ratio=0.03,
            occupancy_min=0.60,
            occupancy_ideal=0.72,
            occupancy_max=0.85,
        ),
        BubbleShape.RECT: BubbleShapeRules(
            safe_inset_ratio_x=0.05,
            safe_inset_ratio_y=0.06,
            padding_ratio_x=0.04,
            padding_ratio_y=0.04,
            max_usable_width_ratio=0.90,
            max_usable_height_ratio=0.88,
            min_safe_margin_ratio=0.03,
            occupancy_min=0.60,
            occupancy_ideal=0.75,
            occupancy_max=0.88,
        ),
        BubbleShape.IRREGULAR: BubbleShapeRules(
            safe_inset_ratio_x=0.10,
            safe_inset_ratio_y=0.12,
            padding_ratio_x=0.06,
            padding_ratio_y=0.06,
            max_usable_width_ratio=0.80,
            max_usable_height_ratio=0.76,
            min_safe_margin_ratio=0.05,
            occupancy_min=0.50,
            occupancy_ideal=0.65,
            occupancy_max=0.78,
        ),
    }


def _default_style_rules() -> dict[TextStyle, TextStyleRules]:
    return {
        TextStyle.NORMAL_DIALOGUE: TextStyleRules(
            style=TextStyle.NORMAL_DIALOGUE,
            font_weight=400,
            relative_size=1.00,
            characteristics=("clean", "unobtrusive"),
        ),
        TextStyle.SHOUT: TextStyleRules(
            style=TextStyle.SHOUT,
            font_weight=800,
            relative_size=1.15,
            letter_spacing_em=0.04,
            outline_enabled=True,
            outline_ratio=0.04,
            characteristics=("energetic", "bold"),
        ),
        TextStyle.WHISPER: TextStyleRules(
            style=TextStyle.WHISPER,
            font_weight=300,
            relative_size=0.85,
            line_height_ratio=1.10,
            letter_spacing_em=-0.01,
            opacity=0.80,
            color_policy="fixed",
            fixed_color="#AAAAAA",
            characteristics=("soft", "subdued", "may_be_gray"),
        ),
        TextStyle.THOUGHT: TextStyleRules(
            style=TextStyle.THOUGHT,
            font_weight=400,
            relative_size=0.90,
            opacity=0.90,
            characteristics=("italic_hint", "cloud_bubble_association"),
        ),
        TextStyle.NARRATION: TextStyleRules(
            style=TextStyle.NARRATION,
            font_weight=400,
            relative_size=1.00,
            line_height_ratio=1.20,
            align_h=HorizontalAlign.RIGHT,
            opacity=0.95,
            characteristics=("boxed_text", "slightly_formal"),
        ),
        TextStyle.CAPTION: TextStyleRules(
            style=TextStyle.CAPTION,
            font_weight=600,
            relative_size=1.00,
            line_height_ratio=1.20,
            letter_spacing_em=0.02,
            align_h=HorizontalAlign.RIGHT,
            shadow_enabled=True,
            shadow_opacity=0.20,
            opacity=0.95,
            characteristics=("title", "place_or_time_boxes"),
        ),
        TextStyle.SYSTEM_MESSAGE: TextStyleRules(
            style=TextStyle.SYSTEM_MESSAGE,
            font_weight=500,
            relative_size=0.90,
            letter_spacing_em=0.02,
            outline_enabled=True,
            outline_ratio=0.03,
            color_policy="fixed",
            fixed_color="#4A90D9",
            characteristics=("ui_or_game_text", "distinct_color_allowed"),
        ),
        TextStyle.MONSTER_VOICE: TextStyleRules(
            style=TextStyle.MONSTER_VOICE,
            font_weight=800,
            relative_size=1.10,
            line_height_ratio=1.20,
            letter_spacing_em=0.02,
            outline_enabled=True,
            outline_ratio=0.06,
            shadow_enabled=True,
            shadow_opacity=0.20,
            characteristics=("intimidating", "rough_font_allowed"),
        ),
        TextStyle.EMPHASIS: TextStyleRules(
            style=TextStyle.EMPHASIS,
            font_weight=700,
            relative_size=1.10,
            letter_spacing_em=0.02,
            outline_enabled=True,
            outline_ratio=0.03,
            characteristics=("bolded", "for_emphasis"),
        ),
    }


def _default_alignment() -> AlignmentRules:
    rules = AlignmentRules()
    h = dict(rules.style_defaults_h)
    v = dict(rules.style_defaults_v)
    for style in ALL_TEXT_STYLES:
        h[style.value] = (
            rules.narration_h
            if style in (TextStyle.NARRATION, TextStyle.CAPTION)
            else rules.bubble_default_h
        )
        v[style.value] = rules.bubble_default_v
    return replace(rules, style_defaults_h=h, style_defaults_v=v)


DEFAULT_TYPOGRAPHY_RULES: TypographyRules = TypographyRules(
    general=replace(
        GeneralTypography(),
        font_roles=_default_font_roles(),
    ),
    bubble=BubbleRules(
        default_shape=BubbleShape.ELLIPSE,
        shapes=_default_bubble_shapes(),
    ),
    styles=StyleRuleSet(
        default_style=TextStyle.NORMAL_DIALOGUE,
        rules=_default_style_rules(),
    ),
    alignment=_default_alignment(),
    outline=replace(
        OutlineRules(),
        allowed_styles=(
            TextStyle.SHOUT,
            TextStyle.MONSTER_VOICE,
            TextStyle.EMPHASIS,
            TextStyle.SYSTEM_MESSAGE,
            TextStyle.CAPTION,
        ),
    ),
    shadow=replace(
        ShadowRules(),
        allowed_styles=(
            TextStyle.CAPTION,
            TextStyle.SYSTEM_MESSAGE,
            TextStyle.MONSTER_VOICE,
            TextStyle.WHISPER,
        ),
    ),
)


# ── Legacy text-type mapping ────────────────────────────────────────────────


LEGACY_TEXT_TYPE_TO_STYLE: dict[str, TextStyle | None] = {
    "dialog": TextStyle.NORMAL_DIALOGUE,
    "action": TextStyle.SHOUT,
    "think": TextStyle.THOUGHT,
    "whisper": TextStyle.WHISPER,
    "narration": TextStyle.NARRATION,
    "system": TextStyle.SYSTEM_MESSAGE,
    "custom": TextStyle.NORMAL_DIALOGUE,
    "sfx": None,  # SFX is outside the rendering system — must be ignored.
}


def style_for_text_type(text_type: str) -> TextStyle | None:
    """Map a legacy ``Block.text_type`` to a :class:`TextStyle`.

    Returns ``None`` for ``"sfx"`` and unknown types, which tells the pipeline
    to ignore that item during translated-text rendering.
    """
    return LEGACY_TEXT_TYPE_TO_STYLE.get(text_type)


# ── Configurable subset + builder ───────────────────────────────────────────


@dataclass(frozen=True)
class TypographyConfig:
    """JSON-serializable typography knobs exposed in config.json.

    Only the text-color matching rules are wired to config — the render
    pipeline consumes those via ``TextColorRules`` (see
    :func:`build_typography_rules`). The rest of the rule catalog keeps its
    :data:`DEFAULT_TYPOGRAPHY_RULES` values.
    """

    match_original_text_color: bool = True
    text_color_contrast_min: float = 3.0
    ink_color_distance_threshold: float = 90.0
    ink_quantization_step: int = 16


def build_typography_rules(
    typography: TypographyConfig | None = None,
) -> TypographyRules:
    """Build the rules the render pipeline uses.

    Starts from :data:`DEFAULT_TYPOGRAPHY_RULES` and applies the config's
    text-color matching overrides on top.
    """
    rules = DEFAULT_TYPOGRAPHY_RULES

    if typography is None:
        return rules

    text_color_rules = replace(
        rules.text_color,
        match_original_text_color=typography.match_original_text_color,
        contrast_min_ratio=typography.text_color_contrast_min,
        ink_color_distance_threshold=typography.ink_color_distance_threshold,
        ink_quantization_step=typography.ink_quantization_step,
    )
    return replace(rules, text_color=text_color_rules)


def apply_overrides(
    rules: TypographyRules,
    overrides: Mapping[str, Any],
) -> TypographyRules:
    """Apply shallow root-level overrides (for testing / programmatic tweaks)."""
    return replace(rules, **{k: v for k, v in overrides.items() if hasattr(rules, k)})
