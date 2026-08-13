"""
emailer.py — 오늘 발행된 기사 목록을 정리해 지메일(SMTP)로 다이제스트 메일을 보냅니다.

트리거 시점: main.py의 Phase A(ko 번역+저장+push) 완료 직후, Phase B(en/ja/zh
백필) 시작 전. main.py의 run_pipeline()에서 호출한다.

필요한 환경변수 (crawler/.env.local, env_local.load_env_local()이 주입):
  GMAIL_ADDRESS       - 발신 지메일 주소
  GMAIL_APP_PASSWORD  - 구글 계정 앱 비밀번호 (일반 로그인 비밀번호 아님)
  DIGEST_RECIPIENT    - 수신자 이메일 (기본값: GMAIL_ADDRESS 자기 자신)

값이 없으면(.env.local 미설정) 발송을 건너뛰고 경고 로그만 남긴다 — 이메일
발송 실패/미설정이 크롤러 파이프라인 자체를 실패시키면 안 된다.
"""
import os
import io
import logging
import smtplib
from typing import Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

THUMB_SIZE = (176, 128)  # @2x 렌더링 대비 표시 크기(88x64)의 2배로 저장
THUMB_JPEG_QUALITY = 78

# html_generator.py의 카테고리 표기와 동일하게 맞춤 (색상만 이메일용으로 별도 지정)
CATEGORY_LABEL_KO = {
    "camera": "카메라",
    "phone": "스마트폰",
    "ai": "AI",
    "image_sensor": "이미지센서",
}
CATEGORY_COLOR = {
    "camera": "#a4693b",
    "phone": "#3b5c8a",
    "ai": "#3b6b5c",
    "image_sensor": "#6b4b8a",
}
DEFAULT_CATEGORY_COLOR = "#6b6559"


