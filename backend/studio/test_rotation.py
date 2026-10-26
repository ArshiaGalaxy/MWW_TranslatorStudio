"""Rotation storage, validation, and pixel-level renderer regression tests."""
from unittest import TestCase
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from PIL import Image, ImageChops

from comic_translator.config import FontConfig
from comic_translator.models import Block
from comic_translator.renderer import (
    ResolvedStyle, draw_persian, render_on_tall_image, render_page_list,
)
from studio.models import GlobalSetting, Page, Project, TextBlock
from studio.serializers import TextBlockUpdateSerializer


class RotationRenderTests(TestCase):
    def setUp(self):
        self.config = FontConfig(size_min=15, size_max=40)

    def test_rotation_about_box_center_preserves_alignment_and_background(self):
        for orientation in ("horizontal", "vertical"):
            for alignment in ("left", "center", "right"):
                for angle in (-90, 45, 90, 180):
                    with self.subTest(orientation=orientation, alignment=alignment, angle=angle):
                        local = Image.new("RGBA", (240, 160), (0, 0, 0, 0))
                        kwargs = dict(text_color="#000000", stroke_width=0,
                                      orientation=orientation, alignment=alignment)
                        draw_persian(local, "سلام\nدنیا", 0, 0, 240, 160,
                                     self.config, **kwargs)
                        self.assertIsNotNone(local.getbbox())
                        rotated = local.rotate(-angle, expand=True,
                                               resample=Image.Resampling.BICUBIC)
                        # Patterned background ensures only text, not the page, rotates.
                        background = Image.new("RGB", (500, 400), "#b0c0d0")
                        background.paste("#a0b0c0", (0, 0, 250, 400))
                        expected = background.copy()
                        expected.paste(rotated, (round((100 + 340 - rotated.width) / 2),
                                                 round((90 + 250 - rotated.height) / 2)), rotated)
                        actual = background.copy()
                        draw_persian(actual, "سلام\nدنیا", 100, 90, 340, 250,
                                     self.config, rotation=angle, **kwargs)
                        self.assertIsNone(ImageChops.difference(expected, actual).getbbox())

    def test_default_and_zero_angle_are_identical(self):
        for orientation in ("horizontal", "vertical"):
            first = Image.new("RGB", (400, 300), "white")
            second = first.copy()
            kwargs = dict(orientation=orientation, text_color="#000000")
            draw_persian(first, "سلام", 50, 50, 350, 250, self.config, **kwargs)
            draw_persian(second, "سلام", 50, 50, 350, 250, self.config,
                         rotation=0, **kwargs)
            self.assertIsNone(ImageChops.difference(first, second).getbbox())

    def test_engine_serialization_preserves_rotation(self):
        block = Block(page=1, text="test", x1=10, y1=10, x2=250, y2=150,
                      rotation=-32.5)
        self.assertEqual(Block.from_dict(block.to_dict()).rotation, -32.5)
        legacy = block.to_dict()
        del legacy["rotation"]
        self.assertEqual(Block.from_dict(legacy).rotation, 0)

    def test_page_renderer_passes_rotation(self):
        block = Block(page=1, text="test", x1=10, y1=10, x2=250, y2=150,
                      rotation=32.5)
        with patch("comic_translator.renderer.draw_persian", side_effect=lambda image, *a, **kw: image) as draw:
            render_page_list([Image.new("RGB", (300, 200), "white")],
                         {1: [("p1_d1", block)]}, {"p1_d1": "سلام"}, self.config)
        self.assertEqual(draw.call_args.kwargs["rotation"], 32.5)

    def test_tall_renderer_passes_rotation(self):
        region = ("p1_d1", 10, 10, 250, 150, "سلام", "#000000", [], "normal",
                  ResolvedStyle(rotation=-17.5))
        with patch("comic_translator.renderer.draw_persian", side_effect=lambda image, *a, **kw: image) as draw:
            render_on_tall_image([Image.new("RGB", (300, 200), "white")],
                                 [region], self.config)
        self.assertEqual(draw.call_args.kwargs["rotation"], -17.5)


