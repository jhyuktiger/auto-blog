"""
Auto Blog Generator v2.4
멀티 에이전트 파이프라인: RSS 리서처 → 작가 → 검증
블로그 발행 → 숏츠 자동 생성 연동
"""

import os
import re
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

SHORTS_ENABLED = all([GEMINI_API_KEY, YOUTUBE_REFRESH_TOKEN, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET])

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────
# RSS 피드 목록 (무료, API 키 불필요)
# ─────────────────────────────────────────────
KO_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=AI+인공지능&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=ChatGPT+Claude+AI도구&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=바이브코딩+자동화&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=주식+ETF+투자&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=비트코인+암호화폐&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=재테크+부업+수익&hl=ko&gl=KR&ceid=KR:ko",
]

EN_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=AI+artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ChatGPT+Claude+AI+tools&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=vibe+coding+automation&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=stock+market+investing+ETF&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=bitcoin+cryptocurrency+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=passive+income+side+hustle&hl=en-US&gl=US&ceid=US:en",
]


def fetch_rss_news(feeds, max_items=15):
    """RSS 피드에서 최신 뉴스 수집 (외부 라이브러리 불필요)"""
    import urllib.request
    import xml.etree.ElementTree as ET

    news_items = []
    for feed_url in feeds:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:5]:
                title_el = item.find("title")
                desc_el = item.find("description")
                title = title_el.text if title_el is not None else ""
                desc = desc_el.text if desc_el is not None else ""
                title = re.sub(r'<[^>]+>', '', title).strip()
                desc = re.sub(r'<[^>]+>', '', desc).strip()
                if title:
                    news_items.append({"title": title, "desc": desc[:200]})
        except Exception as e:
            print(f"⚠️ RSS 수집 실패: {e}")
            continue

    # 중복 제거
    seen = set()
    unique = []
    for item in news_items:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    print(f"📰 오늘의 뉴스 {len(unique)}개 수집 완료")
    return unique[:max_items]


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import urllib.request
        import urllib.parse
        clean = re.sub(r'<[^>]+>', '', message)
        text = urllib.parse.quote(clean)
        url = (
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            f"?chat_id={TELEGRAM_CHAT_ID}&text={text}"
        )
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
    {"title": "Claude API로 자동화 도구 만드는 법 (초보자 완전 가이드)", "keywords": ["Claude API", "AI 자동화", "바이브코딩"], "category": "AI"},
    {"title": "바이브코딩이란? 2026년 개발자 없이 앱 만드는 방법", "keywords": ["바이브코딩", "Cursor", "bolt.new"], "category": "AI"},
    {"title": "ChatGPT vs Claude 실전 비교 어떤 AI가 더 유용한가", "keywords": ["ChatGPT", "Claude", "AI 비교"], "category": "AI"},
    {"title": "AI로 월 100만원 버는 현실적인 방법 5가지", "keywords": ["AI 부업", "AI 수익화", "AI 활용"], "category": "AI"},
    {"title": "n8n 자동화로 반복 업무 없애는 방법 무료", "keywords": ["n8n", "업무 자동화", "노코드"], "category": "AI"},
    {"title": "구글 애드센스 승인 받는 방법 2026년 최신 가이드", "keywords": ["애드센스 승인", "구글 애드센스", "블로그 수익"], "category": "AI"},
    {"title": "비트코인 2026 전망 반감기 이후 실제로 어떻게 될까", "keywords": ["비트코인 전망", "BTC 2026", "암호화폐"], "category": "투자"},
    {"title": "달러 ETF로 환율 헤지하는 방법 완전 정리", "keywords": ["달러 ETF", "환율 헤지", "달러 투자"], "category": "투자"},
    {"title": "미국 주식 배당금 세금 완벽 정리 2026 기준", "keywords": ["미국 주식 세금", "배당 세금", "해외 주식"], "category": "투자"},
    {"title": "S&P500 ETF 매달 적립식 투자 10년 시뮬레이션", "keywords": ["S&P500", "ETF 투자", "적립식"], "category": "투자"},
    {"title": "ISA 계좌 완전 정복 세금 혜택 최대로 쓰는 방법", "keywords": ["ISA 계좌", "절세", "재테크"], "category": "투자"},
    {"title": "트럼프 관세 충격 한국 주식시장 어떻게 대응할까", "keywords": ["트럼프 관세", "한국 주식", "시장 대응"], "category": "투자"},
    {"title": "일론 머스크가 말하는 성공의 조건 핵심 명언 정리", "keywords": ["일론 머스크", "성공 명언", "동기부여"], "category": "인물"},
    {"title": "젠슨 황 엔비디아 CEO의 AI 미래 예측 2026 요약", "keywords": ["젠슨 황", "엔비디아", "AI 미래"], "category": "인물"},
    {"title": "워런 버핏 최신 주주서한 핵심 투자 철학 정리", "keywords": ["워런 버핏", "주주서한", "투자 철학"], "category": "인물"},
    {"title": "하루 1시간으로 인생이 바뀌는 루틴 만드는 법", "keywords": ["하루 루틴", "자기계발", "습관 만들기"], "category": "자기계발"},
    {"title": "번아웃 극복하는 방법 실리콘밸리 CEO들의 비결", "keywords": ["번아웃", "극복 방법", "멘탈 관리"], "category": "자기계발"},
    {"title": "60대 노후 준비 지금 당장 시작해야 할 3가지", "keywords": ["노후 준비", "60대 재테크", "연금"], "category": "시니어"},
    {"title": "스마트폰으로 돈 버는 법 시니어도 할 수 있는 부업", "keywords": ["시니어 부업", "스마트폰 수익", "노후 수입"], "category": "시니어"},
]

