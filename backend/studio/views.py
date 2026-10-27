"""DRF views for Vira Translator Studio."""

import logging
import mimetypes

from django.conf import settings
from django.core.exceptions import BadRequest
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from pathlib import Path

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .jobs import submit_job
from .models import Job, MaskMark, Page, Project, TextBlock
from .serializers import (
    ApplyParamsSerializer,
    ChapterDiscoverySerializer,
    ChapterImportSerializer,
    ExtractParamsSerializer,
    JobSerializer,
    MaskMarkCreateSerializer,
    MaskMarkSerializer,
    PageCropSerializer,
    PageSerializer,
    PreviewLayoutSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectUpdateSerializer,
    TextBlockCreateSerializer,
    TextBlockSerializer,
    TextBlockUpdateSerializer,
    TranslateParamsSerializer,
)
from .chapter_import import discover, discover_chapter

logger = logging.getLogger(__name__)


@api_view(["POST"])
def discover_chapter_images(request):
    """Global chapter preview: no project required (Add Project → Link tab).

    Returns `{images, token}` where the token is NOT bound to a project so
    the client can create the project first and then call
    `POST /api/projects/:id/import-pages` with the stored token.
    """
    serializer = ChapterDiscoverySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        return Response(discover_chapter(serializer.validated_data["url"]))
    except Exception as exc:
        logger.info("Chapter discovery failed: %s", type(exc).__name__)
        message = str(exc) if isinstance(exc, ValueError) else "Unable to load chapter website"
        return Response({"error": message}, status=400)

_RUNNERS = {
    Job.Kind.EXTRACT: services.run_extract,
    Job.Kind.TRANSLATE: services.run_translate,
    Job.Kind.CLEAN: services.run_clean,
    Job.Kind.RENDER: services.run_render_text,
    Job.Kind.APPLY: services.run_apply,
    Job.Kind.REOCR: services.run_reocr,
}


# ── Auth ─────────────────────────────────────────────────────────────────────


