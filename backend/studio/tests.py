"""Tests for the studio API, jobs infrastructure, media view and recovery.

Heavy engine imports are lazy (inside service functions), so tests mock the
runner registry in studio.views._RUNNERS and never need OCR/AI dependencies.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APITestCase

from .jobs import JobContext, JobCancelled, submit_job
from .models import GlobalSetting, Job, MaskMark, Page, Project, TextBlock
from .services import _get_config


def _make_project(**overrides) -> Project:
    data = dict(name="Test Project", pdf_type=Project.PDFType.MANGA)
    data.update(overrides)
    return Project.objects.create(**data)


def _fake_runner(logs: list[str] | None = None, delay: float = 0.0):
    """Build a runner fn that reports progress and returns a result dict."""

    def run(ctx: JobContext):
        if logs is not None:
            logs.append("started")
        ctx.progress(0.5, "halfway")
        if delay:
            time.sleep(delay)
        if logs is not None:
            logs.append("finished")
        return {"ok": True}

    return run


class ProjectTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        GlobalSetting.objects.get_or_create(
            key="config", value={"ocr": {"dpi": 200}, "font": {"size_max": 25}}
        )

    def test_create_snapshots_global_config(self):
        upload = __import__("django").core.files.uploadedfile.SimpleUploadedFile(
            "t.pdf", b"%PDF-1.4 fake"
        )
        res = self.client.post(
            "/api/projects",
            {"name": "P1", "pdf_file": upload, "pdf_type": "manga"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["ocr_config"]["dpi"], 200)
        self.assertEqual(res.json()["font_config"]["size_max"], 25)

    def test_list_open_access(self):
        """Auth removed: the studio is a personal, unauthenticated app."""
        self.client.logout()
        res = self.client.get("/api/projects")
        self.assertEqual(res.status_code, 200)

    def test_create_link_mode_without_pdf(self):
        # Add Project â†’ Link tab: no pdf_file, source_url stored for reference.
        res = self.client.post(
            "/api/projects",
            {
                "name": "Imported Chapter",
                "pdf_type": "manhwa",
                "chapter_id": "c12",
                "uses_page_sources": "true",
                "source_url": "https://example.org/chapter",
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.content[:500])
        body = res.json()
        self.assertTrue(body["uses_page_sources"])
        self.assertEqual(
            body["chapter_id_config"].get("source_url"),
            "https://example.org/chapter",
        )

    def test_create_pdf_mode_requires_file(self):
        res = self.client.post(
            "/api/projects",
            {"name": "P2", "pdf_type": "manga", "uses_page_sources": "false"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    def test_create_sanitizes_hostile_filename(self):
        upload = __import__("django").core.files.uploadedfile.SimpleUploadedFile(
            '../Re:Zero c12? *edition* "x".PDF', b"%PDF-1.4 fake"
        )
        res = self.client.post(
            "/api/projects",
            {"name": "P3", "pdf_file": upload, "pdf_type": "manga"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.content[:500])
        stored = res.json()["pdf_file"]
        self.assertTrue(stored.startswith("/media/projects/pdfs/"))
        self.assertFalse(any(c in stored for c in '<>:"|?*'))
        self.assertNotIn("..", stored)


class BlockFilterTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)
        self.block1 = TextBlock.objects.create(
            project=self.project, page=self.page, key="p1_d1",
            original_text="Hello world", translation="", block_type="dialog",
        )
        self.block2 = TextBlock.objects.create(
            project=self.project, page=self.page, key="p1_d2",
            original_text="BOOM", translation="Ø¨ÙˆÙ…", block_type="sfx",
        )

    def _url(self, query: str = "") -> str:
        return f"/api/projects/{self.project.id}/blocks{query}"

    def test_list_all(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 2)

    def test_filter_type(self):
        res = self.client.get(self._url("?type=sfx"))
        self.assertEqual([b["key"] for b in res.json()], ["p1_d2"])

    def test_filter_translated(self):
        res = self.client.get(self._url("?translated=1"))
        self.assertEqual([b["key"] for b in res.json()], ["p1_d2"])
        res = self.client.get(self._url("?translated=0"))
        self.assertEqual([b["key"] for b in res.json()], ["p1_d1"])

    def test_filter_search(self):
        res = self.client.get(self._url("?search=hello"))
        self.assertEqual([b["key"] for b in res.json()], ["p1_d1"])

    def test_filter_page(self):
        res = self.client.get(self._url("?page=1"))
        self.assertEqual(len(res.json()), 2)
        res = self.client.get(self._url("?page=2"))
        self.assertEqual(len(res.json()), 0)

    def test_patch_translation(self):
        res = self.client.patch(
            self._url(f"/{self.block1.id}"), {"translation": "Ø³Ù„Ø§Ù… Ø¯Ù†ÛŒØ§"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.block1.refresh_from_db()
        self.assertEqual(self.block1.translation, "Ø³Ù„Ø§Ù… Ø¯Ù†ÛŒØ§")

    def test_invalid_block_type_rejected(self):
        res = self.client.patch(
            self._url(f"/{self.block1.id}"), {"block_type": "bogus"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class JobSubmissionTests(TransactionTestCase):
    """Worker threads run outside the test transaction, so real thread jobs
    need TransactionTestCase to see committed rows."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()

    def test_job_runs_and_succeeds(self):
        with patch("studio.views._RUNNERS",
                   {"extract": _fake_runner()}):
            res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
        self.assertEqual(res.status_code, 202)
        job_id = res.json()["id"]
        for _ in range(100):
            job = Job.objects.get(pk=job_id)
            if job.status in (Job.Status.SUCCESS, Job.Status.FAILED):
                break
            time.sleep(0.05)
        self.assertEqual(job.status, Job.Status.SUCCESS)
        self.assertEqual(job.result, {"ok": True})
        self.assertEqual(job.progress, 1.0)

    def test_409_when_active_job_exists(self):
        # A pending/running job row on the project blocks new submissions,
        # but only while a live worker holds the project lock — a free lock
        # means the row is a zombie from a dead process and it self-heals
        # (see ZombieJobRecoveryTests).
        from . import jobs as job_infra

        lock = job_infra._lock_for(str(self.project.id))
        lock.acquire()
        try:
            Job.objects.create(project=self.project, kind=Job.Kind.EXTRACT,
                               status=Job.Status.RUNNING)
            with patch("studio.views._RUNNERS", {"extract": _fake_runner()}):
                res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
            self.assertEqual(res.status_code, 409)
        finally:
            lock.release()

    def test_cancelled_job_does_not_block_new_jobs(self):
        Job.objects.create(project=self.project, kind=Job.Kind.EXTRACT,
                           status=Job.Status.CANCELLED)
        with patch("studio.views._RUNNERS", {"extract": _fake_runner()}):
            res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
        self.assertEqual(res.status_code, 202)