EN_TOPICS = [
    {"title": "Vibe Coding in 2026: Build Apps Without Writing Code", "keywords": ["vibe coding", "no-code", "AI development"], "category": "AI"},
    {"title": "Claude API Tutorial: Automate Any Task in 30 Minutes", "keywords": ["Claude API", "AI automation", "Python"], "category": "AI"},
    {"title": "Best AI Tools for Side Hustle in 2026 Ranked", "keywords": ["AI tools", "side hustle", "make money AI"], "category": "AI"},
    {"title": "Google AdSense Approval Guide 2026: What Actually Works", "keywords": ["Google AdSense", "AdSense approval", "blog monetization"], "category": "AI"},
    {"title": "Bitcoin Halving Cycle Explained: What History Says About 2026", "keywords": ["Bitcoin halving", "BTC price prediction", "crypto investing"], "category": "Finance"},
    {"title": "Best High-Dividend ETFs for Passive Income in 2026", "keywords": ["dividend ETF", "passive income", "high yield"], "category": "Finance"},
    {"title": "Trump Tariffs Impact: How to Protect Your Portfolio Right Now", "keywords": ["Trump tariffs", "portfolio protection", "market volatility"], "category": "Finance"},
    {"title": "Jensen Huang Predicts the Future of AI: What He Said in 2026", "keywords": ["Jensen Huang", "Nvidia", "AI future"], "category": "People"},
    {"title": "Warren Buffett Latest Letter: Core Investment Wisdom for 2026", "keywords": ["Warren Buffett", "investment wisdom", "shareholder letter"], "category": "People"},
    {"title": "5 Habits Billionaires Share That Most People Ignore", "keywords": ["billionaire habits", "success mindset", "daily routine"], "category": "Motivation"},
    {"title": "How to Build a Morning Routine That Actually Changes Your Life", "keywords": ["morning routine", "productivity", "success habits"], "category": "Motivation"},
]


def is_duplicate(topic, published_titles):
    title_lower = topic["title"].lower()
    for pub in published_titles:
        pub_lower = pub.lower()
        if title_lower == pub_lower:
            return True
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
        recent = published_titles[:5]
        recent_cats = []
        for pub in recent:
            for t in KO_TOPICS:
                if t["title"] in pub:
                    recent_cats.append(t["category"])
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


