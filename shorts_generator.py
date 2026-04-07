"""
Shorts Generator v5.1
레이아웃: 썰그린 스타일 + 어머나! 브랜딩
배경: bg_default.png (핑크 체크+구름) 풀스크린
구조:
  ① 상단 채널 UI 바
  ② 텍스트 한 줄 (크고 굵게, 중앙)
  ③ Pixabay 이미지 카드 (라운드 코너)
  ④ 하단 슬로건 바
"""

import os
import re
import json
import datetime
import anthropic
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
except ImportError:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]
YOUTUBE_CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]

# 어머나! 브랜딩 팔레트
BRAND = {
    "pink":        (244, 167, 195),
    "pink_dark":   (210,  80, 140),
    "purple":      (160, 100, 210),
    "purple_light":(201, 177, 232),
    "cream":       (255, 245, 228),
    "white":       (255, 255, 255),
    "text_dark":   ( 60,  30,  80),
    "gold":        (210, 165,  60),
}

W, H = 1080, 1920


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def safe_parse_json(raw):
    s = raw.find("{")
    e = raw.rfind("}") + 1
    if s == -1 or e == 0:
        raise ValueError("JSON 없음")
    js = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw[s:e])
    try:
        return json.loads(js)
    except json.JSONDecodeError:
        return json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', js))


def get_font(size, bold=True):
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def text_wh(font, text):
    try:
        b = font.getbbox(text)
        return b[2]-b[0], b[3]-b[1]
    except Exception:
        return len(text)*20, 30


def draw_text_outlined(draw, x, y, text, font, color, outline_color, outline=4):
    for dx in range(-outline, outline+1):
        for dy in range(-outline, outline+1):
            if dx or dy:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    draw.text((x, y), text, font=font, fill=color)


def wrap_text(text, font, max_w):
    words = text.split()
    if not words:
        return [text]
    lines, cur = [], []
    for w in words:
        test = ' '.join(cur + [w])
        tw, _ = text_wh(font, test)
        if tw <= max_w:
            cur.append(w)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [w]
    if cur:
        lines.append(' '.join(cur))
    return lines or [text]


