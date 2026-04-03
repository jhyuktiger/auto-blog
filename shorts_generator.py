"""
Shorts Generator v4
수정사항:
1. TextClip(ImageMagick) → PIL 방식으로 자막 교체
2. Gemini 모델명 수정: gemini-2.0-flash-exp-image-generation → gemini-2.5-flash-image
"""

import os
import json
import datetime
import base64
import textwrap
import anthropic
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]
YOUTUBE_CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]

# ─────────────────────────────────────────────
# 1. 스크립트 생성
# ─────────────────────────────────────────────
def generate_shorts_script(blog_title, blog_content, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if lang == "ko":
        prompt = f"""블로그 글을 30초 유튜브 숏츠 대본으로 변환해주세요.
제목: {blog_title}
내용: {blog_content[:600]}

규칙: 5문장, 첫문장=강렬한 훅, 마지막="자세한 내용은 링크 참고!", 구어체

순수 JSON만 (다른 텍스트 없이):
{{"title": "숏츠제목(50자이내)", "script": "전체대본", "sentences": ["문장1","문장2","문장3","문장4","문장5"], "hashtags": ["#태그1","#태그2","#태그3","#태그4","#태그5"]}}"""
    else:
        prompt = f"""Convert to 30-second YouTube Shorts script.
Title: {blog_title}
Content: {blog_content[:600]}

Rules: 5 sentences, first=strong hook, last="Check the link!", conversational

Pure JSON only (no other text):
{{"title": "Shorts title(50 chars)", "script": "Full script", "sentences": ["s1","s2","s3","s4","s5"], "hashtags": ["#tag1","#tag2","#tag3","#tag4","#tag5"]}}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    return json.loads(raw[raw.find("{"):raw.rfind("}")+1])


# ─────────────────────────────────────────────
# 2. 배경 이미지 생성 (Gemini → fallback 그라디언트)
# ─────────────────────────────────────────────
def generate_background_image(title, lang):
    """✅ 수정: gemini-2.5-flash-image 모델 사용"""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Professional YouTube Shorts background image for topic: '{title}'. "
            "Dark gradient, modern tech/finance aesthetic, no text, "
            "abstract geometric shapes, blue purple tones, vertical 9:16 ratio"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",  # ✅ 수정된 모델명
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            )
        )
        img_path = f"/tmp/bg_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                img_data = base64.b64decode(part.inline_data.data)
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                img = Image.open(img_path).resize((1080, 1920))
                img.save(img_path)
                print("🖼️ Gemini 이미지 생성 완료")
                return img_path
    except Exception as e:
        print(f"⚠️ Gemini 실패 → 그라디언트 배경 사용: {e}")
    return create_gradient_background(title)


def create_gradient_background(title=""):
    """멋진 그라디언트 배경 생성"""
    width, height = 1080, 1920
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        r = int(5 + ratio * 15)
        g = int(5 + ratio * 10)
        b = int(40 + ratio * 60)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    for cx, cy, cr, ca in [(200, 400, 300, 30), (900, 800, 200, 20),
                            (100, 1500, 250, 25), (800, 1200, 180, 15)]:
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=(100, 150, 255, ca))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(img)
    draw.line([(80, 280), (1000, 280)], fill=(100, 150, 255), width=2)
    draw.line([(80, 1600), (1000, 1600)], fill=(100, 150, 255), width=2)

    img_path = f"/tmp/bg_grad_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    img.save(img_path)
    print("🖼️ 그라디언트 배경 생성 완료")
    return img_path


# ─────────────────────────────────────────────
# 3. PIL 자막 함수 (✅ TextClip 완전 대체)
# ─────────────────────────────────────────────
def get_font(size):
    """폰트 로드 (시스템 폰트 fallback)"""
    font_candidates = [
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        # Linux (GitHub Actions)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_text_with_outline(draw, text, x, y, font, text_color, outline_color, outline_width=3):
    """외곽선 있는 텍스트 그리기"""
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=text_color)


def wrap_text(text, font, max_width):
    """텍스트를 max_width 픽셀 너비에 맞게 줄바꿈"""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines


def create_subtitle_frame(sentence, title, frame_size=(1080, 1920), bg_color=None):
    """
    ✅ PIL로 자막 프레임 이미지 생성
    - 상단: 제목
    - 하단: 자막 문장
    - 반투명 배경 박스
    """
    width, height = frame_size
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 제목 영역 (상단) ──
    title_font = get_font(58)
    title_max_w = width - 160
    title_lines = wrap_text(title[:50], title_font, title_max_w)

    title_line_h = 70
    title_block_h = len(title_lines) * title_line_h + 20
    title_y_start = 300

    # 제목 배경 박스
    draw.rectangle(
        [60, title_y_start - 15, width - 60, title_y_start + title_block_h + 15],
        fill=(0, 0, 0, 140)
    )

    for i, line in enumerate(title_lines):
        bbox = title_font.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = title_y_start + i * title_line_h
        draw_text_with_outline(draw, line, x, y, title_font,
                                text_color=(255, 255, 255, 255),
                                outline_color=(0, 0, 0, 255),
                                outline_width=3)

    # 구분선
    draw.line([(80, title_y_start + title_block_h + 25),
               (width - 80, title_y_start + title_block_h + 25)],
              fill=(100, 150, 255, 200), width=3)

    # ── 자막 영역 (하단) ──
    sub_font = get_font(52)
    sub_max_w = width - 160
    sub_lines = wrap_text(sentence, sub_font, sub_max_w)

    sub_line_h = 65
    sub_block_h = len(sub_lines) * sub_line_h + 30
    sub_y_base = height - 280 - sub_block_h

    # 자막 배경 박스 (반투명)
    draw.rectangle(
        [60, sub_y_base - 20, width - 60, sub_y_base + sub_block_h + 20],
        fill=(0, 0, 0, 170)
    )

    for i, line in enumerate(sub_lines):
        bbox = sub_font.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = sub_y_base + 15 + i * sub_line_h
        draw_text_with_outline(draw, line, x, y, sub_font,
                                text_color=(255, 255, 100, 255),  # 노란색 자막
                                outline_color=(0, 0, 0, 255),
                                outline_width=3)

    # ── 채널명 (최하단) ──
    ch_font = get_font(36)
    ch_name = "AI Insight Labs"
    ch_bbox = ch_font.getbbox(ch_name)
    ch_w = ch_bbox[2] - ch_bbox[0]
    ch_x = (width - ch_w) // 2
    draw_text_with_outline(draw, ch_name, ch_x, height - 180, ch_font,
                            text_color=(150, 180, 255, 220),
                            outline_color=(0, 0, 0, 180),
                            outline_width=2)

    img_path = f"/tmp/frame_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{id(sentence)}.png"
    img.save(img_path, 'PNG')
    return img_path


# ─────────────────────────────────────────────
# 4. TTS
# ─────────────────────────────────────────────
def generate_tts(script, lang):
    audio_path = f"/tmp/audio_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    gTTS(text=script, lang="ko" if lang == "ko" else "en", slow=False).save(audio_path)
    print("🎤 TTS 완료")
    return audio_path


# ─────────────────────────────────────────────
# 5. 영상 생성 (✅ PIL 자막 방식)
# ─────────────────────────────────────────────
def create_video(bg_image_path, audio_path, sentences, title, lang):
    video_path = f"/tmp/shorts_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    time_per = duration / len(sentences)

    clips = []

    for i, sentence in enumerate(sentences):
        # PIL로 자막 프레임 생성
        frame_path = create_subtitle_frame(sentence, title)
        frame_img = Image.open(frame_path).convert('RGBA')

        # 배경 + 자막 합성
        bg_img = Image.open(bg_image_path).resize((1080, 1920)).convert('RGBA')
        combined = Image.alpha_composite(bg_img, frame_img).convert('RGB')
        combined_path = f"/tmp/combined_{i}_{datetime.datetime.now().strftime('%H%M%S%f')}.png"
        combined.save(combined_path)

        clip = (ImageClip(combined_path)
                .set_start(i * time_per)
                .set_duration(time_per))
        clips.append(clip)

    final = CompositeVideoClip(clips, size=(1080, 1920)).set_audio(audio)
    final.write_videofile(
        video_path, fps=30, codec='libx264',
        audio_codec='aac', verbose=False, logger=None
    )
    print(f"🎬 영상 완료: {video_path}")
    return video_path


# ─────────────────────────────────────────────
# 6. YouTube 업로드
# ─────────────────────────────────────────────
def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(video_path, title, description, hashtags, lang):
    service = get_youtube_service()
    tags = [t.replace("#", "") for t in hashtags]
    tags += ["shorts", "AI", "자동화"] if lang == "ko" else ["shorts", "AI", "automation"]

    body = {
        "snippet": {
            "title": title[:100],
            "description": description + "\n\n" + " ".join(hashtags),
            "tags": tags,
            "categoryId": "28",
            "defaultLanguage": lang,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"📤 업로드: {int(status.progress()*100)}%")

    url = f"https://youtube.com/shorts/{response['id']}"
    print(f"✅ YouTube 완료: {url}")
    return url


# ─────────────────────────────────────────────
# 7. 메인 함수
# ─────────────────────────────────────────────
def generate_shorts(blog_title, blog_content, lang, blog_url=""):
    print(f"\n🎬 숏츠 생성 시작: {blog_title}")

    script_data = generate_shorts_script(blog_title, blog_content, lang)
    print(f"📝 스크립트 완료: {script_data['title']}")

    bg_path = generate_background_image(blog_title, lang)
    audio_path = generate_tts(script_data["script"], lang)
    video_path = create_video(bg_path, audio_path, script_data["sentences"], script_data["title"], lang)

    desc = (
        f"{script_data['script']}\n\n"
        f"🔗 {'자세한 내용' if lang == 'ko' else 'Read more'}: {blog_url}"
    )
    return upload_to_youtube(
        video_path, script_data["title"], desc,
        script_data["hashtags"], lang
    )


# ─────────────────────────────────────────────
# 로컬 테스트
# ─────────────────────────────────────────────
if __name__ == "__main__":
    test_title = "AI로 월 100만원 버는 현실적인 방법 5가지"
    test_content = (
        "AI 도구를 활용해 실제로 수익을 만드는 방법을 소개합니다. "
        "블로그 자동화, 콘텐츠 제작, 프리랜서 업무 자동화 등 검증된 방법들입니다."
    )
    url = generate_shorts(
        test_title, test_content, "ko",
        "https://aiinsightlabs.blogspot.com"
    )
    print(f"\n🎉 완료: {url}")
