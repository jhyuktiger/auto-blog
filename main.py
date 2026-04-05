"""
Auto Blog Generator v2.2
블로그 발행 → 숏츠 자동 생성 연동
"""

import os
import json
import random
import datetime
import time
import anthropic
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
KO_BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
KO_BLOGGER_CLIENT_ID = os.environ["BLOGGER_CLIENT_ID"]
KO_BLOGGER_CLIENT_SECRET = os.environ["BLOGGER_CLIENT_SECRET"]
EN_BLOGGER_REFRESH_TOKEN = os.environ["EN_BLOGGER_REFRESH_TOKEN"]
EN_BLOGGER_CLIENT_ID = os.environ["EN_BLOGGER_CLIENT_ID"]
EN_BLOGGER_CLIENT_SECRET = os.environ["EN_BLOGGER_CLIENT_SECRET"]
KO_BLOG_ID = os.environ["KO_BLOG_ID"]
EN_BLOG_ID = os.environ["EN_BLOG_ID"]

# 숏츠 관련 secrets (없으면 숏츠 스킵)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

SHORTS_ENABLED = all([GEMINI_API_KEY, YOUTUBE_REFRESH_TOKEN, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET])

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    """텔레그램 알림 발송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import urllib.request
        import urllib.parse
        text = urllib.parse.quote(message)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={text}&parse_mode=HTML"
        urllib.request.urlopen(url, timeout=10)
        print("📱 텔레그램 알림 발송 완료")
    except Exception as e:
        print(f"⚠️ 텔레그램 실패: {e}")

def get_published_titles(service, blog_id):
    try:
        result = service.posts().list(blogId=blog_id, maxResults=50).execute()
        titles = [post["title"] for post in result.get("items", [])]
        print(f"📋 기발행 {len(titles)}개 확인")
        return titles
    except Exception as e:
        print(f"⚠️ 목록 조회 실패: {e}")
        return []

def get_trending_ko():
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='ko-KR', tz=540)
        df = pt.trending_searches(pn='south_korea')
        topics = df[0].tolist()[:10]
        print(f"🔥 KO 트렌드: {topics[:5]}")
        return topics
    except Exception as e:
        print(f"⚠️ 트렌드 실패: {e}")
        return None

def get_trending_en():
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-US', tz=0)
        df = pt.trending_searches(pn='united_states')
        topics = df[0].tolist()[:10]
        print(f"🔥 EN 트렌드: {topics[:5]}")
        return topics
    except Exception as e:
        print(f"⚠️ 트렌드 실패: {e}")
        return None

KO_TOPICS = [
    # ── AI/자동화 ──
    {"title": "Claude API로 자동화 도구 만드는 법 (초보자 완전 가이드)", "keywords": ["Claude API", "AI 자동화", "바이브코딩"], "category": "AI"},
    {"title": "바이브코딩이란? 2026년 개발자 없이 앱 만드는 방법", "keywords": ["바이브코딩", "Cursor", "bolt.new"], "category": "AI"},
    {"title": "ChatGPT vs Claude 실전 비교 어떤 AI가 더 유용한가", "keywords": ["ChatGPT", "Claude", "AI 비교"], "category": "AI"},
    {"title": "Cursor AI로 코딩 10배 빠르게 하는 실전 팁", "keywords": ["Cursor AI", "AI 코딩", "개발 생산성"], "category": "AI"},
    {"title": "AI로 월 100만원 버는 현실적인 방법 5가지", "keywords": ["AI 부업", "AI 수익화", "AI 활용"], "category": "AI"},
    {"title": "n8n 자동화로 반복 업무 없애는 방법 무료", "keywords": ["n8n", "업무 자동화", "노코드"], "category": "AI"},
    {"title": "구글 애드센스 승인 받는 방법 2026년 최신 가이드", "keywords": ["애드센스 승인", "구글 애드센스", "블로그 수익"], "category": "AI"},
    {"title": "AI 이미지 생성 도구 비교 Midjourney vs DALL-E vs Gemini", "keywords": ["AI 이미지", "Midjourney", "이미지 생성"], "category": "AI"},
    {"title": "챗GPT로 하루 2시간 업무 줄이는 실전 프롬프트 10가지", "keywords": ["챗GPT 프롬프트", "업무 효율", "AI 활용"], "category": "AI"},
    {"title": "노코드로 나만의 앱 만들기 bubble vs flutterflow 비교", "keywords": ["노코드", "bubble", "앱 개발"], "category": "AI"},
    # ── 투자/재테크 ──
    {"title": "비트코인 2026 전망 반감기 이후 실제로 어떻게 될까", "keywords": ["비트코인 전망", "BTC 2026", "암호화폐"], "category": "투자"},
    {"title": "달러 ETF로 환율 헤지하는 방법 완전 정리", "keywords": ["달러 ETF", "환율 헤지", "달러 투자"], "category": "투자"},
    {"title": "미국 주식 배당금 세금 완벽 정리 2026 기준", "keywords": ["미국 주식 세금", "배당 세금", "해외 주식"], "category": "투자"},
    {"title": "S&P500 ETF 매달 적립식 투자 10년 시뮬레이션", "keywords": ["S&P500", "ETF 투자", "적립식"], "category": "투자"},
    {"title": "ISA 계좌 완전 정복 세금 혜택 최대로 쓰는 방법", "keywords": ["ISA 계좌", "절세", "재테크"], "category": "투자"},
    {"title": "ETF vs 개별주식 초보 투자자를 위한 완전 비교", "keywords": ["ETF", "개별주식", "투자 초보"], "category": "투자"},
    {"title": "연금저축펀드 완전 정복 세액공제 최대로 받는 법", "keywords": ["연금저축", "세액공제", "노후준비"], "category": "투자"},
    {"title": "월급쟁이 재테크 로드맵 30대가 꼭 해야 할 5가지", "keywords": ["재테크 로드맵", "30대 투자", "월급 재테크"], "category": "투자"},
    {"title": "트럼프 관세 충격 한국 주식시장 어떻게 대응할까", "keywords": ["트럼프 관세", "한국 주식", "시장 대응"], "category": "투자"},
    # ── CEO/인물 인사이트 ──
    {"title": "일론 머스크가 말하는 성공의 조건 핵심 명언 정리", "keywords": ["일론 머스크", "성공 명언", "동기부여"], "category": "인물"},
    {"title": "젠슨 황 엔비디아 CEO의 AI 미래 예측 2026 요약", "keywords": ["젠슨 황", "엔비디아", "AI 미래"], "category": "인물"},
    {"title": "샘 알트만이 말하는 AGI 시대 살아남는 법", "keywords": ["샘 알트만", "OpenAI", "AGI"], "category": "인물"},
    {"title": "팔란티어 CEO 알렉스 카프 젊은이들에게 주는 조언", "keywords": ["팔란티어", "알렉스 카프", "성공 조언"], "category": "인물"},
    {"title": "워런 버핏 최신 주주서한 핵심 투자 철학 정리", "keywords": ["워런 버핏", "주주서한", "투자 철학"], "category": "인물"},
    {"title": "손정의 소프트뱅크 AI 투자 전략 2026 완전 분석", "keywords": ["손정의", "소프트뱅크", "AI 투자"], "category": "인물"},
    # ── 동기부여/자기계발 ──
    {"title": "하루 1시간으로 인생이 바뀌는 루틴 만드는 법", "keywords": ["하루 루틴", "자기계발", "습관 만들기"], "category": "자기계발"},
    {"title": "성공한 사람들이 절대 하지 않는 5가지 습관", "keywords": ["성공 습관", "자기계발", "동기부여"], "category": "자기계발"},
    {"title": "번아웃 극복하는 방법 실리콘밸리 CEO들의 비결", "keywords": ["번아웃", "극복 방법", "멘탈 관리"], "category": "자기계발"},
    {"title": "돈보다 중요한 것 세계 최고 부자들이 후회하는 것들", "keywords": ["부자 마인드", "인생 후회", "성공의 의미"], "category": "자기계발"},
    # ── 시니어 타겟 ──
    {"title": "60대 노후 준비 지금 당장 시작해야 할 3가지", "keywords": ["노후 준비", "60대 재테크", "연금"], "category": "시니어"},
    {"title": "스마트폰으로 돈 버는 법 시니어도 할 수 있는 부업", "keywords": ["시니어 부업", "스마트폰 수익", "노후 수입"], "category": "시니어"},
    {"title": "카카오페이 토스 안전하게 쓰는 방법 완전 정리", "keywords": ["카카오페이", "토스", "금융 앱 사용법"], "category": "시니어"},
]

EN_TOPICS = [
    # ── AI/Automation ──
    {"title": "Vibe Coding in 2026: Build Apps Without Writing Code", "keywords": ["vibe coding", "no-code", "AI development"], "category": "AI"},
    {"title": "Claude API Tutorial: Automate Any Task in 30 Minutes", "keywords": ["Claude API", "AI automation", "Python"], "category": "AI"},
    {"title": "Best AI Tools for Side Hustle in 2026 Ranked", "keywords": ["AI tools", "side hustle", "make money AI"], "category": "AI"},
    {"title": "How to Make 1000 Per Month Using Claude and n8n Automation", "keywords": ["Claude automation", "n8n", "passive income AI"], "category": "AI"},
    {"title": "Google AdSense Approval Guide 2026: What Actually Works", "keywords": ["Google AdSense", "AdSense approval", "blog monetization"], "category": "AI"},
    {"title": "10 ChatGPT Prompts That Actually Save You Hours Every Day", "keywords": ["ChatGPT prompts", "productivity", "AI workflow"], "category": "AI"},
    {"title": "AI Agents Explained: How to Automate Your Entire Workflow in 2026", "keywords": ["AI agents", "workflow automation", "n8n"], "category": "AI"},
    # ── Finance ──
    {"title": "Bitcoin Halving Cycle Explained: What History Says About 2026", "keywords": ["Bitcoin halving", "BTC price prediction", "crypto investing"], "category": "Finance"},
    {"title": "S&P 500 vs Bitcoin: 10-Year Return Comparison", "keywords": ["S&P 500", "Bitcoin investment", "portfolio"], "category": "Finance"},
    {"title": "Best High-Dividend ETFs for Passive Income in 2026", "keywords": ["dividend ETF", "passive income", "high yield"], "category": "Finance"},
    {"title": "Trump Tariffs Impact: How to Protect Your Portfolio Right Now", "keywords": ["Trump tariffs", "portfolio protection", "market volatility"], "category": "Finance"},
    {"title": "Dollar Cost Averaging Bitcoin: 3-Year Simulation Results", "keywords": ["DCA Bitcoin", "crypto strategy", "dollar cost averaging"], "category": "Finance"},
    {"title": "Index Fund vs ETF: Which Is Better for Long-Term Investing", "keywords": ["index fund", "ETF investing", "long term"], "category": "Finance"},
    # ── CEO Insights ──
    {"title": "Elon Musk on Success: Key Lessons From His Latest Interviews", "keywords": ["Elon Musk", "success lessons", "entrepreneur mindset"], "category": "People"},
    {"title": "Jensen Huang Predicts the Future of AI: What He Said in 2026", "keywords": ["Jensen Huang", "Nvidia", "AI future"], "category": "People"},
    {"title": "Sam Altman on AGI: How to Survive and Thrive in the AI Era", "keywords": ["Sam Altman", "OpenAI", "AGI future"], "category": "People"},
    {"title": "Warren Buffett Latest Letter: Core Investment Wisdom for 2026", "keywords": ["Warren Buffett", "investment wisdom", "shareholder letter"], "category": "People"},
    {"title": "Palantir CEO Alex Karp Advice for Young People: Full Summary", "keywords": ["Palantir", "Alex Karp", "career advice"], "category": "People"},
    # ── Motivation/Growth ──
    {"title": "5 Habits Billionaires Share That Most People Ignore", "keywords": ["billionaire habits", "success mindset", "daily routine"], "category": "Motivation"},
    {"title": "How to Build a Morning Routine That Actually Changes Your Life", "keywords": ["morning routine", "productivity", "success habits"], "category": "Motivation"},
    {"title": "Burnout Recovery: What Silicon Valley CEOs Do Differently", "keywords": ["burnout recovery", "CEO mindset", "mental health"], "category": "Motivation"},
    {"title": "What the World Most Successful People Regret Most", "keywords": ["success regrets", "life lessons", "mindset shift"], "category": "Motivation"},
]

def is_duplicate(topic, published_titles):
    """키워드 기반 유사도 체크 - 핵심 키워드가 2개 이상 겹치면 중복"""
    title_lower = topic["title"].lower()
    for pub in published_titles:
        pub_lower = pub.lower()
        # 제목 완전 일치
        if title_lower == pub_lower:
            return True
        # 핵심 키워드 겹침 체크
        matches = sum(1 for kw in topic["keywords"] if kw.lower() in pub_lower)
        if matches >= 2:
            return True
    return False

def select_topic(lang, published_titles):
    if lang == "ko":
        trends = get_trending_ko()
        if trends:
            for kw in trends:
                t = f"{kw} 완전 정리 2026년 최신 가이드"
                candidate = {"title": t, "keywords": [kw, "트렌드", "최신"], "category": "트렌드", "is_trend": True}
                if not is_duplicate(candidate, published_titles):
                    return candidate
        pool = KO_TOPICS[:]
        random.shuffle(pool)
        # 카테고리 다양성: 최근 발행 카테고리 파악
        recent = published_titles[:5]
        recent_cats = []
        for pub in recent:
            for t in KO_TOPICS:
                if t["title"] in pub:
                    recent_cats.append(t["category"])
        # 덜 나온 카테고리 우선
        for topic in sorted(pool, key=lambda x: recent_cats.count(x["category"])):
            if not is_duplicate(topic, published_titles):
                return topic
    else:
        trends = get_trending_en()
        if trends:
            for kw in trends:
                t = f"{kw}: Complete Guide for 2026"
                candidate = {"title": t, "keywords": [kw, "trending", "2026"], "category": "Trending", "is_trend": True}
                if not is_duplicate(candidate, published_titles):
                    return candidate
        pool = EN_TOPICS[:]
        random.shuffle(pool)
        recent = published_titles[:5]
        recent_cats = []
        for pub in recent:
            for t in EN_TOPICS:
                if t["title"] in pub:
                    recent_cats.append(t["category"])
        for topic in sorted(pool, key=lambda x: recent_cats.count(x["category"])):
            if not is_duplicate(topic, published_titles):
                return topic
    today = datetime.date.today().strftime("%Y-%m-%d")
    base = KO_TOPICS[0] if lang == "ko" else EN_TOPICS[0]
    return {"title": f"{base['title']} ({today})", "keywords": base["keywords"], "category": base["category"], "is_trend": False}

def get_pexels_image(keywords, lang):
    """Pixabay API로 블로그 썸네일 이미지 URL 가져오기"""
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
        if not PIXABAY_API_KEY:
            return None
        query = " ".join(keywords[:2]) if lang == "en" else keywords[0]
        ko_to_en = {
            # AI/기술
            "AI": "artificial intelligence technology",
            "인공지능": "artificial intelligence brain",
            "자동화": "automation robot technology",
            "바이브코딩": "programmer coding laptop",
            "Claude": "artificial intelligence computer",
            "ChatGPT": "chatbot AI technology",
            "코딩": "programming code laptop",
            "앱": "smartphone app mobile",
            "소프트웨어": "software development",
            # 투자/금융
            "비트코인": "bitcoin cryptocurrency coins",
            "코인": "cryptocurrency digital money",
            "주식": "stock market trading charts",
            "ETF": "investment portfolio finance",
            "투자": "investment money growth",
            "재테크": "money saving finance",
            "달러": "dollar currency money",
            "배당": "dividend income money",
            "연금": "retirement pension savings",
            "노후": "retirement elderly couple",
            "절세": "tax saving finance",
            # CEO/인물
            "일론 머스크": "electric car tesla technology",
            "젠슨 황": "GPU chip semiconductor",
            "샘 알트만": "AI startup office",
            "워런 버핏": "investment stocks newspaper",
            "팔란티어": "data analytics office",
            "손정의": "technology investment startup",
            # 동기부여/자기계발
            "번아웃": "burnout stress tired office",
            "동기부여": "motivation inspiration success",
            "자기계발": "personal growth books reading",
            "성공": "success achievement winner",
            "습관": "morning routine healthy lifestyle",
            "루틴": "morning routine workout",
            "멘탈": "mental health mindfulness calm",
            # 시니어/생활
            "시니어": "senior couple happy lifestyle",
            "스마트폰": "smartphone elderly hands",
            "카카오": "mobile payment smartphone",
            # 뉴스/시사
            "트럼프": "business politics office",
            "관세": "trade shipping containers port",
            "경제": "economy business growth chart",
            "금리": "bank interest rate finance",
            # 블로그/수익
            "애드센스": "laptop blogger writing",
            "블로그": "blogger writing laptop coffee",
            "수익": "income money laptop online",
            "부업": "side hustle freelance laptop",
        }
        for ko, en in ko_to_en.items():
            if ko in query:
                query = en
                break
        encoded = urllib.parse.quote(query)
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY.strip()}&q={encoded}&image_type=photo&orientation=horizontal&per_page=10&safesearch=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        hits = data.get("hits", [])
        if hits:
            import random
            photo = random.choice(hits[:10])
            img_url = photo["webformatURL"]
            print(f"🖼️ 블로그 이미지: {query} (Pixabay)")
            return {"url": img_url, "credit": "Pixabay"}
    except Exception as e:
        print(f"⚠️ Pixabay 이미지 실패: {e}")
    return None

def generate_post(topic, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")
    is_trend = topic.get("is_trend", False)
    if lang == "ko":
        system = """당신은 "어머나!" 채널의 전문 블로거입니다. 40~60대 직장인/시니어 독자를 위해 AI·재테크·생활정보를 쉽고 친근하게 씁니다.