class CancelFlowTests(TransactionTestCase):
    """End-to-end cooperative cancellation with a real worker thread."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()

    def _wait_for_status(self, job_id: str, *statuses, timeout: float = 10.0) -> Job:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = Job.objects.get(pk=job_id)
            if job.status in statuses:
                return job
            time.sleep(0.05)
        return Job.objects.get(pk=job_id)

    def test_cancel_running_job(self):
        def slow_runner(ctx: JobContext):
            ctx.progress(0.1, "working")
            while not ctx.cancel_event.is_set():
                time.sleep(0.02)
            ctx.check_cancelled()  # runner honours the flag
            return {"ok": True}  # never reached

        with patch("studio.views._RUNNERS", {"extract": slow_runner}):
            res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
            self.assertEqual(res.status_code, 202)
            job_id = res.json()["id"]

            job = self._wait_for_status(job_id, Job.Status.RUNNING)
            res = self.client.post(f"/api/jobs/{job_id}/cancel")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "cancelled")

            final = self._wait_for_status(
                job_id, Job.Status.CANCELLED, Job.Status.SUCCESS,
                Job.Status.FAILED)
            self.assertEqual(final.status, Job.Status.CANCELLED)
            self.assertEqual(final.error_message, "Cancelled by user")

            # Project settles back based on existing extraction results.
            self.project.refresh_from_db()
            self.assertEqual(
                self.project.status,
                Project.Status.READY if self.project.pages.exists()
                else Project.Status.CREATED,
            )

    def test_cancel_after_finish_returns_current_state(self):
        with patch("studio.views._RUNNERS", {"extract": _fake_runner()}):
            res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
            job_id = res.json()["id"]
            self._wait_for_status(job_id, Job.Status.SUCCESS)

            res = self.client.post(f"/api/jobs/{job_id}/cancel")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], Job.Status.SUCCESS)

    def test_cancelled_job_finalized_even_without_view_flip(self):
        """Simulate the lost-update: a job whose worker raises JobCancelled
        without the cancel view having flipped the row â€” the worker's own
        handler must finalize it to CANCELLED (regression: the row could
        stay RUNNING forever and 409 every future job submission)."""
        job = submit_job(self.project, "extract", {},
                         run=lambda ctx: (_ for _ in ()).throw(
                             JobCancelled("Cancelled by user")))
        final = self._wait_for_status(job.pk, Job.Status.CANCELLED)
        self.assertEqual(final.status, Job.Status.CANCELLED)
        self.assertEqual(final.error_message, "Cancelled by user")

    def test_cancelled_translate_counts_partial_translations(self):
        """Cancel mid-translation: blocks translated before the stop stay in
        the DB, so the project counter must include them (regression: the
        counter stayed 0 and rendering stayed locked after cancelling)."""
        page = Page.objects.create(project=self.project, page_number=1)
        blk = TextBlock.objects.create(
            project=self.project, page=page, key="p1_d1", original_text="Hello")

        def runner(ctx):
            saved = TextBlock.objects.get(pk=blk.pk)
            saved.translation = "Ø³Ù„Ø§Ù…"
            saved.save(update_fields=["translation"])
            ctx.progress(0.5, "chunk done")
            raise JobCancelled("Cancelled by user")

        job = submit_job(self.project, "translate", {}, run=runner)
        final = self._wait_for_status(job.pk, Job.Status.CANCELLED)
        self.assertEqual(final.status, Job.Status.CANCELLED)
        self.project.refresh_from_db()
        self.assertEqual(self.project.translated_count, 1)

    def test_failed_translate_counts_partial_translations(self):
        """Crash mid-translation: partial translations stay in the DB and
        must be counted so the UI never shows stale 0."""
        page = Page.objects.create(project=self.project, page_number=1)
        blk = TextBlock.objects.create(
            project=self.project, page=page, key="p1_d1", original_text="Hello")

        def runner(ctx):
            saved = TextBlock.objects.get(pk=blk.pk)
            saved.translation = "Ø³Ù„Ø§Ù…"
            saved.save(update_fields=["translation"])
            raise RuntimeError("provider exploded")

        job = submit_job(self.project, "translate", {}, run=runner)
        self._wait_for_status(job.pk, Job.Status.FAILED)
        self.project.refresh_from_db()
        self.assertEqual(self.project.translated_count, 1)

    def test_cancel_endpoint_syncs_counters_immediately(self):
        """The cancel view may run while the worker is still draining its
        current chunk; syncing counters right there lets the UI show the true
        count without waiting for the worker's (possibly slow) finalize."""
        page = Page.objects.create(project=self.project, page_number=1)
        TextBlock.objects.create(
            project=self.project, page=page, key="p1_d1",
            original_text="Hello", translation="Ø³Ù„Ø§Ù…")
        job = Job.objects.create(project=self.project, kind="translate",
                                 status=Job.Status.SUCCESS)  # terminal: flip matches 0 rows
        res = self.client.post(f"/api/jobs/{job.id}/cancel")
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.translated_count, 1)

    def test_cancel_view_settles_project_immediately(self):
        """Pressing stop must settle the project NOW, even though the worker
        zombie keeps draining its current provider call for minutes
        (regression: the badge kept showing 'translating' long after the
        cancel, because only the worker ever flipped the project status)."""
        Page.objects.create(project=self.project, page_number=1)
        self.project.status = Project.Status.TRANSLATING
        self.project.save(update_fields=["status"])
        job = Job.objects.create(project=self.project, kind="translate",
                                 status=Job.Status.RUNNING)
        res = self.client.post(f"/api/jobs/{job.id}/cancel")
        self.assertEqual(res.status_code, 200)
        self.job_status = job
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.READY)