# ── Projects ─────────────────────────────────────────────────────────────────


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=True, methods=["post"], url_path="chapter-images")
    def chapter_images(self, request, pk=None):
        from .chapter_import import discover
        project = self.get_object()
        serializer = ChapterDiscoverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(discover(project, serializer.validated_data["url"]))
        except Exception as exc:
            logger.info("Chapter discovery failed: %s", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else "Unable to load chapter website"
            return Response({"error": message}, status=400)

    @action(detail=True, methods=["post"], url_path="import-pages")
    def import_pages(self, request, pk=None):
        from .chapter_import import selected_urls, run_import_pages
        project = self.get_object()
        serializer = ChapterImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            urls = selected_urls(project, **serializer.validated_data)
            if project.jobs.filter(status__in=[Job.Status.PENDING, Job.Status.RUNNING]).exists():
                return Response({"error": "A project job is still running"}, status=409)
            job = submit_job(project, Job.Kind.IMPORT_PAGES, {"urls": urls}, run=run_import_pages)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=409)
        return Response(JobSerializer(job).data, status=202)

    def _start_job(self, request, project: Project, kind: str, params: dict):
        """Shared guard + submit. Returns a DRF Response on failure, else None."""
        active = project.jobs.exclude(
            status__in=[Job.Status.SUCCESS, Job.Status.FAILED,
                        Job.Status.CANCELLED]).first()
        if active:
            from . import jobs as job_infra
            # An active row with a free project lock is a zombie from a dead
            # process (finalize never ran). Heal it and proceed with the new
            # job; only a genuine live worker keeps the 409.
            if not job_infra.settle_zombie(project):
                return Response({"error": f"Job {active.kind} is {active.status}"},
                                status=status.HTTP_409_CONFLICT)
        try:
            job = submit_job(project, kind, params, run=_RUNNERS[kind])
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _opt_page_number(request) -> int | None:
        raw = (request.data or {}).get("page_number")
        if raw is None or str(raw) == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise BadRequest("page_number must be an integer")

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        if self.action == "create":
            return ProjectCreateSerializer
        if self.action in ("update", "partial_update"):
            return ProjectUpdateSerializer
        return ProjectDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Fill per-project config snapshots from global config so the UI can
        # tweak them independently later.
        global_cfg = services.get_global_config()
        uses_page_sources = serializer.validated_data.get("uses_page_sources", False)
        source_url = serializer.validated_data.get("source_url", "")

        project = None
        try:
            project = serializer.save(
                ocr_config=global_cfg.get("ocr", {}),
                font_config=global_cfg.get("font", {}),
                inpaint_config=global_cfg.get("inpaint", {}),
                translator_config=global_cfg.get("translator", {}),
                chapter_id_config=global_cfg.get("chapter_id", {}),
                uses_page_sources=uses_page_sources,
            )
        except OSError as exc:
            # Storage failure (disk full, permissions, …) — actionable 400,
            # never a bare 500.
            logger.warning("Project file save failed: %s", exc)
            return Response(
                {"error": f"Could not save the uploaded file: {exc}"},
                status=status.HTTP_400_BAD_REQUEST)

        # If using page sources, store the source URL in chapter_id_config for reference
        if uses_page_sources and source_url:
            project.chapter_id_config = {**project.chapter_id_config, "source_url": source_url}
            project.save(update_fields=["chapter_id_config"])

        return Response(ProjectDetailSerializer(project).data,
                        status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        import shutil

        from django.conf import settings

        # Don't yank the media tree out from under a running job thread —
        # its saves would crash and dirs would be recreated mid-flight.
        active = instance.jobs.exclude(
            status__in=[Job.Status.SUCCESS, Job.Status.FAILED,
                        Job.Status.CANCELLED]).first()
        if active:
            raise PermissionDenied(
                {"error": f"Job {active.kind} is {active.status} — cancel it "
                          "or wait for it to finish before deleting"})

        pdf_name = instance.pdf_file.name if instance.pdf_file else None
        media_dir = Path(settings.MEDIA_ROOT) / "projects" / str(instance.id)
        instance.delete()
        shutil.rmtree(media_dir, ignore_errors=True)
        # The uploaded PDF lives in the shared projects/pdfs/ dir, outside the
        # per-project media tree above — remove it explicitly.
        if pdf_name:
            (Path(settings.MEDIA_ROOT) / pdf_name).unlink(missing_ok=True)

    # ── Actions ──────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def extract(self, request, pk=None):
        project = self.get_object()
        s = ExtractParamsSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)
        data = s.validated_data
        params = {}
        for src, dst in (("covers", "covers"), ("skip_pages", "skip_pages"),
                         ("pdf_type", "pdf_type"),
                         ("standard_max_side", "standard_max_side"),
                         ("ocr_version", "ocr_version")):
            if data.get(src) is not None:
                params[dst] = data[src]
        return self._start_job(request, project, Job.Kind.EXTRACT, params)

    @action(detail=True, methods=["post"])
    def translate(self, request, pk=None):
        project = self.get_object()
        s = TranslateParamsSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)
        v = s.validated_data
        params = {"force": v.get("force", False)}
        if v.get("block_ids"):
            params["block_ids"] = [str(b) for b in v["block_ids"]]
        if v.get("provider"):
            params["provider"] = v["provider"]
        return self._start_job(request, project, Job.Kind.TRANSLATE, params)

    @action(detail=True, methods=["post"])
    def clean(self, request, pk=None):
        project = self.get_object()
        page_number = self._opt_page_number(request)
        return self._start_job(request, project, Job.Kind.CLEAN,
                               {"page_number": page_number})

    @action(detail=True, methods=["post"], url_path="preview-layout")
    def preview_layout(self, request, pk=None):
        project = self.get_object()
        serializer = PreviewLayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        drafts = data["blocks"]
        stored = {b.id: b for b in project.blocks.select_related("page").filter(
            page__page_number=data["page_number"],
            id__in=[d["id"] for d in drafts],
        )}
        if len(stored) != len(drafts):
            return Response({"error": "Unknown block or page"}, status=400)
        for draft in drafts:
            block = stored[draft["id"]]
            for field, value in draft.items():
                if field != "id":
                    setattr(block, field, value)
        return Response(services.preview_text_layout(project, list(stored.values())))

    @action(detail=True, methods=["post"])
    def render(self, request, pk=None):
        project = self.get_object()
        page_number = self._opt_page_number(request)
        chapter_id = (request.data or {}).get("chapter_id") or ""
        return self._start_job(request, project, Job.Kind.RENDER,
                               {"page_number": page_number,
                                "chapter_id": chapter_id})

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        project = self.get_object()
        s = ApplyParamsSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)
        v = s.validated_data
        params = {
            "chapter_id": v.get("chapter_id", "") or "",
            "formats": v.get("formats") or ["pdf"],
        }
        return self._start_job(request, project, Job.Kind.APPLY, params)

    @action(detail=True, methods=["post"])
    def reocr(self, request, pk=None):
        project = self.get_object()
        page_number = request.data.get("page_number")
        quality = request.data.get("quality", "normal")
        if page_number is None:
            return Response({"error": "page_number required"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            return Response({"error": "page_number must be an integer"},
                            status=status.HTTP_400_BAD_REQUEST)
        params = {"page_number": page_number, "quality": quality}
        return self._start_job(request, project, Job.Kind.REOCR, params)


# Nested routers handled manually below


class PageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PageSerializer

    def destroy(self, request, *args, **kwargs):
        from .page_sources import delete_page
        try:
            delete_page(self.get_object())
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=409)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="append",
            parser_classes=[MultiPartParser, FormParser])
    def append(self, request, project_pk=None):
        """Upload local images as new pages: `images[]` files + `position`.

        `position` is "end" (default), "start", or a page number meaning
        "insert after that page". Synchronous (standardizing ≤20 images takes
        seconds); 409 while another job runs.
        """
        from .page_sources import append_pages, page_mutation, prepare_uploaded_images
        project = get_object_or_404(Project, pk=project_pk)
        raw_position = str(request.data.get("position") or "end").strip().lower()
        uploads = request.FILES.getlist("images")
        try:
            jpgs, originals, stage = prepare_uploaded_images(uploads)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        try:
            if raw_position in ("end", "start"):
                position = raw_position
            else:
                try:
                    position = int(raw_position)
                except (TypeError, ValueError):
                    return Response(
                        {"error": 'position must be "start", "end" or a page number'},
                        status=400)
            with page_mutation(project):
                created = append_pages(project, jpgs, originals, position)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=409)
        finally:
            stage.cleanup()
        return Response({"inserted": created}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="crop")
    def crop(self, request, project_pk=None, pk=None):
        """Crop one page to an image-pixel rect; blocks/marks fully outside
        are deleted, survivors shifted, derivatives invalidated."""
        from .page_sources import crop_page
        page = self.get_object()
        serializer = PageCropSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = crop_page(page.project, page.page_number,
                               data["x1"], data["y1"], data["x2"], data["y2"])
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=409)
        return Response(result)

    def get_queryset(self):
        # Annotate per-page block counts so the serializer skips 2 queries
        # per page (N+1); ProjectDetailSerializer's nested path has no
        # annotations and falls back to per-row counting.
        from django.db.models import Count, Q

        return Page.objects.filter(project_id=self.kwargs["project_pk"]).annotate(
            block_count_annotated=Count("blocks", distinct=True),
            translated_count_annotated=Count(
                "blocks", filter=Q(blocks__translation__gt=""), distinct=True),
        )


