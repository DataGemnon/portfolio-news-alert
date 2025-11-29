from datetime import datetime
from typing import List, Dict
from services.newsapi_client import NewsAPIClient
from services.fred_client import FREDClient
from services.yahoo_finance_client import YahooFinanceClient
from services.fed_scraper import FedScraper


class MacroMonitor:
    """
    Orchestrates multiple data sources for comprehensive macro monitoring
    Sources: NewsAPI (macro news), FRED (economic data), Yahoo (market data), Fed.gov (official)
    """
    
    def __init__(self):
        self.newsapi = NewsAPIClient()
        self.fred = FREDClient()
        self.yahoo = YahooFinanceClient()
        self.fed_scraper = FedScraper()
    
    def get_comprehensive_macro_snapshot(self) -> Dict:
        """
        Get complete macro picture from all sources
        This is the main entry point for macro monitoring
        """
        print("    Fetching from multiple sources...")
        
        snapshot = {
            # Market conditions (Yahoo Finance - real-time)
            'market_indices': self.yahoo.get_market_snapshot(),
            'market_anomalies': self.yahoo.detect_market_anomalies(),
            
            # Economic indicators (FRED - official data)
            'economic_indicators': self.fred.get_latest_values(),
            'significant_economic_changes': self.fred.detect_significant_changes(),
            'yield_curve': self.fred.get_yield_curve_status(),
            
            # News (NewsAPI - premium sources)
            'macro_news': self.newsapi.get_macro_news(hours=24),
            'fed_news': self.newsapi.get_fed_news(hours=24),
            
            # Official Fed communications (Fed.gov - direct source)
            'fed_announcements': self.fed_scraper.get_press_releases(days_back=7),
            'fed_speeches': self.fed_scraper.get_chair_speeches(days_back=7),
            
            'timestamp': datetime.utcnow().isoformat(),
            'sources_used': ['NewsAPI', 'FRED', 'Yahoo Finance', 'Federal Reserve']
        }
        
        print(f"    ✓ Market data: {len(snapshot['market_indices'])} indices")
        print(f"    ✓ Economic indicators: {len(snapshot['economic_indicators'])} series")
        print(f"    ✓ Macro news: {len(snapshot['macro_news'])} articles")
        print(f"    ✓ Fed updates: {len(snapshot['fed_announcements'])} announcements")
        
        return snapshot
    
    def filter_high_impact_macro_events(self, macro_snapshot: Dict) -> List[Dict]:
        """
        Filter to only truly significant macro events
        Pre-filter before sending to expensive AI analysis
        """
        high_impact_events = []
        
        # 1. MARKET ANOMALIES (from Yahoo Finance)
        anomalies = macro_snapshot.get('market_anomalies', [])
        for anomaly in anomalies:
            severity = anomaly.get('severity', 'low')
            if severity in ['critical', 'high']:
                high_impact_events.append({
                    'type': 'market_anomaly',
                    'data': anomaly,
                    'timestamp': datetime.utcnow().isoformat(),
                    'source': 'Yahoo Finance'
                })
        
        # 2. ECONOMIC DATA SURPRISES (from FRED)
        econ_changes = macro_snapshot.get('significant_economic_changes', [])
        for change in econ_changes:
            # Only include critical indicators or major changes
            if change.get('importance') == 'critical' or change.get('significance') == 'high':
                high_impact_events.append({
                    'type': 'economic_surprise',
                    'data': change,
                    'timestamp': datetime.utcnow().isoformat(),
                    'source': 'FRED'
                })
        
        # 3. YIELD CURVE INVERSION (from FRED)
        yield_curve = macro_snapshot.get('yield_curve', {})
        if yield_curve.get('inverted', False):
            high_impact_events.append({
                'type': 'yield_curve_inversion',
                'data': yield_curve,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'FRED',
                'warning': 'Historically precedes recession'
            })
        
        # 4. OFFICIAL FED ANNOUNCEMENTS (from Fed.gov)
        fed_announcements = macro_snapshot.get('fed_announcements', [])
        for announcement in fed_announcements:
            if announcement.get('importance') in ['critical', 'high']:
                high_impact_events.append({
                    'type': 'fed_announcement',
                    'data': announcement,
                    'timestamp': announcement.get('published_date'),
                    'source': 'Federal Reserve'
                })
        
        # 5. FED CHAIR SPEECHES (from Fed.gov)
        speeches = macro_snapshot.get('fed_speeches', [])
        for speech in speeches:
            if speech.get('is_chair', False):  # Only Powell speeches
                high_impact_events.append({
                    'type': 'fed_speech',
                    'data': speech,
                    'timestamp': speech.get('published_date'),
                    'source': 'Federal Reserve'
                })
        
        # 6. HIGH-QUALITY MACRO NEWS (from NewsAPI)
        # Fed news from premium sources
        fed_news = macro_snapshot.get('fed_news', [])
        for news in fed_news[:5]:  # Top 5 most relevant
            title = news.get('title', '').lower()
            
            # High priority terms
            critical_terms = [
                'fed raises', 'fed cuts', 'rate decision', 'fomc decides',
                'powell warns', 'emergency', 'crisis'
            ]
            
            if any(term in title for term in critical_terms):
                formatted_news = self.newsapi.format_for_analysis(news)
                high_impact_events.append({
                    'type': 'macro_news',
                    'data': formatted_news,
                    'timestamp': formatted_news.get('publishedDate'),
                    'source': f"NewsAPI ({formatted_news.get('site')})"
                })
        
        # General macro news - more selective
        macro_news = macro_snapshot.get('macro_news', [])
        for news in macro_news[:10]:  # Top 10
            title = news.get('title', '').lower()
            source = news.get('source', {}).get('name', '').lower()
            
            # Only from top-tier sources
            premium = any(s in source for s in ['reuters', 'bloomberg', 'wall street'])
            
            if premium:
                # Critical terms for general macro news
                critical_macro = [
                    'inflation surge', 'recession', 'banking crisis',
                    'jobs report beats', 'jobs report misses', 'gdp contracts',
                    'cpi spike', 'unemployment surge'
                ]
                
                if any(term in title for term in critical_macro):
                    formatted_news = self.newsapi.format_for_analysis(news)
                    high_impact_events.append({
                        'type': 'macro_news',
                        'data': formatted_news,
                        'timestamp': formatted_news.get('publishedDate'),
                        'source': f"NewsAPI ({formatted_news.get('site')})"
                    })
        
        print(f"    Filtered to {len(high_impact_events)} high-impact events")
        return high_impact_events