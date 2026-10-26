import tempfile
from pathlib import Path
from django.test import override_settings
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from PIL import Image
from studio.models import Project, Page, TextBlock, MaskMark, Job
from studio.services import _extract_stored_pages


class FakeContext:
    def __init__(self, job):
        self.job = job
    def progress(self, value, stage=None): pass
    def log(self, message): pass
    def check_cancelled(self): pass


class StoredExtractionTests(APITestCase):
    def test_extract_uses_surviving_pages_not_pdf(self):
        from unittest.mock import patch
        project = Project.objects.create(name='Stored mode', uses_page_sources=True)
        root = Path('media/projects') / str(project.pk)
        self.addCleanup(lambda: __import__('shutil').rmtree(root.parent / str(project.pk), ignore_errors=True))
        page = Page.objects.create(project=project, page_number=2, width=10, height=10)
        job = Job.objects.create(project=project, kind='extract', params={'covers': [1]})
        called = []
        with patch('studio.services.run_reocr', side_effect=lambda ctx: called.append(ctx.job.params['page_number']) or {'found': 3}):
            result = _extract_stored_pages(FakeContext(job))
        self.assertEqual(result, {'pages': 1, 'blocks': 3})
        self.assertEqual(called, [2])
        job.refresh_from_db()
        self.assertNotIn('page_number', job.params)
        project.refresh_from_db()
        self.assertEqual(project.total_pages, 1)
        self.assertEqual(project.status, Project.Status.READY)
        self.assertTrue(project.pages.filter(pk=page.pk).exists())


