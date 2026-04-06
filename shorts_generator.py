"""
Shorts Generator v4.1
수정사항:
1. TextClip(ImageMagick) → PIL 방식으로 자막 교체
2. JSON 파싱 강화 (Claude 응답 특수문자/줄바꿈 처리)
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
    """Claude 응답에서 JSON 안전하게 파싱"""
    # 1) { ... } 범위 추출
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON 블록 없음")
    json_str = raw[start:end]

    # 2) 제어문자 제거 (줄바꿈·탭은 유지)
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)

    # 3) 1차 시도
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 4) 역슬래시 정규화 후 재시도
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
        print(f"❌ 최고점 {best_score}/10 — 업로드 스킵 (퀄리티 미달)")
        return None

    print(f"✅ 최종 선택 스크립트: {best_score}/10")
    return best_script


def evaluate_script_with_feedback(script_data, lang, client):
    """하네스 v2: 점수 + 구체적 피드백 반환"""
    try:
        if lang == "ko":
            prompt = f"""유튜브 숏츠 스크립트를 평가해주세요.

제목: {script_data.get("title", "")}
스크립트: {script_data.get("script", "")}

평가 기준:
1. 첫 문장이 강렬한 훅인가? (숫자/충격적 사실로 시작)
2. 40~60대 타겟에 맞는 주제와 말투인가?
3. 30초 안에 핵심을 전달하는가?
4. 자연스러운 구어체인가?
5. "어머나! 이런 게 있었어?" 반응 유발하는가?

다음 형식으로만 응답:
점수: [0~10 숫자]
피드백: [구체적으로 무엇을 개선해야 하는지 1~2줄]"""
        else:
            prompt = f"""Evaluate this YouTube Shorts script.

Title: {script_data.get("title", "")}
Script: {script_data.get("script", "")}

Criteria:
1. Strong hook in first sentence? (number or shocking fact)
2. Appropriate for 40-60s professionals?
3. Delivers key message within 30 seconds?
4. Natural conversational tone?
5. Triggers "OhmyG! I didn't know that!" reaction?

Reply in this format only:
Score: [0-10]
Feedback: [1-2 lines on what specifically needs improvement]"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        response = msg.content[0].text.strip()
        lines = response.split("\n")

        score = 7
        feedback = ""
        for line in lines:
            if line.startswith("점수:") or line.startswith("Score:"):
                try:
                    score = int("".join(filter(str.isdigit, line.split(":")[1])))
                except Exception:
                    pass
            if line.startswith("피드백:") or line.startswith("Feedback:"):
                feedback = line.split(":", 1)[1].strip()
        return score, feedback
    except Exception:
        return 7, ""


def evaluate_script(script_data, lang, client):
    """하위 호환용"""
    score, _ = evaluate_script_with_feedback(script_data, lang, client)
    return score


# ─────────────────────────────────────────────
# 2. 배경 이미지 생성
# ─────────────────────────────────────────────
def generate_background_image(title, lang):
    """고정 배경 이미지 사용 (bg_default.png)"""
    try:
        repo_bg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bg_default.png")
        if os.path.exists(repo_bg):
            img = Image.open(repo_bg).resize((1080, 1920)).convert("RGB")
            img_path = f"/tmp/bg_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            img.save(img_path)
            print("🖼️ 고정 배경 이미지 사용")
            return img_path
    except Exception as e:
        print(f"⚠️ 배경 이미지 실패: {e}")
    return create_gradient_background(title)


def get_pixabay_images(keywords, lang, count=3):
    """Pixabay에서 관련 이미지 여러장 가져오기"""
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
        if not PIXABAY_API_KEY:
            return []
        query = " ".join(keywords[:2]) if lang == "en" else keywords[0]
        ko_to_en = {
            "AI": "artificial intelligence technology",
            "인공지능": "artificial intelligence",
            "비트코인": "bitcoin cryptocurrency",
            "코인": "cryptocurrency digital",
            "투자": "investment money growth",
            "주식": "stock market trading",
            "ETF": "investment portfolio finance",
            "재테크": "money saving finance",
            "자동화": "automation technology",
            "번아웃": "burnout stress office",
            "동기부여": "motivation success",
            "성공": "success achievement",
            "노후": "retirement couple",
            "트럼프": "business politics",
            "관세": "trade shipping port",
            "일론 머스크": "electric car technology",
            "젠슨 황": "GPU chip technology",
            "워런 버핏": "investment finance",
            "시니어": "senior lifestyle",
            "부업": "freelance laptop",
        }
        for ko, en in ko_to_en.items():
            if ko in query:
                query = en
                break
        encoded = urllib.parse.quote(query)
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY.strip()}&q={encoded}&image_type=photo&orientation=horizontal&per_page=15&safesearch=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        hits = data.get("hits", [])
        if hits:
            import random
            selected = random.sample(hits[:10], min(count, len(hits[:10])))
            urls = [h["webformatURL"] for h in selected]
            print(f"🖼️ Pixabay 이미지 {len(urls)}개: {query}")
            return urls
    except Exception as e:
        print(f"⚠️ Pixabay 실패: {e}")
    return []


def create_gradient_background(title=""):
    """멋진 그라디언트 배경 생성"""
    width, height = 1080, 1920
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        r = int(240 + ratio * 10)
        g = int(210 + ratio * 5)
        b = int(240 + ratio * 10)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    for cx, cy, cr, ca in [(200, 400, 300, 40), (900, 800, 200, 35),
                            (100, 1500, 250, 40), (800, 1200, 180, 30)]:
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=(220, 180, 240, ca))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(img)
    draw.line([(80, 280), (1000, 280)], fill=(255, 150, 180), width=3)
    draw.line([(80, 1600), (1000, 1600)], fill=(255, 150, 180), width=3)

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
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
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
    return lines if lines else [text]