class CancelGuardInvariantTests(TestCase):
    """Structural invariant behind cooperative cancellation.

    services.py wraps engine calls in broad ``except Exception`` handlers
    that log a fallback and keep going. If a JobCancelled raised inside an
    engine progress callback ever reaches one of those handlers, cancellation
    is swallowed: the worker logs a misleading "FAILED â€” fallback" line and
    burns the rest of the stage before the next choke point finalizes the
    row. So every broad ``except Exception`` in a try must be preceded by
    ``except JobCancelled: raise``.
    """

    def test_broad_excepts_re_raise_job_cancelled(self):
        import ast

        from . import services

        tree = ast.parse(
            Path(services.__file__).read_text(encoding="utf-8"))

        def type_name(t) -> str | None:
            if isinstance(t, ast.Name):
                return t.id
            if isinstance(t, ast.Attribute):
                return t.attr
            return None

        bad: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for idx, handler in enumerate(node.handlers):
                if type_name(handler.type) != "Exception":
                    continue
                guarded = any(
                    type_name(g.type) == "JobCancelled"
                    for g in node.handlers[:idx]
                )
                if not guarded:
                    bad.append(f"{handler.lineno}")
        self.assertEqual(
            bad, [],
            f"broad `except Exception` without an `except JobCancelled: "
            f"raise` guard earlier in the same try at line(s): {', '.join(bad)}"
        )


class ProviderTestEndpointTests(TestCase):
    """POST /api/config/test-provider runs one tiny real request against the
    configured provider/model/endpoint (the payload the UI sends, even if
    unsaved) — never the full 8-model retry cascade the real translate path
    uses, so a broken key answers in seconds instead of minutes."""

    _OK_COMPLETION = {
        "status_code": 200,
        "json": {"choices": [{"message": {"content": '{"hello": "سلام"}'}}]},
    }

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.url = "/api/config/test-provider"

    def _post_body(self, body: dict):
        # Django's Client has no `format=` kwarg (that's DRF APIClient);
        # passing it would leak into the request as an extra field.
        return self.client.post(self.url, json.dumps(body),
                                content_type="application/json")

    def test_custom_provider_ok(self):
        with patch("studio.services.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = self._OK_COMPLETION["json"]
            res = self._post_body({"provider": "custom",
                                   "custom": {"base_url": "http://relay.local/v1",
                                              "model": "m-1", "api_key": "sk-x"}})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        self.assertEqual(res.json()["model"], "m-1")
        self.assertIn("latency_ms", res.json())
        # Single attempt — one URL, not the cascade.
        self.assertEqual(post.call_count, 1)
        self.assertTrue(post.call_args.args[0].startswith("http://relay.local/"))

    def test_http_error_surfaced_with_message(self):
        with patch("studio.services.requests.post") as post:
            post.return_value.status_code = 401
            post.return_value.json.return_value = {
                "error": {"message": "Invalid API key"}}
            res = self._post_body({"provider": "custom",
                                   "custom": {"base_url": "http://relay.local/v1",
                                              "model": "m-1", "api_key": "bad"}})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["ok"])
        self.assertIn("Invalid API key", data["error"])

    def test_gemini_missing_key_fails_fast_without_network(self):
        with patch("studio.services.requests.post") as post:
            res = self._post_body({"provider": "gemini", "gemini": {"model": "gemini-2.0-flash"}})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["ok"])
        self.assertIn("key", data["error"].lower())
        self.assertEqual(post.call_count, 0)

    def test_unknown_provider_400(self):
        res = self._post_body({"provider": "carrier-pigeon"})
        self.assertEqual(res.status_code, 400)


