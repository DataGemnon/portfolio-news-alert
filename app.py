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

# ===========================
# STYLING
# ===========================

st.markdown("""
<style>
    /* Import Google Fonts - Modern Athletic Typography */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    /* Root Variables - Electric Blue & Dark Theme */
    :root {
        --primary: #00D4FF;
        --primary-dark: #00A8CC;
        --secondary: #FF3366;
        --accent: #00FF88;
        --warning: #FFB800;
        --bg-dark: #0A0E17;
        --bg-card: #131A2B;
        --bg-card-hover: #1A2438;
        --text-primary: #FFFFFF;
        --text-secondary: #8892A6;
        --border-color: #1E2A42;
        --gradient-1: linear-gradient(135deg, #00D4FF 0%, #00FF88 100%);
        --gradient-2: linear-gradient(135deg, #FF3366 0%, #FF6B35 100%);
        --gradient-3: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
    }
    
    /* Global Styles */
    .stApp {
        background: var(--bg-dark);
        font-family: 'Outfit', sans-serif;
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0D1321 0%, #131A2B 100%);
        border-right: 1px solid var(--border-color);
    }
    
    [data-testid="stSidebar"] .stRadio > label {
        color: var(--text-secondary) !important;
        font-weight: 500;
    }
    
    /* ===========================
       MARKET PULSE HEADER
       =========================== */
    .market-pulse-container {
        background: linear-gradient(135deg, #0D1321 0%, #131A2B 100%);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1rem 1.5rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 1rem;
    }
    
    .market-pulse-title {
        display: flex;
        align-items: center;
        gap: 10px;
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }
    
    .pulse-dot {
        width: 8px;
        height: 8px;
        background: var(--accent);
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(0, 255, 136, 0.7); }
        50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(0, 255, 136, 0); }
    }
    
    .market-indices {
        display: flex;
        gap: 2rem;
        flex-wrap: wrap;
    }
    
    .index-item {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        min-width: 120px;
    }
    
    .index-name {
        color: var(--text-secondary);
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 2px;
    }
    
    .index-value {
        color: var(--text-primary);
        font-size: 1.1rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .index-change {
        font-size: 0.85rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    
    .index-change.positive {
        color: var(--accent);
    }
    
    .index-change.negative {
        color: var(--secondary);
    }
    
    .market-status {
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(0, 255, 136, 0.1);
        padding: 8px 14px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--accent);
    }
    
    .market-status.closed {
        background: rgba(255, 51, 102, 0.1);
        color: var(--secondary);
    }
    
    /* ===========================
       MAIN HEADER
       =========================== */
    .main-header {
        background: var(--gradient-1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.8rem;
        font-weight: 800;
        letter-spacing: -1px;
        margin-bottom: 0.5rem;
        font-family: 'Outfit', sans-serif;
    }
    
    .sub-header {
        color: var(--text-secondary);
        font-size: 1.1rem;
        font-weight: 400;
        margin-bottom: 2rem;
    }
    
    /* Logo Section */
    .logo-container {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 1.5rem 0;
        margin-bottom: 1rem;
    }
    
    .logo-icon {
        width: 42px;
        height: 42px;
        background: var(--gradient-1);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.4rem;
        box-shadow: 0 8px 32px rgba(0, 212, 255, 0.3);
    }
    
    .logo-text {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.5px;
    }
    
    .logo-text span {
        color: var(--primary);
    }
    
    /* ===========================
       ENRICHED PORTFOLIO CARDS
       =========================== */
    .stock-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.25rem;
        margin: 0.5rem 0;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .stock-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: var(--gradient-1);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .stock-card:hover {
        border-color: var(--primary);
        transform: translateY(-4px);
        box-shadow: 0 20px 40px rgba(0, 212, 255, 0.15);
    }
    
    .stock-card:hover::before {
        opacity: 1;
    }
    
    .stock-card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 0.75rem;
    }
    
    .stock-logo {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: var(--bg-card-hover);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        border: 1px solid var(--border-color);
    }
    
    .stock-logo img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        padding: 6px;
    }
    
    .stock-logo-placeholder {
        font-size: 1.2rem;
        font-weight: 700;
        color: var(--primary);
        font-family: 'JetBrains Mono', monospace;
    }
    
    .stock-info {
        flex: 1;
    }
    
    .stock-symbol {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary);
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.5px;
    }
    
    .stock-name {
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-weight: 400;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 150px;
    }
    
    .stock-badge {
        background: rgba(0, 212, 255, 0.1);
        color: var(--primary);
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .stock-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 0.5rem;
    }
    
    .stock-sector {
        font-size: 0.75rem;
        color: var(--text-secondary);
        background: var(--bg-card-hover);
        padding: 4px 10px;
        border-radius: 12px;
    }
    
    .stock-exchange {
        font-size: 0.7rem;
        color: var(--text-secondary);
        font-family: 'JetBrains Mono', monospace;
    }
    
    /* ===========================
       STAT CARDS
       =========================== */
    .stat-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .stat-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: var(--gradient-1);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .stat-card:hover {
        border-color: var(--primary);
        transform: translateY(-4px);
        box-shadow: 0 20px 40px rgba(0, 212, 255, 0.15);
    }
    
    .stat-card:hover::before {
        opacity: 1;
    }
    
    .stat-label {
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
    }
    
    .stat-value {
        color: var(--text-primary);
        font-size: 2.2rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-value.positive {
        color: var(--accent);
    }
    
    .stat-value.negative {
        color: var(--secondary);
    }
    
    /* ===========================
       ALERT CARDS
       =========================== */
    .alert-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 1rem 0;
        position: relative;
        transition: all 0.3s ease;
    }
    
    .alert-card:hover {
        border-color: rgba(0, 212, 255, 0.5);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    
    .alert-card.urgent {
        border-left: 4px solid var(--secondary);
        background: linear-gradient(135deg, rgba(255, 51, 102, 0.05) 0%, var(--bg-card) 100%);
    }
    
    .alert-card.normal {
        border-left: 4px solid var(--primary);
    }
    
    .alert-symbol {
        display: inline-block;
        background: var(--gradient-1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 1.3rem;
        font-weight: 800;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .alert-title {
        color: var(--text-primary);
        font-size: 1rem;
        font-weight: 500;
        margin: 0.5rem 0;
        line-height: 1.5;
    }
    
    .alert-meta {
        color: var(--text-secondary);
        font-size: 0.85rem;
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
        margin-top: 0.75rem;
    }
    
    /* Impact Badge */
    .impact-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    
    .impact-high {
        background: rgba(255, 51, 102, 0.15);
        color: var(--secondary);
    }
    
    .impact-medium {
        background: rgba(255, 184, 0, 0.15);
        color: var(--warning);
    }
    
    .impact-low {
        background: rgba(0, 255, 136, 0.15);
        color: var(--accent);
    }
    
    /* Section Headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 2rem 0 1.5rem 0;
    }
    
    .section-title {
        color: var(--text-primary);
        font-size: 1.4rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    
    .section-icon {
        width: 36px;
        height: 36px;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
    }
    
    /* Buttons */
    .stButton > button {
        background: var(--gradient-1) !important;
        color: #0A0E17 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        font-family: 'Outfit', sans-serif !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.3px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 8px 24px rgba(0, 212, 255, 0.25) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 12px 32px rgba(0, 212, 255, 0.35) !important;
    }
    
    /* Input Fields */
    .stTextInput > div > div > input {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
        font-family: 'Outfit', sans-serif !important;
        padding: 0.75rem 1rem !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.15) !important;
    }
    
    .stNumberInput > div > div > input {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }
    
    /* Select Box */
    .stSelectbox > div > div {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: var(--bg-card) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }
    
    /* Metrics Override */
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
        color: var(--text-primary) !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        font-size: 0.8rem !important;
    }
    
    /* Divider */
    .custom-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, var(--border-color), transparent);
        margin: 2rem 0;
    }
    
    /* Sidebar User Card */
    .user-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 14px;
        padding: 1.2rem;
        margin-top: 1rem;
    }
    
    .user-email {
        color: var(--text-primary);
        font-weight: 500;
        font-size: 0.9rem;
    }
    
    .user-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-top: 0.5rem;
        color: var(--accent);
        font-size: 0.8rem;
    }
    
    .status-dot {
        width: 8px;
        height: 8px;
        background: var(--accent);
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    /* Empty State */
    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: var(--text-secondary);
    }
    
    .empty-state-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
        opacity: 0.5;
    }
    
    .empty-state-text {
        font-size: 1.1rem;
        max-width: 300px;
        margin: 0 auto;
        line-height: 1.6;
    }
    
    /* Footer */
    .app-footer {
        text-align: center;
        padding: 2rem 0;
        color: var(--text-secondary);
        font-size: 0.85rem;
        border-top: 1px solid var(--border-color);
        margin-top: 3rem;
    }
    
    .footer-brand {
        background: var(--gradient-1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    
    /* Last Updated */
    .last-updated {
        font-size: 0.75rem;
        color: var(--text-secondary);
        text-align: right;
        margin-top: 0.5rem;
    }
    
    /* Plotly Chart Override */
    .js-plotly-plot {
        border-radius: 16px !important;
        overflow: hidden !important;
    }
</style>
""", unsafe_allow_html=True)

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
            'AMD': 'AMD Inc.',
            'INTC': 'Intel Corporation',
            'MU': 'Micron Technology'
        }
        company_name = known_names.get(symbol, symbol)
    
    # Truncate if needed
    if len(company_name) > 25:
        company_name = company_name[:22] + "..."
    
    # Sector with fallback
    sector = profile.get('sector', '') or 'Stock'
    if sector == 'N/A':
        sector = 'Stock'
    
    return symbol, company_name, sector


