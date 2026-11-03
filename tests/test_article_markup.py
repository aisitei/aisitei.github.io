"""Regression coverage for translated HTML escaping its language container."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'crawler'))
BROKEN='<ul><li>第一项<ul><li>细节</li></ul><p>说明。</div><li>第二项</li></ul><p>结尾。</p>'

class ArticleMarkupTests(unittest.TestCase):
    def assert_contained(self,text):
        doc=BeautifulSoup(text,'html.parser')
        main=doc.select_one('.article-main')
        self.assertIsNotNone(main.select_one('.images-section'))
        self.assertEqual(len(main.select('.article-body > .lang-body')),4)
        self.assertIsNotNone(main.select_one('.source-footer'))
        for lang in ('ko','zh','ja','en'):
            self.assertIsNotNone(main.select_one(f'.article-body > .lang-body[data-lang="{lang}"]'))

    def test_reported_article_keeps_languages_gallery_and_source_in_main(self):
        path=ROOT/'articles/2026-11/2026-11-03/vivo-x500-pro-vs-iphone-17-pro/index.html'
        self.assert_contained(path.read_text())

    def test_generated_translation_cannot_close_the_article_layout(self):
        from html_generator import render_html
        original=SimpleNamespace(category='phone',image_urls=[],url='https://example.com/story',source='gizmochina',title='Source',brand='Vivo',brand_color='#123456',author='Author')
        article=SimpleNamespace(original=original,titles={'ko':'제목'},bodies={'ko':['<p>한국어 본문</p>'],'zh':[BROKEN],'ja':['<p>日本語</p>'],'en':['<p>English</p>']},image_translations={})
        self.assert_contained(render_html(article,'2026-11-03',['images/photo.jpg']))

    def test_valid_article_formatting_and_entities_survive_normalization(self):
        from html_fragments import normalize_body_html
        fragment='<h3>제목</h3><p>A &amp; B <strong>강조</strong></p><ul><li>첫째</li></ul><table><tr><td>사양</td></tr></table>'
        self.assertEqual(normalize_body_html(fragment),fragment)

    def test_backfilled_translation_keeps_following_language_inside_wrapper(self):
        from backfill_multilang import build_lang_body_inner
        fragment=build_lang_body_inner([BROKEN])
        doc=BeautifulSoup('<main><div class="lang-body">'+fragment+'</div><div id="next">Next language</div></main>','html.parser')
        self.assertIsNotNone(doc.select_one('main > #next'))
        self.assertIn('结尾。',doc.select_one('.lang-body').get_text())
        self.assertNotIn('<div',fragment)

if __name__=='__main__':unittest.main()
