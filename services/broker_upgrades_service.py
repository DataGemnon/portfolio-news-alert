"""
Enhanced Broker Rating Changes Service
Captures BOTH upgrades AND downgrades (critical for portfolio monitoring)

Fixed issue: Previous version only captured upgrades, missing important 
downgrades like Morgan Stanley's Tesla downgrade on Dec 10, 2025.
"""

from typing import List, Dict, Set
from datetime import datetime, timedelta
from services.fmp_client import FMPClient
from config.settings import settings
import redis
import json


class BrokerUpgradesService:
    """
    Fetches and organizes recent broker rating changes (upgrades AND downgrades)
    Separates portfolio stocks from market opportunities
    
    IMPORTANT: This service now captures BOTH upgrades and downgrades
    since both are critical signals for traders.
    """
    
    def __init__(self):
        self.fmp = FMPClient()
        
        # Redis optional
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
        
        # Top-tier brokers (their rating changes carry more weight)
        self.premium_brokers = [
            'Goldman Sachs', 'Morgan Stanley', 'JP Morgan', 'JPMorgan',
            'Bank of America', 'BofA Securities', 'Merrill Lynch',
            'Barclays', 'Deutsche Bank', 'Credit Suisse', 'UBS', 'Citi', 'Citigroup',
            'Wells Fargo', 'Wells Fargo Securities', 'Jefferies', 'Raymond James',
            'Evercore ISI', 'Evercore', 'Bernstein', 'Sanford C. Bernstein',
            'RBC Capital Markets', 'RBC', 'HSBC', 'Societe Generale', 'BNP Paribas',
            'Piper Sandler', 'Wedbush', 'Oppenheimer', 'Needham', 'Stifel'
        ]
        
        # Rating classifications
        self.bullish_ratings = [
            'buy', 'strong buy', 'outperform', 'overweight', 'positive',
            'accumulate', 'add', 'sector outperform', 'market outperform',
            'conviction buy', 'top pick'
        ]
        
        self.bearish_ratings = [
            'sell', 'strong sell', 'underperform', 'underweight', 'negative',
            'reduce', 'avoid', 'sector underperform', 'market underperform'
        ]
        
        self.neutral_ratings = [
            'hold', 'neutral', 'equal-weight', 'equal weight', 'market perform',
            'sector perform', 'in-line', 'inline', 'peer perform', 'mixed'
        ]
    
    def _classify_rating(self, rating: str) -> str:
        """Classify a rating as bullish, bearish, or neutral"""
        rating_lower = rating.lower().strip()
        
        if any(bull in rating_lower for bull in self.bullish_ratings):
            return 'bullish'
        elif any(bear in rating_lower for bear in self.bearish_ratings):
            return 'bearish'
        elif any(neut in rating_lower for neut in self.neutral_ratings):
            return 'neutral'
        else:
            return 'unknown'
    
    def _determine_action_type(self, action: str, old_rating: str, new_rating: str) -> str:
        """
        Determine if this is an upgrade, downgrade, or initiation
        
        Returns: 'upgrade', 'downgrade', 'initiated', or 'reiterated'
        """
        action_lower = action.lower()
        
        # Check explicit action keywords first
        if 'upgrade' in action_lower:
            return 'upgrade'
        elif 'downgrade' in action_lower:
            return 'downgrade'
        elif 'initiat' in action_lower or 'start' in action_lower:
            return 'initiated'
        elif 'reiterat' in action_lower or 'maintain' in action_lower:
            return 'reiterated'
        
        # If not explicit, compare old vs new rating
        old_class = self._classify_rating(old_rating)
        new_class = self._classify_rating(new_rating)
        
        rating_order = {'bearish': 0, 'neutral': 1, 'bullish': 2, 'unknown': 1}
        
        if rating_order.get(new_class, 1) > rating_order.get(old_class, 1):
            return 'upgrade'
        elif rating_order.get(new_class, 1) < rating_order.get(old_class, 1):
            return 'downgrade'
        else:
            return 'reiterated'
    
    def get_recent_rating_changes(self, portfolio_symbols: List[str], hours: int = 72) -> Dict:
        """
        Get recent broker rating changes (BOTH upgrades AND downgrades)
        
        Args:
            portfolio_symbols: List of symbols in user's portfolio
            hours: Look back this many hours (default 72 = 3 days)
            
        Returns:
            Dict with 'portfolio_upgrades', 'portfolio_downgrades', 
            'market_upgrades', 'market_downgrades'
        """
        cache_key = f"broker_ratings:{datetime.utcnow().strftime('%Y%m%d%H')}"
        
        # Check cache (1 hour) - if Redis available
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    return self._separate_by_type_and_portfolio(cached_data, set(portfolio_symbols))
            except:
                pass
        
        # Combine portfolio symbols with watchlist
        all_symbols = list(set(portfolio_symbols + self.watchlist_symbols))
        
        print(f"  📊 Fetching broker rating changes for {len(all_symbols)} symbols...")
        
        all_changes = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Fetch rating changes for all symbols
        for symbol in all_symbols:
            try:
                analyst_data = self.fmp.get_price_targets(symbol)
                
                # Process ALL rating changes (upgrades AND downgrades)
                for rating in analyst_data.get('rating_changes', []):
                    try:
                        pub_date_str = rating.get('publishedDate', '')
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time:
                            broker = rating.get('analystCompany', 'Unknown')
                            action = rating.get('action', '')
                            old_rating = rating.get('previousGrade', 'N/A')
                            new_rating = rating.get('newGrade', 'N/A')
                            
                            # Determine the type of change
                            action_type = self._determine_action_type(action, old_rating, new_rating)
                            
                            # Calculate importance score
                            score = self._calculate_rating_change_score(
                                rating, broker, action_type, symbol in portfolio_symbols
                            )
                            
                            change_info = {
                                'symbol': symbol,
                                'broker': broker,
                                'analyst': rating.get('analystName', 'Unknown'),
                                'action': action,
                                'action_type': action_type,  # 'upgrade', 'downgrade', 'initiated', 'reiterated'
                                'new_rating': new_rating,
                                'previous_rating': old_rating,
                                'new_rating_class': self._classify_rating(new_rating),
                                'date': pub_date.strftime('%Y-%m-%d'),
                                'timestamp': pub_date,
                                'score': score,
                                'is_premium_broker': self._is_premium_broker(broker),
                                'is_portfolio': symbol in portfolio_symbols
                            }
                            
                            all_changes.append(change_info)
                            
                    except Exception as e:
                        continue
                
                # Also process significant price target changes
                for target in analyst_data.get('price_targets', []):
                    try:
                        pub_date_str = target.get('publishedDate', '')
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        if pub_date >= cutoff_time:
                            current_price = target.get('priceWhenPosted', 0)
                            new_target = target.get('priceTarget', 0)
                            old_target = target.get('adjPriceTarget', new_target)  # Previous target if available
                            
                            if current_price and new_target:
                                change_pct = ((new_target - current_price) / current_price) * 100
                                
                                # Include significant target changes (>15% above OR >10% below current price)
                                if change_pct >= 15 or change_pct <= -10:
                                    broker = target.get('analystCompany', 'Unknown')
                                    
                                    if change_pct >= 15:
                                        action_type = 'target_raised'
                                    else:
                                        action_type = 'target_lowered'
                                    
                                    score = self._calculate_target_score(change_pct, broker, symbol in portfolio_symbols)
                                    
                                    change_info = {
                                        'symbol': symbol,
                                        'broker': broker,
                                        'analyst': target.get('analystName', 'Unknown'),
                                        'action': f'Price Target {"Raised" if change_pct > 0 else "Lowered"}',
                                        'action_type': action_type,
                                        'new_rating': f'${new_target:.0f} ({change_pct:+.1f}%)',
                                        'previous_rating': f'${old_target:.0f}' if old_target else 'N/A',
                                        'new_rating_class': 'bullish' if change_pct > 0 else 'bearish',
                                        'price_target': new_target,
                                        'change_pct': change_pct,
                                        'date': pub_date.strftime('%Y-%m-%d'),
                                        'timestamp': pub_date,
                                        'score': score,
                                        'is_premium_broker': self._is_premium_broker(broker),
                                        'is_portfolio': symbol in portfolio_symbols
                                    }
                                    
                                    all_changes.append(change_info)
                                    
                    except Exception as e:
                        continue
            
            except Exception as e:
                print(f"    ⚠️ Error fetching ratings for {symbol}: {e}")
                continue
        
        # Sort by score (highest first), then by timestamp
        all_changes.sort(key=lambda x: (x['score'], x['timestamp']), reverse=True)
        
        # Cache for 1 hour (if Redis available)
        if self.redis_client and all_changes:
            try:
                self.redis_client.setex(cache_key, 3600, json.dumps(all_changes, default=str))
            except:
                pass
        
        print(f"  ✅ Found {len(all_changes)} recent rating changes")
        
        # Separate by type and portfolio
        return self._separate_by_type_and_portfolio(all_changes, set(portfolio_symbols))
    
    def _is_premium_broker(self, broker: str) -> bool:
        """Check if broker is in premium list"""
        broker_lower = broker.lower()
        return any(premium.lower() in broker_lower for premium in self.premium_brokers)
    
    def _calculate_rating_change_score(self, rating: Dict, broker: str, 
                                        action_type: str, is_portfolio: bool) -> float:
        """
        Calculate importance score for a rating change
        Higher score = more important
        """
        score = 5.0  # Base score
        
        # Portfolio stocks get priority
        if is_portfolio:
            score += 3.0
        
        # Premium broker bonus
        if self._is_premium_broker(broker):
            score += 3.0
        
        # Action type weighting
        if action_type == 'downgrade':
            score += 2.0  # Downgrades are often more actionable
        elif action_type == 'upgrade':
            score += 1.5
        elif action_type == 'initiated':
            score += 1.0
        
        # New rating consideration
        new_rating = rating.get('newGrade', '').lower()
        if 'strong buy' in new_rating:
            score += 2.0
        elif 'buy' in new_rating or 'outperform' in new_rating:
            score += 1.5
        elif 'sell' in new_rating or 'underperform' in new_rating:
            score += 2.0  # Sell ratings are rare and significant
        
        # Big rating swing bonus
        prev_rating = rating.get('previousGrade', '').lower()
        if ('buy' in prev_rating and 'sell' in new_rating) or \
           ('sell' in prev_rating and 'buy' in new_rating):
            score += 3.0  # Major reversal
        
        return score
    
    def _calculate_target_score(self, change_pct: float, broker: str, is_portfolio: bool) -> float:
        """Calculate score for price target change"""
        score = 3.0  # Base score (lower than rating changes)
        
        # Portfolio bonus
        if is_portfolio:
            score += 2.0
        
        # Premium broker bonus
        if self._is_premium_broker(broker):
            score += 2.0
        
        # Magnitude bonus
        abs_change = abs(change_pct)
        if abs_change >= 30:
            score += 3.0
        elif abs_change >= 20:
            score += 2.0
        elif abs_change >= 15:
            score += 1.0
        
        # Negative targets are more significant (rarer)
        if change_pct < 0:
            score += 1.0
        
        return score
    
    def _separate_by_type_and_portfolio(self, all_changes: List[Dict], 
                                         portfolio_symbols: Set[str]) -> Dict:
        """
        Separate rating changes into categories:
        - Portfolio upgrades/downgrades (most important)
        - Market upgrades/downgrades (opportunities)
        """
        portfolio_upgrades = []
        portfolio_downgrades = []
        market_upgrades = []
        market_downgrades = []
        
        for change in all_changes:
            is_portfolio = change['symbol'] in portfolio_symbols
            action_type = change.get('action_type', '')
            
            is_positive = action_type in ['upgrade', 'initiated', 'target_raised'] or \
                         (action_type == 'initiated' and change.get('new_rating_class') == 'bullish')
            is_negative = action_type in ['downgrade', 'target_lowered'] or \
                         (action_type == 'initiated' and change.get('new_rating_class') == 'bearish')
            
            if is_portfolio:
                if is_negative:
                    portfolio_downgrades.append(change)
                elif is_positive:
                    portfolio_upgrades.append(change)
            else:
                if is_negative:
                    market_downgrades.append(change)
                elif is_positive:
                    market_upgrades.append(change)
        
        return {
            'portfolio_upgrades': portfolio_upgrades[:10],
            'portfolio_downgrades': portfolio_downgrades[:10],  # NEW! Critical for risk management
            'market_upgrades': market_upgrades[:10],
            'market_downgrades': market_downgrades[:10]
        }
    
    # Keep backward compatibility with old method name
    def get_recent_upgrades(self, portfolio_symbols: List[str], hours: int = 72) -> Dict:
        """
        Backward compatible method - now returns both upgrades AND downgrades
        """
        result = self.get_recent_rating_changes(portfolio_symbols, hours)
        
        # Convert to old format for backward compatibility
        return {
            'portfolio': result['portfolio_upgrades'] + result['portfolio_downgrades'],
            'market': result['market_upgrades'] + result['market_downgrades'],
            # New detailed breakdowns
            'portfolio_upgrades': result['portfolio_upgrades'],
            'portfolio_downgrades': result['portfolio_downgrades'],
            'market_upgrades': result['market_upgrades'],
            'market_downgrades': result['market_downgrades']
        }
    
    def get_rating_summary_stats(self, ratings: Dict) -> Dict:
        """
        Get summary statistics about rating changes
        """
        return {
            'portfolio_upgrades': len(ratings.get('portfolio_upgrades', [])),
            'portfolio_downgrades': len(ratings.get('portfolio_downgrades', [])),
            'market_upgrades': len(ratings.get('market_upgrades', [])),
            'market_downgrades': len(ratings.get('market_downgrades', [])),
            'portfolio_premium_upgrades': sum(1 for u in ratings.get('portfolio_upgrades', []) if u.get('is_premium_broker')),
            'portfolio_premium_downgrades': sum(1 for d in ratings.get('portfolio_downgrades', []) if d.get('is_premium_broker')),
            'has_changes': any([
                ratings.get('portfolio_upgrades'),
                ratings.get('portfolio_downgrades'),
                ratings.get('market_upgrades'),
                ratings.get('market_downgrades')
            ])
        }
    
    def format_alert_message(self, change: Dict) -> str:
        """
        Format a rating change for display/notification
        """
        symbol = change['symbol']
        broker = change['broker']
        action_type = change['action_type']
        new_rating = change['new_rating']
        prev_rating = change.get('previous_rating', 'N/A')
        
        # Emoji based on action type
        if action_type == 'downgrade' or action_type == 'target_lowered':
            emoji = '🔴'
        elif action_type == 'upgrade' or action_type == 'target_raised':
            emoji = '🟢'
        else:
            emoji = '🟡'
        
        # Premium broker indicator
        premium = '⭐' if change.get('is_premium_broker') else ''
        
        if 'target' in action_type:
            return f"{emoji} {symbol}: {broker}{premium} - {change['action']} to {new_rating}"
        else:
            return f"{emoji} {symbol}: {broker}{premium} {action_type.upper()} - {prev_rating} → {new_rating}"