def get_bg_default():
    """레포 루트의 bg_default.png 로드 → 1080x1920 리사이즈"""
    repo_bg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bg_default.png")
    if os.path.exists(repo_bg):
        try:
            img = Image.open(repo_bg).convert('RGBA')
            # 비율 유지 center-crop → 1080x1920
            bw, bh = img.size
            tr = W / H
            sr = bw / bh
            if sr > tr:
                nw = int(bh * tr)
                img = img.crop(((bw-nw)//2, 0, (bw-nw)//2+nw, bh))
            else:
                nh = int(bw / tr)
                img = img.crop((0, 0, bw, nh))
            img = img.resize((W, H), Image.LANCZOS)
            print("✅ bg_default.png 배경 사용")
            return img
        except Exception as e:
            print(f"⚠️ bg_default.png 로드 실패: {e}")
    # 폴백: 핑크 체크 패턴 생성
    print("⚠️ bg_default.png 없음, 폴백 배경 사용")
    img = Image.new('RGBA', (W, H), (*BRAND["cream"], 255))
    draw = ImageDraw.Draw(img)
    for x in range(0, W, 50):
        draw.line([(x,0),(x,H)], fill=(*BRAND["pink"],50), width=1)
    for y in range(0, H, 50):
        draw.line([(0,y),(W,y)], fill=(*BRAND["pink"],50), width=1)
    return img


# ─────────────────────────────────────────────
# 프레임 생성
# 썰그린 스타일:
#
#  ┌────────────────────────┐
#  │ ← 썰그린  [로고]  ···  │  ← 상단 채널 UI 바 (140px)
#  ├────────────────────────┤
#  │                        │
#  │   텍스트 한 줄           │  ← 텍스트 영역 (500px)
#  │   (크고 굵게, 중앙)     │    is_hook이면 더 크게
#  │                        │
#  ├────────────────────────┤
#  │                        │
│  │   Pixabay 이미지 카드   │  ← 이미지 카드 (나머지)
│  │   (라운드 코너 + 그림자) │
│  │                        │
│  ├────────────────────────┤
│  │ 매일 2번 업로드 · ...   │  ← 하단 바 (70px)
└──┴────────────────────────┘
# ─────────────────────────────────────────────
def create_frame(sentence, title, img_path=None, is_hook=False):
    # ── 배경: bg_default.png 풀스크린 ──
    canvas = get_bg_default()
    draw = ImageDraw.Draw(canvas)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ① 상단 채널 UI 바 (썰그린 스타일)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    BAR_H = 140
    bar = Image.new('RGBA', (W, BAR_H), (255, 255, 255, 210))
    canvas.paste(bar, (0, 0), bar)

    # 하단 핑크 라인
    draw.rectangle([0, BAR_H-5, W, BAR_H], fill=(*BRAND["pink_dark"], 255))

    # 왼쪽: 뒤로가기 + 채널명
    back_font = get_font(52)
    draw_text_outlined(draw, 30, 38, "←", back_font,
                       (*BRAND["text_dark"], 255), (*BRAND["white"], 200), 2)

    ch_font = get_font(52)
    draw_text_outlined(draw, 120, 38, "어머나!", ch_font,
                       (*BRAND["text_dark"], 255), (*BRAND["white"], 200), 2)

    # 오른쪽: 프로필 원 + 점 3개
    cx, cy, cr = W-100, BAR_H//2, 32
    draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr],
                 fill=(*BRAND["pink"], 255),
                 outline=(*BRAND["pink_dark"], 255), width=3)
    pf = get_font(28)
    draw_text_outlined(draw, cx-10, cy-14, "나!", pf,
                       (*BRAND["white"], 255), (*BRAND["pink_dark"], 200), 1)

    dot_x = W - 175
    for i in range(3):
        draw.ellipse([dot_x+i*22-6, cy-6, dot_x+i*22+6, cy+6],
                     fill=(*BRAND["text_dark"], 180))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ② 텍스트 영역 (BAR_H+20 ~ BAR_H+520)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    TEXT_TOP = BAR_H + 20
    TEXT_H = 500
    TEXT_BOT = TEXT_TOP + TEXT_H

    # 텍스트 배경 (반투명 흰색)
    tbg = Image.new('RGBA', (W, TEXT_H), (255, 255, 255, 160))
    canvas.paste(tbg, (0, TEXT_TOP), tbg)

    # 훅 문장: 왼쪽 핑크 강조 바
    if is_hook:
        draw.rectangle([0, TEXT_TOP, 16, TEXT_BOT],
                       fill=(*BRAND["pink_dark"], 255))

    # 폰트 크기: 훅이면 더 크게
    fs = 96 if is_hook else 84
    mf = get_font(fs)
    lines = wrap_text(sentence, mf, W - 80)
    lh = fs + 24
    total_h = len(lines) * lh
    ty = TEXT_TOP + (TEXT_H - total_h) // 2

    for i, line in enumerate(lines):
        lw, _ = text_wh(mf, line)
        lx = (W - lw) // 2
        ly = ty + i * lh
        draw_text_outlined(draw, lx, ly, line, mf,
                           color=(*BRAND["text_dark"], 255),
                           outline_color=(*BRAND["white"], 220),
                           outline=6)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ③ 이미지 카드 (TEXT_BOT+20 ~ H-90)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    CARD_TOP = TEXT_BOT + 20
    CARD_H = H - CARD_TOP - 90
    CARD_W = W - 80
    CARD_X = 40

    if img_path and os.path.exists(img_path):
        try:
            ci = Image.open(img_path).convert('RGBA')
            # center-crop to card ratio
            cw, ch = ci.size
            tr = CARD_W / CARD_H
            sr = cw / ch
            if sr > tr:
                nw = int(ch * tr)
                ci = ci.crop(((cw-nw)//2, 0, (cw-nw)//2+nw, ch))
            else:
                nh = int(cw / tr)
                ci = ci.crop((0, 0, cw, nh))
            ci = ci.resize((CARD_W, CARD_H), Image.LANCZOS)

            # 그림자 효과
            shadow_pad = 14
            shadow = Image.new('RGBA',
                               (CARD_W+shadow_pad*2, CARD_H+shadow_pad*2),
                               (0,0,0,0))
            sd = ImageDraw.Draw(shadow)
            sd.rounded_rectangle(
                [shadow_pad//2, shadow_pad//2,
                 CARD_W+shadow_pad+shadow_pad//2,
                 CARD_H+shadow_pad+shadow_pad//2],
                radius=44, fill=(0,0,0,60))
            canvas.paste(shadow,
                         (CARD_X-shadow_pad, CARD_TOP-shadow_pad),
                         shadow)

            # 핑크 테두리
            border_pad = 8
            border = Image.new('RGBA',
                               (CARD_W+border_pad*2, CARD_H+border_pad*2),
                               (*BRAND["pink"], 255))
            bm = Image.new('L', border.size, 0)
            ImageDraw.Draw(bm).rounded_rectangle(
                [0, 0, CARD_W+border_pad*2, CARD_H+border_pad*2],
                radius=48, fill=255)
            canvas.paste(border,
                         (CARD_X-border_pad, CARD_TOP-border_pad),
                         bm)

            # 이미지 (라운드 마스크)
            mask = Image.new('L', (CARD_W, CARD_H), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, CARD_W, CARD_H], radius=40, fill=255)
            canvas.paste(ci, (CARD_X, CARD_TOP), mask)

        except Exception as e:
            print(f"⚠️ 이미지 렌더: {e}")
            _draw_card_fallback(canvas, CARD_X, CARD_TOP, CARD_W, CARD_H)
    else:
        _draw_card_fallback(canvas, CARD_X, CARD_TOP, CARD_W, CARD_H)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ④ 하단 슬로건 바
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    SB_TOP = H - 70
    sbar = Image.new('RGBA', (W, 70), (*BRAND["pink_dark"], 230))
    canvas.paste(sbar, (0, SB_TOP), sbar)

    sf = get_font(34, bold=False)
    sl = "🌸 매일 2번 업로드  |  생활 밀착 정보 채널 🌸"
    sw, _ = text_wh(sf, sl)
    draw_text_outlined(draw, (W-sw)//2, SB_TOP+16, sl, sf,
                       (*BRAND["white"], 255),
                       (*BRAND["pink_dark"], 200), 2)

    path = f"/tmp/f_{datetime.datetime.now().strftime('%H%M%S%f')}.png"
    canvas.save(path, 'PNG')
    return path


def _draw_card_fallback(canvas, x, y, w, h):
    """이미지 없을 때 핑크→보라 그라디언트 카드"""
    grad = Image.new('RGBA', (w, h))
    gd = ImageDraw.Draw(grad)
    for row in range(h):
        r2 = row/h
        gd.line([(0,row),(w,row)], fill=(
            int(BRAND["pink"][0]*(1-r2)+BRAND["purple_light"][0]*r2),
            int(BRAND["pink"][1]*(1-r2)+BRAND["purple_light"][1]*r2),
            int(BRAND["pink"][2]*(1-r2)+BRAND["purple_light"][2]*r2),
            255))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0,0,w,h], radius=40, fill=255)
    canvas.paste(grad, (x, y), mask)


