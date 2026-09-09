import unittest
import build


def article(i=0):
    return dict(title=f'기사 {i}', title_ko=f'기사 {i}', title_en=f'News {i}',
                title_ja=f'記事 {i}', title_zh=f'新闻 {i}', url=f'articles/{i}/index.html',
                date='2026-09-09', month='2026-09', category='camera',
                brand='Sony', brand_color='#123456', thumbnail='')


class HomeTests(unittest.TestCase):
    def test_home_has_bounded_cards_and_real_next_page(self):
        page = build.build_page([article(i) for i in range(61)], 'IT뉴스', 'index')
        self.assertEqual(page.count('class="news-card'), 24)
        self.assertIn('news/page-2.html', page)
        self.assertNotIn('기사 60', page)

    def test_brand_does_not_add_unrelated_category(self):
        badges = build.article_badges_html(article())
        self.assertNotIn('스마트폰', badges)
        self.assertIn('카메라', badges)


if __name__ == '__main__':
    unittest.main()

class GenerationTests(unittest.TestCase):
    def test_corpus_survives_pagination_and_escapes_inline_script(self):
        import json
        import tempfile
        from pathlib import Path
        from site_ui import write_home_files
        with tempfile.TemporaryDirectory() as folder:
            records = [article(i) for i in range(61)]
            records[0]['title_ko'] = '</script><script>alert(1)</script>'
            write_home_files(folder, records)
            root = Path(folder)
            self.assertEqual(len(json.loads((root/'assets/data/articles.json').read_text())), 61)
            page = (root/'news/page-3.html').read_text()
            self.assertIn('기사 60', page)
            self.assertIn('<base href="../">', page)
            self.assertIn('href="news/page-3.html#news-content"', page)
            self.assertNotIn('</script><script>alert', (root/'index.html').read_text())

    def test_migration_preserves_body_and_disables_mid_typing_navigation(self):
        from site_ui import upgrade_article
        text = '<head></head><main class="article-main"><div class="lang-body" data-lang="ko"><p>원래 본문 &amp; 사진</p></div></main><script>\n    // 입력 중에도 딜레이 후 이동\n    setTimeout(go, 800);\n  </script>'
        result = upgrade_article(text, '../../../../')
        self.assertIn('assets/news.js', result)
        self.assertIn('<p>원래 본문 &amp; 사진</p>', result)
        self.assertNotIn('setTimeout(go', result)
        self.assertEqual(upgrade_article(result, '../../../../'), result)

    def test_migration_puts_title_before_image_without_reserializing_body(self):
        from site_ui import upgrade_article
        body = '<div class="lang-body" data-lang="ko"><p>원문 <em>유지</em></p></div>'
        text = '<head></head><main class="article-main"><div class="hero-image-wrap"><img src="x.jpg"></div><!-- meta --><div class="article-meta"><div><h1>제목</h1></div></div>'+body+'</main>'
        result = upgrade_article(text, '../../../../')
        self.assertLess(result.index('<h1>제목'), result.index('<img src="x.jpg"'))
        self.assertIn(body, result)
        self.assertEqual(upgrade_article(result, '../../../../'), result)

    def test_file_migration_preserves_embedded_carriage_return(self):
        import tempfile
        from pathlib import Path
        from site_ui import upgrade_article_files
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'articles'/'example'/'index.html'
            path.parent.mkdir(parents=True)
            original=b'<head></head><main class="article-main"><div class="article-meta"><h1>Title</h1></div><div class="article-body"><p>4500 $\rightarrow$ 4850</p></div></main>'
            path.write_bytes(original)
            upgrade_article_files(Path(folder))
            self.assertIn(b'4500 $\rightarrow$ 4850', path.read_bytes())

    def test_report_reader_uses_its_own_search_corpus(self):
        page=build.build_page([article(i) for i in range(30)],'발표회 정리','smartphone')
        self.assertIn('assets/data/reports.json',page)
        self.assertIn('report-pages/page-2.html',page)