class TextBlockViewSet(viewsets.ModelViewSet):
    serializer_class = TextBlockSerializer
    http_method_names = ["get", "patch", "delete", "post"]

    def _refresh_project_counts(self) -> None:
        """Recompute Project.total_blocks / translated_count after a block
        mutation. These counters gate the workspace's Render button
        (translated_count === 0), but were only refreshed by translate jobs —
        so hand-typed and JSON-imported translations never opened the gate."""
        from .services import _refresh_counts

        _refresh_counts(Project.objects.get(pk=self.kwargs["project_pk"]))

    def get_queryset(self):
        qs = TextBlock.objects.filter(project_id=self.kwargs["project_pk"])
        qp = self.request.query_params
        block_type = qp.get("type")
        if block_type:
            qs = qs.filter(block_type=block_type)
        page = qp.get("page")
        if page:
            try:
                qs = qs.filter(page__page_number=int(page))
            except ValueError:
                raise BadRequest("page must be an integer")
        translated = qp.get("translated")
        if translated == "0":
            qs = qs.filter(translation="")
        elif translated == "1":
            qs = qs.exclude(translation="")
        search = qp.get("search")
        if search:
            # Bound the icontains scan to something sane.
            qs = qs.filter(original_text__icontains=search[:200])
        return qs.select_related("page")

    def get_serializer_class(self):
        if self.action == "partial_update":
            return TextBlockUpdateSerializer
        return TextBlockSerializer

    def partial_update(self, request, *args, **kwargs):
        """PATCH a block. When the box geometry moves/resizes, the stored
        OCR word boxes (text_boxes) move with it — clean/render build their
        masks from those polygons preferentially, so without this they keep
        erasing the OLD location after a move."""
        blk = self.get_object()
        data = request.data or {}
        geo_keys = ("x1", "y1", "x2", "y2")
        if blk.text_boxes and any(k in data for k in geo_keys):
            old = (blk.x1, blk.y1, blk.x2, blk.y2)
            try:
                new = tuple(int(data.get(k, v)) for k, v in zip(geo_keys, old))
            except (TypeError, ValueError):
                new = None  # invalid — let the serializer report it
            if new is not None and tuple(new) != tuple(old):
                ox1, oy1, ox2, oy2 = old
                nx1, ny1, nx2, ny2 = new
                ow, oh = ox2 - ox1, oy2 - oy1
                nw, nh = nx2 - nx1, ny2 - ny1
                try:
                    if ow > 0 and oh > 0 and nw > 0 and nh > 0:
                        sx, sy = nw / ow, nh / oh
                        blk.text_boxes = [
                            [[round(nx1 + (x - ox1) * sx), round(ny1 + (y - oy1) * sy)]
                             for x, y in poly]
                            for poly in blk.text_boxes
                        ]
                    else:
                        # Degenerate geometry — word boxes can't map; drop
                        # them so clean/render fall back to the bbox.
                        blk.text_boxes = []
                except (TypeError, ValueError):
                    blk.text_boxes = []
                blk.save(update_fields=["text_boxes"])
        translating = "translation" in (request.data or {})
        response = super().partial_update(request, *args, **kwargs)
        # Only translation-bearing PATCHes can change the counters; skip the
        # two COUNT queries + project save for geometry-only edits.
        if translating and status.is_success(response.status_code):
            self._refresh_project_counts()
        return response

    def create(self, request, *args, **kwargs):
        """Manually add a new text block on a page."""
        s = TextBlockCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        project_pk = self.kwargs["project_pk"]
        page = get_object_or_404(Page, project_id=project_pk,
                                 page_number=data["page_number"])
        # Collision-safe key: count() alone can collide after deletions.
        suffix = page.blocks.count() + 1
        key = f"p{page.page_number}_m{suffix}"
        while TextBlock.objects.filter(project_id=project_pk, key=key).exists():
            suffix += 1
            key = f"p{page.page_number}_m{suffix}"
        blk = TextBlock.objects.create(
            project_id=project_pk, page=page, key=key,
            original_text=data["original_text"],
            translation=data["translation"],
            block_type=data.get("block_type", TextBlock.BlockType.DIALOG),
            x1=data["x1"], y1=data["y1"], x2=data["x2"], y2=data["y2"],
            order=suffix * 100,
        )
        self._refresh_project_counts()
        return Response(TextBlockSerializer(blk).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            self._refresh_project_counts()
        return response


class JobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = JobSerializer
    queryset = Job.objects.all()

    def retrieve(self, request, pk=None):
        """Polling endpoint. The UI polls this while a job runs — also
        self-heal a zombie row here (active job with no live worker holding
        the project lock) so a server restart that killed a worker never
        spins the progress bar or bricks the project forever."""
        job = self.get_object()
        from . import jobs as job_infra

        if job.status in (Job.Status.PENDING, Job.Status.RUNNING):
            job_infra.settle_zombie(job.project)
            job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cooperative cancellation: signal the worker thread, then flip the
        row. The thread checks the flag at choke points (progress reports,
        service loops) and exits without overwriting the terminal state. If
        the job already finished, the update matches 0 rows and we just
        return its current state."""
        job = self.get_object()
        from . import jobs as job_infra

        job_infra.request_cancel(job.id)
        updated = Job.objects.filter(
            pk=job.pk,
            status__in=[Job.Status.PENDING, Job.Status.RUNNING],
        ).update(
            status=Job.Status.CANCELLED,
            stage="Cancelled",
            error_message="Cancelled by user",
            finished_at=timezone.now(),
        )
        job.refresh_from_db()
        # Immediate settle: the worker zombie can keep draining its current
        # provider call for minutes before it observes the cancel, and until
        # then nobody else touched the project row — the badge would keep
        # showing 'translating' long after the user pressed stop.
        from .services import _refresh_counts

        try:
            if updated:
                # The flip transitioned a live job: settle project status
                # (READY/CREATED) and re-sync the block counters from the
                # partial work already saved.
                job_infra._project_after_interrupt(
                    job.project, "Cancelled by user")
            else:
                # Terminal job: nothing to settle; keep counters truthful.
                _refresh_counts(job.project)
        except Exception:
            logging.getLogger(__name__).exception(
                "Counter sync after cancel failed for job %s", job.pk)
        return Response(JobSerializer(job).data)


# ── Global config / fonts ───────────────────────────────────────────────────


class ConfigView(APIView):
    def get(self, request):
        return Response(services.get_global_config())

    def put(self, request):
        if not isinstance(request.data, dict):
            return Response({"error": "JSON object expected"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            cfg = services.update_global_config(request.data)
        except ValueError as e:
            return Response({"error": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(cfg)


class ConfigTestProviderView(APIView):
    """POST with the translator config (as in the UI, unsaved values fine)
    — fires one real request against the configured provider/model and
    reports ok/latency/error so a bad key is found before a job runs."""

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response({"error": "JSON object expected"},
                            status=status.HTTP_400_BAD_REQUEST)
        body = dict(request.data)
        if not str(body.get("provider") or "").strip():
            return Response({"error": "provider is required"},
                            status=status.HTTP_400_BAD_REQUEST)
        from comic_translator.config import _build_config
        allowed = services._allowed_config_sections()
        pruned = services._prune_config(body, allowed, path="translator", warn=False)
        if not pruned.get("provider"):
            pruned["provider"] = str(body.get("provider"))

        try:
            tc = _build_config({"translator": pruned}).translator
            result = services.run_provider_test(tc)
        except ValueError as e:
            return Response({"error": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class FontsView(APIView):
    def get(self, request):
        from django.conf import settings

        fonts = []
        d = Path(settings.FONTS_DIR)
        if d.exists():
            for f in sorted(list(d.glob("*.ttf")) + list(d.glob("*.otf"))):
                fonts.append({"name": f.stem, "path": str(f),
                              "url": f"/api/fonts/{f.name}"})
        return Response(fonts)


def font_file(request, name: str):
    from django.conf import settings

    f = Path(settings.FONTS_DIR) / Path(name).name
    if not f.exists():
        raise Http404
    response = FileResponse(open(f, "rb"),
                            content_type="font/ttf" if f.suffix.lower() == ".ttf"
                            else "font/otf")
    response["X-Content-Type-Options"] = "nosniff"
    return response


class MaskMarkViewSet(viewsets.ModelViewSet):
    """Freehand eraser marks: list/create/delete, optional ?page= filter."""

    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = MaskMark.objects.filter(project_id=self.kwargs["project_pk"])
        page = self.request.query_params.get("page")
        if page:
            try:
                qs = qs.filter(page__page_number=int(page))
            except ValueError:
                raise BadRequest("page must be an integer")
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return MaskMarkCreateSerializer
        return MaskMarkSerializer

    def create(self, request, *args, **kwargs):
        s = MaskMarkCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        page = Page.objects.get(
            project_id=self.kwargs["project_pk"],
            page_number=data["page_number"],
        )
        mark = MaskMark.objects.create(project_id=self.kwargs["project_pk"],
                                       page=page, points=data["points"])
        return Response(MaskMarkSerializer(mark).data,
                        status=status.HTTP_201_CREATED)


# ── Media serving ────────────────────────────────────────────────────────────


def media_file(request, file_path: str):
    """Serve MEDIA_ROOT files.

    The studio is an unauthenticated personal app; the hardening that still
    matters is path containment and download semantics, not login. No Range
    support — assets are jpg/pdf/zip/psd (no seeking media), browsers fetch
    them whole.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    full = (media_root / file_path).resolve()
    # 404 (not 403) for traversal/missing so the endpoint reveals nothing.
    if not full.is_relative_to(media_root) or not full.is_file():
        raise Http404

    content_type = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
    # Only rendered page images are safe to show inline; everything else
    # (uploaded PDFs, exports, anything unexpected) downloads as an opaque
    # attachment so a hostile upload can never execute in the app origin.
    relative = full.relative_to(media_root).parts
    inline_ok = (
        "pages" in relative or "cleaned" in relative or "rendered" in relative
    ) and content_type.startswith("image/")
    response = FileResponse(full.open("rb"), content_type=content_type)
    if "outputs" in relative or not inline_ok:
        response["Content-Disposition"] = f'attachment; filename="{full.name}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