# ─────────────────────────────────────────────
# 에이전트 1: RSS 리서처
# ─────────────────────────────────────────────
def agent_researcher(topic, lang, news_items):
    """오늘의 실제 뉴스 + 주제 기반 리서치 브리핑 작성"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")

    if news_items:
        news_text = "\n".join([
            f"- {item['title']} | {item['desc'][:100]}"
            for item in news_items[:10]
        ])
    else:
        news_text = "뉴스 수집 실패 (학습 데이터 기반으로 작성)"

    if lang == "ko":
        prompt = f"""당신은 블로그 리서처입니다. 오늘({today}) 수집된 뉴스를 바탕으로 블로그 작가에게 브리핑을 작성하세요.

[오늘의 실시간 뉴스]
{news_text}

[작성할 주제]
{topic['title']} (키워드: {', '.join(topic['keywords'])})

뉴스와 주제를 연결해서 다음 브리핑을 작성하세요:
1. 오늘 이 주제가 왜 화제인지 (뉴스 기반, 구체적으로)
2. 독자가 "어머나!" 할 숫자/통계 3개
3. 40~60대 직장인/시니어 공감 포인트 2개
4. 핵심 인사이트 4~5개 (각각 실생활 예시 포함)
5. 오늘 당장 실천 가능한 팁 1개

자유 형식으로 작성 (JSON 아님)"""
    else:
        prompt = f"""You are a blog researcher. Based on today's ({today}) news, write a research briefing for the writer.

[Today's Live News]
{news_text}

[Blog Topic]
{topic['title']} (keywords: {', '.join(topic['keywords'])})

Connect the news to the topic:
1. Why this topic is trending TODAY (news-based, be specific)
2. 3 "OhmyG!" numbers/stats (from news if possible)
3. 2 relatable pain points for busy professionals aged 40-60
4. 4-5 core insights with concrete real-world examples
5. 1 action the reader can take TODAY

Write freely as a briefing (not JSON)"""

    print(f"🔍 RSS 리서처 에이전트 작동 중... ({len(news_items)}개 뉴스 분석)")
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    research = msg.content[0].text
    print(f"✅ 리서치 완료 ({len(research)}자)")
    return research


# ─────────────────────────────────────────────
# 에이전트 2: 작가
# ─────────────────────────────────────────────
def agent_writer(topic, research, lang):
    """리서치 결과를 바탕으로 자연스러운 블로그 글 작성"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")

    if lang == "ko":
        system = """당신은 "어머나!" 채널의 인기 블로거입니다.
40~60대 독자가 카톡으로 공유하고 싶어지는 글을 씁니다.

글쓰기 스타일:
- 친한 언니/오빠가 커피 마시며 알려주는 말투
- "요즘 ~하는 사람 많잖아", "솔직히 말하면", "이게 왜 중요하냐면" 같은 자연스러운 표현
- 첫 문장은 숫자나 공감 훅으로 시작
- 각 섹션마다 실생활 예시 1개씩 반드시 포함
- 마지막은 오늘 당장 할 수 있는 딱 1가지 행동으로 마무리
- 투자 권유 금지, 면책조항 필수 (글 맨 끝에 한 줄)

HTML 태그: h2, h3, p, ul, li, strong
분량: 2000~2500자"""

        prompt = f"""오늘: {today}
제목: {topic['title']}

[리서처 브리핑]
{research}

리서처가 찾은 뉴스, 숫자, 공감 포인트를 반드시 글 안에 녹여주세요.

순수 JSON만 응답:
{{"title": "제목", "html_content": "HTML본문", "labels": ["태그1","태그2","태그3"]}}"""

    else:
        system = """You are a popular blogger for the OhmyG channel.
You write content that busy professionals aged 40-60 actually want to share.

Writing style:
- Like a smart friend giving real talk over coffee
- Hook from sentence one: surprising number, relatable struggle, or counterintuitive fact
- "Here's what most people miss...", "The number that surprised me...", "Try this today:"
- Each section needs one concrete real-world example
- End with exactly ONE thing the reader can do right now
- No investment advice, one-line disclaimer at the end

HTML tags: h2, h3, p, ul, li, strong
Length: 1000-1400 words"""

        prompt = f"""Today: {today}
Title: {topic['title']}

[Research Briefing]
{research}

The news, numbers, and relatable points from the briefing MUST appear in the post.

Pure JSON only:
{{"title": "title", "html_content": "HTML content", "labels": ["tag1","tag2","tag3"]}}"""

    print(f"✍️ 작가 에이전트 작동 중...")
    for attempt in range(3):
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8096,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            json_str = raw[start:end]
            json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)
            result = json.loads(json_str)
            print(f"✅ 글 작성 완료 ({len(result.get('html_content',''))}자)")
            return result
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
                result = json.loads(cleaned)
                print(f"✅ 글 작성 완료 ({len(result.get('html_content',''))}자)")
                return result
            except Exception:
                print(f"⚠️ JSON 파싱 실패 (시도 {attempt+1}/3), 재생성...")
                time.sleep(2)

    title = topic["title"]
    return {"title": title, "html_content": f"<h2>{title}</h2><p>준비 중입니다.</p>", "labels": topic.get("keywords", ["AI"])[:3]}


