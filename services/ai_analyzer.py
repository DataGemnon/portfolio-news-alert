import anthropic
import json
from typing import Dict, Optional
from config.settings import settings
import redis


class AIAnalyzer:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        
        # Redis optionnel (pas disponible sur Streamlit Cloud)
        if settings.redis_url:
            try:
                self.redis_client = redis.from_url(settings.redis_url)
            except:
                self.redis_client = None
        else:
            self.redis_client = None
        
        self.model = "claude-sonnet-4-20250514"
    
    def analyze_news_impact(self, news_item: Dict, user_holding: Optional[Dict] = None) -> Dict:
        """
        Analyze a news article's potential impact on a stock
        
        Args:
            news_item: Dict with keys: symbol, title, text, publishedDate, site
            user_holding: Optional dict with quantity, avg_cost
            
        Returns:
            Dict with impact_score, sentiment, urgency, category, summary, affected_sector
        """
        # Check cache (si Redis disponible)
        cache_key = f"analysis:{news_item.get('url', '')}"
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass  # Pas grave si cache non dispo
        
        # Prepare context
        symbol = news_item.get('symbol', 'Unknown')
        title = news_item.get('title', '')
        content = news_item.get('text', '')[:2000]  # Limit content length
        source = news_item.get('site', '')
        
        holding_context = ""
        if user_holding:
            holding_context = f"\nUser Position: Holds {user_holding.get('quantity', 0)} shares at avg cost ${user_holding.get('avg_cost', 0)}"
        
        prompt = f"""Analyze this financial news article for investment impact:

Symbol: {symbol}
Title: {title}
Source: {source}
Content: {content}
{holding_context}

Provide a structured analysis with the following:

1. **Impact Score** (0-10 scale):
   - 0-2: Negligible impact
   - 3-4: Minor impact
   - 5-6: Moderate impact
   - 7-8: Significant impact
   - 9-10: Major/Critical impact

2. **Sentiment** (-2 to +2 scale):
   - -2: Very Negative
   - -1: Negative
   - 0: Neutral
   - +1: Positive
   - +2: Very Positive

3. **Urgency** (choose one):
   - Immediate: Requires attention within hours
   - Hours: Actionable within 24 hours
   - Days: Monitor over several days
   - Long-term: Weeks to months timeframe

4. **Category** (choose one):
   - Earnings: Earnings reports, guidance, surprises
   - Management: Leadership changes, strategy shifts
   - Regulatory: Legal, compliance, government action
   - Product: New products, services, innovations
   - Market: Macro conditions, sector trends
   - Legal: Lawsuits, investigations
   - M&A: Mergers, acquisitions, partnerships
   - Financial: Debt, buybacks, dividends
   - Other: Doesn't fit above categories

5. **Summary**: Maximum 10 words - ultra-concise headline
   - Use keywords: "Q4 earnings beat, guidance raised"
   - NOT: "The company reported better than expected earnings..."
   - Examples:
     * "Beats Q3 EPS $2.50 vs $2.30 expected"
     * "CEO resigns, stock down 8%"
     * "FDA approves new drug, revenue boost expected"
     * "Upgraded to Buy, $300 target"

6. **Keywords**: 3-5 key terms (comma-separated)
   - Example: "earnings beat, guidance up, revenue growth"

7. **Affected Sector**: If this news impacts a broader sector beyond the single stock, name it (e.g., "Technology", "Banking", "Energy"). Otherwise, say "Individual Stock Only"

Respond ONLY with valid JSON in this exact format:
{{
    "impact_score": <number 0-10>,
    "sentiment": <number -2 to 2>,
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "category": "<category>",
    "summary": "<10 words max>",
    "keywords": "<3-5 keywords>",
    "affected_sector": "<sector or 'Individual Stock Only'>"
}}

Do not include any text before or after the JSON."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_token