import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List
import redis
import json
from config.settings import settings


class YahooFinanceClient:
    """
    Yahoo Finance client for market indices and real-time data
    Completely free, no API key needed
    """
    
    def __init__(self):
        self.redis_client = redis.from_url(settings.redis_url) if settings.redis_url else None
        
        # Major indices to monitor
        self.indices = {
            '^GSPC': 'S&P 500',
            '^IXIC': 'NASDAQ',
            '^DJI': 'Dow Jones',
            '^VIX': 'VIX (Fear Index)',
            '^TNX': '10-Year Treasury Yield',
            '^IRX': '13-Week Treasury Bill'
        }
    
    def get_market_snapshot(self) -> Dict:
        """
        Get current snapshot of all major indices
        Returns real-time data
        """
        cache_key = f"yahoo_snapshot:{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        
        # Cache for 5 minutes (market data changes frequently)
        if self.redis_client:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        snapshot = {}
        
        for symbol, name in self.indices.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period='5d')
                
                if len(hist) > 0:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                    
                    change = current_price - previous_close
                    change_percent = (change / previous_close * 100) if previous_close != 0 else 0
                    
                    snapshot[symbol] = {
                        'name': name,
                        'price': float(current_price),
                        'change': float(change),
                        'change_percent': float(change_percent),
                        'previous_close': float(previous_close),
                        'timestamp': datetime.utcnow().isoformat()
                    }
            
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue
        
        # Cache for 5 minutes
        if self.redis_client and snapshot:
            self.redis_client.setex(cache_key, 300, json.dumps(snapshot))
        
        return snapshot
    
    def get_index(self, symbol: str, period: str = '1d') -> Dict:
        """
        Get specific index data
        
        Args:
            symbol: Ticker symbol (e.g., '^GSPC')
            period: '1d', '5d', '1mo', '3mo', '1y'
        """
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            
            if len(hist) > 0:
                return {
                    'symbol': symbol,
                    'name': self.indices.get(symbol, symbol),
                    'data': hist.to_dict(),
                    'latest_close': float(hist['Close'].iloc[-1]),
                    'latest_date': hist.index[-1].strftime('%Y-%m-%d')
                }
            
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
        
        return {}
    
    def detect_market_anomalies(self) -> List[Dict]:
        """
        Detect significant market movements
        Returns list of anomalies worth alerting about
        """
        snapshot = self.get_market_snapshot()
        anomalies = []
        
        # Check S&P 500
        sp500 = snapshot.get('^GSPC', {})
        sp500_change = sp500.get('change_percent', 0)
        
        if abs(sp500_change) >= 2.0:
            anomalies.append({
                'type': 'major_market_move',
                'index': 'S&P 500',
                'symbol': '^GSPC',
                'change_percent': sp500_change,
                'price': sp500.get('price'),
                'severity': 'critical' if abs(sp500_change) >= 3.0 else 'high',
                'description': f"S&P 500 {'up' if sp500_change > 0 else 'down'} {abs(sp500_change):.2f}% - significant market move",
                'impact': 'Portfolio-wide impact expected'
            })
        
        # Check VIX (fear index)
        vix = snapshot.get('^VIX', {})
        vix_level = vix.get('price', 0)
        vix_change = vix.get('change_percent', 0)
        
        if vix_level > 25:  # VIX > 25 = elevated fear
            anomalies.append({
                'type': 'vix_spike',
                'index': 'VIX',
                'symbol': '^VIX',
                'level': vix_level,
                'change_percent': vix_change,
                'severity': 'critical' if vix_level > 35 else 'high' if vix_level > 30 else 'medium',
                'description': f"VIX at {vix_level:.1f} - {'extreme' if vix_level > 35 else 'elevated'} market fear",
                'impact': 'High volatility expected, consider defensive positioning'
            })
        
        # Check NASDAQ vs S&P divergence (tech underperformance)
        nasdaq = snapshot.get('^IXIC', {})
        nasdaq_change = nasdaq.get('change_percent', 0)
        
        if sp500_change != 0:
            divergence = nasdaq_change - sp500_change
            if abs(divergence) >= 1.5:
                anomalies.append({
                    'type': 'sector_divergence',
                    'description': f"Tech {'underperforming' if divergence < 0 else 'outperforming'} market by {abs(divergence):.1f}%",
                    'severity': 'high' if abs(divergence) >= 2.5 else 'medium',
                    'nasdaq_change': nasdaq_change,
                    'sp500_change': sp500_change,
                    'divergence': divergence,
                    'impact': f"Tech-heavy portfolios {'facing pressure' if divergence < 0 else 'outperforming'}"
                })
        
        # Check Treasury yield movements (10Y)
        treasury = snapshot.get('^TNX', {})
        treasury_change = treasury.get('change_percent', 0)
        treasury_level = treasury.get('price', 0)
        
        if abs(treasury_change) >= 3.0:  # 3% change in yield is significant
            anomalies.append({
                'type': 'treasury_move',
                'index': '10-Year Treasury',
                'symbol': '^TNX',
                'level': treasury_level,
                'change_percent': treasury_change,
                'severity': 'high',
                'description': f"10Y Treasury yield {'up' if treasury_change > 0 else 'down'} {abs(treasury_change):.1f}%",
                'impact': 'Affects bond-like stocks, rate-sensitive sectors'
            })
        
        return anomalies
    
    def get_intraday_trend(self, symbol: str = '^GSPC') -> Dict:
        """
        Get intraday trend for a symbol
        Useful for detecting market direction during trading hours
        """
        try:
            ticker = yf.Ticker(symbol)
            # Get 1-day data with 15-minute intervals
            hist = ticker.history(period='1d', interval='15m')
            
            if len(hist) > 0:
                opening = hist['Close'].iloc[0]
                current = hist['Close'].iloc[-1]
                high = hist['High'].max()
                low = hist['Low'].min()
                
                change_from_open = ((current - opening) / opening * 100) if opening != 0 else 0
                
                return {
                    'symbol': symbol,
                    'opening': float(opening),
                    'current': float(current),
                    'high': float(high),
                    'low': float(low),
                    'change_from_open': float(change_from_open),
                    'trend': 'up' if change_from_open > 0 else 'down',
                    'timestamp': hist.index[-1].strftime('%Y-%m-%d %H:%M:%S')
                }
        
        except Exception as e:
            print(f"Error getting intraday trend for {symbol}: {e}")
        
        return {}
    
    def is_market_hours(self) -> bool:
        """
        Check if US market is currently open
        Simplified check: Mon-Fri 9:30 AM - 4:00 PM ET
        """
        now = datetime.utcnow()
        # Convert to ET (UTC-5 or UTC-4 depending on DST)
        # Simplified - doesn't account for DST perfectly
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