class ZombieJobRecoveryTests(TransactionTestCase):
    """An active PENDING/RUNNING row with no live worker holding the project
    lock is a zombie left by a dead process (dev-server autoreload/restart
    kills the worker thread mid-provider-call, so finalize never runs). It
    used to 409 every new submit and spin the UI forever."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()

    def _wait_for_status(self, job_id: str, *statuses, timeout: float = 10.0) -> Job:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = Job.objects.get(pk=job_id)
            if job.status in statuses:
                return job
            time.sleep(0.05)
        return Job.objects.get(pk=job_id)

    def test_job_poll_heals_zombie_row(self):
        from . import jobs as job_infra

        self.assertFalse(job_infra.worker_alive(str(self.project.id)))
        Page.objects.create(project=self.project, page_number=1)
        self.project.status = Project.Status.TRANSLATING
        self.project.save(update_fields=["status"])
        job = Job.objects.create(project=self.project, kind="translate",
                                 status=Job.Status.RUNNING)

        res = self.client.get(f"/api/jobs/{job.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "failed")

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.FAILED)
        self.assertTrue(job.finished_at)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.READY)

    def test_job_poll_leaves_live_job_alone(self):
        from . import jobs as job_infra

        lock = job_infra._lock_for(str(self.project.id))
        lock.acquire()
        try:
            job = Job.objects.create(project=self.project, kind="extract",
                                     status=Job.Status.RUNNING)
            res = self.client.get(f"/api/jobs/{job.id}")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "running")
            job.refresh_from_db()
            self.assertEqual(job.status, Job.Status.RUNNING)
        finally:
            lock.release()

    def test_start_job_unbricks_zombie_and_submits(self):
        zombie = Job.objects.create(project=self.project, kind="extract",
                                    status=Job.Status.RUNNING)
        with patch("studio.views._RUNNERS", {"extract": _fake_runner()}):
            res = self.client.post(f"/api/projects/{self.project.id}/extract", {})
        self.assertEqual(res.status_code, 202)
        self.assertNotEqual(res.json()["id"], str(zombie.id))
        zombie.refresh_from_db()
        self.assertEqual(zombie.status, Job.Status.FAILED)
        self._wait_for_status(res.json()["id"], Job.Status.SUCCESS)

    def test_start_job_still_409_while_worker_alive(self):
        from . import jobs as job_infra

        lock = job_infra._lock_for(str(self.project.id))
        lock.acquire()
        try:
            Job.objects.create(project=self.project, kind="extract",
                               status=Job.Status.RUNNING)
            with patch("studio.views._RUNNERS",
                       {"extract": lambda ctx: {"ok": True}}):
                res = self.client.post(
                    f"/api/projects/{self.project.id}/extract", {})
            self.assertEqual(res.status_code, 409)
        finally:
            lock.release()


class JobTerminalStatusTests(TestCase):
    """run_clean / run_render_text must settle the project status they set
    to APPLYING at start. Regression: a finished clean left the project in
    APPLYING forever (recover_jobs only fixed it at the next restart)."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.project = _make_project()
        self._media_tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media_tmp.name)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._media_tmp.cleanup()

    def _ctx(self, kind: str) -> JobContext:
        job = Job.objects.create(project=self.project, kind=kind,
                                 status=Job.Status.RUNNING)
        return JobContext(job)

    def _set_applying(self) -> None:
        self.project.status = Project.Status.APPLYING
        self.project.save(update_fields=["status"])

    def test_clean_success_sets_project_ready(self):
        from PIL import Image

        Page.objects.create(project=self.project, page_number=1)
        self._set_applying()
        with patch("studio.services._load_page_image",
                   return_value=Image.new("RGB", (8, 8))), \
             patch("studio.services._inpaint_pages"):
            from . import services
            services.run_clean(self._ctx("clean"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.READY)

    def test_render_success_sets_project_ready(self):
        from PIL import Image

        from . import services

        page = Page.objects.create(project=self.project, page_number=1)
        cleaned_dir = Path(settings.MEDIA_ROOT) / "projects" / str(self.project.id) / "cleaned"
        cleaned_dir.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(cleaned_dir / f"page-{page.page_number}.jpg")
        self._set_applying()
        with patch("comic_translator.renderer.render_page_list",
                   return_value=([Image.new("RGB", (8, 8))],
                                 {"rendered_regions": 2})):
            services.run_render_text(self._ctx("render"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.READY)


class ConfigTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)

    def test_get_seeded_defaults(self):
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), dict)

    def test_put_deep_merges(self):
        GlobalSetting.objects.update_or_create(
            key="config",
            defaults={"value": {"ocr": {"dpi": 200, "confidence_min": 0.5}}},
        )
        res = self.client.put("/api/config",
                              {"ocr": {"dpi": 300}}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["ocr"]["dpi"], 300)
        self.assertEqual(res.json()["ocr"]["confidence_min"], 0.5)

    def test_put_rejects_non_dict(self):
        res = self.client.put("/api/config", [1, 2], format="json")
        self.assertEqual(res.status_code, 400)

    def test_get_ensures_provider_subobjects(self):
        """A stored config predating the custom provider still yields all
        provider cards: GET /api/config must always expose openrouter,
        gemini and custom sub-objects under translator, without clobbering
        existing values."""
        GlobalSetting.objects.update_or_create(
            key="config",
            defaults={"value": {
                "translator": {"provider": "gemini",
                               "gemini": {"api_key": "k", "model": "m"}},
            }},
        )
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        translator = res.json()["translator"]
        for key in ("openrouter", "gemini", "custom"):
            self.assertIsInstance(translator.get(key), dict, key)
        # Existing values untouched; missing card comes with editable fields.
        self.assertEqual(translator["gemini"]["api_key"], "k")
        self.assertEqual(translator["gemini"]["model"], "m")
        self.assertEqual(translator["custom"].get("base_url"), "")
        self.assertEqual(translator["custom"].get("api_key"), "")
        self.assertEqual(translator["custom"].get("model"), "")