[독자 특성]
- 40~60대 직장인, 은퇴 준비 중인 시니어
- 어려운 용어보다 쉬운 설명 선호
- 실생활에 바로 적용 가능한 정보 원함
- 카카오톡으로 공유하고 싶은 콘텐츠

[글쓰기 규칙]
1. 분량: 2000~3000자, h2/h3/p/ul/li 태그 사용
2. 어미 5가지를 아래 비율로 혼용:
   - "~다" (30%): 단정적 서술
   - "~요" (25%): 친근한 설명
   - "~죠" (15%): 공감 유도
   - "~거든요" (15%): 구어체 설명
   - "~네요" (15%): 감탄/발견
3. 같은 어미 2문장 연속 금지 → 반드시 다른 어미로 변경
4. 첫 문장은 숫자나 질문으로 시작 (예: "월 100만원을 더 버는 방법이 있다면?")

[절대 금지 표현]
- "살펴보겠습니다", "알아보겠습니다", "정리해보겠습니다"
- "이번 글에서는", "~해 보겠습니다", "~드리겠습니다"
- "중요합니다", "필요합니다" (→ "중요해요", "필요해요"로 대체)
- "하였습니다", "되었습니다" (→ "했어요", "됐어요"로 대체)
- "본 포스팅", "해당 내용", "위의 내용"
- 전문용어 남발 (반드시 쉬운 말로 풀어서 설명)

