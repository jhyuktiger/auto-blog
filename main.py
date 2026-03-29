"""
Auto Blog Generator v2
Claude API → Google Blogger API (OAuth)
트렌드 기반 주제 자동 선정 + Evaluator 품질 체크 + 매일 한/영 자동 발행
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

# ── Config ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

KO_BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
KO_BLOGGER_CLIENT_ID = os.environ["BLOGGER_CLIENT_ID"]
KO_BLOGGER_CLIENT_SECRET = os.environ["BLOGGER_CLIENT_SECRET"]

EN_BLOGGER_REFRESH_TOKEN = os.environ["EN_BLOGGER_REFRESH_TOKEN"]
EN_BLOGGER_CLIENT_ID = os.environ["EN_BLOGGER_CLIENT_ID"]
EN_BLOGGER_CLIENT_SECRET = os.environ["EN_BLOGGER_CLIENT_SECRET"]

KO_BLOG_ID = os.environ["KO_BLOG_ID"]
EN_BLOG_ID = os.environ["EN_BLOG_ID"]

# ── 트렌드 수집 ─────────────────────────────────────────
def get_trending_topics_ko():
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='ko-KR', tz=540)
        trending = pytrends.trending_searches(pn='south_korea')
        topics = trending[0].tolist()[:5]
        print(f"🔥 KO 트렌드: {topics}")
        return topics
    except Exception as e:
        print(f"⚠️ 트렌드 수집 실패: {e}")
        return None

def get_trending_topics_en():
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-US', tz=0)
        trending = pytrends.trending_searches(pn='united_states')
        topics = trending[0].tolist()[:5]
        print(f"🔥 EN 트렌드: {topics}")
        return topics
    except Exception as e:
        print(f"⚠️ 트렌드 수집 실패: {e}")
        return None

# ── Fallback 주제 풀 ────────────────────────────────────
KO_TOPICS = [
    {"title": "Claude API로 자동화 도구 만드는 법 (초보자 완전 가이드)", "keywords": ["Claude API", "AI 자동화", "바이브코딩"], "category": "AI"},
    {"title": "바이브코딩이란? 2026년 개발자 없이 앱 만드는 방법", "keywords": ["바이브코딩", "Cursor", "bolt.new"], "category": "AI"},
    {"title": "ChatGPT vs Claude 실전 비교 – 어떤 AI가 더 유용한가", "keywords": ["ChatGPT", "Claude", "AI 비교"], "category": "AI"},
    {"title": "Cursor AI로 코딩 10배 빠르게 하는 실전 팁", "keywords": ["Cursor AI", "AI 코딩", "개발 생산성"], "category": "AI"},
    {"title": "AI로 월 100만원 버는 현실적인 방법 5가지", "keywords": ["AI 부업", "AI 수익화", "AI 활용"], "category": "AI"},
    {"title": "n8n 자동화로 반복 업무 없애는 방법 (무료)", "keywords": ["n8n", "업무 자동화", "노코드"], "category": "AI"},
    {"title": "비트코인 2026 전망 – 반감기 이후 실제로 어떻게 될까", "keywords": ["비트코인 전망", "BTC 2026", "암호화폐"], "category": "투자"},
    {"title": "달러 ETF로 환율 헤지하는 방법 완전 정리", "keywords": ["달러 ETF", "환율 헤지", "달러 투자"], "category": "투자"},
    {"title": "미국 주식 배당금 세금 완벽 정리 (2026 기준)", "keywords": ["미국 주식 세금", "배당 세금", "해외 주식"], "category": "투자"},
    {"title": "S&P500 ETF 매달 적립식 투자 10년 시뮬레이션", "keywords": ["S&P500", "ETF 투자", "적립식"], "category": "투자"},
    {"title": "코인 선물거래 리스크 관리 – 청산 당하지 않는 법", "keywords": ["선물거래", "코인 리스크", "청산 방지"], "category": "투자"},
    {"title": "ISA 계좌 완전 정복 – 세금 혜택 최대로 쓰는 방법", "keywords": ["ISA 계좌", "절세", "재테크"], "category": "투자"},
]

EN_TOPICS = [
    {"title": "Vibe Coding in 2026: Build Apps Without Writing Code", "keywords": ["vibe coding", "no-code", "AI development"], "category": "AI"},
    {"title": "Claude API Tutorial: Automate Any Task in 30 Minutes", "keywords": ["Claude API", "AI automation", "Python"], "category": "AI"},
    {"title": "Best AI Tools for Side Hustle in 2026 (Ranked)", "keywords": ["AI tools", "side hustle", "make money AI"], "category": "AI"},
    {"title": "Cursor vs GitHub Copilot: Which AI Coding Tool Wins in 2026?", "keywords": ["Cursor AI", "GitHub Copilot", "AI coding"], "category": "AI"},
    {"title": "How to Make $1000/Month Using Claude and n8n Automation", "keywords": ["Claude automation", "n8n", "passive income AI"], "category": "AI"},
    {"title": "Build a Crypto Dashboard with AI in One Day (No Code)", "keywords": ["crypto dashboard", "vibe coding", "bolt.new"], "category": "AI"},
    {"title": "Bitcoin Halving Cycle Explained: What History Says About 2026", "keywords": ["Bitcoin halving", "BTC price prediction", "crypto investing"], "category": "Finance"},
    {"title": "S&P 500 vs Bitcoin: 10-Year Return Comparison", "keywords": ["S&P 500", "Bitcoin investment", "portfolio"], "category": "Finance"},
    {"title": "How to Invest in US Stocks from Korea (Step-by-Step)", "keywords": ["invest US stocks Korea", "overseas investing", "ETF"], "category": "Finance"},
    {"title": "Dollar Cost Averaging Bitcoin: 3-Year Simulation Results", "keywords": ["DCA Bitcoin", "crypto strategy", "dollar cost averaging"], "category": "Finance"},
    {"title": "Best High-Dividend ETFs for Passive Income in 2026", "keywords": ["dividend ETF", "passive income", "high yield"], "category": "Finance"},
    {"title": "Crypto Fear & Greed Index: How to Use It to Time the Market", "keywords": ["fear greed index", "crypto timing", "market sentiment"], "category": "Finance"},
]

# ── 주제 선정 ───────────────────────────────────────────
def select_topic(lang: str) -> dict:
    today_seed = int(datetime.date.today().strftime("%Y%m%d"))
    random.seed(today_seed)

    if lang == "ko":
        trends = get_trending_topics_ko()
        if trends:
            keyword = random.choice(trends)
            return {
                "title": f"{keyword} 완전 정리 – 2026년 최신 가이드",
                "keywords": [keyword, "트렌드", "최신"],
                "category": "트렌드",
                "is_trend": True
            }
        return random.choice(KO_TOPICS)
    else:
        trends = get_trending_topics_en()
        if trends:
            keyword = random.choice(trends)
            return {
                "title": f"{keyword}: Complete Guide for 2026",
                "keywords": [keyword, "trending", "guide 2026"],
                "category": "Trending",
                "is_trend": True
            }
        return random.choice(EN_TOPICS)

# ── Claude API 글 생성 ──────────────────────────────────
def generate_post(topic: dict, lang: str) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")
    is_trend = topic.get("is_trend", False)

    if lang == "ko":
        system = """당신은 한국의 전문 블로거입니다.