def _resize_thumbnail(image_path: str) -> Optional[bytes]:
    """이미지를 작은 JPEG 썸네일로 축소해 바이트로 반환. 실패 시 None."""
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow 미설치 — 썸네일 없이 발송")
        return None

    if not image_path or not os.path.exists(image_path):
        return None

    try:
        im = Image.open(image_path).convert("RGB")
        w, h = im.size
        target_w, target_h = THUMB_SIZE
        scale = max(target_w / w, target_h / h)
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))))
        left = (im.width - target_w) // 2
        top = (im.height - target_h) // 2
        im = im.crop((left, top, left + target_w, top + target_h))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=THUMB_JPEG_QUALITY)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"썸네일 생성 실패 ({image_path}): {e}")
        return None


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html_body(items: list[dict], date_str: str) -> tuple[str, list[tuple[str, bytes]]]:
    """다이제스트 HTML 본문과 (cid, jpeg_bytes) 임베드 이미지 목록을 반환.

    items: [{"title": str, "url": str, "category_label": str, "image_bytes": bytes|None}, ...]
    """
    cid_images: list[tuple[str, bytes]] = []
    rows_html = []

    for i, item in enumerate(items):
        cid = f"thumb{i}"
        if item.get("image_bytes"):
            cid_images.append((cid, item["image_bytes"]))
            img_tag = (
                f'<img class="thumb" src="cid:{cid}" width="88" height="64" '
                f'style="display:block; width:88px; height:64px; object-fit:cover; '
                f'border:1px solid #e4e0d6;">'
            )
        else:
            img_tag = (
                '<div class="thumb" style="width:88px; height:64px; '
                'background-color:#efece4; border:1px solid #e4e0d6;"></div>'
            )

        color = CATEGORY_COLOR.get(item.get("category_key", ""), DEFAULT_CATEGORY_COLOR)
        pad_top = "26px" if i == 0 else "20px"

        rows_html.append(f"""
  <tr>
    <td class="pad-outer" style="padding:{pad_top} 48px 0 48px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="thumb-cell" width="88" valign="top" style="padding-right:18px;">
            {img_tag}
          </td>
          <td valign="top">
            <div style="font-family:'Helvetica Neue',Arial,sans-serif; font-size:10px; letter-spacing:1.5px; color:{color}; text-transform:uppercase; margin-bottom:6px;">
              {_esc(item.get("category_label", ""))}
            </div>
            <a href="{_esc(item['url'])}" class="row-title" style="font-family:Georgia,'Times New Roman',serif; font-size:16.5px; line-height:1.4; color:#1c1a17; text-decoration:none;">
              {_esc(item['title'])}
            </a>
          </td>
        </tr>
      </table>
      <div style="height:1px; background-color:#e4e0d6; margin-top:20px;"></div>
    </td>
  </tr>""")

    count = len(items)
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI시테이 데일리</title>
<style>
  @media only screen and (max-width: 600px) {{
    .container {{ width: 100% !important; }}
    .pad-outer {{ padding-left: 20px !important; padding-right: 20px !important; }}
    .masthead-title {{ font-size: 25px !important; }}
    .row-title {{ font-size: 15px !important; line-height: 1.38 !important; }}
    .thumb {{ width: 68px !important; height: 50px !important; }}
    .thumb-cell {{ width: 68px !important; padding-right: 14px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; background-color:#e9e6df;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#e9e6df;">
<tr><td align="center" style="padding:40px 12px;">
<table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" style="width:600px; max-width:600px; background-color:#fdfcfa;">

  <tr>
    <td class="pad-outer" style="padding:44px 48px 0 48px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="font-family:'Helvetica Neue',Arial,sans-serif; font-size:11px; letter-spacing:2.5px; color:#8a8478; text-transform:uppercase;">
            {_esc(date_str)}
          </td>
          <td align="right" style="font-family:'Helvetica Neue',Arial,sans-serif; font-size:11px; letter-spacing:1px; color:#8a8478;">
            {count}건 발행
          </td>
        </tr>
      </table>
      <div class="masthead-title" style="font-family:Georgia,'Times New Roman',serif; font-size:30px; line-height:1.15; color:#1c1a17; margin-top:14px; letter-spacing:-0.3px;">
        AI시테이 <span style="color:#8a8478; font-style:italic; font-size:26px;">데일리</span>
      </div>
      <div style="height:1px; background-color:#1c1a17; margin-top:20px;"></div>
    </td>
  </tr>

  <tr>
    <td class="pad-outer" style="padding:22px 48px 6px 48px; font-family:Georgia,'Times New Roman',serif; font-size:14px; line-height:1.7; color:#4a463e; font-style:italic;">
      오늘 새로 올라온 IT 뉴스를 정리했습니다. 제목을 누르면 원문 페이지로 이동합니다.
    </td>
  </tr>
{"".join(rows_html)}

  <tr>
    <td class="pad-outer" style="padding:28px 48px 40px 48px;">
      <div style="height:1px; background-color:#1c1a17; margin-bottom:20px;"></div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="font-family:Georgia,serif; font-size:12.5px; color:#8a8478; font-style:italic;">
            AI시테이 — 매일 아침 자동 발행
          </td>
          <td align="right" style="font-family:'Helvetica Neue',Arial,sans-serif; font-size:11px; color:#8a8478;">
            <a href="https://aisitei.github.io/" style="color:#8a8478; text-decoration:underline;">전체 보기</a>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html, cid_images


def send_digest_email(items: list[dict], date_str: str) -> bool:
    """다이제스트 메일을 발송. 성공 시 True, .env.local 미설정/실패 시 False (예외를 던지지 않음)."""
    if not items:
        logger.info("오늘 발행된 기사 없음 — 다이제스트 메일 발송 건너뜀")
        return False

    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("DIGEST_RECIPIENT") or gmail_address

    if not gmail_address or not gmail_app_password:
        logger.warning(
            "GMAIL_ADDRESS/GMAIL_APP_PASSWORD 미설정(.env.local) — "
            "다이제스트 메일 발송 건너뜀"
        )
        return False

    for item in items:
        item["image_bytes"] = _resize_thumbnail(item.get("image_abs_path"))

    html_body, cid_images = build_html_body(items, date_str)

    msg = MIMEMultipart("related")
    msg["Subject"] = f"AI시테이 IT뉴스 다이제스트 — {date_str} ({len(items)}건)"
    msg["From"] = formataddr(("AI시테이", gmail_address))
    msg["To"] = recipient

    alt = MIMEMultipart("alternative")
    plain_lines = [f"{it['title']} — {it['url']}" for it in items]
    alt.attach(MIMEText("\n".join(plain_lines), "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for cid, img_bytes in cid_images:
        img = MIMEImage(img_bytes, _subtype="jpeg")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.jpg")
        msg.attach(img)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, [recipient], msg.as_string())
        logger.info(f"다이제스트 메일 발송 완료 → {recipient} ({len(items)}건)")
        return True
    except Exception as e:
        logger.error(f"다이제스트 메일 발송 실패: {e}")
        return False