class ProjectConfigMergeTests(TestCase):
    """_get_config merges project snapshots over global config. Project
    *_config snapshots are written once at creation with no edit UI, so an
    empty string in a snapshot (e.g. api_key saved in Settings AFTER the
    project existed) must not clobber the global value â€” jobs for
    pre-existing projects otherwise run keyless and the provider raises
    "OpenRouter API key not set"."""

    def _global(self, translator: dict) -> None:
        GlobalSetting.objects.update_or_create(
            key="config", defaults={"value": {"translator": translator}}
        )

    def test_empty_snapshot_key_does_not_clobber_global(self):
        self._global({
            "provider": "openrouter",
            "openrouter": {"api_key": "sk-or-live-key", "model": "m"},
        })
        p = _make_project(
            translator_config={"provider": "openrouter",
                               "openrouter": {"api_key": "", "model": "m"}},
        )
        cfg = _get_config(p)
        self.assertEqual(cfg.translator.openrouter_api_key, "sk-or-live-key")

    def test_nonempty_snapshot_still_overrides(self):
        self._global({
            "provider": "openrouter",
            "openrouter": {"api_key": "sk-global", "model": "m"},
        })
        p = _make_project(
            translator_config={"openrouter": {"api_key": "sk-project"}},
        )
        cfg = _get_config(p)
        self.assertEqual(cfg.translator.openrouter_api_key, "sk-project")

    def test_snapshot_can_clear_explicitly_different_value(self):
        # A snapshot that deliberately differs (model name) still wins.
        self._global({
            "provider": "openrouter",
            "openrouter": {"api_key": "sk-global", "model": "global-model"},
        })
        p = _make_project(
            translator_config={"openrouter": {"api_key": "sk-project",
                                              "model": "project-model"}},
        )
        cfg = _get_config(p)
        self.assertEqual(cfg.translator.openrouter_model, "project-model")

    def test_scalar_empty_does_not_clobber(self):
        self._global({"provider": "openrouter", "chunk_size": 50})
        p = _make_project(translator_config={"chunk_size": 0, "provider": ""})
        cfg = _get_config(p)
        # 0 is a legitimate override (falsy but not ""); "" is not.
        self.assertEqual(cfg.translator.provider, "openrouter")


class MaskMarkTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)

    def _url(self) -> str:
        return f"/api/projects/{self.project.id}/masks"

    def test_create_list_delete(self):
        res = self.client.post(
            self._url(),
            {"page_number": 1, "points": [[10, 10], [60, 14], [90, 40], [30, 44]]},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["page_number"], 1)
        mark_id = res.json()["id"]

        res = self.client.get(self._url() + "?page=1")
        self.assertEqual(len(res.json()), 1)
        res = self.client.get(self._url() + "?page=2")
        self.assertEqual(len(res.json()), 0)

        res = self.client.delete(f"{self._url()}/{mark_id}")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(MaskMark.objects.count(), 0)

    def test_create_rejects_short_or_malformed_points(self):
        for bad in ([[1, 2]], "nope", [[1, 2], [3, "x"], [4, 5]], []):
            res = self.client.post(self._url(),
                                   {"page_number": 1, "points": bad},
                                   format="json")
            self.assertEqual(res.status_code, 400, bad)
        self.assertEqual(MaskMark.objects.count(), 0)

    def test_region_property_bbox_and_polygon(self):
        mark = MaskMark.objects.create(
            project=self.project, page=self.page,
            points=[[10, 20], [50, 12], [40, 60]],
        )
        region = mark.region
        self.assertEqual(
            (region["x1"], region["y1"], region["x2"], region["y2"]),
            (10, 12, 50, 60),
        )
        self.assertEqual(region["text_boxes"], [mark.points])

    def test_mask_regions_by_page(self):
        from .services import _mask_regions_by_page

        page2 = Page.objects.create(project=self.project, page_number=2,
                                    width=800, height=1200)
        MaskMark.objects.create(project=self.project, page=self.page,
                                points=[[1, 1], [9, 1], [5, 9]])
        MaskMark.objects.create(project=self.project, page=page2,
                                points=[[5, 5], [15, 5], [10, 15]])
        regions = _mask_regions_by_page(self.project, {1})
        self.assertEqual(set(regions.keys()), {1})
        self.assertEqual(len(regions[1]), 1)
        self.assertEqual(regions[1][0]["x2"], 9)


