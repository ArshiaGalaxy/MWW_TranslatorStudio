"""Regression tests for renderer/preview font-size parity."""
from unittest import TestCase
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from studio.models import GlobalSetting, Job, Page, Project, TextBlock

from PIL import Image, ImageDraw

from comic_translator.config import FontConfig
from comic_translator.renderer import draw_persian, find_font, text_layout


class RenderLayoutParityTests(TestCase):
    def test_drawing_uses_the_preview_fitted_font(self):
        config = FontConfig(size_min=15, size_max=40)
        font_path = find_font(config)
        self.assertIsNotNone(font_path, "Test requires a shipped font")
        text = "سلام\nدنیا"
        # Two explicit lines fit at 30px: 2*30*2 + 10 = 130.
        # 32px needs 138px and must shrink for this 132px-high box.
        layout = text_layout(text, 600, 132, config, font_path)
        self.assertEqual(layout["font_size"], 30)
        self.assertEqual(layout["lines"], ["سلام", "دنیا"])
        image = Image.new("RGB", (600, 132), "white")
        actual_draw = ImageDraw.ImageDraw.multiline_text
        used_sizes = []

        def capture(draw, xy, content, *args, **kwargs):
            used_sizes.append(kwargs["font"].size)
            return actual_draw(draw, xy, content, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, "multiline_text", capture):
            result = draw_persian(
                image, text, 0, 0, 600, 132, config,
                font_path=font_path, text_color="#000000", stroke_width=0,
            )
        self.assertIs(result, image)
        self.assertEqual(used_sizes, [layout["font_size"]])
        self.assertNotEqual(image.getextrema(), ((255, 255),) * 3)

    def test_size_bounds_and_manual_breaks(self):
        config = FontConfig(size_min=15, size_max=40)
        for text, width, height, override in [
            ("سلام", 600, 500, None),
            ("سلام\n\nدنیا", 600, 132, 40),
            ("سلام دنیا " * 20, 100, 40, None),
            ("سلام", 600, 500, 22),
            ("سلام", 600, 500, 6),
        ]:
            with self.subTest(text=text, override=override):
                from comic_translator.renderer import fit_font_size
                fp = find_font(config)
                expected = fit_font_size(text, fp, width, height,
                                         max(15, override or 40), 15)
                layout = text_layout(text, width, height, config, fp,
                                     font_size_max=override)
                self.assertEqual(layout["font_size"], expected[2])
                self.assertEqual(layout["lines"], expected[1])


    def test_alignment_reaches_the_render(self):
        """The panel sends left/right; render must honor them (regression)."""
        config = FontConfig(size_min=15, size_max=40)
        font_path = find_font(config)
        text = "سلام"
        image = Image.new("RGB", (600, 132), "white")
        actual_draw = ImageDraw.ImageDraw.multiline_text
        x_positions = []

        def capture(draw, xy, content, *args, **kwargs):
            x_positions.append(xy[0])
            return actual_draw(draw, xy, content, *args, **kwargs)

        left_w = None
        for alignment in ("left", "right", "center", "ltr", "rtl"):
            x_positions.clear()
            with patch.object(ImageDraw.ImageDraw, "multiline_text", capture):
                draw_persian(Image.new("RGB", (600, 132), "white"), text,
                             0, 0, 600, 132, config, font_path=font_path,
                             text_color="#000000", stroke_width=0,
                             alignment=alignment)
            self.assertEqual(len(x_positions), 1, alignment)
            tw = text_layout(text, 600, 132, config, font_path)["bbox"][2]
            if alignment in ("left", "ltr"):
                self.assertAlmostEqual(x_positions[0], 4, delta=2, msg=alignment)
                left_w = x_positions[0]
            elif alignment in ("right", "rtl"):
                self.assertAlmostEqual(x_positions[0], 600 - tw - 4, delta=2, msg=alignment)
            else:
                self.assertAlmostEqual(x_positions[0], (600 - tw) / 2, delta=2, msg=alignment)
        self.assertGreater(600 - tw - left_w, 100, "left vs right must differ")


class PreviewEndpointTests(APITestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("preview-user"))
        GlobalSetting.objects.create(key="config", value={"font": {"size_min": 15, "size_max": 40}})
        self.project = Project.objects.create(name="Preview test")
        self.page = Page.objects.create(project=self.project, page_number=1, width=600, height=800)
        self.block = TextBlock.objects.create(
            project=self.project, page=self.page, key="p1_d1", translation="stored",
            x1=0, y1=0, x2=600, y2=132,
        )
        self.url = f"/api/projects/{self.project.id}/preview-layout"
        self.draft = {"id": str(self.block.id), "translation": "سلام\nدنیا",
                      "x1": 0, "y1": 0, "x2": 600, "y2": 132}

    def post(self, drafts=None, page=1):
        return self.client.post(self.url, {"page_number": page,
                                "blocks": drafts if drafts is not None else [self.draft]}, format="json")

    def test_layout_and_no_writes(self):
        result = self.post()
        self.assertEqual(result.status_code, 200, result.data)
        layout = result.data[str(self.block.id)]
        self.assertEqual(layout["font_size"], 30)
        self.assertEqual([line["text"] for line in layout["lines"]], ["سلام", "دنیا"])
        self.assertTrue(layout["font_url"].startswith("/api/fonts/"))
        self.block.refresh_from_db()
        self.assertEqual(self.block.translation, "stored")
        self.assertFalse(Job.objects.exists())
        font = self.client.get(layout["font_url"])
        self.assertEqual(font.status_code, 200)
        font.close()

    def test_open_access(self):
        self.client.logout()
        self.assertEqual(self.post().status_code, 200)

    def test_scope_and_invalid_inputs(self):
        self.assertEqual(self.post(page=2).status_code, 400)
        other = Project.objects.create(name="Other project")
        self.url = f"/api/projects/{other.id}/preview-layout"
        self.assertEqual(self.post().status_code, 400)
        self.url = f"/api/projects/{self.project.id}/preview-layout"
        for patch_data in [{"x2": 0}, {"font_size_override": 999},
                           {"font_override": "not-a-shipped-font.ttf"},
                           {"translation": "x" * 20001}]:
            with self.subTest(patch_data=patch_data.keys()):
                self.assertEqual(self.post([{**self.draft, **patch_data}]).status_code, 400)
        self.assertEqual(self.post([self.draft, self.draft]).status_code, 400)
        self.assertEqual(self.post([self.draft] * 101).status_code, 400)

    def test_empty_and_sfx_are_skipped(self):
        for patch_data in [{"translation": "  "}, {"block_type": "sfx"}]:
            result = self.post([{**self.draft, **patch_data}])
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data[str(self.block.id)], {"skipped": True})

    def test_alignment_changes_line_anchors(self):
        for alignment, expected_x in [("left", 4.0), ("center", 300.0), ("right", 596.0)]:
            with self.subTest(alignment=alignment):
                result = self.post([{**self.draft, "alignment": alignment}])
                self.assertEqual(result.status_code, 200)
                layout = result.data[str(self.block.id)]
                self.assertEqual(layout["align"], alignment)
                for line in layout["lines"]:
                    self.assertAlmostEqual(line["x"], expected_x, delta=2)