# ─────────────────────────────────────────────
# 스크립트 생성
# ─────────────────────────────────────────────
def generate_shorts_script(blog_title, blog_content, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if lang == "ko":
        prompt = f"""블로그를 30초 숏츠 대본으로 변환하세요.
제목: {blog_title}
내용: {blog_content[:600]}

규칙:
- 정확히 5문장
- 1문장: 강렬한 훅 (숫자나 충격 사실, 예: "월 50만원을 손가락만으로 버는 방법이 있어요!")
- 2~4문장: 핵심 정보 (짧고 임팩트, 한 문장 = 한 포인트, 10~20자)
- 5문장: "자세한 내용은 링크에서 확인하세요! 어머나~"
- 구어체, 40~60대 공감 톤

순수 JSON만:
{{"title": "숏츠제목(40자이내)", "script": "전체대본", "sentences": ["문장1","문장2","문장3","문장4","문장5"], "hashtags": ["#태그1","#태그2","#태그3","#태그4","#태그5"]}}"""
    else:
        prompt = f"""Convert to 30-second Shorts script.
Title: {blog_title}
Content: {blog_content[:600]}

Rules:
- Exactly 5 sentences
- S1: Strong hook (number or shocking fact)
- S2-4: Key insights (short, one point each, 8-15 words)
- S5: "Check the link for more! OhmyG~"
- Conversational tone

Pure JSON only:
{{"title": "title(40 chars)", "script": "full script", "sentences": ["s1","s2","s3","s4","s5"], "hashtags": ["#t1","#t2","#t3","#t4","#t5"]}}"""

    best, best_score, last_fb = None, 0, ""
    for attempt in range(3):
        p = prompt + (f"\n[피드백 반영]\n{last_fb}" if last_fb else "")
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1024,
            messages=[{"role": "user", "content": p}]
        )
        try:
            data = safe_parse_json(msg.content[0].text.strip())
            score, fb = _eval_script(data, lang, client)
            print(f"📊 스크립트 (시도{attempt+1}): {score}/10")
            if score > best_score:
                best_score, best = score, data
            last_fb = fb
            if score >= 8:
                break
        except Exception as e:
            print(f"⚠️ 파싱 실패: {e}")

    if best_score < 6:
        print(f"❌ 품질 미달 ({best_score}/10)")
        return None
    print(f"✅ 스크립트 확정: {best_score}/10")
    return best