def display_stock_card_streamlit(symbol: str, company_name: str, sector: str):
    """Display a stock card using Streamlit native components"""
    with st.container():
        st.markdown(f"**{symbol}** · {company_name}")
        st.caption(f"📊 {sector} · Tracking")

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

with st.sidebar:
    # Logo
    st.markdown("""
    <div class="logo-container">
        <div class="logo-icon">⚡</div>
        <div class="logo-text">Stock<span>Pulse</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Navigation
    page = st.radio(
        "Navigation",
        ["🏠 Dashboard", "📊 Portfolio", "🔔 Alerts", "⚙️ Settings", "🚀 Run Scan"],
        label_visibility="collapsed"
    )
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # User Card
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if user:
        holdings_count = db.query(UserHolding).filter(UserHolding.user_id == user.id).count()
        alerts_count = db.query(Notification).filter(Notification.user_id == user.id).count()
        
        st.markdown(f"""
        <div class="user-card">
            <div class="user-email">👤 {st.session_state.user_email}</div>
            <div class="user-status">
                <div class="status-dot"></div>
                Active
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Stocks", holdings_count)
        with col2:
            st.metric("Alerts", alerts_count)
    
    db.close()

# ===========================
# PAGE 1: DASHBOARD
# ===========================
if page == "🏠 Dashboard":
    # Market Pulse Header
    render_market_pulse()
    
    st.markdown('<p class="main-header">Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Real-time insights for your portfolio</p>', unsafe_allow_html=True)
    
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
        <div class="stat-card">
            <div class="stat-label">Tracked Stocks</div>
            <div class="stat-value">{len(holdings)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">Weekly Alerts</div>
            <div class="stat-value">{len(recent_alerts)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">High Impact</div>
            <div class="stat-value negative">{high_impact_alerts}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">Status</div>
            <div class="stat-value positive">{"✓" if user.active else "✗"}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
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
            # Display stock cards using Streamlit native components
            cols = st.columns(2)
            for idx, holding in enumerate(holdings):
                profile = get_company_profile_cached(holding.symbol)
                symbol, company_name, sector = render_stock_card(holding.symbol, profile)
                with cols[idx % 2]:
                    with st.container(border=True):
                        st.markdown(f"**{symbol}** · {company_name}")
                        st.caption(f"📊 {sector}")
        else:
            st.info("📊 No stocks in your portfolio yet. Head to Portfolio to add some!")
    
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
        # Grid of stock cards using Streamlit native components
        cols = st.columns(3)
        for idx, holding in enumerate(holdings):
            profile = get_company_profile_cached(holding.symbol)
            symbol, company_name, sector = render_stock_card(holding.symbol, profile)
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{symbol}**")
                    st.caption(f"{company_name}")
                    st.caption(f"📊 {sector}")
        
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