class BlockGeometryPatchTests(APITestCase):
    """Regression: geometry PATCHes were silently dropped (serializer gap),
    so resized boxes snapped back on the next reload."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)
        self.block = TextBlock.objects.create(
            project=self.project, page=self.page, key="p1_d1",
            original_text="hi", x1=10, y1=10, x2=100, y2=50,
        )

    def test_patch_geometry_persists(self):
        res = self.client.patch(
            f"/api/projects/{self.project.id}/blocks/{self.block.id}",
            {"x1": 20, "y1": 30, "x2": 220, "y2": 120},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.block.refresh_from_db()
        self.assertEqual(
            (self.block.x1, self.block.y1, self.block.x2, self.block.y2),
            (20, 30, 220, 120),
        )


class BlockPatchRefreshesCountsTests(APITestCase):
    """Regression: hand-typed and JSON-imported translations PATCH blocks
    one by one, but Project.translated_count was only recomputed by
    translate/apply jobs — so manually translated projects stayed at 0 and
    the workspace's render gate (translated_count === 0) never opened."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)
        self.a = TextBlock.objects.create(project=self.project, page=self.page,
                                          key="p1_d1", original_text="a")
        self.b = TextBlock.objects.create(project=self.project, page=self.page,
                                          key="p1_d2", original_text="b")
        self.url = f"/api/projects/{self.project.id}/blocks"

    def test_patch_translation_updates_project_count(self):
        res = self.client.patch(f"{self.url}/{self.a.id}",
                                {"translation": "سلام"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.translated_count, 1)
        self.assertEqual(self.project.total_blocks, 2)

    def test_clearing_translation_decrements_count(self):
        self.b.translation = "قبلی"
        self.b.save(update_fields=["translation"])
        self.project.translated_count = 1
        self.project.save()
        res = self.client.patch(f"{self.url}/{self.b.id}",
                                {"translation": ""}, format="json")
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.translated_count, 0)

    def test_geometry_only_patch_skips_count_query(self):
        """Geometry patches don't touch translations — the save and its two
        COUNT queries are wasted work there."""
        with patch("studio.services._refresh_counts") as refresh:
            res = self.client.patch(f"{self.url}/{self.a.id}",
                                    {"x1": 11}, format="json")
        self.assertEqual(res.status_code, 200)
        refresh.assert_not_called()

    def test_create_updates_total_blocks(self):
        res = self.client.post(
            self.url,
            {"page_number": 1, "original_text": "new"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.project.refresh_from_db()
        self.assertEqual(self.project.total_blocks, 3)

    def test_delete_updates_total_blocks(self):
        with patch("studio.services._refresh_counts") as refresh:
            res = self.client.delete(f"{self.url}/{self.a.id}")
        self.assertEqual(res.status_code, 204)
        refresh.assert_called()


class BlockMoveShiftsTextBoxesTests(APITestCase):
    """Regression: moving a box PATCHed x1/y1/x2/y2 but left the OCR word
    boxes (text_boxes) at the old spot â€” clean/render masks prefer those
    polygons, so they erased the OLD location instead of the new one."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)
        self.url = f"/api/projects/{self.project.id}/blocks"

    def _make_block(self, **kw):
        params = dict(project=self.project, page=self.page, key="p1_d1",
                      original_text="hi", x1=10, y1=10, x2=110, y2=60,
                      text_boxes=[[[20, 20], [100, 20], [100, 50], [20, 50]]])
        params.update(kw)
        return TextBlock.objects.create(**params)

    def _patch(self, block, body):
        res = self.client.patch(f"{self.url}/{block.id}", body, format="json")
        self.assertEqual(res.status_code, 200, res.content[:300])
        block.refresh_from_db()
        return block

    def test_move_translates_word_boxes(self):
        block = self._patch(self._make_block(), {"x1": 30, "y1": 40, "x2": 130, "y2": 90})
        self.assertEqual(block.text_boxes,
                         [[[40, 50], [120, 50], [120, 80], [40, 80]]])

    def test_resize_scales_word_boxes(self):
        # Double width/height around the same origin â†’ word boxes scale too.
        block = self._patch(self._make_block(), {"x2": 210, "y2": 110})
        self.assertEqual(block.text_boxes,
                         [[[30, 30], [190, 30], [190, 90], [30, 90]]])

    def test_non_geometry_patch_leaves_word_boxes(self):
        block = self._patch(self._make_block(), {"translation": "Ø³Ù„Ø§Ù…"})
        self.assertEqual(block.text_boxes,
                         [[[20, 20], [100, 20], [100, 50], [20, 50]]])

    def test_degenerate_old_geometry_clears_word_boxes(self):
        # Zero-size boxes exist (default 0,0,0,0) â€” word boxes can't map
        # from them, so they are dropped and clean falls back to the bbox.
        block = self._make_block(x1=0, y1=0, x2=0, y2=0)
        block = self._patch(block, {"x1": 10, "y1": 10, "x2": 110, "y2": 60})
        self.assertEqual(block.text_boxes, [])

    def test_moved_block_feeds_clean_with_new_word_boxes(self):
        # End-to-end link: PATCH move â†’ clean's region builder must see the
        # shifted polygons (this is what the inpaint mask is built from).
        from . import services
        block = self._make_block(translation="Ø³Ù„Ø§Ù…")
        self._patch(block, {"x1": 30, "y1": 40, "x2": 130, "y2": 90})
        pages, pages_map, translations = services._scoped_targets(self.project, 1)
        self.assertEqual(len(pages), 1)
        key, eb = pages_map[1][0]
        self.assertEqual(key, block.key)
        self.assertEqual((eb.x1, eb.y1, eb.x2, eb.y2), (30, 40, 130, 90))
        self.assertEqual(eb.text_boxes,
                         [[[40, 50], [120, 50], [120, 80], [40, 80]]])
        self.assertEqual(translations, {block.key: "Ø³Ù„Ø§Ù…"})
        region = eb.region
        self.assertEqual(region["text_boxes"],
                         [[[40, 50], [120, 50], [120, 80], [40, 80]]])


class MediaViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self._media_tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media_tmp.name)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._media_tmp.cleanup()

    def _write(self, rel: str, content: bytes = b"hello") -> Path:
        path = Path(settings_media_root()) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_anonymous_reads_files(self):
        """Auth removed: media serves anonymously; traversal guards remain."""
        self._write("projects/x/pages/page-1.jpg", b"\xff\xd8 fake jpg")
        res = self.client.get("/media/projects/x/pages/page-1.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/jpeg")
        res.close()

    def test_outputs_gets_attachment_disposition(self):
        self.client.force_login(self.user)
        self._write("projects/x/outputs/out.pdf", b"%PDF-1.4")
        res = self.client.get("/media/projects/x/outputs/out.pdf")
        self.assertEqual(res.status_code, 200)
        self.assertIn("attachment", res["Content-Disposition"])
        res.close()

    def test_missing_file_404(self):
        self.client.force_login(self.user)
        res = self.client.get("/media/projects/none/pages/page-99.jpg")
        self.assertEqual(res.status_code, 404)

    def test_traversal_blocked(self):
        self.client.force_login(self.user)
        res = self.client.get("/media/..%2Fdb.sqlite3")
        self.assertIn(res.status_code, (404, 500))  # resolved â†’ outside root


def settings_media_root() -> str:
    from django.conf import settings

    return settings.MEDIA_ROOT


class RecoverJobsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")

    def test_reaps_stale_jobs_and_projects(self):
        stuck_running = _make_project(status=Project.Status.EXTRACTING)
        Page.objects.create(project=stuck_running, page_number=1)
        stuck_job = Job.objects.create(project=stuck_running,
                                       kind=Job.Kind.EXTRACT,
                                       status=Job.Status.RUNNING)
        fresh_project = _make_project(status=Project.Status.CREATED)

        call_command("recover_jobs")

        stuck_job.refresh_from_db()
        stuck_running.refresh_from_db()
        fresh_project.refresh_from_db()
        self.assertEqual(stuck_job.status, Job.Status.FAILED)
        self.assertEqual(stuck_job.error_message, "Interrupted by server restart")
        self.assertEqual(stuck_running.status, Project.Status.READY)
        self.assertEqual(fresh_project.status, Project.Status.CREATED)

    def test_project_without_pages_goes_to_created(self):
        stuck = _make_project(status=Project.Status.APPLYING)
        Job.objects.create(project=stuck, kind=Job.Kind.APPLY,
                           status=Job.Status.RUNNING)

        call_command("recover_jobs")

        stuck.refresh_from_db()
        self.assertEqual(stuck.status, Project.Status.CREATED)

    def test_recovered_project_counts_partial_translations(self):
        """A translate job killed by a server restart may have saved some
        translations already â€” recovery must re-sync the project counter."""
        stuck = _make_project(status=Project.Status.TRANSLATING)
        page = Page.objects.create(project=stuck, page_number=1)
        TextBlock.objects.create(project=stuck, page=page, key="p1_d1",
                                 original_text="A", translation="ÙØ§Ø±Ø³ÛŒ")
        stuck.translated_count = 0
        stuck.save(update_fields=["translated_count"])
        Job.objects.create(project=stuck, kind="translate",
                           status=Job.Status.RUNNING)

        call_command("recover_jobs")

        stuck.refresh_from_db()
        self.assertEqual(stuck.status, Project.Status.READY)
        self.assertEqual(stuck.translated_count, 1)

    def test_ignores_terminal_jobs_and_idle_projects(self):
        project = _make_project(status=Project.Status.READY)
        done = Job.objects.create(project=project, kind=Job.Kind.EXTRACT,
                                  status=Job.Status.SUCCESS)

        call_command("recover_jobs")

        done.refresh_from_db()
        project.refresh_from_db()
        self.assertEqual(done.status, Job.Status.SUCCESS)
        self.assertEqual(project.status, Project.Status.READY)


class SubmitJobUnitTests(TransactionTestCase):
    """Direct submit_job behaviour: lock guard and cancel event plumbing."""

    def test_second_job_while_running_raises(self):
        project = _make_project()
        release = {"flag": False}

        def blocker(ctx: JobContext):
            while not release["flag"]:
                time.sleep(0.02)
            return {}

        job1 = submit_job(project, Job.Kind.EXTRACT, {}, run=blocker)
        with self.assertRaises(RuntimeError):
            submit_job(project, Job.Kind.EXTRACT, {}, run=blocker)
        release["flag"] = True
        self._wait(job1.pk, Job.Status.SUCCESS)

    def test_progress_after_cancel_raises(self):
        project = _make_project(status=Project.Status.READY)
        job = Job.objects.create(project=project, kind=Job.Kind.EXTRACT,
                                 status=Job.Status.RUNNING)
        ctx = JobContext(job)
        ctx.progress(0.2, "ok")  # not cancelled yet
        from . import jobs as job_infra

        job_infra.request_cancel(job.id)
        with self.assertRaises(JobCancelled):
            ctx.progress(0.3, "nope")

    @staticmethod
    def _wait(job_id: str, status: str, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if Job.objects.get(pk=job_id).status == status:
                return
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} never reached {status}")


class FitFontSizeTests(TestCase):
    """Engine contract: fit_font_size always returns a (font, lines, fs)
    tuple. It used to fall through to an implicit None when text could not
    fit even at size_min, crashing render jobs with
    "cannot unpack non-iterable NoneType" (renderer.draw_persian)."""

    @staticmethod
    def _fit(text: str, box_w: int, box_h: int, size_max: int, size_min: int):
        from comic_translator.renderer import fit_font_size

        return fit_font_size(text, None, box_w, box_h, size_max, size_min)

    def test_overflow_returns_size_min_tuple(self):
        # Far too much text for a tiny box â€” the exact crash case.
        text = "Ù…ØªÙ† Ø¢Ø²Ù…Ø§ÛŒØ´ÛŒ Ø·ÙˆÙ„Ø§Ù†ÛŒ Ú©Ù‡ Ø¯Ø± Ø¬Ø¹Ø¨Ù‡ Ú©ÙˆÚ†Ú© Ø¬Ø§ Ù†Ù…ÛŒâ€ŒØ´ÙˆØ¯ " * 10
        result = self._fit(text, box_w=60, box_h=30, size_max=60, size_min=15)
        self.assertIsNotNone(result)
        font, lines, fs = result
        self.assertEqual(fs, 15)
        self.assertTrue(lines)

    def test_fitting_text_starts_at_size_max(self):
        font, lines, fs = self._fit("Ø³Ù„Ø§Ù…", box_w=400, box_h=300,
                                    size_max=48, size_min=15)
        self.assertEqual(fs, 48)
        self.assertTrue(lines)

    def test_size_min_is_hard_floor(self):
        # Odd size_min vs even size_max: the shrink loop steps by 2 and must
        # never land below the floor in the final fallback.
        text = "Ø®Ø· Ø¨Ù„Ù†Ø¯ ÙØ§Ø±Ø³ÛŒ Ø¨Ø±Ø§ÛŒ Ø¢Ø²Ù…ÙˆÙ† Ú©Ù Ø§Ù†Ø¯Ø§Ø²Ù‡ ÙÙˆÙ†Øª " * 5
        for size_min in (14, 15, 16):
            with self.subTest(size_min=size_min):
                font, lines, fs = self._fit(text, box_w=80, box_h=40,
                                            size_max=60, size_min=size_min)
                self.assertGreaterEqual(fs, size_min)


class SecurityRegressionTests(APITestCase):
    """Regression tests for the audit fixes: upload validation, config
    whitelist, media headers, block-create validation."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin123")
        self.client.force_login(self.user)
        self.project = _make_project()
        self.page = Page.objects.create(project=self.project, page_number=1,
                                        width=800, height=1200)

    # â”€â”€ Upload validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_upload_rejects_non_pdf_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("evil.html", b"<h1>x</h1>")
        res = self.client.post(
            "/api/projects",
            {"name": "P", "pdf_file": upload, "pdf_type": "manga"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    def test_upload_rejects_non_pdf_content(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("fake.pdf", b"<script>alert(1)</script>")
        res = self.client.post(
            "/api/projects",
            {"name": "P", "pdf_file": upload, "pdf_type": "manga"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    def test_upload_accepts_real_pdf_bytes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("t.pdf", b"%PDF-1.4 fake")
        res = self.client.post(
            "/api/projects",
            {"name": "P", "pdf_file": upload, "pdf_type": "manga"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)

    # â”€â”€ Media serving â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_media_uploaded_pdf_served_as_attachment(self):
        # Plant a file where an upload would live and point the project at it.
        pdfs = Path(settings.MEDIA_ROOT) / "projects" / "pdfs"
        pdfs.mkdir(parents=True, exist_ok=True)
        fname = f"{self.project.id}-t.pdf"
        (pdfs / fname).write_bytes(b"%PDF-1.4 fake")
        self.project.pdf_file.name = f"projects/pdfs/{fname}"
        self.project.save(update_fields=["pdf_file"])

        res = self.client.get(f"/media/projects/pdfs/{fname}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", res["Content-Disposition"])

    def test_media_blocks_traversal(self):
        res = self.client.get("/media/../../db.sqlite3")
        self.assertIn(res.status_code, (404, 400))

    # â”€â”€ Config whitelist (RCE chain) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_config_put_drops_unknown_keys(self):
        res = self.client.put("/api/config", {
            "inpaint": {"method": "cv_auto", "evil_key": "x"},
            "rogue_section": {"a": 1},
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("rogue_section", res.json())
        self.assertNotIn("evil_key", res.json()["inpaint"])

    def test_config_put_rejects_missing_cli_path(self):
        res = self.client.put("/api/config", {
            "inpaint": {"pcleaner_cli_path": "Z:/definitely/not/real.exe"},
        }, format="json")
        self.assertEqual(res.status_code, 400)

    # â”€â”€ Block create validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_block_create_bad_page_400_not_500(self):
        res = self.client.post(
            f"/api/projects/{self.project.id}/blocks",
            {"page_number": 999, "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_block_create_bad_geometry_400(self):
        res = self.client.post(
            f"/api/projects/{self.project.id}/blocks",
            {"page_number": 1, "x1": 50, "y1": 0, "x2": 10, "y2": 10},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_block_create_ok(self):
        res = self.client.post(
            f"/api/projects/{self.project.id}/blocks",
            {"page_number": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 50},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["key"].startswith("p1_m"))

    # â”€â”€ Job cancel race hardening: covered in CancelFlowTests (needs
    # TransactionTestCase â€” worker threads can't see uncommitted rows).