[콘텐츠 품질 기준]
- 독자가 읽고 나서 "어머나! 이런 게 있었어?" 반응 유도
- 실생활 예시 반드시 포함 (숫자, 사례, 비교)
- 각 소제목 아래 3~5개 핵심 포인트
- 마지막 단락: 오늘 당장 실천할 수 있는 1가지 행동 제시
- 투자 권유 금지, 허위 정보 금지, 면책조항 필수"""
        prompt = f"오늘: {today}\n{'[트렌딩 주제]' if is_trend else ''}\n제목: {topic['title']}\n키워드: {', '.join(topic['keywords'])}\n\n순수 JSON만 응답:\n{{\"title\": \"제목\", \"html_content\": \"HTML본문\", \"labels\": [\"태그1\",\"태그2\",\"태그3\"]}}"
    else:
        system = """You are a blogger for OhmyG channel, writing for professionals aged 40-60 interested in AI, finance, and self-improvement.

[Reader Profile]
- Busy professionals and pre-retirees aged 40-60
- Want practical, actionable information
- Prefer clear explanations over jargon
- Share content they find genuinely useful

[Writing Rules]
1. Length: 1000-1500 words, use h2/h3/p/ul/li tags
2. Start with a surprising number or bold question (e.g. "What if you could save 00/month with one simple change?")
3. Write like a smart friend giving real advice, not a textbook
4. Mix short punchy sentences with longer explanatory ones
5. Include at least one real example or comparison with numbers
6. End with one concrete action reader can take TODAY

