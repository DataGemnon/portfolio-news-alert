from typing import List, Dict, Set
from datetime import datetime, timedelta
from services.fmp_client import FMPClient
from config.settings import settings
import redis
import json


class BrokerUpgradesService:
    """
    Fetches and organizes recent broker upgrades/downgrades
    Separates portfolio stocks from market opportunities
    """
    
    def __init__(self):
        self.fmp = FMPClient()
        
        # Redis optionnel
        if settings.redis_url:
            try:
                self.redis_client = redis.from_url(settings.redis_url)
            except:
                self.redis_client = None
        else:
            self.redis_client = None
        
        # Major sectors/indices to monitor for market opportunities
        self.watchlist_symbols = [
            # Tech
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'AMD', 'TSLA', 'NFLX', 'ADBE',
            # Finance
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA',
            # Healthcare
            'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'TMO', 'LLY',
            # Consumer
            'WMT', 'HD', 'MCD', 'NKE', 'SBUX', 'DIS', 'COST',
            # Energy
            'XOM', 'CVX', 'COP', 'SLB',
            # Industrial
            'BA', 'CAT', 'GE', 'HON', 'UPS'
        ]
        
        # Top-tier brokers (their upgrades carry more weight)
        self.premium_brokers = [
            'Goldman Sachs', 'Morgan Stanley', 'JP Morgan', 'Bank of America',
            'Barclays', 'Deutsche Bank', 'Credit Suisse', 'UBS', 'Citi',
            'Wells Fargo Securities', 'Jefferies', 'Raymond James',
            'Evercore ISI', 'Bernstein', 'RBC Capital Markets'
        ]
    
    def get_recent_upgrades(self, portfolio_symbols: List[str], hours: int = 48) -> Dict:
        """
        Get recent broker upgrades/downgrades
        
        Args:
            portfolio_symbols: List of symbols in user's portfolio
            hours: Look back this many hours (default 48 = 2 days)
            
        Returns:
            Dict with 'portfolio' and 'market' upgrade lists
        """
        cache_key = f"broker_upgrades:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        # Check cache (1 hour) - si Redis disponible
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    return self._separate_portfolio_vs_market(cached_data, set(portfolio_symbols))
            except:
                pass
        
        # Combine portfolio symbols with watchlist
        all_symbols = list(set(portfolio_symbols + self.watchlist_symbols))
        
        print(f"  Fetching broker upgrades for {len(all_symbols)} symbols...")
        
        all_upgrades = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Fetch upgrades/downgrades for all symbols
        for symbol in all_symbols:
            try:
                analyst_data = self.fmp.get_price_targets(symbol)
                
                # Process rating changes (upgrades/downgrades)
                for rating in analyst_data.get('rating_changes', []):
                    try:
                        pub_date = datetime.strptime(rating.get('publishedDate', ''), '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time:
                            action = rating.get('action', '').lower()
                            
                            # Filter to upgrades only (or initiations with Buy rating)
                            if 'upgrade' in action or ('initiat' in action and 'buy' in rating.get('newGrade', '').lower()):
                                broker = rating.get('analystCompany', 'Unknown')
                                
                                # Calculate upgrade score (premium brokers get higher weight)
                                score = self._calculate_upgrade_score(rating, broker)
                                
                                upgrade_info = {
                                    'symbol': symbol,
                                    'broker': broker,
                                    'analyst': rating.get('analystName', 'Unknown'),
                                    'action': rating.get('action', 'Unknown'),
                                    'new_rating': rating.get('newGrade', 'N/A'),
                                    'previous_rating': rating.get('previousGrade', 'N/A'),
                                    'date': pub_date.strftime('%Y-%m-%d'),
                                    'timestamp': pub_date,
                                    'score': score,
                                    'is_premium_broker': any(premium in broker for premium in self.premium_brokers)
                                }
                                
                                all_upgrades.append(upgrade_info)
                    except Exception as e:
                        continue
                
                # Process price target increases (also positive signal)
                for target in analyst_data.get('price_targets', []):
                    try:
                        pub_date = datetime.strptime(target.get('publishedDate', ''), '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time:
                            # Get current price to calculate increase
                            current_price = target.get('priceWhenPosted', 0)
                            new_target = target.get('priceTarget', 0)
                            
                            if current_price and new_target and new_target > current_price:
                                increase_pct = ((new_target - current_price) / current_price) * 100
                                
                                # Only include significant increases (>10%)
                                if increase_pct >= 10:
                                    broker = target.get('analystCompany', 'Unknown')
                                    score = self._calculate_target_score(increase_pct, broker)
                                    
                                    upgrade_info = {
                                        'symbol': symbol,
                                        'broker': broker,
                                        'analyst': target.get('analystName', 'Unknown'),
                                        'action': 'Price Target Raised',
                                        'new_rating': f'Target ${new_target:.2f}',
                                        'price_target': new_target,
                                        'increase_pct': increase_pct,
                                        'date': pub_date.strftime('%Y-%m-%d'),
                                        'timestamp': pub_date,
                                        'score': score,
                                        'is_premium_broker': any(premium in broker for premium in self.premium_brokers)
                                    }
                                    
                                    all_upgrades.append(upgrade_info)
                    except Exception as e:
                        continue
            
            except Exception as e:
                print(f"    Error fetching upgrades for {symbol}: {e}")
                continue
        
        # Sort by score (highest first)
        all_upgrades.sort(key=lambda x: (x['score'], x['timestamp']), reverse=True)
        
        # Cache for 1 hour (si Redis disponible)
        if self.redis_client and all_upgrades:
            try:
                self.redis_client.setex(cache_key, 3600, json.dumps(all_upgrades, default=str))
            except:
                pass
        
        print(f"  Found {len(all_upgrades)} recent upgrades")
        
        # Separate portfolio vs market opportunities
        return self._separate_portfolio_vs_market(all_upgrades, set(portfolio_symbols))
    
    def _calculate_upgrade_score(self, rating: Dict, broker: str) -> float:
        """
        Calculate importance score for an upgrade
        Higher score = more important
        """
        score = 5.0  # Base score
        
        # Premium broker bonus
        if any(premium in broker for premium in self.premium_brokers):
            score += 3.0
        
        # New rating bonus
        new_rating = rating.get('newGrade', '').lower()
        if 'buy' in new_rating or 'outperform' in new_rating:
            score += 2.0
        elif 'strong buy' in new_rating or 'overweight' in new_rating:
            score += 3.0
        
        # Previous rating consideration
        prev_rating = rating.get('previousGrade', '').lower()
        if 'sell' in prev_rating or 'underperform' in prev_rating:
            # Upgrade from sell/underperform is very significant
            score += 2.0
        
        return score
    
    def _calculate_target_score(self, increase_pct: float, broker: str) -> float:
        """Calculate score for price target increase"""
        score = 3.0  # Base score (lower than rating upgrades)
        
        # Premium broker bonus
        if any(premium in broker for premium in self.premium_brokers):
            score += 2.0
        
        # Magnitude bonus
        if increase_pct >= 30:
            score += 3.0
        elif increase_pct >= 20:
            score += 2.0
        elif increase_pct >= 15:
            score += 1.0
        
        return score
    
    def _separate_portfolio_vs_market(self, all_upgrades: List[Dict], portfolio_symbols: Set[str]) -> Dict:
        """
        Separate upgrades into portfolio holdings vs market opportunities
        """
        portfolio_upgrades = []
        market_upgrades = []
        
        for upgrade in all_upgrades:
            if upgrade['symbol'] in portfolio_symbols:
                portfolio_upgrades.append(upgrade)
            else:
                market_upgrades.append(upgrade)
        
        return {
            'portfolio': portfolio_upgrades[:5],  # Top 5 for portfolio
            'market': market_upgrades[:10]  # Top 10 market opportunities
        }
    
    def get_upgrade_summary_stats(self, upgrades: Dict) -> Dict:
        """
        Get summary statistics about upgrades
        Useful for logging/debugging
        """
        portfolio_count = len(upgrades.get('portfolio', []))
        market_count = len(upgrades.get('market', []))
        
        # Count premium broker upgrades
        portfolio_premium = sum(1 for u in upgrades.get('portfolio', []) if u.get('is_premium_broker'))
        market_premium = sum(1 for u in upgrades.get('market', []) if u.get('is_premium_broker'))
        
        return {
            'total_portfolio_upgrades': portfolio_count,
            'total_market_upgrades': market_count,
            'portfolio_premium_brokers': portfolio_premium,
            'market_premium_brokers': market_premium,
            'has_upgrades': portfolio_count > 0 or market_count > 0
        }