애드센스 수익을 극대화하는 SEO 최적화 블로그 글을 작성합니다.
규칙:
- HTML 형식으로 작성 (h2, h3, p, ul, li, strong 태그 사용)
- 2000~3000자 분량
- 키워드를 자연스럽게 3~5회 반복
- 서론 → 본론(3~5개 섹션) → 결론 구조
- 실용적이고 구체적인 내용
- 과장 표현, 투자 권유 금지
- 투자 주제면 마지막에 면책조항 추가
- 절대 허위 정보 작성 금지"""

        trend_note = "오늘 한국에서 실제로 트렌딩 중인 주제입니다. 시의성 있게 작성해주세요." if is_trend else ""

        user_prompt = f"""오늘 날짜: {today}
{trend_note}

제목: {topic['title']}
키워드: {', '.join(topic['keywords'])}
카테고리: {topic['category']}

위 주제로 SEO 최적화된 블로그 글을 HTML 형식으로 작성해주세요.
JSON으로 응답하세요 (마크다운 코드블록 없이 순수 JSON만):
{{
  "title": "최종 제목",
  "html_content": "HTML 본문",
  "labels": ["태그1", "태그2", "태그3"]
}}"""

    else:
        system = """You are a professional blogger writing high-quality SEO content.
Rules:
- Write in HTML format (use h2, h3, p, ul, li, strong tags)
- 1000-1500 words
- Naturally include keywords 3-5 times
- Structure: intro → body (3-5 sections) → conclusion
- Practical, specific, actionable content
- No investment advice or guarantees
- Add disclaimer for finance topics
- Never write false information"""

        trend_note = "This is actually trending in the US right now. Make it timely." if is_trend else ""

        user_prompt = f"""Today: {today}
{trend_note}

