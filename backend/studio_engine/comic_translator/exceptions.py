"""Custom exceptions for comic_translator."""


class ComicTranslatorError(Exception):
    """Base exception for the project."""


class ConfigError(ComicTranslatorError):
    """Configuration loading or validation error."""


class OCRError(ComicTranslatorError):
    """OCR processing error."""


class TranslationError(ComicTranslatorError):
    """Translation provider error."""


class PDFError(ComicTranslatorError):
    """PDF processing error."""