class RotationEndpointTests(APITestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("rotation-user"))
        GlobalSetting.objects.create(key="config", value={"font": {"size_min": 15, "size_max": 40}})
        self.project = Project.objects.create(name="Rotation test")
        self.page = Page.objects.create(project=self.project, page_number=1, width=600, height=800)
        self.block = TextBlock.objects.create(project=self.project, page=self.page,
                                              key="p1_d1", translation="سلام",
                                              x1=100, y1=100, x2=400, y2=300)
        self.url = f"/api/projects/{self.project.id}/blocks/{self.block.id}"

    def test_patch_roundtrip_and_engine_mapping(self):
        for angle in (-180, -32.5, 0, 180):
            response = self.client.patch(self.url, {"rotation": angle}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.block.refresh_from_db()
            self.assertEqual(self.block.rotation, angle)
            self.assertEqual(self.block.to_engine_block().rotation, angle)
            response = self.client.get(self.url)
            self.assertEqual(response.data["rotation"], angle)

    def test_saved_rotation_reaches_render_endpoint_pixels(self):
        """Exercise PATCH -> render action -> real service -> generated JPEG."""
        import tempfile
        from pathlib import Path
        from django.test import override_settings
        from studio.jobs import JobContext
        from studio.models import Job

        self.block.translation = "سلام دنیا"
        self.block.color = "#000000"
        self.block.stroke_size = 0
        self.block.save()
        saved = self.client.patch(self.url, {"rotation": 90}, format="json")
        self.assertEqual(saved.status_code, 200)
        self.block.refresh_from_db()
        self.assertEqual(self.block.rotation, 90)

        # Only replace thread scheduling; execute the endpoint-selected runner
        # synchronously against this test DB and isolated media directory.
        def run_inline(project, kind, params, run):
            job = Job.objects.create(project=project, kind=kind, params=params)
            job.result = run(JobContext(job))
            job.status = Job.Status.SUCCESS
            job.save()
            return job

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            root = Path(media) / "projects" / str(self.project.id)
            (root / "cleaned").mkdir(parents=True)
            Image.new("RGB", (600, 800), "white").save(root / "cleaned/page-1.jpg")
            with patch("studio.views.submit_job", side_effect=run_inline):
                response = self.client.post(f"/api/projects/{self.project.id}/render",
                                            {"page_number": 1}, format="json")
            self.assertEqual(response.status_code, 202, response.data)
            self.assertEqual(response.data["result"]["rendered"], [1])
            with Image.open(root / "rendered/page-1.jpg") as rendered:
                ink = rendered.convert("L").point(lambda p: 255 if p < 100 else 0)
                bounds = ink.getbbox()
            self.assertIsNotNone(bounds)
            left, top, right, bottom = bounds
            self.assertGreater(bottom - top, (right - left) * 2)
            self.assertTrue(190 < (left + right) / 2 < 300, bounds)
            self.assertTrue(150 < (top + bottom) / 2 < 250, bounds)

    def test_rotation_rejects_nonfinite_and_out_of_range(self):
        for value in (-181, 181, "NaN", "Infinity", "-Infinity", "oops", None):
            with self.subTest(value=value):
                serializer = TextBlockUpdateSerializer(self.block, data={"rotation": value}, partial=True)
                self.assertFalse(serializer.is_valid())
                self.assertIn("rotation", serializer.errors)

    def test_preview_rotation_draft_does_not_persist(self):
        response = self.client.post(f"/api/projects/{self.project.id}/preview-layout", {
            "page_number": 1, "blocks": [{"id": str(self.block.id), "translation": "سلام",
                "x1": 100, "y1": 100, "x2": 400, "y2": 300, "rotation": 27.5}],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data[str(self.block.id)]["rotation"], 27.5)
        self.block.refresh_from_db()
        self.assertEqual(self.block.rotation, 0)
