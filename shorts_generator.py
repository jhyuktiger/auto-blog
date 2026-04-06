"""
Shorts Generator v4.2
수정사항:
1. TextClip(ImageMagick) → PIL 방식으로 자막 교체
2. JSON 파싱 강화
3. 레이아웃 완전 재설계 - 이미지 풀스크린 + overlay 자막
4. 점수 파싱 버그 수정
"""

import os
import re
import json
import datetime
import anthropic
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
try:
    from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
except ImportError:
    from moviepy import ImageClip, AudioFileClip, CompositeVideoClip
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
# JSON 파싱 유틸
# ─────────────────────────────────────────────
def safe_parse_json(raw):
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON 블록 없음")
    json_str = raw[start:end]
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        json_str2 = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
        return json.loads(json_str2)


# ─────────────────────────────────────────────
# 1. 스크립트 생성
# ─────────────────────────────────────────────
def generate_shorts_script(blog_title, blog_content, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if lang == "ko":
        prompt = f"""블로그 글을 30초 유튜브 숏츠 대본으로 변환해주세요.
제목: {blog_title}
내용: {blog_content[:600]}

타겟: 40~60대 직장인/시니어, AI·재테크 정보에 관심 있는 분들
규칙: 5문장, 첫문장=강렬한 훅(숫자나 충격적 사실로 시작), 마지막="자세한 내용은 링크 참고!", 구어체

순수 JSON만 응답 (마크다운 없이):
{{"title": "숏츠제목(50자이내)", "script": "전체대본", "sentences": ["문장1","문장2","문장3","문장4","문장5"], "hashtags": ["#태그1","#태그2","#태그3","#태그4","#태그5"]}}"""
    else:
        prompt = f"""Convert to 30-second YouTube Shorts script.
Title: {blog_title}
Content: {blog_content[:600]}

Target: 40-60s professionals interested in AI and finance
Rules: 5 sentences, first=strong hook (start with number or shocking fact), last="Check the link!", conversational

Pure JSON only (no markdown):
{{"title": "Shorts title(50 chars)", "script": "Full script", "sentences": ["s1","s2","s3","s4","s5"], "hashtags": ["#tag1","#tag2","#tag3","#tag4","#tag5"]}}"""

    best_script = None
    best_score = 0
    last_feedback = ""

    for attempt in range(3):
        current_prompt = prompt
        if last_feedback:
            current_prompt += f"\n[이전 평가 피드백 - 반드시 반영하세요]\n{last_feedback}"

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1024,
            messages=[{"role": "user", "content": current_prompt}]
        )
        raw = msg.content[0].text.strip()
        try:
            script_data = safe_parse_json(raw)
            score, feedback = evaluate_script_with_feedback(script_data, lang, client)
            print(f"📊 스크립트 품질 (시도 {attempt+1}/3): {score}/10")
            if score > best_score:
                best_score = score
                best_script = script_data
            last_feedback = feedback
            if score >= 8:
                break
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패 (시도 {attempt+1}/3): {e}")

    if best_score < 6:
        print(f"❌ 최고점 {best_score}/10 — 업로드 스킵")
        return None

    print(f"✅ 최종 선택 스크립트: {best_score}/10")
    return best_script


