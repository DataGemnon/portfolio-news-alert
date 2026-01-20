import anthropic
import json
import asyncio
from typing import Dict, Optional, List
from config.settings import settings

try:
    import redis
except ImportError:
    redis = None


class AIAnalyzer:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        
        # Redis optionnel (pas disponible sur Streamlit Cloud)
        if settings.redis_url and redis is not None:
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
                pass
        
        # Prepare context
        symbol = news_item.get('symbol', 'Unknown')
        title = news_item.get('title', '')
        content = news_item.get('text', '')[:2000]
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

6. **Keywords**: 3-5 key terms (comma-separated)

7. **Affected Sector**: If this news impacts a broader sector beyond the single stock, name it. Otherwise, say "Individual Stock Only"

Respond ONLY with valid JSON in this exact format:
{{
    "impact_score": <number 0-10>,
    "sentiment": <number -2 to 2>,
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "category": "<category>",
    "summary": "<10 words max>",
    "keywords": "<3-5 keywords>",
    "affected_sector": "<sector or Individual Stock Only>"
}}

Do not include any text before or after the JSON."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            result.setdefault('impact_score', 5)
            result.setdefault('sentiment', 0)
            result.setdefault('urgency', 'Days')
            result.setdefault('category', 'Other')
            result.setdefault('summary', title[:150])
            result.setdefault('affected_sector', 'Individual Stock Only')
            
            if self.redis_client:
                try:
                    self.redis_client.setex(cache_key, 86400, json.dumps(result))
                except:
                    pass
            
            return result
            
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            words = title.split()[:10] if title else []
            short_summary = ' '.join(words) if words else 'News update'
            
            return {
                'impact_score': 5,
                'sentiment': 0,
                'urgency': 'Days',
                'category': 'Other',
                'summary': short_summary,
                'keywords': 'market, update, news',
                'affected_sector': 'Individual Stock Only'
            }
    async def analyze_news_impact_async(self, news_item: Dict, user_holding: Optional[Dict] = None) -> Dict:
        """Async version of analyze_news_impact"""
        # Check cache
        cache_key = f"analysis:{news_item.get('url', '')}"
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        # Prepare context
        symbol = news_item.get('symbol', 'Unknown')
        title = news_item.get('title', '')
        content = news_item.get('text', '')[:2000]
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

6. **Keywords**: 3-5 key terms (comma-separated)

7. **Affected Sector**: If this news impacts a broader sector beyond the single stock, name it. Otherwise, say "Individual Stock Only"

Respond ONLY with valid JSON in this exact format:
{{
    "impact_score": <number 0-10>,
    "sentiment": <number -2 to 2>,
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "category": "<category>",
    "summary": "<10 words max>",
    "keywords": "<3-5 keywords>",
    "affected_sector": "<sector or Individual Stock Only>"
}}