[Absolute Forbidden]
- "In this article", "Let's dive in", "In conclusion, we explored"
- "It's worth noting that", "As we can see", "Without further ado"
- "Leverage", "Utilize", "Robust", "Delve into" (too corporate/AI-sounding)
- Vague advice without specific numbers or examples
- Overly formal or academic tone

[Quality Standard]
- Reader reaction should be: "OhmyG! I didn't know that!"
- Every section needs a practical takeaway
- No investment advice, no false info, disclaimer required"""
        prompt = f"Today: {today}\n{'[Trending topic]' if is_trend else ''}\nTitle: {topic['title']}\nKeywords: {', '.join(topic['keywords'])}\n\nPure JSON only:\n{{\"title\": \"title\", \"html_content\": \"HTML content\", \"labels\": [\"tag1\",\"tag2\",\"tag3\"]}}"
    for attempt in range(3):
        msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=8096, system=system, messages=[{"role": "user", "content": prompt}])
        raw = msg.content[0].text
        try:
            return json.loads(raw[raw.find("{"):raw.rfind("}")+1])
        except json.JSONDecodeError:
            try:
                import re
                cleaned = raw[raw.find("{"):raw.rfind("}")+1]
                cleaned = re.sub(r'\\(?!["\\/bfnrt])', r'\\\\', cleaned)
                return json.loads(cleaned)
            except Exception:
                print(f"⚠️ JSON 파싱 실패 (시도 {attempt+1}/3), 재생성...")
                time.sleep(2)
    title = topic["title"]
    return {"title": title, "html_content": f"<h2>{title}</h2><p>준비 중입니다.</p>", "labels": topic.get("keywords", ["AI"])[:3]}

def evaluate_post(post, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if lang == "ko":
        prompt = f"블로그 글 품질 0~10점:\n제목: {post['title']}\n미리보기: {post['html_content'][:400]}\n숫자만 응답"
    else:
        prompt = f"Rate blog 0-10:\nTitle: {post['title']}\nPreview: {post['html_content'][:400]}\nNumber only"
    msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10, messages=[{"role": "user", "content": prompt}])
    try:
        score = int(msg.content[0].text.strip())
        print(f"📊 품질: {score}/10")
        return score
    except:
        return 7

def get_blogger_service(rt, ci, cs):
    creds = Credentials(token=None, refresh_token=rt, client_id=ci, client_secret=cs, token_uri="https://oauth2.googleapis.com/token", scopes=["https://www.googleapis.com/auth/blogger"])
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)

def publish_post(service, blog_id, title, html_content, labels, img_data=None):
    # 이미지 상단 삽입
    if img_data:
        img_html = f'''<div style="text-align:center;margin-bottom:24px;">
<img src="{img_data["url"]}" alt="{title}" style="max-width:100%;border-radius:8px;"/>
<p style="font-size:12px;color:#888;">Photo by {img_data["credit"]} on Pexels</p>
</div>'''
        html_content = img_html + html_content
    body = {"title": title, "content": html_content, "labels": labels}
    result = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return result.get("url", "")

# ─────────────────────────────────────────────
# 숏츠 연동 (블로그 발행 후 자동 실행)
# ─────────────────────────────────────────────
def try_generate_shorts(title, content, lang, blog_url):
    """숏츠 생성 시도 - 실패해도 블로그 발행에 영향 없음"""
    if not SHORTS_ENABLED:
        print("⏭️ 숏츠 스킵 (YouTube secrets 없음)")
        return None
    try:
        # 환경변수 임시 설정 (shorts_generator가 os.environ 직접 읽으므로)
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
        os.environ["YOUTUBE_REFRESH_TOKEN"] = YOUTUBE_REFRESH_TOKEN
        os.environ["YOUTUBE_CLIENT_ID"] = YOUTUBE_CLIENT_ID
        os.environ["YOUTUBE_CLIENT_SECRET"] = YOUTUBE_CLIENT_SECRET

        from shorts_generator import generate_shorts
        shorts_url = generate_shorts(title, content, lang, blog_url)
        print(f"🎬 숏츠 완료: {shorts_url}")
        return shorts_url
    except Exception as e:
        print(f"⚠️ 숏츠 실패 (블로그는 정상 발행됨): {e}")
        return None

def html_to_plain(html_content):
    """HTML 태그 제거해서 숏츠 스크립트용 텍스트 추출"""
    import re
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:800]

def main():
    print("🚀 Auto Blog Generator v2.2 (블로그 + 숏츠)")
    print(f"🎬 숏츠 자동화: {'✅ 활성화' if SHORTS_ENABLED else '⏭️ 비활성화'}")

    # ── 한국어 블로그 ──
    ko_svc = get_blogger_service(KO_BLOGGER_REFRESH_TOKEN, KO_BLOGGER_CLIENT_ID, KO_BLOGGER_CLIENT_SECRET)
    ko_pub = get_published_titles(ko_svc, KO_BLOG_ID)
    ko_topic = select_topic("ko", ko_pub)
    print(f"📝 KO: {ko_topic['title']} {'[트렌드]' if ko_topic.get('is_trend') else '[고정]'}")
    ko_post = generate_post(ko_topic, "ko")
    if evaluate_post(ko_post, "ko") < 7:
        print("⚠️ 재생성")
        time.sleep(2)
        ko_post = generate_post(ko_topic, "ko")
    ko_img = get_pexels_image(ko_topic["keywords"], "ko")
    ko_url = publish_post(ko_svc, KO_BLOG_ID, ko_post["title"], ko_post["html_content"], ko_post["labels"], ko_img)
    print(f"✅ KO 블로그: {ko_url}")
    send_telegram(f"""✅ <b>어머나! 발행 완료</b>
