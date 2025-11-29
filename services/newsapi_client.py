from newsapi import NewsApiClient
from datetime import datetime, timedelta
from typing import List, Dict
from config.settings import settings
import redis
import json


class NewsAPIClient:
    """
    High-quality macro news from premium sources
    Uses NewsAPI for Reuters, Bloomberg, WSJ, CNBC, etc.
    """
    
    def __init__(self):
        self.client = NewsApiClient(api_key=settings.newsapi_key)
        self.redis_client = redis.from_url(settings.redis_url) if settings.redis_url else None
        
        # Premium sources for financial/macro news
        self.premium_sources = [
            'reuters',
            'bloomberg',
            'the-wall-street-journal',
            'cnbc',
            'financial-times',
            'fortune',
            'business-insider'
        ]
        
        # Blocked sources (low quality, spam, video)
        self.blocked_sources = [
            'youtube', 'tiktok', 'instagram', 'facebook',
            'reddit', 'twitter', 'x.com',
            'seeking alpha', 'benzinga',  # Often clickbait
            'yahoo', 'marketwatch'  # Lower quality than premium sources
        ]
        
        # Critical macro keywords
        self.macro_keywords = {
            'fed': ['federal reserve', 'fomc', 'jerome powell', 'interest rate decision'],
            'treasury': ['treasury secretary', 'janet yellen', 'debt ceiling'],
            'inflation': ['cpi', 'inflation', 'consumer price index', 'ppi'],
            'jobs': ['jobs report', 'unemployment', 'nonfarm payroll', 'labor market'],
            'gdp': ['gdp', 'economic growth', 'recession'],
            'crisis': ['banking crisis', 'financial crisis', 'market crash', 'correction']
        }
    
    def get_macro_news(self, hours: int = 24, max_articles: int = 50) -> List[Dict]:
        """
        Get high-quality macro news from premium sources
        
        Args:
            hours: Look back this many hours
            max_articles: Maximum number of articles to return
            
        Returns:
            List of news articles with macro relevance
        """
        cache_key = f"newsapi_macro:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        # Check cache
        if self.redis_client:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        from_date = (datetime.utcnow() - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%S')
        all_articles = []
        
        # Search for each category of macro news
        for category, keywords in self.macro_keywords.items():
            for keyword in keywords[:2]:  # Limit to avoid hitting API limits
                try:
                    results = self.client.get_everything(
                        q=keyword,
                        sources=','.join(self.premium_sources[:5]),  # Top 5 sources
                        language='en',
                        from_param=from_date,
                        sort_by='publishedAt',
                        page_size=10
                    )
                    
                    if results.get('status') == 'ok':
                        articles = results.get('articles', [])
                        for article in articles:
                            article['macro_category'] = category.replace('_', ' ').title()
                            all_articles.append(article)
                
                except Exception as e:
                    print(f"NewsAPI error for '{keyword}': {e}")
                    continue
        
        # Remove duplicates by URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)
        
        # Sort by published date (most recent first)
        unique_articles.sort(
            key=lambda x: x.get('publishedAt', ''),
            reverse=True
        )
        
        # Limit results
        unique_articles = unique_articles[:max_articles]
        
        # Cache for 1 hour
        if self.redis_client:
            self.redis_client.setex(cache_key, 3600, json.dumps(unique_articles))
        
        return unique_articles
    
    def get_fed_news(self, hours: int = 24) -> List[Dict]:
        """Get news specifically about Federal Reserve"""
        cache_key = f"newsapi_fed:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        if self.redis_client:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        from_date = (datetime.utcnow() - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%S')
        
        try:
            results = self.client.get_everything(
                q='federal reserve OR fomc OR jerome powell OR fed chairman',
                sources=','.join(self.premium_sources),
                language='en',
                from_param=from_date,
                sort_by='relevancy',
                page_size=20
            )
            
            articles = results.get('articles', []) if results.get('status') == 'ok' else []
            
            for article in articles:
                article['macro_category'] = 'Federal Reserve'
            
            # Cache for 1 hour
            if self.redis_client:
                self.redis_client.setex(cache_key, 3600, json.dumps(articles))
            
            return articles
            
        except Exception as e:
            print(f"NewsAPI Fed news error: {e}")
            return []
    
    def format_for_analysis(self, newsapi_article: Dict) -> Dict:
        """
        Convert NewsAPI format to our standard format
        Makes it compatible with existing analysis code
        Also filters out blocked sources
        """
        source_name = newsapi_article.get('source', {}).get('name', 'Unknown').lower()
        
        # Check if source is blocked
        if any(blocked in source_name for blocked in self.blocked_sources):
            return None  # Signal to skip this article
        
        return {
            'title': newsapi_article.get('title', ''),
            'text': newsapi_article.get('description', '') + ' ' + newsapi_article.get('content', ''),
            'url': newsapi_article.get('url', ''),
            'site': newsapi_article.get('source', {}).get('name', 'Unknown'),
            'publishedDate': self._convert_datetime(newsapi_article.get('publishedAt', '')),
            'image': newsapi_article.get('urlToImage', ''),
            'macro_category': newsapi_article.get('macro_category', 'Economic'),
            'author': newsapi_article.get('author', 'Unknown')
        }
    
    def _convert_datetime(self, iso_datetime: str) -> str:
        """Convert ISO datetime to our format (YYYY-MM-DD HH:MM:SS)"""
        try:
            dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')