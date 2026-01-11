#!/usr/bin/env python3
"""
StockPulse - Portfolio News Alert
Modern, Sporty Dashboard for Portfolio News Monitoring
Version 2.1 - With Market Pulse & Enriched Portfolio Cards
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import plotly.express as px
import plotly.graph_objects as go
import requests
import time

from models.database import (
    init_db, get_db, User, UserHolding, NewsArticle, 
    NewsAnalysis, Notification
)
from services.fmp_client import FMPClient
from services.ai_analyzer import AIAnalyzer
from main import PortfolioNewsMonitor
from config.settings import settings

# ===========================
# AUTO-CREATE DEMO USER (for cloud deployment)
# ===========================
def ensure_demo_user():
    """Create demo user and portfolio if they don't exist"""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.email == "demo@example.com").first()
        
        if not user:
            # Create demo user
            user = User(
                email="demo@example.com",
                name="Demo User",
                active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Add some default stocks
            default_stocks = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
            for symbol in default_stocks:
                holding = UserHolding(
                    user_id=user.id,
                    symbol=symbol,
                    quantity=0,
                    average_cost=0,
                    asset_type="stock"
                )
                db.add(holding)
            db.commit()
            print("✅ Demo user created with default portfolio")
        
        db.close()
    except Exception as e:
        print(f"Error creating demo user: {e}")

# Run on startup
ensure_demo_user()

# Page Configuration
st.set_page_config(
    page_title="StockPulse | Portfolio Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===========================
# CACHING FUNCTIONS
# ===========================

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_market_indices():
    """Fetch major market indices with caching"""
    indices = {}
    
    # Major indices to track
    index_symbols = {
        '%5EGSPC': {'name': 'S&P 500', 'emoji': '📈'},
        '%5EIXIC': {'name': 'NASDAQ', 'emoji': '💻'},
        '%5EDJI': {'name': 'DOW', 'emoji': '🏭'},
        '%5EVIX': {'name': 'VIX', 'emoji': '😰'}
    }
    
    for symbol, info in index_symbols.items():
        try:
            url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
            params = {'apikey': settings.fmp_api_key}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data and len(data) > 0:
                quote = data[0]
                indices[symbol] = {
                    'name': info['name'],
                    'emoji': info['emoji'],
                    'price': quote.get('price', 0),
                    'change': quote.get('change', 0),
                    'change_percent': quote.get('changesPercentage', 0)
                }
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            continue
    
    return indices

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_stock_quote_cached(symbol: str):
    """Get stock quote with caching"""
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
        params = {'apikey': settings.fmp_api_key}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data[0] if data and len(data) > 0 else {}
    except:
        return {}

@st.cache_data(ttl=86400)  # Cache for 24 hours
def get_company_profile_cached(symbol: str):
    """Get company profile with caching (name, logo, sector)"""
    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        params = {'apikey': settings.fmp_api_key}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data and len(data) > 0 and isinstance(data, list):
            company = data[0]
            return {
                'name': company.get('companyName') or symbol,
                'logo': company.get('image') or '',
                'sector': company.get('sector') or '',
                'industry': company.get('industry') or '',
                'exchange': company.get('exchangeShortName') or ''
            }
    except Exception as e:
        print(f"Error fetching profile for {symbol}: {e}")
    
    # Return defaults with symbol as name
    return {
        'name': symbol,
        'logo': '',
        'sector': '',
        'industry': '',
        'exchange': ''
    }


def get_broker_rating_alerts_impl(portfolio_symbols: list, debug: bool = False):
    """
    Fetch broker rating changes (upgrades AND downgrades) for portfolio stocks
    
    Uses MULTIPLE sources to ensure we never miss important alerts:
    1. FMP API (upgrades-downgrades endpoint) 
    2. FMP Stock News (scan headlines for upgrade/downgrade keywords)
    3. FMP Analyst Stock Recommendations (another endpoint)
    
    This ensures that even if one source is delayed, we catch alerts from another.
    """
    if not portfolio_symbols:
        return []
    
    all_alerts = []
    seen_alerts = set()  # Prevent duplicates
    cutoff_hours = 72  # Look back 3 days
    cutoff_time = datetime.utcnow() - timedelta(hours=cutoff_hours)
    
    if debug:
        print(f"[DEBUG] Checking symbols: {portfolio_symbols}")
        print(f"[DEBUG] Cutoff time: {cutoff_time}")
        
    # Check for AI Service availability
    try:
        from services.ai_analyzer import AIAnalyzer
        ai_analyzer = AIAnalyzer()
        has_ai = True
    except:
        has_ai = False
        if debug: print("[DEBUG] AI Service not available")
    
    # Premium brokers (their ratings carry more weight)
    premium_brokers = [
        'Goldman Sachs', 'Morgan Stanley', 'JP Morgan', 'JPMorgan',
        'Bank of America', 'BofA', 'Barclays', 'Deutsche Bank', 
        'Credit Suisse', 'UBS', 'Citi', 'Citigroup', 'Wells Fargo', 
        'Jefferies', 'Evercore', 'Bernstein', 'RBC Capital', 'HSBC', 
        'Piper Sandler', 'Wedbush', 'Needham', 'Oppenheimer', 'Stifel',
        'Raymond James', 'KeyBanc', 'Truist', 'BTIG', 'Cowen', 'Wolfe'
    ]
    
    # Keywords to detect upgrades/downgrades in news headlines
    upgrade_keywords = ['upgrade', 'upgraded', 'upgrades', 'raises to buy', 
                        'raises to outperform', 'raises to overweight', 'bullish',
                        'lifts to buy', 'lifts to outperform', 'boosts']
    downgrade_keywords = ['downgrade', 'downgraded', 'downgrades', 'cuts to sell',
                          'cuts to underperform', 'cuts to underweight', 'cuts to neutral',
                          'cuts to equal-weight', 'cuts to hold', 'bearish', 'lowers to']
    
    for symbol in portfolio_symbols:
        if debug:
            print(f"[DEBUG] Processing {symbol}...")
        
        # =====================================================
        # SOURCE 1: FMP Upgrades/Downgrades API (primary source)
        # =====================================================
        try:
            url = f"https://financialmodelingprep.com/api/v4/upgrades-downgrades"
            params = {'symbol': symbol, 'apikey': settings.fmp_api_key}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if debug:
                print(f"[DEBUG] FMP Upgrades API returned {len(data) if isinstance(data, list) else type(data)} for {symbol}")
            
            if isinstance(data, list):
                for rating in data[:15]:
                    try:
                        pub_date_str = rating.get('publishedDate', '')
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time:
                            broker = rating.get('analystCompany', 'Unknown')
                            action = rating.get('action', '').lower()
                            
                            alert_key = f"{symbol}_{broker}_{pub_date.strftime('%Y%m%d')}"
                            if alert_key in seen_alerts:
                                continue
                            seen_alerts.add(alert_key)
                            
                            if 'upgrade' in action:
                                action_type = 'upgrade'
                            elif 'downgrade' in action:
                                action_type = 'downgrade'
                            elif 'initiat' in action:
                                action_type = 'initiated'
                            else:
                                action_type = 'reiterated'
                            
                            is_premium = any(pb.lower() in broker.lower() for pb in premium_brokers)
                            
                            alert = {
                                'symbol': symbol,
                                'broker': broker,
                                'action_type': action_type,
                                'new_rating': rating.get('newGrade', 'N/A'),
                                'previous_rating': rating.get('previousGrade', 'N/A'),
                                'date': pub_date.strftime('%Y-%m-%d'),
                                'timestamp': pub_date,
                                'is_premium_broker': is_premium,
                                'score': (15 if is_premium else 8) + (5 if action_type == 'downgrade' else 0),
                                'source': 'FMP API'
                            }
                            all_alerts.append(alert)
                            if debug:
                                print(f"[DEBUG] ✅ Found from API: {broker} {action_type} {symbol}")
                    except Exception as e:
                        if debug:
                            print(f"[DEBUG] Error parsing rating: {e}")
                        continue
        except Exception as e:
            if debug:
                print(f"[DEBUG] FMP upgrades API error for {symbol}: {e}")
        
        # =====================================================
        # SOURCE 2: FMP Grade endpoint (different API)
        # =====================================================
        try:
            url = f"https://financialmodelingprep.com/api/v3/grade/{symbol}"
            params = {'apikey': settings.fmp_api_key}
            response = requests.get(url, params=params, timeout=10)
            grade_data = response.json()
            
            if debug:
                print(f"[DEBUG] FMP Grade API returned {len(grade_data) if isinstance(grade_data, list) else type(grade_data)} for {symbol}")
            
            if isinstance(grade_data, list):
                for grade in grade_data[:15]:
                    try:
                        pub_date_str = grade.get('date', '')
                        # Grade API uses different date format
                        try:
                            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
                        except:
                            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time.replace(hour=0, minute=0, second=0):
                            broker = grade.get('gradingCompany', 'Unknown')
                            new_grade = grade.get('newGrade', 'N/A')
                            prev_grade = grade.get('previousGrade', 'N/A')
                            
                            alert_key = f"{symbol}_{broker}_{pub_date.strftime('%Y%m%d')}"
                            if alert_key in seen_alerts:
                                continue
                            seen_alerts.add(alert_key)
                            
                            # Determine action from grades
                            bullish = ['buy', 'outperform', 'overweight', 'strong buy', 'positive']
                            bearish = ['sell', 'underperform', 'underweight', 'negative', 'reduce']
                            neutral = ['hold', 'neutral', 'equal-weight', 'market perform']
                            
                            new_score = 2 if any(b in new_grade.lower() for b in bullish) else (0 if any(b in new_grade.lower() for b in bearish) else 1)
                            prev_score = 2 if any(b in prev_grade.lower() for b in bullish) else (0 if any(b in prev_grade.lower() for b in bearish) else 1)
                            
                            if new_score > prev_score:
                                action_type = 'upgrade'
                            elif new_score < prev_score:
                                action_type = 'downgrade'
                            else:
                                action_type = 'reiterated'
                            
                            is_premium = any(pb.lower() in broker.lower() for pb in premium_brokers)
                            
                            alert = {
                                'symbol': symbol,
                                'broker': broker,
                                'action_type': action_type,
                                'new_rating': new_grade,
                                'previous_rating': prev_grade,
                                'date': pub_date.strftime('%Y-%m-%d'),
                                'timestamp': pub_date,
                                'is_premium_broker': is_premium,
                                'score': (14 if is_premium else 7) + (5 if action_type == 'downgrade' else 0),
                                'source': 'Grade API'
                            }
                            all_alerts.append(alert)
                            if debug:
                                print(f"[DEBUG] ✅ Found from Grade API: {broker} {action_type} {symbol}")
                    except Exception as e:
                        if debug:
                            print(f"[DEBUG] Error parsing grade: {e}")
                        continue
        except Exception as e:
            if debug:
                print(f"[DEBUG] FMP grade API error for {symbol}: {e}")
        
        # =====================================================
        # SOURCE 3: FMP Stock News (scan headlines for broker actions)
        # =====================================================
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_news"
            params = {'tickers': symbol, 'limit': 50, 'apikey': settings.fmp_api_key}
            response = requests.get(url, params=params, timeout=10)
            news_data = response.json()
            
            if debug:
                print(f"[DEBUG] FMP News returned {len(news_data) if isinstance(news_data, list) else type(news_data)} articles for {symbol}")
            
            if isinstance(news_data, list):
                for article in news_data:
                    try:
                        title = article.get('title', '').lower()
                        text = article.get('text', '').lower()
                        pub_date_str = article.get('publishedDate', '')
                        
                        # Check if it's about an upgrade/downgrade
                        is_upgrade = any(kw in title for kw in upgrade_keywords)
                        is_downgrade = any(kw in title for kw in downgrade_keywords)
                        
                        if not (is_upgrade or is_downgrade):
                            continue
                        
                        if debug:
                            print(f"[DEBUG] Found news match: {article.get('title', '')[:60]}...")
                        
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        if pub_date < cutoff_time:
                            continue
                        
                        # Try to extract broker name from title/text
                        broker_found = None
                        for broker in premium_brokers:
                            if broker.lower() in title or broker.lower() in text:
                                broker_found = broker
                                break
                        
                        if not broker_found:
                            if 'morgan stanley' in title or 'morgan stanley' in text:
                                broker_found = 'Morgan Stanley'
                            elif 'jpmorgan' in title or 'jp morgan' in title or 'jpmorgan' in text:
                                broker_found = 'JPMorgan'
                            elif 'goldman' in title or 'goldman' in text:
                                broker_found = 'Goldman Sachs'
                            elif 'bank of america' in title or 'bofa' in title:
                                broker_found = 'Bank of America'
                            elif 'ubs' in title or 'ubs' in text:
                                broker_found = 'UBS'
                            elif 'barclays' in title or 'barclays' in text:
                                broker_found = 'Barclays'
                            elif 'citi' in title or 'citigroup' in text:
                                broker_found = 'Citi'
                            else:
                                broker_found = 'Analyst'
                        
                        action_type = 'upgrade' if is_upgrade else 'downgrade'
                        new_rating = 'N/A'
                        previous_rating = 'N/A'
                        
                        # Keyword rating extraction (STRICTER)
                        import re
                        for rating_word in ['buy', 'sell', 'hold', 'outperform', 'underperform', 
                                           'overweight', 'underweight', 'neutral', 'equal-weight']:
                            # Use regex to match whole words only (prevents 'holdings' -> 'hold')
                            pattern = r'\b' + re.escape(rating_word) + r'\b'
                            if re.search(pattern, title, re.IGNORECASE):
                                new_rating = rating_word.title()
                                break
                                
                        # AI ENHANCEMENT: If we have vague data ("Analyst" or "N/A"), ask AI
                        if has_ai and (broker_found == 'Analyst' or new_rating == 'N/A'):
                            if debug: print(f"[DEBUG] 🧠 Invoking AI to extract broker details for: {title[:50]}...")
                            try:
                                ai_data = ai_analyzer.extract_broker_rating(title, text, symbol=symbol)
                                
                                # CRITICAL: If AI says action is "N/A", it means this is a false positive (not relevant to this stock)
                                if ai_data.get('action') == 'N/A' and new_rating == 'N/A':
                                    if debug: print(f"[DEBUG] AI rejected alert for {symbol} (Action: N/A)")
                                    continue
                                
                                if ai_data.get('broker') and ai_data.get('broker') != 'Analyst':
                                    broker_found = ai_data.get('broker')
                                
                                # Refine action if AI identifies it better
                                if ai_data.get('action') and ai_data.get('action') != 'N/A': 
                                    ai_action = ai_data.get('action').lower()
                                    if 'upgrade' in ai_action: action_type = 'upgrade'
                                    elif 'downgrade' in ai_action: action_type = 'downgrade'
                                    elif 'initiate' in ai_action: action_type = 'initiated'
                                
                                if ai_data.get('new_rating') and ai_data.get('new_rating') != 'N/A':
                                    new_rating = ai_data.get('new_rating')
                                    
                                if ai_data.get('old_rating') and ai_data.get('old_rating') != 'N/A':
                                    previous_rating = ai_data.get('old_rating')
                                    
                                old_target = ai_data.get('old_target', 'N/A')
                                new_target = ai_data.get('new_target', 'N/A')
                                
                                # If rating didn't change but target did, it's still an upgrade/downgrade event
                                if action_type == 'reiterated' or action_type == 'N/A':
                                    if old_target != 'N/A' and new_target != 'N/A':
                                        try:
                                            # Simple parsing to compare numbers (stripping $ and commas)
                                            ot_val = float(str(old_target).replace('$', '').replace(',', ''))
                                            nt_val = float(str(new_target).replace('$', '').replace(',', ''))
                                            if nt_val > ot_val: action_type = 'target_raised'
                                            elif nt_val < ot_val: action_type = 'target_lowered'
                                        except:
                                            pass
                                     
                            except Exception as e:
                                if debug: print(f"[DEBUG] AI Extraction failed: {e}")
                                old_target = 'N/A'
                                new_target = 'N/A'
                        else:
                            old_target = 'N/A'
                            new_target = 'N/A'
                        
                        alert_key = f"{symbol}_{broker_found}_{pub_date.strftime('%Y%m%d')}"
                        if alert_key in seen_alerts:
                            continue
                        seen_alerts.add(alert_key)
                        
                        is_premium = any(pb.lower() in broker_found.lower() for pb in premium_brokers)
                        
                        alert = {
                            'symbol': symbol,
                            'broker': broker_found,
                            'action_type': action_type,
                            'new_rating': new_rating,
                            'previous_rating': previous_rating,
                            'old_target': old_target,
                            'new_target': new_target,
                            'date': pub_date.strftime('%Y-%m-%d'),
                            'timestamp': pub_date,
                            'is_premium_broker': is_premium,
                            'score': (12 if is_premium else 6) + (5 if action_type == 'downgrade' else 0),

                            'source': 'News Scan',
                            'headline': article.get('title', '')[:100]
                        }
                        all_alerts.append(alert)
                        if debug:
                            print(f"[DEBUG] ✅ Found from News: {broker_found} {action_type} {symbol}")
                    except Exception as e:
                        if debug:
                            print(f"[DEBUG] Error parsing news: {e}")
                        continue
        except Exception as e:
            if debug:
                print(f"[DEBUG] FMP news scan error for {symbol}: {e}")
    
    # Sort by score (highest first), then by timestamp (most recent first)
    all_alerts.sort(key=lambda x: (x['score'], x['timestamp']), reverse=True)
    
    # Remove duplicates
    final_alerts = []
    seen_final = set()
    for alert in all_alerts:
        key = f"{alert['symbol']}_{alert['broker']}_{alert['date']}"
        if key not in seen_final:
            seen_final.add(key)
            final_alerts.append(alert)
    
    if debug:
        print(f"[DEBUG] Total alerts found: {len(final_alerts)}")
    
    return final_alerts[:10]



# Cached wrapper - cache key changes every 10 minutes - UPDATED V2 for cache busting
# Cached wrapper - cache key changes every 10 minutes - UPDATED V2 for cache busting
# Cached wrapper - cache key changes every 10 minutes - UPDATED V4 for cache busting
@st.cache_data(ttl=600)
def get_broker_rating_alerts_v4(portfolio_symbols: list):
    """Cached wrapper for broker rating alerts"""
    return get_broker_rating_alerts_impl(portfolio_symbols, debug=False)


@st.cache_data(ttl=1800)  # Cache for 30 minutes
def get_fed_macro_alerts():
    """
    Fetch Fed/FOMC and major macro economic alerts
    These affect ALL stocks and should always be displayed
    """
    alerts = []
    
    # HARDCODED BREAKING NEWS - Fed Rate Cut Dec 10, 2025
    # This ensures critical Fed news is always displayed
    fed_rate_cut_date = datetime(2025, 12, 10, 19, 0, 0)  # 2PM EST = 7PM UTC
    if datetime.utcnow() >= fed_rate_cut_date and datetime.utcnow() <= fed_rate_cut_date + timedelta(days=3):
        alerts.append({
            'title': '🚨 BREAKING: Fed Cuts Rates by 25bps to 3.50%-3.75%',
            'text': 'The Federal Reserve cut interest rates for the third consecutive time, lowering the target range by 25 basis points. Powell signals "wait and see" approach for 2026. Three dissents highlight FOMC division.',
            'url': 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20251210a.htm',
            'source': 'Federal Reserve',
            'date': '2025-12-10 14:00',
            'timestamp': fed_rate_cut_date,
            'alert_type': 'rate_cut',
            'emoji': '🏛️',
            'color': '#00FF88',
            'is_breaking': True
        })
    
    try:
        # Fetch Fed news from FMP
        url = "https://financialmodelingprep.com/api/v4/general_news"
        params = {
            'apikey': settings.fmp_api_key,
            'page': 0
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # Keywords for Fed/macro news
        fed_keywords = [
            'federal reserve', 'fed ', 'fomc', 'rate cut', 'rate hike', 
            'interest rate', 'powell', 'monetary policy', 'basis point',
            'inflation', 'cpi', 'pce', 'employment', 'jobs report', 
            'nonfarm payroll', 'gdp', 'recession', 'treasury yield'
        ]
        
        if isinstance(data, list):
            for article in data[:50]:
                title = article.get('title', '').lower()
                text = article.get('text', '').lower()
                
                # Check if it's Fed/macro related
                is_macro = any(kw in title or kw in text for kw in fed_keywords)
                
                if is_macro:
                    pub_date_str = article.get('publishedDate', '')
                    try:
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        # Only last 48 hours
                        if pub_date >= datetime.utcnow() - timedelta(hours=48):
                            # Determine alert type
                            title_lower = article.get('title', '').lower()
                            if 'cut' in title_lower and ('rate' in title_lower or 'fed' in title_lower):
                                alert_type = 'rate_cut'
                                emoji = '📉'
                                color = '#00FF88'
                            elif 'hike' in title_lower or 'raise' in title_lower:
                                alert_type = 'rate_hike'
                                emoji = '📈'
                                color = '#FF3366'
                            elif 'inflation' in title_lower:
                                alert_type = 'inflation'
                                emoji = '🔥'
                                color = '#FFB800'
                            elif 'fomc' in title_lower or 'powell' in title_lower:
                                alert_type = 'fomc'
                                emoji = '🏛️'
                                color = '#00D4FF'
                            else:
                                alert_type = 'macro'
                                emoji = '📊'
                                color = '#8892A6'
                            
                            alerts.append({
                                'title': article.get('title', 'Macro Alert'),
                                'text': article.get('text', '')[:200] + '...' if len(article.get('text', '')) > 200 else article.get('text', ''),
                                'url': article.get('url', ''),
                                'source': article.get('site', 'News'),
                                'date': pub_date.strftime('%Y-%m-%d %H:%M'),
                                'timestamp': pub_date,
                                'alert_type': alert_type,
                                'emoji': emoji,
                                'color': color
                            })
                    except:
                        continue
    except Exception as e:
        print(f"Error fetching macro alerts: {e}")
    
    # Sort by timestamp (most recent first), but keep breaking news at top
    alerts.sort(key=lambda x: (x.get('is_breaking', False), x['timestamp']), reverse=True)
    
    # Return top 5 macro alerts
    return alerts[:5]

# ===========================
# STYLING
# ===========================

def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css('assets/style.css')

# ===========================
# HELPER FUNCTIONS
# ===========================

def is_market_open():
    """Check if US market is currently open (simplified)"""
    now = datetime.utcnow()
    # Convert to ET (UTC-5, simplified - doesn't account for DST)
    et_hour = (now.hour - 5) % 24
    
    # Check if weekday
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if trading hours (9:30 AM - 4:00 PM ET)
    if 9 <= et_hour < 16:
        if et_hour == 9 and now.minute < 30:
            return False
        return True
    
    return False

def render_market_pulse():
    """Render the Market Pulse header with live indices using Streamlit columns"""
    indices = get_market_indices()
    market_open = is_market_open()
    
    # Create a container with custom styling
    st.markdown("""
    <div style="background: linear-gradient(135deg, #0D1321 0%, #131A2B 100%); 
                border: 1px solid #1E2A42; 
                border-radius: 16px; 
                padding: 1rem 1.5rem; 
                margin-bottom: 1.5rem;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 0.75rem;">
            <div style="width: 8px; height: 8px; background: #00FF88; border-radius: 50%;"></div>
            <span style="color: #8892A6; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px;">Market Pulse</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Use Streamlit columns for indices
    cols = st.columns(len(indices) + 1)
    
    for idx, (symbol, data) in enumerate(indices.items()):
        with cols[idx]:
            change_color = "#00FF88" if data['change_percent'] >= 0 else "#FF3366"
            arrow = "▲" if data['change_percent'] >= 0 else "▼"
            
            st.markdown(f"""
            <div style="text-align: center; padding: 0.5rem;">
                <div style="color: #8892A6; font-size: 0.75rem; font-weight: 500; text-transform: uppercase;">{data['emoji']} {data['name']}</div>
                <div style="color: #FFFFFF; font-size: 1.2rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;">{data['price']:,.2f}</div>
                <div style="color: {change_color}; font-size: 0.85rem; font-weight: 600;">{arrow} {abs(data['change_percent']):.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Market status in the last column
    with cols[-1]:
        status_color = "#00FF88" if market_open else "#FF3366"
        status_bg = "rgba(0, 255, 136, 0.1)" if market_open else "rgba(255, 51, 102, 0.1)"
        status_text = "Market Open" if market_open else "Market Closed"
        status_icon = "🟢" if market_open else "🔴"
        
        st.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: center; height: 100%;">
            <div style="background: {status_bg}; padding: 8px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; color: {status_color};">
                {status_icon} {status_text}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

def render_stock_card(symbol: str, profile: dict):
    """Render stock info using simple, reliable format"""
    # Company name with fallback
    company_name = profile.get('name', '')
    if not company_name or company_name == symbol or company_name == 'N/A':
        known_names = {
            'AAPL': 'Apple Inc.',
            'MSFT': 'Microsoft Corporation',
            'GOOGL': 'Alphabet Inc.',
            'GOOG': 'Alphabet Inc.',
            'TSLA': 'Tesla Inc.',
            'NVDA': 'NVIDIA Corporation',
            'META': 'Meta Platforms Inc.',
            'AMZN': 'Amazon.com Inc.',
            'NFLX': 'Netflix Inc.',
            'AMD': 'Advanced Micro Devices',
            'INTC': 'Intel Corporation',
            'MU': 'Micron Technology',
            'JPM': 'JPMorgan Chase',
            'V': 'Visa Inc.',
            'JNJ': 'Johnson & Johnson',
            'WMT': 'Walmart Inc.',
            'PG': 'Procter & Gamble',
            'DIS': 'Walt Disney Co.',
            'PYPL': 'PayPal Holdings',
            'ADBE': 'Adobe Inc.',
            'CRM': 'Salesforce Inc.',
            'NFLX': 'Netflix Inc.',
            'COST': 'Costco Wholesale',
            'PEP': 'PepsiCo Inc.',
            'KO': 'Coca-Cola Co.'
        }
        company_name = known_names.get(symbol, symbol)
    
    # Truncate if needed
    if len(company_name) > 30:
        company_name = company_name[:27] + "..."
    
    # Sector with fallback and emoji
    sector = profile.get('sector', '') or ''
    if sector == 'N/A' or not sector:
        sector = 'Equity'
    
    sector_emoji = {
        'Technology': '💻',
        'Healthcare': '🏥',
        'Financial Services': '🏦',
        'Consumer Cyclical': '🛒',
        'Consumer Defensive': '🛡️',
        'Communication Services': '📡',
        'Industrials': '🏭',
        'Energy': '⚡',
        'Utilities': '💡',
        'Real Estate': '🏠',
        'Basic Materials': '🧱',
        'Equity': '📈'
    }.get(sector, '📊')
    
    return symbol, company_name, sector, sector_emoji


def display_stock_card_beautiful(symbol: str, company_name: str, sector: str, sector_emoji: str):
    """Display a beautiful stock card"""
    # Get a gradient color based on the symbol
    colors = ['#00D4FF', '#00FF88', '#FF3366', '#FFB800', '#8B5CF6', '#F472B6']
    color = colors[hash(symbol) % len(colors)]
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(19, 26, 43, 0.9) 0%, rgba(26, 36, 56, 0.9) 100%);
        border: 1px solid #1E2A42;
        border-left: 4px solid {color};
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div style="font-size: 1.3rem; font-weight: 700; color: #FFFFFF; font-family: 'JetBrains Mono', monospace; letter-spacing: 1px;">
                    {symbol}
                </div>
                <div style="font-size: 0.85rem; color: #8892A6; margin-top: 4px;">
                    {company_name}
                </div>
            </div>
            <div style="
                background: rgba(0, 212, 255, 0.1);
                color: #00D4FF;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 0.7rem;
                font-weight: 600;
            ">
                ● TRACKING
            </div>
        </div>
        <div style="margin-top: 0.75rem; display: flex; gap: 8px;">
            <span style="
                background: rgba(255, 255, 255, 0.05);
                color: #8892A6;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.75rem;
            ">
                {sector_emoji} {sector}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ===========================
# INITIALIZE
# ===========================

init_db()

@st.cache_resource
def get_services():
    return {
        'fmp': FMPClient(),
        'ai': AIAnalyzer(),
        'monitor': PortfolioNewsMonitor()
    }

services = get_services()

if 'user_email' not in st.session_state:
    st.session_state.user_email = 'demo@example.com'

# ===========================
# SIDEBAR
# ===========================

# ===========================
# SIDEBAR (SIMPLIFIED)
# ===========================

with st.sidebar:
    # Minimal Logo/Brand
    st.markdown("""
    <div class="sidebar-logo-container">
        <div class="sidebar-logo-text">STOCK<span style="color:#00F0FF">PULSE</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    # User Profile (Compact)
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if user:
        holdings_count = db.query(UserHolding).filter(UserHolding.user_id == user.id).count()
        alerts_count = db.query(Notification).filter(Notification.user_id == user.id).count()
        
        st.markdown(f"""
        <div style="background: var(--glass); border-radius: 8px; padding: 10px; border: 1px solid var(--glass-border);">
            <div style="color: #fff; font-size: 0.8rem;">👤 {st.session_state.user_email.split('@')[0]}</div>
            <div style="display: flex; gap: 10px; margin-top: 5px;">
                <span style="font-size: 0.7rem; color: #888;">Stocks: <b style="color: #fff">{holdings_count}</b></span>
                <span style="font-size: 0.7rem; color: #888;">Alerts: <b style="color: #fff">{alerts_count}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    db.close()
    
    st.markdown("---")
    st.caption("v2.5 - Cyber Update ⚡")

# ===========================
# TOP NAVIGATION
# ===========================

# Horizontal Radio Button Group
page = st.radio(
    "Navigation",
    ["🏠 Dashboard", "📊 Portfolio", "🔔 Alerts", "🚀 Run Scan", "⚙️ Settings"],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown('<div class="neon-divider"></div>', unsafe_allow_html=True)

# ===========================
# PAGE 1: DASHBOARD
# ===========================
if page == "🏠 Dashboard":
    # Market Pulse Header
    render_market_pulse()
    
    st.markdown('<p class="main-header">Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Real-time insights for your portfolio</p>', unsafe_allow_html=True)
    
    # ========================
    # 🏛️ FED / MACRO ALERTS (affects ALL stocks)
    # ========================
    macro_alerts = get_fed_macro_alerts()
    
    if macro_alerts:
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.15) 0%, rgba(139, 92, 246, 0.1) 100%);
            border: 2px solid rgba(0, 212, 255, 0.3);
            border-radius: 16px;
            padding: 1.25rem;
            margin-bottom: 1.5rem;
        ">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 1rem;">
                <span style="font-size: 1.5rem;">🏛️</span>
                <span style="font-size: 1.1rem; font-weight: 700; color: #00D4FF; text-transform: uppercase; letter-spacing: 1px;">
                    Fed & Macro Alerts
                </span>
                <span style="background: #FF3366; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600;">
                    MARKET-WIDE
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        for alert in macro_alerts[:3]:
            st.markdown(f"""
            <div style="
                background: rgba(10, 14, 23, 0.7);
                border-left: 4px solid {alert['color']};
                border-radius: 8px;
                padding: 0.75rem 1rem;
                margin-bottom: 0.5rem;
            ">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div style="flex: 1;">
                        <div style="font-size: 0.95rem; font-weight: 600; color: #FFFFFF; margin-bottom: 4px;">
                            {alert['emoji']} {alert['title'][:80]}{'...' if len(alert['title']) > 80 else ''}
                        </div>
                        <div style="font-size: 0.8rem; color: #8892A6;">
                            {alert['source']} · {alert['date']}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("User not found. Run `python main.py setup` to create demo user.")
        db.close()
        st.stop()
    
    # Main Metrics
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    recent_alerts = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.sent_at.desc()).limit(7).all()
    
    high_impact_alerts = db.query(Notification).join(NewsArticle).join(NewsAnalysis).filter(
        Notification.user_id == user.id,
        NewsAnalysis.impact_score >= 7
    ).count()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(0, 255, 136, 0.05) 100%);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📊</div>
            <div style="font-size: 2rem; font-weight: 800; color: #00D4FF; font-family: 'JetBrains Mono', monospace;">{len(holdings)}</div>
            <div style="font-size: 0.85rem; color: #8892A6; text-transform: uppercase; letter-spacing: 1px;">Tracked</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, rgba(255, 184, 0, 0.1) 0%, rgba(255, 107, 53, 0.05) 100%);
            border: 1px solid rgba(255, 184, 0, 0.2);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔔</div>
            <div style="font-size: 2rem; font-weight: 800; color: #FFB800; font-family: 'JetBrains Mono', monospace;">{len(recent_alerts)}</div>
            <div style="font-size: 0.85rem; color: #8892A6; text-transform: uppercase; letter-spacing: 1px;">Alerts</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, rgba(255, 51, 102, 0.1) 0%, rgba(255, 107, 53, 0.05) 100%);
            border: 1px solid rgba(255, 51, 102, 0.2);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">⚠️</div>
            <div style="font-size: 2rem; font-weight: 800; color: #FF3366; font-family: 'JetBrains Mono', monospace;">{high_impact_alerts}</div>
            <div style="font-size: 0.85rem; color: #8892A6; text-transform: uppercase; letter-spacing: 1px;">High Impact</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        status_color = "#00FF88" if user.active else "#FF3366"
        status_icon = "✓" if user.active else "✗"
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, rgba(0, 255, 136, 0.1) 0%, rgba(0, 212, 255, 0.05) 100%);
            border: 1px solid rgba(0, 255, 136, 0.2);
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">⚡</div>
            <div style="font-size: 2rem; font-weight: 800; color: {status_color}; font-family: 'JetBrains Mono', monospace;">{status_icon}</div>
            <div style="font-size: 0.85rem; color: #8892A6; text-transform: uppercase; letter-spacing: 1px;">Active</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div style="margin: 2rem 0;"></div>', unsafe_allow_html=True)
    
    # Two Column Layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        <div class="section-header">
            <div class="section-icon">💼</div>
            <div class="section-title">Your Portfolio</div>
        </div>
        """, unsafe_allow_html=True)
        
        if holdings:
            # Display beautiful stock cards
            cols = st.columns(2)
            for idx, holding in enumerate(holdings):
                profile = get_company_profile_cached(holding.symbol)
                symbol, company_name, sector, sector_emoji = render_stock_card(holding.symbol, profile)
                with cols[idx % 2]:
                    display_stock_card_beautiful(symbol, company_name, sector, sector_emoji)
        else:
            st.info("📊 No stocks in your portfolio yet. Head to Portfolio to add some!")
        
        # ========================
        # BROKER RATING ALERTS
        # ========================
        st.markdown('<div style="margin-top: 2rem;"></div>', unsafe_allow_html=True)
        
        # Header with refresh button
        col_header, col_refresh = st.columns([4, 1])
        with col_header:
            st.markdown("""
            <div class="section-header">
                <div class="section-icon">📈</div>
                <div class="section-title">Broker Rating Changes</div>
            </div>
            """, unsafe_allow_html=True)
        with col_refresh:
            if st.button("🔄", help="Refresh broker alerts (clears cache)"):
                st.cache_data.clear()
                st.rerun()
        
        # Fetch broker rating changes for portfolio stocks
        portfolio_symbols = [h.symbol for h in holdings] if holdings else []
        
        # Show what symbols we're checking
        if portfolio_symbols:
            st.caption(f"Checking: {', '.join(portfolio_symbols)}")
        
        broker_alerts = get_broker_rating_alerts_v4(portfolio_symbols)
        
        if broker_alerts:
            for alert in broker_alerts[:5]:
                action_type = alert.get('action_type', '')
                is_negative = action_type in ['downgrade', 'target_lowered']
                is_premium = alert.get('is_premium_broker', False)
                
                # Color coding
                if is_negative:
                    border_color = '#FF3366'
                    action_label = '⬇️ DOWNGRADE'
                    bg_gradient = 'rgba(255, 51, 102, 0.15)'
                elif action_type == 'upgrade':
                    border_color = '#00FF88'
                    action_label = '⬆️ UPGRADE'
                    bg_gradient = 'rgba(0, 255, 136, 0.15)'
                elif action_type == 'initiated':
                    border_color = '#00D4FF'
                    action_label = '🆕 INITIATED'
                    bg_gradient = 'rgba(0, 212, 255, 0.15)'
                else:
                    border_color = '#8892A6'
                    action_label = '📊 RATING'
                    bg_gradient = 'rgba(136, 146, 166, 0.1)'
                
                premium_badge = '⭐ ' if is_premium else ''
                headline = alert.get('headline', '')
                source_badge = f"<span style='font-size:0.65rem;background:#1A2438;color:#8892A6;padding:2px 6px;border-radius:4px;margin-left:8px;'>{alert.get('source', 'API')}</span>" if alert.get('source') else ''
                
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, {bg_gradient} 0%, rgba(19, 26, 43, 0.95) 100%);
                    border: 1px solid #1E2A42;
                    border-left: 5px solid {border_color};
                    border-radius: 12px;
                    padding: 1rem 1.25rem;
                    margin-bottom: 0.75rem;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                        <div style="font-size: 1.2rem; font-weight: 800; color: #FFFFFF; font-family: 'JetBrains Mono', monospace;">
                            {alert['symbol']} {action_label}
                        </div>
                        <div style="font-size: 0.7rem; color: #8892A6; background: #1A2438; padding: 4px 8px; border-radius: 8px;">
                            {alert['date']}
                        </div>
                    </div>
                    <div style="font-size: 0.9rem; color: #FFFFFF; margin-bottom: 6px;">
                        {premium_badge}{alert['broker']}{source_badge}
                    </div>
                    <div style="font-size: 0.85rem; color: #00D4FF; margin-bottom: 6px;">
                        {alert.get('previous_rating', '')} {'→' if alert.get('previous_rating') and alert.get('previous_rating') != 'N/A' else ''} <strong>{alert['new_rating']}</strong>
                    </div>
                    {f"<div style='font-size: 0.85rem; color: #00FF88; margin-bottom: 6px;'>🎯 Target: {alert.get('old_target', 'N/A')} → <strong>{alert.get('new_target', 'N/A')}</strong></div>" if alert.get('new_target') and alert.get('new_target') != 'N/A' else ""}
                    {"<div style='font-size: 0.8rem; color: #8892A6; font-style: italic; margin-top: 6px;'>" + headline[:80] + ('...' if len(headline) > 80 else '') + "</div>" if headline else ""}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="
                background: rgba(19, 26, 43, 0.5);
                border: 1px dashed #1E2A42;
                border-radius: 12px;
                padding: 2rem;
                text-align: center;
                color: #8892A6;
            ">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📊</div>
                <div>No recent broker rating changes for your portfolio</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="section-header">
            <div class="section-icon">🔥</div>
            <div class="section-title">Recent Alerts</div>
        </div>
        """, unsafe_allow_html=True)
        
        if recent_alerts:
            for notif in recent_alerts[:5]:
                article = db.query(NewsArticle).filter(NewsArticle.id == notif.article_id).first()
                analysis = db.query(NewsAnalysis).filter(NewsAnalysis.article_id == notif.article_id).first()
                
                if article and analysis:
                    impact = analysis.impact_score
                    if impact >= 7:
                        impact_class = "impact-high"
                        impact_emoji = "🔴"
                    elif impact >= 5:
                        impact_class = "impact-medium"
                        impact_emoji = "🟡"
                    else:
                        impact_class = "impact-low"
                        impact_emoji = "🟢"
                    
                    urgent_class = "urgent" if analysis.urgency in ['Immediate', 'Hours'] else "normal"
                    
                    st.markdown(f"""
                    <div class="alert-card {urgent_class}">
                        <div class="alert-symbol">{article.symbol}</div>
                        <div class="alert-title">{analysis.summary[:60]}...</div>
                        <div class="alert-meta">
                            <span class="impact-badge {impact_class}">{impact_emoji} {impact}/10</span>
                            <span>{analysis.urgency}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">🔔</div>
                <div class="empty-state-text">No alerts yet. Run a scan to get started!</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown(f'<div class="last-updated">Last updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</div>', unsafe_allow_html=True)
    
    db.close()

# ===========================
# PAGE 2: PORTFOLIO
# ===========================
elif page == "📊 Portfolio":
    render_market_pulse()
    
    st.markdown('<p class="main-header">Portfolio</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Manage your tracked stocks</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("User not found.")
        db.close()
        st.stop()
    
    # Current Holdings - Enriched Cards
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">💼</div>
        <div class="section-title">Your Watchlist</div>
    </div>
    """, unsafe_allow_html=True)
    
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    
    if holdings:
        # Grid of beautiful stock cards
        cols = st.columns(3)
        for idx, holding in enumerate(holdings):
            profile = get_company_profile_cached(holding.symbol)
            symbol, company_name, sector, sector_emoji = render_stock_card(holding.symbol, profile)
            with cols[idx % 3]:
                display_stock_card_beautiful(symbol, company_name, sector, sector_emoji)
        
        st.divider()
        
        # Delete section
        st.subheader("🗑️ Remove Stock")
        
        symbols = [h.symbol for h in holdings]
        symbol_to_delete = st.selectbox("Select stock to remove", symbols, label_visibility="collapsed")
        
        if st.button("Remove from Watchlist", type="secondary"):
            holding_to_delete = db.query(UserHolding).filter(
                UserHolding.user_id == user.id,
                UserHolding.symbol == symbol_to_delete
            ).first()
            if holding_to_delete:
                db.delete(holding_to_delete)
                db.commit()
                st.success(f"✓ {symbol_to_delete} removed successfully!")
                st.rerun()
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">📭</div>
            <div class="empty-state-text">Your watchlist is empty. Add some stocks below!</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Add New Stock
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">➕</div>
        <div class="section-title">Add Stock</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        new_symbol = st.text_input("Stock Symbol (e.g., AAPL, TSLA, NVDA)", key="new_symbol", placeholder="Enter ticker symbol...").upper()
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add to Watchlist", type="primary", use_container_width=True):
            if new_symbol:
                existing = db.query(UserHolding).filter(
                    UserHolding.user_id == user.id,
                    UserHolding.symbol == new_symbol
                ).first()
                
                if existing:
                    st.warning(f"⚠️ {new_symbol} is already in your watchlist.")
                else:
                    new_holding = UserHolding(
                        user_id=user.id,
                        symbol=new_symbol,
                        quantity=1,
                        avg_cost=0,
                        asset_type='stock'
                    )
                    db.add(new_holding)
                    db.commit()
                    st.success(f"✓ {new_symbol} added to your watchlist!")
                    st.rerun()
            else:
                st.error("Please enter a valid stock symbol.")
    
    db.close()

# ===========================
# PAGE 3: ALERTS
# ===========================
elif page == "🔔 Alerts":
    render_market_pulse()
    
    st.markdown('<p class="main-header">Alerts</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your news feed and notifications</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("User not found.")
        db.close()
        st.stop()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        days_filter = st.selectbox("Time Period", [7, 14, 30, 90, 365], index=2, format_func=lambda x: f"Last {x} days")
    
    with col2:
        impact_filter = st.slider("Minimum Impact", 0, 10, 5)
    
    with col3:
        category_filter = st.multiselect(
            "Category",
            ["Earnings", "Management", "Regulatory", "Product", "Market", "Legal", "M&A", "Financial", "Other"],
            default=[]
        )
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Get alerts
    cutoff_date = datetime.utcnow() - timedelta(days=days_filter)
    
    query = db.query(Notification).join(NewsArticle).join(NewsAnalysis).filter(
        Notification.user_id == user.id,
        NewsArticle.published_date >= cutoff_date,
        NewsAnalysis.impact_score >= impact_filter
    )
    
    if category_filter:
        query = query.filter(NewsAnalysis.category.in_(category_filter))
    
    notifications = query.order_by(NewsArticle.published_date.desc()).all()
    
    st.markdown(f"**{len(notifications)} alerts found**")
    
    if notifications:
        for notif in notifications:
            article = db.query(NewsArticle).filter(NewsArticle.id == notif.article_id).first()
            analysis = db.query(NewsAnalysis).filter(NewsAnalysis.article_id == notif.article_id).first()
            
            if article and analysis:
                impact = analysis.impact_score
                if impact >= 7:
                    impact_class = "impact-high"
                    impact_emoji = "🔴"
                elif impact >= 5:
                    impact_class = "impact-medium"
                    impact_emoji = "🟡"
                else:
                    impact_class = "impact-low"
                    impact_emoji = "🟢"
                
                urgent_class = "urgent" if analysis.urgency in ['Immediate', 'Hours'] else "normal"
                
                st.markdown(f"""
                <div class="alert-card {urgent_class}">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <div class="alert-symbol">{article.symbol}</div>
                            <div class="alert-title">{article.title}</div>
                            <p style="color: var(--text-secondary); font-size: 0.9rem; margin: 0.75rem 0;">{analysis.summary}</p>
                        </div>
                        <div class="impact-badge {impact_class}">{impact_emoji} {impact}/10</div>
                    </div>
                    <div class="alert-meta">
                        <span>📅 {article.published_date.strftime('%Y-%m-%d %H:%M')}</span>
                        <span>📰 {article.source}</span>
                        <span>🏷️ {analysis.category}</span>
                        <span>⏰ {analysis.urgency}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("View Details"):
                    st.write(f"**Sentiment:** {analysis.sentiment}")
                    st.write(f"**Affected Sector:** {analysis.affected_sector}")
                    st.markdown(f"[Read Full Article →]({article.url})")
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">🔍</div>
            <div class="empty-state-text">No alerts match your criteria. Try adjusting the filters.</div>
        </div>
        """, unsafe_allow_html=True)
    
    db.close()

# ===========================
# PAGE 4: SETTINGS
# ===========================
elif page == "⚙️ Settings":
    st.markdown('<p class="main-header">Settings</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Configure your account and preferences</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("User not found.")
        db.close()
        st.stop()
    
    # User Info Section
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">👤</div>
        <div class="section-title">Account Information</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        new_name = st.text_input("Name", value=user.name or "")
        new_email = st.text_input("Email", value=user.email)
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        user_active = st.checkbox("Account Active", value=user.active)
    
    if st.button("Save Changes", type="primary"):
        user.name = new_name
        user.email = new_email
        user.active = user_active
        db.commit()
        st.success("✓ Settings saved successfully!")
        st.session_state.user_email = new_email
        st.rerun()
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Notification Preferences
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">🔔</div>
        <div class="section-title">Notification Preferences</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.info("💡 Advanced settings like impact threshold and polling frequency can be found in `config/settings.py`")
    
    with st.expander("View Current Configuration"):
        st.markdown(f"""
        | Setting | Value |
        |---------|-------|
        | Polling Interval | **{settings.polling_interval_minutes} minutes** |
        | Impact Threshold | **{settings.impact_threshold}/10** |
        | News Lookback | **{settings.news_lookback_hours} hours** |
        | SMTP Host | **{settings.smtp_host}** |
        """)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Danger Zone
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">⚠️</div>
        <div class="section-title">Danger Zone</div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("Clear All Alerts", type="secondary"):
        notifications = db.query(Notification).filter(Notification.user_id == user.id).all()
        for n in notifications:
            db.delete(n)
        db.commit()
        st.warning("All alerts have been cleared.")
    
    db.close()

# ===========================
# PAGE 5: RUN SCAN
# ===========================
elif page == "🚀 Run Scan":
    render_market_pulse()
    
    st.markdown('<p class="main-header">Run Scan</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Manually trigger a portfolio news scan</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="stat-card" style="text-align: center; padding: 3rem;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">🔍</div>
        <div style="color: var(--text-primary); font-size: 1.2rem; margin-bottom: 0.5rem;">Ready to Scan</div>
        <div style="color: var(--text-secondary); font-size: 0.95rem;">Click the button below to analyze your portfolio for relevant news</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("⚡ Launch Scan", type="primary", use_container_width=True):
            with st.spinner("Scanning news sources... This may take 30-60 seconds."):
                try:
                    services['monitor'].run_monitoring_cycle()
                    st.success("✓ Scan completed! Check your email and the Alerts tab for results.")
                    st.balloons()
                except Exception as e:
                    st.error(f"Scan failed: {e}")
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Last Scan Info
    st.markdown("""
    <div class="section-header">
        <div class="section-icon">📊</div>
        <div class="section-title">Last Scan</div>
    </div>
    """, unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if user:
        last_notif = db.query(Notification).filter(
            Notification.user_id == user.id
        ).order_by(Notification.sent_at.desc()).first()
        
        if last_notif:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Last Activity</div>
                <div class="stat-value" style="font-size: 1.5rem;">{last_notif.sent_at.strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No scans recorded yet. Run your first scan above!")
    
    db.close()

# Footer
st.markdown("""
<div class="app-footer">
    <span class="footer-brand">StockPulse</span> v2.1 | Powered by Claude AI & Financial APIs
</div>
""", unsafe_allow_html=True)