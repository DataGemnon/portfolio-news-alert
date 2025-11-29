import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config.settings import settings
import redis
import json


class FMPClient:
    def __init__(self):
        self.api_key = settings.fmp_api_key
        self.base_url = settings.fmp_base_url
        
        # Redis optionnel
        if settings.redis_url:
            try:
                self.redis_client = redis.from_url(settings.redis_url)
            except:
                self.redis_client = None
        else:
            self.redis_client = None
        
        # 🆕 SOURCES DE HAUTE QUALITÉ UNIQUEMENT
        # Ces sources publient de vraies nouvelles financières, pas des opinions
        self.trusted_sources = [
            # Agences de presse financière (niveau premium)
            'reuters.com', 'bloomberg.com', 'wsj.com', 'ft.com',
            'marketwatch.com', 'barrons.com', 'cnbc.com',
            
            # Publications financières établies
            'investors.com', 'fortune.com', 'forbes.com',
            'businessinsider.com', 'thestreet.com',
            
            # Sources officielles d'entreprises
            'investor.', 'ir.', 'newsroom.',  # Ex: investor.nvidia.com
            
            # Publications économiques respectées
            'economist.com', 'financial-times.com',
            'morningstar.com', 'kiplinger.com'
        ]
        
        # 🆕 SOURCES À BLOQUER (blogs, clickbait, opinion)
        self.blocked_sources = [
            # Vidéos et réseaux sociaux
            'youtube.com', 'youtu.be', 'tiktok.com',
            'instagram.com', 'facebook.com',
            'reddit.com', 'twitter.com', 'x.com',
            
            # Blogs et agrégateurs de mauvaise qualité
            'seeking alpha', 'seekingalpha.com',  # Souvent des opinions d'amateurs
            'benzinga.com',  # Beaucoup de clickbait
            'fool.com', 'motleyfool.com',  # Titres sensationnalistes
            'zacks.com',  # Contenu promotionnel
            'stocktwits.com',
            
            # Blogs tech qui font du clickbait financier
            'techcrunch.com',  # ← Votre exemple !
            'gizmodo.com', 'engadget.com',
            'theverge.com', 'arstechnica.com',
            
            # Sites à contenu sponsorisé/promotionnel
            'investorplace.com',
            'gurufocus.com',
            'tipranks.com'  # Souvent promotionnel
        ]
        
        # 🆕 MOTS-CLÉS CLICKBAIT à éviter dans les titres
        self.clickbait_keywords = [
            'drama', 'war', 'battle', 'fight', 'slams', 'destroys',
            'you won\'t believe', 'shocking', 'mind-blowing',
            'this is why', 'here\'s why', 'the real reason',
            'what you need to know', 'everything you need',
            'will shock you', 'versus', 'vs.',
            'thanksgiving', 'christmas', 'holiday'  # Articles saisonniers non-pertinents
        ]
        
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request to FMP"""
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"FMP API Error: {e}")
            return []
    
    def _is_quality_source(self, news_item: Dict) -> bool:
        """
        🆕 Vérification renforcée de la qualité de la source
        
        Retourne True seulement si :
        1. La source est dans trusted_sources OU
        2. La source n'est PAS dans blocked_sources ET le titre n'est pas clickbait
        """
        site = news_item.get('site', '').lower()
        url = news_item.get('url', '').lower()
        title = news_item.get('title', '').lower()
        
        # Vérifier si dans les sources bloquées
        for blocked in self.blocked_sources:
            if blocked in site or blocked in url:
                return False
        
        # Vérifier si le titre contient du clickbait
        for keyword in self.clickbait_keywords:
            if keyword in title:
                return False
        
        # Si on est ici, c'est que :
        # - Pas dans blocked_sources
        # - Pas de clickbait dans le titre
        # → On accepte
        return True
    
    def _is_trusted_source(self, news_item: Dict) -> bool:
        """
        Vérifier si c'est une source premium (trusted)
        Ces sources sont toujours acceptées, même si le titre semble clickbait
        """
        site = news_item.get('site', '').lower()
        url = news_item.get('url', '').lower()
        
        for trusted in self.trusted_sources:
            if trusted in site or trusted in url:
                return True
        
        return False
    
    def _is_recent_actual_news(self, news_item: Dict, max_hours: int = 48) -> bool:
        """
        🆕 Vérifier si c'est une vraie nouvelle récente
        Pas un article d'opinion sur des événements passés
        """
        # Vérifier la date de publication
        pub_date_str = news_item.get('publishedDate', '')
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
            cutoff = datetime.utcnow() - timedelta(hours=max_hours)
            
            if pub_date < cutoff:
                return False
        except:
            # Si impossible de parser la date, on rejette
            return False
        
        # Vérifier que le texte contient des indicateurs de news factuelles
        text = (news_item.get('text', '') + ' ' + news_item.get('title', '')).lower()
        
        # Indicateurs de vraies news
        news_indicators = [
            'announced', 'reports', 'filing', 'sec', 'earnings',
            'revenue', 'profit', 'quarter', 'fiscal', 'guidance',
            'upgrade', 'downgrade', 'initiated', 'price target',
            'merger', 'acquisition', 'partnership', 'deal',
            'appointed', 'ceo', 'cfo', 'executive',
            'fda', 'approved', 'regulatory', 'investigation'
        ]
        
        # Indicateurs d'opinion/éditorial (à éviter)
        opinion_indicators = [
            'may be', 'could be', 'might', 'perhaps', 'opinion',
            'i think', 'we believe', 'in my view', 'analysis',
            'commentary', 'perspective', 'should you', 'why you should'
        ]
        
        has_news = any(indicator in text for indicator in news_indicators)
        has_opinion = any(indicator in text for indicator in opinion_indicators)
        
        # Accepter si c'est une vraie news, rejeter si c'est principalement opinion
        if has_news and not has_opinion:
            return True
        elif has_opinion and not has_news:
            return False
        else:
            # Cas ambigu → On fait confiance à la source
            return self._is_trusted_source(news_item)
    
    def get_stock_news(self, tickers: List[str] = None, limit: int = 50) -> List[Dict]:
        """
        Get stock news for specific tickers or general news
        🆕 Avec filtrage renforcé
        """
        cache_key = f"fmp_news:{','.join(tickers) if tickers else 'general'}:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        # Check cache (si Redis disponible)
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        if tickers:
            # Get news for specific tickers
            params = {
                'tickers': ','.join(tickers),
                'limit': limit * 2  # 🆕 Demander plus car on va filtrer
            }
            news = self._make_request('/v3/stock_news', params)
        else:
            # Get general market news
            params = {'limit': limit * 2}
            news = self._make_request('/v4/general_news', params)
        
        # 🆕 FILTRAGE EN 3 ÉTAPES
        quality_news = []
        for item in news:
            # Étape 1 : Source bloquée ?
            if not self._is_quality_source(item):
                continue
            
            # Étape 2 : Vraie news récente ?
            if not self._is_recent_actual_news(item):
                continue
            
            # Étape 3 : OK, on garde
            quality_news.append(item)
        
        # Limiter au nombre demandé
        quality_news = quality_news[:limit]
        
        # Cache for 1 hour (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 3600, json.dumps(quality_news))
            except:
                pass
        
        print(f"    Filtered {len(news)} → {len(quality_news)} quality news items")
        
        return quality_news
    
    def get_press_releases(self, symbol: str, limit: int = 20) -> List[Dict]:
        """Get press releases for a specific symbol"""
        cache_key = f"fmp_press:{symbol}:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        params = {'limit': limit}
        releases = self._make_request(f'/v3/press-releases/{symbol}', params)
        
        # Cache for 6 hours (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 21600, json.dumps(releases))
            except:
                pass
        
        return releases
    
    def get_price_targets(self, symbol: str) -> Dict:
        """
        Get analyst price targets and upgrades/downgrades
        Returns recent analyst actions with ratings and price targets
        """
        cache_key = f"fmp_price_target:{symbol}:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        # Get price targets
        targets = self._make_request(f'/v4/price-target', {'symbol': symbol})
        
        # Get upgrades/downgrades
        upgrades = self._make_request(f'/v4/upgrades-downgrades', {'symbol': symbol})
        
        # Combine both
        combined = {
            'price_targets': targets if isinstance(targets, list) else [],
            'rating_changes': upgrades if isinstance(upgrades, list) else []
        }
        
        # Cache for 2 hours (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 7200, json.dumps(combined))
            except:
                pass
        
        return combined
    
    def get_analyst_estimates(self, symbol: str) -> Dict:
        """Get analyst earnings estimates and consensus"""
        cache_key = f"fmp_estimates:{symbol}:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        estimates = self._make_request(f'/v3/analyst-estimates/{symbol}')
        
        # Cache for 24 hours (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 86400, json.dumps(estimates))
            except:
                pass
        
        return estimates
    
    def get_sec_filings(self, symbol: str = None, filing_type: str = None) -> List[Dict]:
        """
        Get SEC filings
        filing_type examples: '8-K', '10-K', '10-Q', '13F'
        8-K = Material events (most important for real-time alerts)
        """
        params = {'limit': 20}
        if symbol:
            params['symbol'] = symbol
        if filing_type:
            params['type'] = filing_type
            
        return self._make_request('/v4/sec_filing', params)
    
    def get_earnings_calendar(self, from_date: str = None, to_date: str = None) -> List[Dict]:
        """
        Get earnings calendar
        Dates in format: YYYY-MM-DD
        """
        if not from_date:
            from_date = datetime.utcnow().strftime('%Y-%m-%d')
        if not to_date:
            to_date = (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        params = {
            'from': from_date,
            'to': to_date
        }
        
        return self._make_request('/v3/earning_calendar', params)
    
    def get_insider_trading(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get insider trading activity for a symbol"""
        params = {'symbol': symbol, 'limit': limit}
        return self._make_request(f'/v4/insider-trading', params)
    
    def get_stock_quote(self, symbol: str) -> Dict:
        """Get current stock price and basic info"""
        cache_key = f"fmp_quote:{symbol}:{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        quote = self._make_request(f'/v3/quote/{symbol}')
        result = quote[0] if isinstance(quote, list) and len(quote) > 0 else {}
        
        # Cache for 5 minutes (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 300, json.dumps(result))
            except:
                pass
        
        return result
    
    def filter_recent_news(self, news_items: List[Dict], hours: int = None) -> List[Dict]:
        """Filter news to only recent items"""
        if hours is None:
            hours = settings.news_lookback_hours
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        filtered = []
        
        for item in news_items:
            # FMP uses 'publishedDate' field
            pub_date_str = item.get('publishedDate', '')
            try:
                # Parse datetime (FMP format: 2024-01-15 10:30:00)
                pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                if pub_date >= cutoff:
                    filtered.append(item)
            except ValueError:
                # If date parsing fails, include the item to be safe
                filtered.append(item)
        
        return filtered
    
    def get_portfolio_news(self, symbols: List[str], hours: int = None) -> List[Dict]:
        """Get recent news for a portfolio of symbols"""
        all_news = []
        
        # Batch symbols in groups of 5 to avoid overwhelming the API
        batch_size = 5
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            news = self.get_stock_news(tickers=batch, limit=100)
            all_news.extend(news)
        
        # Filter to recent news
        recent_news = self.filter_recent_news(all_news, hours)
        
        # Remove duplicates by URL
        seen_urls = set()
        unique_news = []
        for item in recent_news:
            url = item.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_news.append(item)
        
        return unique_news
    
    def get_portfolio_analyst_updates(self, symbols: List[str], hours: int = 24) -> Dict:
        """
        Get all recent analyst updates (price targets, upgrades/downgrades) for portfolio
        Returns dict mapping symbol -> analyst updates
        """
        updates = {}
        
        for symbol in symbols:
            analyst_data = self.get_price_targets(symbol)
            recent_data = self.filter_recent_analyst_actions(analyst_data, hours)
            
            # Only include if there are recent updates
            if recent_data['price_targets'] or recent_data['rating_changes']:
                updates[symbol] = recent_data
        
        return updates
    
    def filter_recent_analyst_actions(self, analyst_data: Dict, hours: int = 24) -> Dict:
        """Filter analyst price targets and rating changes to recent only"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        filtered = {
            'price_targets': [],
            'rating_changes': []
        }
        
        # Filter price targets
        for target in analyst_data.get('price_targets', []):
            try:
                pub_date = datetime.strptime(target.get('publishedDate', ''), '%Y-%m-%d %H:%M:%S')
                if pub_date >= cutoff:
                    filtered['price_targets'].append(target)
            except:
                pass
        
        # Filter rating changes
        for change in analyst_data.get('rating_changes', []):
            try:
                pub_date = datetime.strptime(change.get('publishedDate', ''), '%Y-%m-%d %H:%M:%S')
                if pub_date >= cutoff:
                    filtered['rating_changes'].append(change)
            except:
                pass
        
        return filtered