class PageDeletionTests(APITestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client.force_login(User.objects.create_user('pages-user'))
        self.project = Project.objects.create(name='Pages')
        self.root = Path(self.tmp.name) / 'projects' / str(self.project.pk)
        for folder in ('pages', 'cleaned', 'rendered'):
            (self.root / folder).mkdir(parents=True)
            for n in (1, 2, 3):
                Image.new('RGB', (100, 200), 'white').save(self.root / folder / f'page-{n}.jpg')
        self.pages = [Page.objects.create(project=self.project, page_number=n, width=100, height=200) for n in (1, 2, 3)]
        self.block = TextBlock.objects.create(project=self.project, page=self.pages[1], translation='test')
        MaskMark.objects.create(project=self.project, page=self.pages[1], points=[[1, 1], [2, 2]])
        self.url = f'/api/projects/{self.project.pk}/pages/{self.pages[1].pk}'

    def test_delete_preserves_sources_and_other_pages(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204, response.data)
        self.project.refresh_from_db()
        self.assertTrue(self.project.uses_page_sources)
        self.assertEqual(list(self.project.pages.values_list('page_number', flat=True)), [1, 3])
        self.assertEqual(self.project.total_pages, 2)
        self.assertEqual(self.project.total_blocks, 0)
        self.assertFalse(MaskMark.objects.exists())
        for folder in ('sources', 'pages', 'cleaned', 'rendered'):
            self.assertFalse((self.root / folder / 'page-2.jpg').exists())
            self.assertTrue((self.root / folder / 'page-3.jpg').exists())

    def test_active_job_guard(self):
        Job.objects.create(project=self.project, kind='render')
        self.assertEqual(self.client.delete(self.url).status_code, 409)
        self.assertEqual(self.project.pages.count(), 3)

    def test_chapter_link_adds_selected_pages(self):
        from unittest.mock import patch
        from io import BytesIO
        from studio.jobs import JobContext
        image = BytesIO()
        Image.new('RGB', (120, 240), 'white').save(image, format='PNG')
        def fetched(url, limit):
            if url.endswith('/chapter'):
                return b'<img src="/page.png">', url, 'text/html'
            return image.getvalue(), url, 'image/png'
        def inline(project, kind, params, run):
            job = Job.objects.create(project=project, kind=kind, params=params)
            job.result = run(JobContext(job))
            job.status = Job.Status.SUCCESS
            job.save()
            return job
        base = f'/api/projects/{self.project.pk}'
        with patch('studio.chapter_import.fetch_public', side_effect=fetched), patch('studio.views.submit_job', side_effect=inline):
            discovery = self.client.post(base + '/chapter-images', {'url': 'https://example.org/chapter'}, format='json')
            self.assertEqual(discovery.status_code, 200)
            imported = self.client.post(base + '/import-pages', {'token': discovery.data['token'], 'indices': [0]}, format='json')
            self.assertEqual(imported.status_code, 202, imported.data)
        self.assertEqual(imported.data['result']['imported'], [4])
        self.assertEqual(self.project.pages.count(), 4)
        self.assertTrue((self.root / 'sources/page-4.jpg').exists())
        self.block.refresh_from_db()
        self.assertEqual(self.block.translation, 'test')

    def test_missing_preview_loads_durable_source(self):
        from studio.page_sources import preserve_sources
        from studio.services import _load_page_image
        preserve_sources(self.project)
        (self.root / 'pages/page-3.jpg').unlink()
        with _load_page_image(self.project, 3) as image:
            self.assertEqual(image.size, (100, 200))

    def test_project_scope(self):
        other = Project.objects.create(name='Other')
        self.assertEqual(self.client.delete(f'/api/projects/{other.pk}/pages/{self.pages[1].pk}').status_code, 404)


def _jpeg_bytes(w=120, h=240, color='white'):
    from io import BytesIO
    from django.core.files.uploadedfile import SimpleUploadedFile
    buf = BytesIO()
    Image.new('RGB', (w, h), color).save(buf, format='JPEG')
    return SimpleUploadedFile('up.jpg', buf.getvalue(), content_type='image/jpeg')


class AppendImagesTests(APITestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client.force_login(User.objects.create_user('append-user'))
        self.project = Project.objects.create(name='Append')
        self.root = Path(self.tmp.name) / 'projects' / str(self.project.pk)
        for folder in ('sources', 'pages'):
            (self.root / folder).mkdir(parents=True)
            for n in (1, 2, 3):
                Image.new('RGB', (100, 200), 'white').save(self.root / folder / f'page-{n}.jpg')
        self.pages = [Page.objects.create(project=self.project, page_number=n, width=100, height=200) for n in (1, 2, 3)]
        self.block = TextBlock.objects.create(project=self.project, page=self.pages[2],
                                              x1=10, y1=10, x2=50, y2=50, translation='t')
        self.project.cover_pages = [1]
        self.project.save(update_fields=['cover_pages'])
        self.url = f'/api/projects/{self.project.pk}/pages/append'

    def _post(self, files, position='end'):
        return self.client.post(self.url, {'position': position, 'images': files}, format='multipart')

    def test_append_end(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self._post([_jpeg_bytes(), _jpeg_bytes()])
        self.assertEqual(res.status_code, 201, res.content[:500])
        self.assertEqual(res.json()['inserted'], [4, 5])
        self.assertEqual(self.project.pages.count(), 5)
        self.assertTrue((self.root / 'pages/page-5.jpg').exists())
        self.assertTrue((self.root / 'sources_original/page-4.jpg').exists())

    def test_append_start_shifts_numbers_files_covers_and_blocks(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self._post([_jpeg_bytes()], 'start')
        self.assertEqual(res.status_code, 201, res.content[:500])
        self.assertEqual(res.json()['inserted'], [1])
        numbers = list(self.project.pages.order_by('page_number').values_list('page_number', flat=True))
        self.assertEqual(numbers, [1, 2, 3, 4])
        # Old page 3 (with the block) is now page 4; block followed its Page row.
        self.block.refresh_from_db()
        self.assertEqual(self.block.page.page_number, 4)
        self.assertEqual(self.block.x1, 10)
        # Cover list remapped; shifted image files exist at new numbers.
        self.project.refresh_from_db()
        self.assertEqual(self.project.cover_pages, [2])
        self.assertTrue((self.root / 'pages/page-4.jpg').exists())
        self.assertTrue((self.root / 'sources/page-2.jpg').exists())

    def test_append_after_middle(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self._post([_jpeg_bytes()], '2')
        self.assertEqual(res.status_code, 201, res.content[:500])
        self.assertEqual(res.json()['inserted'], [3])
        self.block.refresh_from_db()
        self.assertEqual(self.block.page.page_number, 4)

    def test_append_rejects_non_image_and_bad_position(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('x.txt', b'hello', content_type='text/plain')
        self.assertEqual(self._post([bad]).status_code, 400)
        self.assertEqual(self._post([_jpeg_bytes()], '99').status_code, 400)
        self.assertEqual(self._post([_jpeg_bytes()], 'bogus').status_code, 400)

    def test_append_conflicts_with_running_job(self):
        Job.objects.create(project=self.project, kind='render')
        self.assertEqual(self._post([_jpeg_bytes()]).status_code, 409)


class CropPageTests(APITestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client.force_login(User.objects.create_user('crop-user'))
        self.project = Project.objects.create(name='Crop', uses_page_sources=True)
        self.root = Path(self.tmp.name) / 'projects' / str(self.project.pk)
        for folder in ('sources', 'pages', 'cleaned', 'rendered'):
            (self.root / folder).mkdir(parents=True)
            Image.new('RGB', (100, 200), 'white').save(self.root / folder / 'page-1.jpg')
        (self.root / 'sources_original').mkdir(parents=True)
        Image.new('RGB', (100, 200), 'white').save(self.root / 'sources_original' / 'page-1.png')
        self.page = Page.objects.create(project=self.project, page_number=1, width=100, height=200)
        # Fully inside / touching-outside / fully outside blocks.
        self.inside = TextBlock.objects.create(
            project=self.project, page=self.page, key='p1_d1',
            x1=10, y1=10, x2=40, y2=40, text_boxes=[[[12, 12], [38, 38]]],
            translation='in')
        self.partial = TextBlock.objects.create(
            project=self.project, page=self.page, key='p1_d2',
            x1=30, y1=30, x2=90, y2=90, translation='part')
        self.outside = TextBlock.objects.create(
            project=self.project, page=self.page, key='p1_d3',
            x1=70, y1=150, x2=95, y2=195, translation='out')
        MaskMark.objects.create(project=self.project, page=self.page,
                                points=[[12, 12], [30, 30], [20, 40]])
        MaskMark.objects.create(project=self.project, page=self.page,
                                points=[[80, 160], [90, 170], [85, 180]])
        self.url = f'/api/projects/{self.project.pk}/pages/{self.page.pk}/crop'

    def test_crop_keeps_inside_shifts_and_drops_rest(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(self.url, {'x1': 0, 'y1': 0, 'x2': 60, 'y2': 100}, format='json')
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertEqual((body['width'], body['height']), (60, 100))
        self.assertEqual((body['kept_blocks'], body['removed_blocks']), (1, 2))
        self.assertEqual((body['kept_marks'], body['removed_marks']), (1, 1))
        self.inside.refresh_from_db()
        self.assertEqual((self.inside.x1, self.inside.y1), (10, 10))
        self.assertEqual(self.inside.text_boxes, [[[12, 12], [38, 38]]])
        self.assertFalse(TextBlock.objects.filter(pk__in=[self.partial.pk, self.outside.pk]).exists())
        self.page.refresh_from_db()
        self.assertEqual((self.page.width, self.page.height), (60, 100))
        with Image.open(self.root / 'pages/page-1.jpg') as im:
            self.assertEqual(im.size, (60, 100))
        with Image.open(self.root / 'sources/page-1.jpg') as im:
            self.assertEqual(im.size, (60, 100))
        # Derivatives invalidated for rebuild; archival original cropped too.
        self.assertFalse((self.root / 'cleaned/page-1.jpg').exists())
        self.assertFalse((self.root / 'rendered/page-1.jpg').exists())
        self.assertTrue((self.root / 'sources_original/page-1.png').exists())
        self.project.refresh_from_db()
        self.assertEqual((self.project.total_pages, self.project.total_blocks), (1, 1))

    def test_crop_rejects_bad_rect(self):
        self.assertEqual(
            self.client.post(self.url, {'x1': 10, 'y1': 10, 'x2': 20, 'y2': 20}, format='json').status_code, 400)
        self.assertEqual(
            self.client.post(self.url, {'x1': 0, 'y1': 0, 'x2': 500, 'y2': 500}, format='json').status_code, 400)
        self.assertEqual(
            self.client.post(self.url, {'x1': 50, 'y1': 10, 'x2': 10, 'y2': 90}, format='json').status_code, 400)

    def test_crop_conflicts_with_running_job(self):
        Job.objects.create(project=self.project, kind='render')
        res = self.client.post(self.url, {'x1': 0, 'y1': 0, 'x2': 60, 'y2': 100}, format='json')
        self.assertEqual(res.status_code, 409)