def _eval_script(data, lang, client):
    try:
        p = (f"숏츠 스크립트 평가:\n제목: {data.get('title','')}\n스크립트: {data.get('script','')}\n\n점수: 7\n피드백: 개선점"
             if lang == "ko" else
             f"Rate Shorts:\nTitle: {data.get('title','')}\nScript: {data.get('script','')}\n\nScore: 7\nFeedback: improvement")
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=80,
            messages=[{"role": "user", "content": p}]
        )
        score, fb = 7, ""
        for line in msg.content[0].text.strip().split("\n"):
            if line.startswith(("점수:", "Score:")):
                nums = re.findall(r'\b([0-9]|10)\b', line.split(":",1)[1])
                if nums:
                    score = int(nums[0])
            if line.startswith(("피드백:", "Feedback:")):
                fb = line.split(":",1)[1].strip()
        return score, fb
    except Exception:
        return 7, ""


# ─────────────────────────────────────────────
# Pixabay
# ─────────────────────────────────────────────
def get_pixabay_images(keywords, lang, count=5):
    try:
        import urllib.request, urllib.parse, json as _j
        key = os.environ.get("PIXABAY_API_KEY", "")
        if not key:
            return []
        q = " ".join(keywords[:2]) if lang == "en" else keywords[0]
        ko2en = {
            "AI": "technology laptop workspace",
            "인공지능": "computer technology future",
            "비트코인": "gold coins money wealth",
            "투자": "growth chart money finance",
            "주식": "stock market chart graph",
            "ETF": "investment portfolio finance",
            "재테크": "piggy bank savings money",
            "자동화": "laptop workflow productivity",
            "번아웃": "tired office person stress",
            "동기부여": "sunrise mountain success road",
            "성공": "business success achievement",
            "노후": "happy senior couple outdoor",
            "트럼프": "business newspaper office",
            "관세": "cargo ship port trade",
            "일론 머스크": "electric car road night",
            "젠슨 황": "computer chip circuit board",
            "워런 버핏": "finance books newspaper",
            "시니어": "senior lifestyle happy outdoor",
            "부업": "laptop coffee freelance home",
            "블로그": "writing laptop coffee desk",
            "연금": "retirement savings jar coins",
            "바이브코딩": "coding laptop desk coffee",
            "챗GPT": "laptop chat screen AI",
        }
        for ko, en in ko2en.items():
            if ko in q:
                q = en
                break
        enc = urllib.parse.quote(q)
        for ori in ["vertical", "horizontal"]:
            url = (f"https://pixabay.com/api/?key={key.strip()}"
                   f"&q={enc}&image_type=photo&orientation={ori}"
                   f"&per_page=20&safesearch=true&min_width=600")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _j.loads(resp.read())
            hits = data.get("hits", [])
            if hits:
                import random
                sel = random.sample(hits[:15], min(count, len(hits[:15])))
                print(f"🖼️ Pixabay {len(sel)}개: {q}")
                return [h["webformatURL"] for h in sel]
    except Exception as e:
        print(f"⚠️ Pixabay: {e}")
    return []