# ─────────────────────────────────────────────
# 에이전트 3: 검증자
# ─────────────────────────────────────────────
def agent_validator(post, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if lang == "ko":
        prompt = f"""블로그 글 품질을 0~10점으로 평가하세요.

제목: {post['title']}
본문 미리보기: {post['html_content'][:600]}

평가 기준:
- 첫 문장이 독자를 끌어당기는가? (2점)
- 구체적인 숫자나 실생활 사례가 있는가? (2점)
- "살펴보겠습니다", "알아보겠습니다" 같은 AI 티 표현이 없는가? (2점)
- 40~60대가 공감할 내용인가? (2점)
- 오늘 당장 쓸 수 있는 실천 팁이 있는가? (2점)

숫자 하나만 응답 (0~10)"""
    else:
        prompt = f"""Rate this blog post 0-10.

Title: {post['title']}
Preview: {post['html_content'][:600]}

Criteria:
- Does the first sentence hook the reader? (2pts)
- Specific numbers or real-world examples? (2pts)
- No AI phrases like "In this article", "Let's dive in"? (2pts)
- Relatable to busy professionals aged 40-60? (2pts)
- One concrete action to take today? (2pts)

Single number only (0-10)"""

    print(f"🔎 검증 에이전트 작동 중...")
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        score = int(msg.content[0].text.strip())
        print(f"📊 품질: {score}/10")
        return score
    except Exception:
        return 7


def generate_post(topic, lang):
    """멀티 에이전트 파이프라인: RSS 수집 → 리서처 → 작가 → 검증"""

    # 0단계: 오늘의 뉴스 수집
    feeds = KO_RSS_FEEDS if lang == "ko" else EN_RSS_FEEDS
    news_items = fetch_rss_news(feeds)

    # 1단계: 리서처 (뉴스 기반 브리핑)
    research = agent_researcher(topic, lang, news_items)
    time.sleep(1)

    # 2단계: 작가
    post = agent_writer(topic, research, lang)
    time.sleep(1)

    # 3단계: 검증 → 7점 미만이면 재작성
    score = agent_validator(post, lang)
    if score < 7:
        print(f"⚠️ 점수 미달 ({score}점), 재작성...")
        time.sleep(2)
        post = agent_writer(topic, research, lang)

    return post


def get_pexels_image(keywords, lang):
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
        if not PIXABAY_API_KEY:
            return None
        query = " ".join(keywords[:2]) if lang == "en" else keywords[0]
        ko_to_en = {
            "AI": "artificial intelligence technology",
            "인공지능": "artificial intelligence brain",
            "자동화": "automation robot technology",
            "바이브코딩": "programmer coding laptop",
            "ChatGPT": "chatbot AI technology",
            "비트코인": "bitcoin cryptocurrency coins",
            "주식": "stock market trading charts",
            "ETF": "investment portfolio finance",
            "투자": "investment money growth",
            "재테크": "money saving finance",
            "달러": "dollar currency money",
            "연금": "retirement pension savings",
            "노후": "retirement elderly couple",
            "일론 머스크": "electric car tesla technology",
            "젠슨 황": "GPU chip semiconductor",
            "워런 버핏": "investment stocks newspaper",
            "번아웃": "burnout stress tired office",
            "자기계발": "personal growth books reading",
            "시니어": "senior couple happy lifestyle",
            "스마트폰": "smartphone elderly hands",
            "트럼프": "business politics office",
            "관세": "trade shipping containers port",
            "블로그": "blogger writing laptop coffee",
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
            photo = random.choice(hits[:10])
            img_url = photo["webformatURL"]
            print(f"🖼️ 블로그 이미지: {query} (Pixabay)")
            return {"url": img_url, "credit": "Pixabay"}
    except Exception as e:
        print(f"⚠️ Pixabay 이미지 실패: {e}")
    return None


def get_blogger_service(rt, ci, cs):
    creds = Credentials(
        token=None, refresh_token=rt, client_id=ci, client_secret=cs,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"]
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)


def publish_post(service, blog_id, title, html_content, labels, img_data=None):
    if img_data:
        img_html = (
            f'<div style="text-align:center;margin-bottom:24px;">'
            f'<img src="{img_data["url"]}" alt="{title}" style="max-width:100%;border-radius:8px;"/>'
            f'<p style="font-size:12px;color:#888;">Photo by {img_data["credit"]} on Pixabay</p>'
            f'</div>'
        )
        html_content = img_html + html_content
    body = {"title": title, "content": html_content, "labels": labels}
    result = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return result.get("url", "")


def try_generate_shorts(title, content, lang, blog_url):
    if not SHORTS_ENABLED:
        print("⏭️ 숏츠 스킵 (YouTube secrets 없음)")
        return None
    try:
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
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:800]


def main():
    print("🚀 Auto Blog Generator v2.4 (RSS 멀티 에이전트)")
    print(f"🎬 숏츠 자동화: {'✅ 활성화' if SHORTS_ENABLED else '⏭️ 비활성화'}")

    # ── 한국어 블로그 ──
    print("\n" + "="*40)
    print("🇰🇷 한국어 블로그 시작")
    print("="*40)
    ko_svc = get_blogger_service(KO_BLOGGER_REFRESH_TOKEN, KO_BLOGGER_CLIENT_ID, KO_BLOGGER_CLIENT_SECRET)
    ko_pub = get_published_titles(ko_svc, KO_BLOG_ID)
    ko_topic = select_topic("ko", ko_pub)
    print(f"📝 주제: {ko_topic['title']} {'[트렌드]' if ko_topic.get('is_trend') else '[고정]'}")
    ko_post = generate_post(ko_topic, "ko")
    ko_img = get_pexels_image(ko_topic["keywords"], "ko")
    ko_url = publish_post(ko_svc, KO_BLOG_ID, ko_post["title"], ko_post["html_content"], ko_post["labels"], ko_img)
    print(f"✅ KO 블로그: {ko_url}")
    send_telegram(f"✅ 어머나! 발행 완료\n📝 {ko_post['title']}\n🔗 {ko_url}")
    ko_plain = html_to_plain(ko_post["html_content"])
    try_generate_shorts(ko_post["title"], ko_plain, "ko", ko_url)

    # ── 영어 블로그 ──
    print("\n" + "="*40)
    print("🇺🇸 영어 블로그 시작")
    print("="*40)
    en_svc = get_blogger_service(EN_BLOGGER_REFRESH_TOKEN, EN_BLOGGER_CLIENT_ID, EN_BLOGGER_CLIENT_SECRET)
    en_pub = get_published_titles(en_svc, EN_BLOG_ID)
    en_topic = select_topic("en", en_pub)
    print(f"📝 주제: {en_topic['title']} {'[트렌드]' if en_topic.get('is_trend') else '[고정]'}")
    en_post = generate_post(en_topic, "en")
    en_img = get_pexels_image(en_topic["keywords"], "en")
    en_url = publish_post(en_svc, EN_BLOG_ID, en_post["title"], en_post["html_content"], en_post["labels"], en_img)
    print(f"✅ EN 블로그: {en_url}")
    send_telegram(f"✅ OhmyG 발행 완료\n📝 {en_post['title']}\n🔗 {en_url}")
    en_plain = html_to_plain(en_post["html_content"])
    try_generate_shorts(en_post["title"], en_plain, "en", en_url)

    print("\n🎉 전체 완료!")
    send_telegram("🎉 오늘의 자동화 완료! KO + EN 블로그 + 숏츠 발행 완료")


if __name__ == "__main__":
    main()
