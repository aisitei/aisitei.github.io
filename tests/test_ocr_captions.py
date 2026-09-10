import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'crawler'))
import ocr
import backfill_captions

class OCRTests(unittest.TestCase):
    def test_scheduled_environment_resolves_homebrew_tesseract(self):
        buffer=io.BytesIO();Image.new('RGB',(300,100),'white').save(buffer,format='PNG')
        seen=[]
        def extract(image,lang,config=None):
            seen.append((ocr.pytesseract.pytesseract.tesseract_cmd,config))
            return '全新铰链'
        with patch.dict(os.environ, {'PATH':'/usr/bin:/bin','TESSERACT_CMD':''}), patch.object(ocr.pytesseract,'image_to_string',side_effect=extract):
            self.assertEqual(ocr.call_tesseract_ocr(buffer.getvalue()),'全新铰链')
        self.assertTrue(Path(seen[0][0]).is_absolute())
        self.assertEqual(seen[0][1], '--psm 11')

    def test_caption_html_escapes_translated_text(self):
        value=ocr.ImageTranslation('原文','화면 <120Hz> & 밝기','<script>bad</script>','画面')
        rendered=backfill_captions.build_caption_html([value])
        self.assertNotIn('<script>',rendered)
        self.assertIn('&lt;120Hz&gt; &amp;',rendered)
        self.assertNotIn('data-lang="zh"',rendered)

    def test_incomplete_batch_does_not_crash_or_drop_other_languages(self):
        result=ocr._translate_sentences(['第一行','第二行'],lambda s:'한국어',lambda s:'English',lambda s:'日本語',lambda _:dict(ko=['한글','한글'],en=['English'],ja=[]))
        self.assertEqual(len(result),2)
        self.assertTrue(all(t.translated_english and t.translated_japanese for t in result))

    def test_resume_skips_images_with_all_three_captions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'images').mkdir();(root/'images/x.jpg').write_bytes(b'fixture')
            page=root/'index.html'
            captions=backfill_captions.build_caption_html([ocr.ImageTranslation('铰链','힌지','Hinge','ヒンジ')])
            page.write_text('<div class="image-item"><img src="images/x.jpg">'+captions+'</div>')
            with patch.object(ocr,'call_local_ocr',return_value=None) as extract:
                self.assertFalse(backfill_captions.process_article(page))
                extract.assert_not_called()

    def test_backfill_keeps_completed_image_when_next_image_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'images').mkdir()
            for name in ('a.jpg','b.jpg'):(root/'images'/name).write_bytes(b'fixture')
            page=root/'index.html';page.write_text(''.join('<div class="image-item"><img src="images/'+name+'"></div>' for name in ('a.jpg','b.jpg')))
            values=[ocr.ImageTranslation('铰链','힌지','Hinge','ヒンジ')]
            with patch.object(ocr,'call_local_ocr',side_effect=['全新铰链',RuntimeError('interrupted')]),patch.object(ocr,'_translate_sentences',return_value=values):
                with self.assertRaises(RuntimeError):backfill_captions.process_article(page)
            self.assertIn('data-lang="ko"',page.read_text())

    def test_english_only_ocr_does_not_create_translation_candidates(self):
        self.assertEqual(ocr._filter_caption_lines('Sony IMX\n120Hz OLED\n@camera'),[])

    def test_sparse_slide_noise_is_not_translated(self):
        candidates=ocr._filter_caption_lines('Zz的y&口人\n+站|一 1 4\n禾二总 a rN "lf sj\n小 米 龙 骨 转 轴\n外屏离子注入强化')
        self.assertEqual(candidates,['小米龙骨转轴','外屏离子注入强化'])

    def test_auto_ocr_uses_native_result_and_falls_back_only_on_failure(self):
        self.assertTrue(hasattr(ocr,'call_local_ocr'))
        with patch.object(ocr,'call_apple_vision_ocr',return_value='小米龙骨转轴'),patch.object(ocr,'call_tesseract_ocr') as fallback:
            self.assertEqual(ocr.call_local_ocr(b'image'),'小米龙骨转轴')
            fallback.assert_not_called()
        with patch.object(ocr,'call_apple_vision_ocr',return_value=None),patch.object(ocr,'call_tesseract_ocr',return_value='三级连杆') as fallback:
            self.assertEqual(ocr.call_local_ocr(b'image'),'三级连杆')
            fallback.assert_called_once()

    def test_mixed_technology_labels_are_retained(self):
        self.assertEqual(ocr._filter_caption_lines('支持 Wi-Fi 7\n搭载 Snapdragon 处理器'),['支持 Wi-Fi 7','搭载 Snapdragon 处理器'])

    def test_resume_repairs_any_incomplete_caption_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'images').mkdir();(root/'images/x.jpg').write_bytes(b'fixture')
            page=root/'index.html'
            caps=backfill_captions.build_caption_html([ocr.ImageTranslation('一','하나','One','一'),ocr.ImageTranslation('二','둘','','二')])
            page.write_text('<div class="image-item"><img src="images/x.jpg">'+caps+'</div>')
            with patch.object(ocr,'call_local_ocr',return_value=None) as extract:
                backfill_captions.process_article(page)
                extract.assert_called_once()