📝 {ko_post["title"]}
🔗 {ko_url}""")

    # 한국어 숏츠 생성
    ko_plain = html_to_plain(ko_post["html_content"])
    try_generate_shorts(ko_post["title"], ko_plain, "ko", ko_url)

    # ── 영어 블로그 ──
    en_svc = get_blogger_service(EN_BLOGGER_REFRESH_TOKEN, EN_BLOGGER_CLIENT_ID, EN_BLOGGER_CLIENT_SECRET)
    en_pub = get_published_titles(en_svc, EN_BLOG_ID)
    en_topic = select_topic("en", en_pub)
    print(f"📝 EN: {en_topic['title']} {'[트렌드]' if en_topic.get('is_trend') else '[고정]'}")
    en_post = generate_post(en_topic, "en")
    if evaluate_post(en_post, "en") < 7:
        print("⚠️ 재생성")
        time.sleep(2)
        en_post = generate_post(en_topic, "en")
    en_img = get_pexels_image(en_topic["keywords"], "en")
    en_url = publish_post(en_svc, EN_BLOG_ID, en_post["title"], en_post["html_content"], en_post["labels"], en_img)
    print(f"✅ EN 블로그: {en_url}")
    send_telegram(f"""✅ <b>OhmyG 발행 완료</b>
📝 {en_post["title"]}
🔗 {en_url}""")

    # 영어 숏츠 생성
    en_plain = html_to_plain(en_post["html_content"])
    try_generate_shorts(en_post["title"], en_plain, "en", en_url)

    print("🎉 전체 완료!")
    send_telegram("🎉 <b>오늘의 자동화 완료!</b>
KO + EN 블로그 + 숏츠 발행 완료 ✅")

if __name__ == "__main__":
    main()