def evaluate_script_with_feedback(script_data, lang, client):
    try:
        if lang == "ko":
            prompt = f"""유튜브 숏츠 스크립트를 평가해주세요.
제목: {script_data.get("title", "")}
스크립트: {script_data.get("script", "")}

반드시 아래 형식으로만 응답 (숫자는 0~10 사이 정수 하나만):
점수: 7
피드백: 개선점"""
        else:
            prompt = f"""Evaluate this YouTube Shorts script.
Title: {script_data.get("title", "")}
Script: {script_data.get("script", "")}

Reply ONLY in this format (score must be a single integer 0-10):
Score: 7
Feedback: improvement point"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        response = msg.content[0].text.strip()
        lines = response.split("\n")
        score = 7
        feedback = ""
        for line in lines:
            if line.startswith("점수:") or line.startswith("Score:"):
                nums = re.findall(r'\b([0-9]|10)\b', line.split(":", 1)[1])
                if nums:
                    score = int(nums[0])
            if line.startswith("피드백:") or line.startswith("Feedback:"):
                feedback = line.split(":", 1)[1].strip()
        return score, feedback
    except Exception:
        return 7, ""


def evaluate_script(script_data, lang, client):
    score, _ = evaluate_script_with_feedback(script_data, lang, client)
    return score


# ─────────────────────────────────────────────
# 2. 이미지 관련
# ─────────────────────────────────────────────
def get_pixabay_images(keywords, lang, count=5):
    """Pixabay - 따뜻하고 친근한 이미지 키워드로 매핑 (로봇 얼굴 NO)"""
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
        if not PIXABAY_API_KEY:
            return []

        query = " ".join(keywords[:2]) if lang == "en" else keywords[0]

        ko_to_en = {
            "AI": "technology laptop digital workspace",
            "인공지능": "computer technology future",
            "비트코인": "gold coins money wealth",
            "코인": "coins money gold",
            "투자": "growth chart money finance",
            "주식": "stock chart finance graph",
            "ETF": "investment portfolio coins",
            "재테크": "piggy bank savings money",
            "자동화": "laptop workflow productivity desk",
            "번아웃": "tired person office desk",
            "동기부여": "sunrise road mountain success",
            "성공": "handshake business success",
            "노후": "happy senior couple outdoor",
            "트럼프": "business newspaper office",
            "관세": "cargo ship port trade",
            "일론 머스크": "electric car road night",
            "젠슨 황": "computer chip circuit board",
            "워런 버핏": "newspaper finance books",
            "시니어": "happy senior lifestyle outdoor",
            "부업": "laptop coffee freelance home",
            "챗GPT": "laptop chat screen",
            "Claude": "laptop technology office",
            "바이브코딩": "coding laptop coffee desk",
            "애드센스": "laptop money online",
            "블로그": "writing laptop coffee desk",
            "연금": "retirement savings jar coins",
            "ISA": "savings bank piggy",
            "ETF": "graph chart investment",
            "S&P500": "stock market graph",
            "배당": "money coins dividend",
        }
        for ko, en in ko_to_en.items():
            if ko in query:
                query = en
                break

        encoded = urllib.parse.quote(query)
        # orientation=vertical 로 세로 이미지 우선
        url = (
            f"https://pixabay.com/api/?key={PIXABAY_API_KEY.strip()}"
            f"&q={encoded}&image_type=photo&orientation=vertical"
            f"&per_page=20&safesearch=true&min_width=600"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        hits = data.get("hits", [])

        # 세로 이미지 없으면 horizontal로 재시도
        if not hits:
            url2 = url.replace("orientation=vertical", "orientation=horizontal")
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                data2 = _json.loads(resp2.read())
            hits = data2.get("hits", [])

        if hits:
            import random
            selected = random.sample(hits[:15], min(count, len(hits[:15])))
            urls = [h["webformatURL"] for h in selected]
            print(f"🖼️ Pixabay 이미지 {len(urls)}개: {query}")
            return urls
    except Exception as e:
        print(f"⚠️ Pixabay 실패: {e}")
    return []


def download_image(url, path):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"⚠️ 이미지 다운로드 실패: {e}")
        return False


def create_gradient_fallback():
    """폴백용 그라디언트 배경 (딥 퍼플 → 핑크)"""
    width, height = 1080, 1920
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(60 + ratio * 160)
        g = int(20 + ratio * 60)
        b = int(120 + ratio * 80)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    img_path = f"/tmp/bg_grad_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    img.save(img_path)
    return img_path


# ─────────────────────────────────────────────
# 3. 폰트 & 텍스트 유틸
# ─────────────────────────────────────────────
def get_font(size):
    font_candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
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


def draw_text_with_outline(draw, text, x, y, font,
                            text_color=(255, 255, 255, 255),
                            outline_color=(0, 0, 0, 230),
                            outline_width=3):
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=text_color)


def wrap_text(text, font, max_width):
    words = text.split()
    if not words:
        return [text]
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test_line) * 30
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines if lines else [text]


def _fill_gradient(img, width, height):
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(40 + ratio * 120)
        g = int(10 + ratio * 30)
        b = int(80 + ratio * 100)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))


# ─────────────────────────────────────────────
# 4. ✅ 새 레이아웃 프레임 생성
#
#  ┌──────────────────────┐
#  │ 어머나! @OhmyG7       │ ← 반투명 상단바 (100px)
#  ├──────────────────────┤
#  │ [제목 반투명 박스]     │ ← 노란 텍스트
#  │                      │
#  │   이미지 풀스크린      │ ← 화면 전체 배경
#  │                      │
#  │▓▓▓ 그라데이션 overlay ▓│
#  │  자막 흰색 텍스트      │ ← 하단 overlay
#  └──────────────────────┘
# ─────────────────────────────────────────────
def create_subtitle_frame(sentence, title, content_image_path=None, frame_size=(1080, 1920)):
    width, height = frame_size
    img = Image.new('RGBA', (width, height), (20, 10, 40, 255))

    # ── Step 1: 배경 이미지 풀스크린 (9:16 center-crop) ──
    if content_image_path and os.path.exists(content_image_path):
        try:
            bg = Image.open(content_image_path).convert('RGBA')
            bg_w, bg_h = bg.size
            target_ratio = width / height  # 0.5625

            src_ratio = bg_w / bg_h
            if src_ratio > target_ratio:
                new_w = int(bg_h * target_ratio)
                left = (bg_w - new_w) // 2
                bg = bg.crop((left, 0, left + new_w, bg_h))
            else:
                new_h = int(bg_w / target_ratio)
                top = 0  # 상단 기준 crop
                bg = bg.crop((0, top, bg_w, top + new_h))

            bg = bg.resize((width, height), Image.LANCZOS)
            img.paste(bg, (0, 0))
        except Exception as e:
            print(f"⚠️ 배경 이미지 적용 실패: {e}")
            _fill_gradient(img, width, height)
    else:
        _fill_gradient(img, width, height)

    draw = ImageDraw.Draw(img)

    # ── Step 2: 상단 채널 바 ──
    bar_h = 100
    bar_bg = Image.new('RGBA', (width, bar_h), (0, 0, 0, 170))
    img.paste(bar_bg, (0, 0), bar_bg)
    # 핑크 하단 강조선
    draw.rectangle([0, bar_h - 5, width, bar_h], fill=(220, 80, 150, 255))

    ch_font = get_font(48)
    ch_name = "어머나!  @OhmyG7"
    try:
        ch_bbox = ch_font.getbbox(ch_name)
        ch_w = ch_bbox[2] - ch_bbox[0]
    except Exception:
        ch_w = 400
    ch_x = (width - ch_w) // 2
    draw_text_with_outline(draw, ch_name, ch_x, 22, ch_font,
                           text_color=(255, 255, 255, 255),
                           outline_color=(150, 30, 90, 255),
                           outline_width=2)

    # ── Step 3: 제목 박스 (상단바 아래, 반투명) ──
    title_font = get_font(50)
    title_lines = wrap_text(title[:42], title_font, width - 60)
    title_line_h = 64
    title_block_h = len(title_lines) * title_line_h + 24
    title_y = bar_h + 6

    title_bg = Image.new('RGBA', (width, title_block_h), (0, 0, 0, 150))
    img.paste(title_bg, (0, title_y), title_bg)

    for i, line in enumerate(title_lines):
        try:
            bbox = title_font.getbbox(line)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = 400
        x = (width - text_w) // 2
        y = title_y + 12 + i * title_line_h
        draw_text_with_outline(draw, line, x, y, title_font,
                               text_color=(255, 230, 50, 255),   # 노란색
                               outline_color=(0, 0, 0, 240),
                               outline_width=3)

    # ── Step 4: 하단 그라데이션 + 자막 overlay ──
    sub_font = get_font(58)
    sub_lines = wrap_text(sentence, sub_font, width - 80)
    sub_line_h = 74
    sub_block_h = len(sub_lines) * sub_line_h + 60

    # 하단 그라데이션 (자막 위로 자연스럽게)
    grad_h = sub_block_h + 100
    grad_start = height - grad_h
    grad_overlay = Image.new('RGBA', (width, grad_h), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad_overlay)
    for row in range(grad_h):
        alpha = int(220 * (row / grad_h) ** 0.6)
        grad_draw.line([(0, row), (width, row)], fill=(0, 0, 0, alpha))
    img.paste(grad_overlay, (0, grad_start), grad_overlay)

    # 자막 텍스트 (하단에서 50px 여백)
    sub_y = height - sub_block_h - 50
    for i, line in enumerate(sub_lines):
        try:
            bbox = sub_font.getbbox(line)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = 400
        x = (width - text_w) // 2
        y = sub_y + 30 + i * sub_line_h
        draw_text_with_outline(draw, line, x, y, sub_font,
                               text_color=(255, 255, 255, 255),
                               outline_color=(0, 0, 0, 255),
                               outline_width=4)

    # ── Step 5: 핑크 하단 강조선 ──
    draw.rectangle([0, height - 8, width, height], fill=(220, 80, 150, 255))

    img_path = f"/tmp/frame_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{id(sentence)}.png"
    img.save(img_path, 'PNG')
    return img_path


# ─────────────────────────────────────────────
# 5. TTS
# ─────────────────────────────────────────────
def generate_tts(script, lang):
    audio_path = f"/tmp/audio_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    gTTS(text=script, lang="ko" if lang == "ko" else "en", slow=False).save(audio_path)
    print("🎤 TTS 완료")
    return audio_path


# ─────────────────────────────────────────────
# 6. 영상 생성 (배경 합성 제거 - 프레임 자체가 풀스크린)
# ─────────────────────────────────────────────
def create_video(audio_path, sentences, title, lang, keywords=None):
    video_path = f"/tmp/shorts_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    time_per = duration / len(sentences)

    # 문장 수만큼 이미지 가져오기
    content_images = []
    if keywords:
        img_urls = get_pixabay_images(keywords, lang, count=len(sentences))
        for j, url in enumerate(img_urls):
            img_path = f"/tmp/content_img_{j}_{datetime.datetime.now().strftime('%H%M%S')}.jpg"
            if download_image(url, img_path):
                content_images.append(img_path)

    if not content_images:
        fallback = create_gradient_fallback()
        content_images = [fallback]

    clips = []
    for i, sentence in enumerate(sentences):
        content_img = content_images[i % len(content_images)]
        # 프레임 자체가 풀스크린 (별도 배경 합성 불필요)
        frame_path = create_subtitle_frame(sentence, title, content_image_path=content_img)
        clip = (ImageClip(frame_path)
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
# 7. YouTube 업로드
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
# 8. 메인 함수
# ─────────────────────────────────────────────
def generate_shorts(blog_title, blog_content, lang, blog_url=""):
    print(f"\n🎬 숏츠 생성 시작: {blog_title}")

    script_data = generate_shorts_script(blog_title, blog_content, lang)
    if script_data is None:
        print("⏭️ 숏츠 스킵 (퀄리티 미달)")
        return None
    print(f"📝 스크립트 완료: {script_data['title']}")

    audio_path = generate_tts(script_data["script"], lang)
    keywords = blog_title.split()[:3]
    video_path = create_video(audio_path, script_data["sentences"],
                              script_data["title"], lang, keywords=keywords)

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
