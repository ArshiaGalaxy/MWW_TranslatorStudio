from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace
from studio.chapter_import import ChapterImages, discover, selected_urls, fetch_public


class ChapterImportTests(TestCase):
    def test_discovery_selection_order_and_scope(self):
        project = SimpleNamespace(pk='project')
        html = b'<img data-src="/p2.jpg"><img src="p1.png"><img src="/p2.jpg">'
        with patch('studio.chapter_import.fetch_public', return_value=(html, 'https://example.org/chapter/', 'text/html')):
            result = discover(project, 'https://example.org/chapter/')
        self.assertEqual([im['url'] for im in result['images']], ['https://example.org/p2.jpg', 'https://example.org/chapter/p1.png'])
        self.assertEqual(selected_urls(project, result['token'], [1, 0])[0], 'https://example.org/chapter/p1.png')
        with self.assertRaises(ValueError):
            selected_urls(SimpleNamespace(pk='other'), result['token'], [0])
        with self.assertRaises(ValueError):
            selected_urls(project, result['token'], [0, 0])

    def test_private_destination_rejected_before_connection(self):
        with patch('studio.chapter_import.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), patch('studio.chapter_import.urllib3.HTTPSConnectionPool') as connect:
            with self.assertRaises(ValueError):
                fetch_public('https://example.org/a', 100)
            connect.assert_not_called()

    def test_relative_lazy_and_unsafe_images(self):
        parser = ChapterImages('https://example.org/chapter/')
        parser.feed('<img src="data:image/png,x" data-original="../page.jpg"><img src="javascript:x"><img srcset="/small.jpg 1x, /large.jpg 2x">')
        self.assertEqual([im['url'] for im in parser.images], ['https://example.org/page.jpg', 'https://example.org/large.jpg'])
