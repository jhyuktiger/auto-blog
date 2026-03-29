"""
Auto Blog Generator v2.1
트렌드 기반 + Evaluator + 중복 방지
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
    {"title": "Cursor AI로 코딩 10배 빠르게 하는 실전 팁", "keywords": ["Cursor AI", "AI 코딩", "개발 생산성"], "category": "AI"},
    {"title": "AI로 월 100만원 버는 현실적인 방법 5가지", "keywords": ["AI 부업", "AI 수익화", "AI 활용"], "category": "AI"},
    {"title": "n8n 자동화로 반복 업무 없애는 방법 무료", "keywords": ["n8n", "업무 자동화", "노코드"], "category": "AI"},
    {"title": "비트코인 2026 전망 반감기 이후 실제로 어떻게 될까", "keywords": ["비트코인 전망", "BTC 2026", "암호화폐"], "category": "투자"},
    {"title": "달러 ETF로 환율 헤지하는 방법 완전 정리", "keywords": ["달러 ETF", "환율 헤지", "달러 투자"], "category": "투자"},
    {"title": "미국 주식 배당금 세금 완벽 정리 2026 기준", "keywords": ["미국 주식 세금", "배당 세금", "해외 주식"], "category": "투자"},
    {"title": "S&P500 ETF 매달 적립식 투자 10년 시뮬레이션", "keywords": ["S&P500", "ETF 투자", "적립식"], "category": "투자"},
    {"title": "코인 선물거래 리스크 관리 청산 당하지 않는 법", "keywords": ["선물거래", "코인 리스크", "청산 방지"], "category": "투자"},
    {"title": "ISA 계좌 완전 정복 세금 혜택 최대로 쓰는 방법", "keywords": ["ISA 계좌", "절세", "재테크"], "category": "투자"},
    {"title": "구글 애드센스 승인 받는 방법 2026년 최신 가이드", "keywords": ["애드센스 승인", "구글 애드센스", "블로그 수익"], "category": "AI"},
    {"title": "GitHub Actions로 업무 자동화하는 방법 완전 정리", "keywords": ["GitHub Actions", "CI/CD", "자동화"], "category": "AI"},
    {"title": "파이썬으로 텔레그램 봇 만드는 법 30분 완성", "keywords": ["텔레그램 봇", "파이썬", "자동화"], "category": "AI"},
    {"title": "ETF vs 개별주식 초보 투자자를 위한 완전 비교", "keywords": ["ETF", "개별주식", "투자 초보"], "category": "투자"},
    {"title": "연금저축펀드 완전 정복 세액공제 최대로 받는 법", "keywords": ["연금저축", "세액공제", "노후준비"], "category": "투자"},
    {"title": "AI 이미지 생성 도구 비교 Midjourney vs DALL-E vs Gemini", "keywords": ["AI 이미지", "Midjourney", "이미지 생성"], "category": "AI"},
]

EN_TOPICS = [
    {"title": "Vibe Coding in 2026: Build Apps Without Writing Code", "keywords": ["vibe coding", "no-code", "AI development"], "category": "AI"},
    {"title": "Claude API Tutorial: Automate Any Task in 30 Minutes", "keywords": ["Claude API", "AI automation", "Python"], "category": "AI"},
    {"title": "Best AI Tools for Side Hustle in 2026 Ranked", "keywords": ["AI tools", "side hustle", "make money AI"], "category": "AI"},
    {"title": "Cursor vs GitHub Copilot: Which AI Coding Tool Wins in 2026", "keywords": ["Cursor AI", "GitHub Copilot", "AI coding"], "category": "AI"},
    {"title": "How to Make 1000 Per Month Using Claude and n8n Automation", "keywords": ["Claude automation", "n8n", "passive income AI"], "category": "AI"},
    {"title": "Build a Crypto Dashboard with AI in One Day No Code", "keywords": ["crypto dashboard", "vibe coding", "bolt.new"], "category": "AI"},
    {"title": "Bitcoin Halving Cycle Explained: What History Says About 2026", "keywords": ["Bitcoin halving", "BTC price prediction", "crypto investing"], "category": "Finance"},
    {"title": "S&P 500 vs Bitcoin: 10-Year Return Comparison", "keywords": ["S&P 500", "Bitcoin investment", "portfolio"], "category": "Finance"},
    {"title": "How to Invest in US Stocks from Korea Step-by-Step", "keywords": ["invest US stocks Korea", "overseas investing", "ETF"], "category": "Finance"},
    {"title": "Dollar Cost Averaging Bitcoin: 3-Year Simulation Results", "keywords": ["DCA Bitcoin", "crypto strategy", "dollar cost averaging"], "category": "Finance"},
    {"title": "Best High-Dividend ETFs for Passive Income in 2026", "keywords": ["dividend ETF", "passive income", "high yield"], "category": "Finance"},
    {"title": "Crypto Fear and Greed Index: How to Use It to Time the Market", "keywords": ["fear greed index", "crypto timing", "market sentiment"], "category": "Finance"},
    {"title": "Google AdSense Approval Guide 2026: What Actually Works", "keywords": ["Google AdSense", "AdSense approval", "blog monetization"], "category": "AI"},
    {"title": "How to Use GitHub Actions for Complete Workflow Automation", "keywords": ["GitHub Actions", "automation", "CI/CD"], "category": "AI"},
    {"title": "Best Passive Income Ideas Using AI Tools in 2026", "keywords": ["passive income", "AI tools", "make money online"], "category": "Finance"},
    {"title": "Index Fund vs ETF: Which Is Better for Long-Term Investing", "keywords": ["index fund", "ETF investing", "long term"], "category": "Finance"},
    {"title": "AI Image Generation Showdown: Midjourney vs DALL-E vs Gemini", "keywords": ["AI image generation", "Midjourney", "DALL-E"], "category": "AI"},
    {"title": "How to Build a Telegram Bot with Python in 30 Minutes", "keywords": ["Telegram bot", "Python", "automation"], "category": "AI"},
]

def select_topic(lang, published_titles):
    if lang == "ko":
        trends = get_trending_ko()
        if trends:
            for kw in trends:
                t = f"{kw} 완전 정리 2026년 최신 가이드"
                if t not in published_titles:
                    return {"title": t, "keywords": [kw, "트렌드", "최신"], "category": "트렌드", "is_trend": True}
        pool = KO_TOPICS[:]
        random.shuffle(pool)
        for topic in pool:
            if topic["title"] not in published_titles:
                return topic
    else:
        trends = get_trending_en()
        if trends:
            for kw in trends:
                t = f"{kw}: Complete Guide for 2026"
                if t not in published_titles:
                    return {"title": t, "keywords": [kw, "trending", "2026"], "category": "Trending", "is_trend": True}
        pool = EN_TOPICS[:]
        random.shuffle(pool)
        for topic in pool:
            if topic["title"] not in published_titles:
                return topic
    today = datetime.date.today().strftime("%Y-%m-%d")
    base = KO_TOPICS[0] if lang == "ko" else EN_TOPICS[0]
    return {"title": f"{base['title']} ({today})", "keywords": base["keywords"], "category": base["category"], "is_trend": False}

def generate_post(topic, lang):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")
    is_trend = topic.get("is_trend", False)
    if lang == "ko":
        system = "당신은 한국의 전문 블로거입니다. SEO 최적화 HTML 블로그 글을 작성합니다. 2000~3000자, h2/h3/p/ul/li 태그 사용, 투자 권유 금지, 허위 정보 금지."
        prompt = f"오늘: {today}\n{'[트렌딩 주제]' if is_trend else ''}\n제목: {topic['title']}\n키워드: {', '.join(topic['keywords'])}\n\n순수 JSON만 응답:\n{{\"title\": \"제목\", \"html_content\": \"HTML본문\", \"labels\": [\"태그1\",\"태그2\",\"태그3\"]}}"
    else:
        system = "You are a professional blogger. Write SEO-optimized HTML blog posts. 1000-1500 words, use h2/h3/p/ul/li tags, no investment advice, no false info."
        prompt = f"Today: {today}\n{'[Trending topic]' if is_trend else ''}\nTitle: {topic['title']}\nKeywords: {', '.join(topic['keywords'])}\n\nPure JSON only:\n{{\"title\": \"title\", \"html_content\": \"HTML content\", \"labels\": [\"tag1\",\"tag2\",\"tag3\"]}}"
    msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=8096, system=system, messages=[{"role": "user", "content": prompt}])
    raw = msg.content[0].text
    return json.loads(raw[raw.find("{"):raw.rfind("}")+1])

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

def publish_post(service, blog_id, title, html_content, labels):
    body = {"title": title, "content": html_content, "labels": labels}
    result = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return result.get("url", "")

def main():
    print("🚀 Auto Blog Generator v2.1")
    ko_svc = get_blogger_service(KO_BLOGGER_REFRESH_TOKEN, KO_BLOGGER_CLIENT_ID, KO_BLOGGER_CLIENT_SECRET)
    ko_pub = get_published_titles(ko_svc, KO_BLOG_ID)
    ko_topic = select_topic("ko", ko_pub)
    print(f"📝 KO: {ko_topic['title']} {'[트렌드]' if ko_topic.get('is_trend') else '[고정]'}")
    ko_post = generate_post(ko_topic, "ko")
    if evaluate_post(ko_post, "ko") < 7:
        print("⚠️ 재생성")
        time.sleep(2)
        ko_post = generate_post(ko_topic, "ko")
    ko_url = publish_post(ko_svc, KO_BLOG_ID, ko_post["title"], ko_post["html_content"], ko_post["labels"])
    print(f"✅ KO: {ko_url}")

    en_svc = get_blogger_service(EN_BLOGGER_REFRESH_TOKEN, EN_BLOGGER_CLIENT_ID, EN_BLOGGER_CLIENT_SECRET)
    en_pub = get_published_titles(en_svc, EN_BLOG_ID)
    en_topic = select_topic("en", en_pub)
    print(f"📝 EN: {en_topic['title']} {'[트렌드]' if en_topic.get('is_trend') else '[고정]'}")
    en_post = generate_post(en_topic, "en")
    if evaluate_post(en_post, "en") < 7:
        print("⚠️ 재생성")
        time.sleep(2)
        en_post = generate_post(en_topic, "en")
    en_url = publish_post(en_svc, EN_BLOG_ID, en_post["title"], en_post["html_content"], en_post["labels"])
    print(f"✅ EN: {en_url}")
    print("🎉 완료!")

if __name__ == "__main__":
    main()