def create_subtitle_frame(sentence, title, content_image_path=None, frame_size=(1080, 1920), bg_color=None):
    """
    아이반 스타일 프레임:
    - 상단 바: 어머나! 채널명
    - 제목 박스 (흰 배경)
    - 중앙 이미지 (있으면)
    - 하단 자막
    """
    width, height = frame_size
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 상단 채널 바 ──
    bar_h = 110
    draw.rectangle([0, 0, width, bar_h], fill=(220, 80, 150, 255))
    ch_font = get_font(52)
    ch_name = "어머나!  @OhmyG7"
    ch_bbox = ch_font.getbbox(ch_name)
    ch_w = ch_bbox[2] - ch_bbox[0]
    ch_x = (width - ch_w) // 2
    draw_text_with_outline(draw, ch_name, ch_x, 28, ch_font,
                           text_color=(255, 255, 255, 255),
                           outline_color=(180, 40, 100, 200),
                           outline_width=2)

    # ── 제목 박스 (흰 배경) ──
    title_font = get_font(58)
    title_max_w = width - 80
    title_lines = wrap_text(title[:45], title_font, title_max_w)
    title_line_h = 72
    title_block_h = len(title_lines) * title_line_h + 40
    title_y_start = bar_h + 30

    draw.rectangle([20, title_y_start, width - 20, title_y_start + title_block_h],
                   fill=(255, 255, 255, 240))
    draw.rectangle([20, title_y_start, width - 20, title_y_start + title_block_h],
                   fill=None, outline=(220, 80, 150, 180))

    for i, line in enumerate(title_lines):
        bbox = title_font.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = title_y_start + 20 + i * title_line_h
        draw.text((x, y), line, font=title_font, fill=(30, 30, 30, 255))

    # ── 중앙 이미지 ──
    img_y_start = title_y_start + title_block_h + 30
    img_area_h = 680

    if content_image_path and os.path.exists(content_image_path):
        try:
            content_img = Image.open(content_image_path).convert('RGBA')
            content_img = content_img.resize((width - 40, img_area_h))
            img.paste(content_img, (20, img_y_start), content_img)
        except Exception:
            _draw_placeholder(draw, img_y_start, img_area_h, width)
    else:
        _draw_placeholder(draw, img_y_start, img_area_h, width)

    # ── 하단 자막 ──
    sub_font = get_font(52)
    sub_max_w = width - 80
    sub_lines = wrap_text(sentence, sub_font, sub_max_w)
    sub_line_h = 64
    sub_block_h = len(sub_lines) * sub_line_h + 30
    sub_y_base = img_y_start + img_area_h + 20

    draw.rectangle([20, sub_y_base, width - 20, sub_y_base + sub_block_h],
                   fill=(255, 255, 255, 230))

    for i, line in enumerate(sub_lines):
        bbox = sub_font.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = sub_y_base + 15 + i * sub_line_h
        draw_text_with_outline(draw, line, x, y, sub_font,
                               text_color=(30, 30, 30, 255),
                               outline_color=(255, 255, 255, 200),
                               outline_width=1)

    img_path = f"/tmp/frame_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{id(sentence)}.png"
    img.save(img_path, 'PNG')
    return img_path


def _draw_placeholder(draw, y_start, height, width):
    """이미지 없을 때 플레이스홀더"""
    draw.rectangle([20, y_start, width - 20, y_start + height],
                   fill=(245, 230, 245, 200))


def generate_tts(script, lang):
    audio_path = f"/tmp/audio_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    gTTS(text=script, lang="ko" if lang == "ko" else "en", slow=False).save(audio_path)
    print("🎤 TTS 완료")
    return audio_path


# ─────────────────────────────────────────────
# 4. 영상 생성 (✅ PIL 자막 방식)
# ─────────────────────────────────────────────
def download_image(url, path):
    """이미지 URL 다운로드"""
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


def create_video(bg_image_path, audio_path, sentences, title, lang, keywords=None):
    video_path = f"/tmp/shorts_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    time_per = duration / len(sentences)

    content_images = []
    if keywords:
        img_urls = get_pixabay_images(keywords, lang, count=3)
        for j, url in enumerate(img_urls):
            img_path = f"/tmp/content_img_{j}_{datetime.datetime.now().strftime('%H%M%S')}.jpg"
            if download_image(url, img_path):
                content_images.append(img_path)

    clips = []
    for i, sentence in enumerate(sentences):
        content_img = content_images[i % len(content_images)] if content_images else None
        frame_path = create_subtitle_frame(sentence, title, content_image_path=content_img)
        frame_img = Image.open(frame_path).convert('RGBA')

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
# 5. YouTube 업로드
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
# 6. 메인 함수
# ─────────────────────────────────────────────
def generate_shorts(blog_title, blog_content, lang, blog_url=""):
    print(f"\n🎬 숏츠 생성 시작: {blog_title}")

    script_data = generate_shorts_script(blog_title, blog_content, lang)
    if script_data is None:
        print("⏭️ 숏츠 스킵 (퀄리티 미달)")
        return None
    print(f"📝 스크립트 완료: {script_data['title']}")

    bg_path = generate_background_image(blog_title, lang)
    audio_path = generate_tts(script_data["script"], lang)
    keywords = blog_title.split()[:3]
    video_path = create_video(bg_path, audio_path, script_data["sentences"],
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