Do not include any text before or after the JSON."""

        try:
            message = await self.async_client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Set defaults
            result.setdefault('impact_score', 5)
            result.setdefault('sentiment', 0)
            result.setdefault('urgency', 'Days')
            result.setdefault('category', 'Other')
            result.setdefault('summary', title[:150])
            result.setdefault('affected_sector', 'Individual Stock Only')
            
            if self.redis_client:
                try:
                    self.redis_client.setex(cache_key, 86400, json.dumps(result))
                except:
                    pass
            
            return result
            
        except Exception as e:
            print(f"Async AI Analysis Error: {e}")
            words = title.split()[:10] if title else []
            short_summary = ' '.join(words) if words else 'News update'
            
            return {
                'impact_score': 5,
                'sentiment': 0,
                'urgency': 'Days',
                'category': 'Other',
                'summary': short_summary,
                'keywords': 'market, update, news',
                'affected_sector': 'Individual Stock Only'
            }
    async def batch_analyze_async(self, news_items: list, user_holdings: Dict = None) -> list:
        """Analyze multiple news items in parallel (async)"""
        if not news_items:
            return []
            
        tasks = []
        for news in news_items:
            symbol = news.get('symbol', '')
            holding = user_holdings.get(symbol) if user_holdings else None
            tasks.append(self.analyze_news_impact_async(news, holding))
            
        # Run all analysis tasks in parallel
        analyses = await asyncio.gather(*tasks)
        
        # Merge results back into news items
        results = []
        for news, analysis in zip(news_items, analyses):
            news_with_analysis = {**news, 'analysis': analysis}
            results.append(news_with_analysis)
        
        return results

    def batch_analyze(self, news_items: list, user_holdings: Dict = None) -> list:
        """Analyze multiple news items (legacy sync)"""
        results = []
        
        for news in news_items:
            symbol = news.get('symbol', '')
            holding = user_holdings.get(symbol) if user_holdings else None
            analysis = self.analyze_news_impact(news, holding)
            news_with_analysis = {**news, 'analysis': analysis}
            results.append(news_with_analysis)
        
        return results
    
    def should_notify(self, analysis: Dict) -> bool:
        """Determine if the news warrants a notification"""
        impact_score = analysis.get('impact_score', 0)
        urgency = analysis.get('urgency', 'Days')
        
        if impact_score >= settings.impact_threshold:
            return True
        
        if urgency in ['Immediate', 'Hours'] and impact_score >= 4:
            return True
        
        return False

        return False

    def analyze_macro_impact(self, title: str, text: str = "") -> Dict:
        """
        Analyze general news to detect HIGH IMPACT global market events
        (e.g., Tariffs, Geopolitics, Federal Reserve, Major Policy)
        """
        # Check cache
        cache_key = f"macro_analysis_v2:{hash(title)}"
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        prompt = f"""Analyze this news headline for GLOBAL MARKET IMPACT:
        
        Headline: "{title}"
        Context: "{text[:300]}"
        
        Determine if this is a "Significant Global Market Event" that affects the BROADER MARKET (S&P 500, Nasdaq, Global Trade).
        Examples of YES: 
        - US imposes tariffs on China/Mexico/Canada
        - Federal Reserve raises/cuts rates
        - Major geopolitical conflict outbreak
        - President signs major economic legislation
        - US Bans export of chips
        
        Examples of NO:
        - Individual stock earnings (e.g. "Apple earnings beat") -> NO, unless it crashes the whole market
        - Minor economic data
        - Opinion pieces
        
        Respond ONLY with a JSON using this structure:
        {{
            "is_global_event": <true/false>,
            "category": "<Geopolitics|Trade|Monetary Policy|Economy|Regulation>",
            "impact_score": <1-10>,
            "summary": "<Very short summary>"
        }}
        """
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Cache (longer duration for macro events as they don't change status)
            if self.redis_client:
                try:
                    self.redis_client.setex(cache_key, 86400 * 2, json.dumps(result))
                except:
                    pass
            
            return result
            
        except Exception as e:
            print(f"AI Macro Analysis Error: {e}")
            return {
                "is_global_event": False,
                "category": "Other",
                "impact_score": 0,
                "summary": "Error analyzing"
            }

    def extract_broker_rating(self, title: str, text: str = "", symbol: str = None) -> Dict:
        """
        Extract structured broker data from a headline using AI
        Used when regex fails to identify broker or rating details
        """
        # Check cache if available (cache key based on title + symbol)
        cache_key = f"broker_extract_v2:{hash(title)}:{symbol or 'ANY'}"
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
                
        # Construct prompt
        context_instruction = ""
        if symbol:
            context_instruction = f"""
            CRITICAL INSTRUCTION:
            You are analyzing this news specifically for the stock **{symbol}**.
            - If the rating change/action is NOT for {symbol} (e.g. it is for a competitor or another company mentioned), return "action": "N/A".
            - Example: If headline is "Qualcomm Downgrade flags Apple risk" and symbol is "AAPL", action is "N/A" (because Qualcomm was downgraded, not Apple).
            """

        prompt = f"""Extract broker rating details from this financial news headline:
        {context_instruction}
        
        Headline: "{title}"
        Context: "{text[:500]}"
        
        Identify:
        1. Broker Name (e.g. Goldman Sachs, Mizuho, Raymond James)
        2. Action (Upgrade, Downgrade, Initiate, Reiterate, etc.)
        3. Old Rating (if mentioned, otherwise "N/A")
        4. New Rating (Buy, Sell, Hold, Outperform, etc., otherwise "N/A")
        5. Old Price Target (if mentioned, extract value e.g. "150", otherwise "N/A")
        6. New Price Target (if mentioned, extract value e.g. "180", otherwise "N/A")
        
        Respond ONLY with a JSON object:
        {{
            "broker": "Name",
            "action": "Action",
            "old_rating": "Rating",
            "new_rating": "Rating",
            "old_target": "Price",
            "new_target": "Price"
        }}
        """
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            # Clean potential markdown
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Cache result
            if self.redis_client:
                try:
                    self.redis_client.setex(cache_key, 86400 * 7, json.dumps(result)) # Cache for 7 days
                except:
                    pass
            
            return result
            
        except Exception as e:
            print(f"AI Extraction Error: {e}")
            return {
                "broker": "Analyst",
                "action": "N/A",
                "old_rating": "N/A",
                "new_rating": "N/A",
                "old_target": "N/A",
                "new_target": "N/A"
            }