def download_image(url, path):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────
# TTS
# ─────────────────────────────────────────────
def generate_tts(script, lang):
    path = f"/tmp/audio_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    gTTS(text=script, lang="ko" if lang == "ko" else "en", slow=False).save(path)
    print("🎤 TTS 완료")
    return path


# ─────────────────────────────────────────────
# 영상 생성
# ─────────────────────────────────────────────
def create_video(audio_path, sentences, title, lang, keywords=None):
    vpath = f"/tmp/shorts_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"

    # 이미지 다운로드 (문장 수만큼)
    imgs = []
    if keywords:
        urls = get_pixabay_images(keywords, lang, count=len(sentences))
        for j, url in enumerate(urls):
            p = f"/tmp/ci_{j}_{datetime.datetime.now().strftime('%H%M%S%f')}.jpg"
            if download_image(url, p):
                imgs.append(p)
    if not imgs:
        imgs = [None]

    # TTS 길이 균등 분할
    audio = AudioFileClip(audio_path)
    total = audio.duration
    per = total / len(sentences)
    audio.close()

    # 문장마다 프레임 생성
    clips = []
    for i, sentence in enumerate(sentences):
        frame = create_frame(
            sentence, title,
            img_path=imgs[i % len(imgs)],
            is_hook=(i == 0)
        )
        clips.append(ImageClip(frame).set_duration(per))

    audio2 = AudioFileClip(audio_path)
    final = concatenate_videoclips(clips, method="compose").set_audio(audio2)
    final.write_videofile(vpath, fps=30, codec='libx264',
                          audio_codec='aac', verbose=False, logger=None)
    print(f"🎬 영상 완료: {vpath}")
    return vpath


# ─────────────────────────────────────────────
# YouTube 업로드
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
    svc = get_youtube_service()
    tags = [t.replace("#", "") for t in hashtags]
    tags += (["shorts", "어머나", "AI", "재테크"] if lang == "ko"
             else ["shorts", "OhmyG", "AI", "finance"])
    body = {
        "snippet": {
            "title": title[:100],
            "description": description + "\n\n" + " ".join(hashtags),
            "tags": tags,
            "categoryId": "28",
            "defaultLanguage": lang,
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"📤 {int(status.progress()*100)}%")
    url = f"https://youtube.com/shorts/{response['id']}"
    print(f"✅ YouTube: {url}")
    return url


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def generate_shorts(blog_title, blog_content, lang, blog_url=""):
    print(f"\n🎬 숏츠 시작: {blog_title}")
    data = generate_shorts_script(blog_title, blog_content, lang)
    if not data:
        return None
    print(f"📝 {data['title']}")
    audio = generate_tts(data["script"], lang)
    kw = blog_title.split()[:3]
    video = create_video(audio, data["sentences"], data["title"], lang, keywords=kw)
    desc = (
        f"{data['script']}\n\n"
        f"🔗 {'자세한 내용' if lang=='ko' else 'Read more'}: {blog_url}\n\n"
        f"{'📌 구독하면 매일 생활 밀착 정보를 드려요~' if lang=='ko' else '📌 Subscribe for daily tips!'}"
    )
    return upload_to_youtube(video, data["title"], desc, data["hashtags"], lang)


if __name__ == "__main__":
    url = generate_shorts(
        "AI로 월 100만원 버는 현실적인 방법 5가지",
        "AI 도구를 활용해 실제로 수익을 만드는 방법. 블로그 자동화, 콘텐츠 제작, 프리랜서 자동화.",
        "ko", "https://aiinsightlabs.blogspot.com"
    )
    print(f"🎉 완료: {url}")