Title: {topic['title']}
Keywords: {', '.join(topic['keywords'])}
Category: {topic['category']}

Write an SEO-optimized blog post in HTML format.
Respond in JSON only (no markdown code blocks, pure JSON):
{{
  "title": "Final Title",
  "html_content": "HTML body content",
  "labels": ["tag1", "tag2", "tag3"]
}}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8096,
        system=system,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw = message.content[0].text
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])

# ── Evaluator 에이전트 ──────────────────────────────────
def evaluate_post(post: dict, lang: str) -> int:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if lang == "ko":
        prompt = f"""다음 블로그 글 품질을 0~10점으로 평가하세요.
기준: SEO 최적화, 가독성, 정보 유용성, 구조, 분량 적절성
제목: {post['title']}
본문 미리보기: {post['html_content'][:500]}
숫자만 응답 (예: 8)"""
    else:
        prompt = f"""Rate this blog post 0-10.
Criteria: SEO, readability, usefulness, structure, length
Title: {post['title']}
Preview: {post['html_content'][:500]}
Reply with number only (e.g.: 8)"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        score = int(message.content[0].text.strip())
        print(f"📊 품질 점수: {score}/10")
        return score
    except:
        return 7

# ── Google Blogger API ──────────────────────────────────
def get_blogger_service(refresh_token, client_id, client_secret):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"]
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)

def publish_post(service, blog_id, title, html_content, labels):
    leaderview_banner = """
<!-- LeaderView AD (reserved) -->
<!-- <div style="margin:24px 0;text-align:center;">
  <a href="https://leaderview.app" target="_blank">
    <img src="https://leaderview.app/banner.png" alt="LeaderView" style="max-width:728px;width:100%;border-radius:8px;">
  </a>
</div> -->
"""
    body = {
        "title": title,
        "content": leaderview_banner + html_content,
        "labels": labels,
    }
    result = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return result.get("url", "")

# ── 메인 ────────────────────────────────────────────────
def main():
    print("🚀 Auto Blog Generator v2 시작")

    # 한국어
    ko_service = get_blogger_service(KO_BLOGGER_REFRESH_TOKEN, KO_BLOGGER_CLIENT_ID, KO_BLOGGER_CLIENT_SECRET)
    ko_topic = select_topic("ko")
    print(f"📝 KO: {ko_topic['title']} {'[트렌드]' if ko_topic.get('is_trend') else '[고정]'}")
    ko_post = generate_post(ko_topic, "ko")
    if evaluate_post(ko_post, "ko") < 7:
        print("⚠️ 품질 미달 → 재생성")
        time.sleep(2)
        ko_post = generate_post(ko_topic, "ko")
    ko_url = publish_post(ko_service, KO_BLOG_ID, ko_post["title"], ko_post["html_content"], ko_post["labels"])
    print(f"✅ KO 발행: {ko_url}")

    # 영어
    en_service = get_blogger_service(EN_BLOGGER_REFRESH_TOKEN, EN_BLOGGER_CLIENT_ID, EN_BLOGGER_CLIENT_SECRET)
    en_topic = select_topic("en")
    print(f"📝 EN: {en_topic['title']} {'[트렌드]' if en_topic.get('is_trend') else '[고정]'}")
    en_post = generate_post(en_topic, "en")
    if evaluate_post(en_post, "en") < 7:
        print("⚠️ 품질 미달 → 재생성")
        time.sleep(2)
        en_post = generate_post(en_topic, "en")
    en_url = publish_post(en_service, EN_BLOG_ID, en_post["title"], en_post["html_content"], en_post["labels"])
    print(f"✅ EN 발행: {en_url}")

    print("🎉 완료!")

if __name__ == "__main__":
    main()
