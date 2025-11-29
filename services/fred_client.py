from fredapi import Fred
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config.settings import settings
import redis
import json


class FREDClient:
    """
    Federal Reserve Economic Data (FRED) client
    Official US economic indicators
    """
    
    def __init__(self):
        self.client = Fred(api_key=settings.fred_api_key)
        
        # Redis optionnel
        if settings.redis_url:
            try:
                self.redis_client = redis.from_url(settings.redis_url)
            except:
                self.redis_client = None
        else:
            self.redis_client = None
        
        # Key economic indicators to monitor
        self.indicators = {
            # Inflation
            'CPIAUCSL': {
                'name': 'Consumer Price Index (CPI)',
                'category': 'Inflation',
                'importance': 'critical',
                'frequency': 'monthly'
            },
            'PPIACO': {
                'name': 'Producer Price Index (PPI)',
                'category': 'Inflation',
                'importance': 'high',
                'frequency': 'monthly'
            },
            'PCEPILFE': {
                'name': 'Core PCE Price Index',
                'category': 'Inflation',
                'importance': 'critical',
                'frequency': 'monthly'
            },
            
            # Employment
            'UNRATE': {
                'name': 'Unemployment Rate',
                'category': 'Employment',
                'importance': 'critical',
                'frequency': 'monthly'
            },
            'PAYEMS': {
                'name': 'Nonfarm Payrolls',
                'category': 'Employment',
                'importance': 'critical',
                'frequency': 'monthly'
            },
            
            # Growth
            'GDP': {
                'name': 'Gross Domestic Product',
                'category': 'Growth',
                'importance': 'critical',
                'frequency': 'quarterly'
            },
            'INDPRO': {
                'name': 'Industrial Production',
                'category': 'Growth',
                'importance': 'high',
                'frequency': 'monthly'
            },
            
            # Interest Rates
            'DFF': {
                'name': 'Federal Funds Rate',
                'category': 'Interest Rates',
                'importance': 'critical',
                'frequency': 'daily'
            },
            'DGS10': {
                'name': '10-Year Treasury Yield',
                'category': 'Interest Rates',
                'importance': 'critical',
                'frequency': 'daily'
            },
            'DGS2': {
                'name': '2-Year Treasury Yield',
                'category': 'Interest Rates',
                'importance': 'high',
                'frequency': 'daily'
            },
            
            # Consumer
            'RSXFS': {
                'name': 'Retail Sales',
                'category': 'Consumer',
                'importance': 'high',
                'frequency': 'monthly'
            },
            'UMCSENT': {
                'name': 'Consumer Sentiment',
                'category': 'Consumer',
                'importance': 'medium',
                'frequency': 'monthly'
            }
        }
    
    def get_latest_values(self) -> Dict[str, Dict]:
        """
        Get latest values for all key indicators
        Returns dict with current value and recent change
        """
        cache_key = f"fred_latest:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        results = {}
        
        for series_id, info in self.indicators.items():
            try:
                # Get last 3 data points
                data = self.client.get_series(series_id, observation_start=(datetime.now() - timedelta(days=180)))
                
                if data is not None and len(data) > 0:
                    # Get latest value
                    latest_value = float(data.iloc[-1])
                    latest_date = data.index[-1].strftime('%Y-%m-%d')
                    
                    # Get previous value for change calculation
                    if len(data) > 1:
                        previous_value = float(data.iloc[-2])
                        change = latest_value - previous_value
                        change_percent = (change / previous_value * 100) if previous_value != 0 else 0
                    else:
                        change = 0
                        change_percent = 0
                    
                    results[series_id] = {
                        'name': info['name'],
                        'category': info['category'],
                        'importance': info['importance'],
                        'latest_value': latest_value,
                        'latest_date': latest_date,
                        'change': change,
                        'change_percent': change_percent,
                        'previous_value': previous_value if len(data) > 1 else None
                    }
            
            except Exception as e:
                print(f"Error fetching {series_id}: {e}")
                continue
        
        # Cache for 24 hours (si Redis disponible)
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 86400, json.dumps(results))
            except:
                pass
        
        return results
    
    def get_indicator(self, series_id: str, days_back: int = 30) -> Optional[Dict]:
        """Get specific indicator with historical context"""
        try:
            start_date = datetime.now() - timedelta(days=days_back)
            data = self.client.get_series(series_id, observation_start=start_date)
            
            if data is None or len(data) == 0:
                return None
            
            return {
                'series_id': series_id,
                'name': self.indicators.get(series_id, {}).get('name', series_id),
                'data': data.to_dict(),
                'latest_value': float(data.iloc[-1]),
                'latest_date': data.index[-1].strftime('%Y-%m-%d')
            }
        
        except Exception as e:
            print(f"Error fetching indicator {series_id}: {e}")
            return None
    
    def detect_significant_changes(self) -> List[Dict]:
        """
        Detect significant changes in economic indicators
        Returns list of indicators with notable movements
        """
        latest_values = self.get_latest_values()
        significant_changes = []
        
        for series_id, data in latest_values.items():
            importance = data.get('importance')
            change_percent = abs(data.get('change_percent', 0))
            
            # Define thresholds based on importance
            threshold = {
                'critical': 0.3,  # 0.3% change for critical indicators
                'high': 0.5,      # 0.5% change for high importance
                'medium': 1.0     # 1.0% change for medium importance
            }.get(importance, 1.0)
            
            if change_percent >= threshold:
                significant_changes.append({
                    'series_id': series_id,
                    'name': data['name'],
                    'category': data['category'],
                    'importance': importance,
                    'latest_value': data['latest_value'],
                    'change': data['change'],
                    'change_percent': data['change_percent'],
                    'latest_date': data['latest_date'],
                    'significance': 'high' if change_percent >= threshold * 2 else 'moderate'
                })
        
        # Sort by importance and magnitude
        importance_order = {'critical': 0, 'high': 1, 'medium': 2}
        significant_changes.sort(
            key=lambda x: (importance_order.get(x['importance'], 3), -abs(x['change_percent']))
        )
        
        return significant_changes
    
    def get_yield_curve_status(self) -> Dict:
        """
        Check yield curve (2Y vs 10Y Treasury)
        Inverted yield curve is recession indicator
        """
        cache_key = f"fred_yield_curve:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        try:
            # Get 2-year and 10-year yields
            two_year = self.client.get_series('DGS2', observation_start=(datetime.now() - timedelta(days=7)))
            ten_year = self.client.get_series('DGS10', observation_start=(datetime.now() - timedelta(days=7)))
            
            if two_year is not None and ten_year is not None and len(two_year) > 0 and len(ten_year) > 0:
                two_year_latest = float(two_year.iloc[-1])
                ten_year_latest = float(ten_year.iloc[-1])
                spread = ten_year_latest - two_year_latest
                
                result = {
                    'two_year_yield': two_year_latest,
                    'ten_year_yield': ten_year_latest,
                    'spread': spread,
                    'inverted': spread < 0,
                    'status': 'Inverted (Recession Warning)' if spread < 0 else 'Normal',
                    'date': ten_year.index[-1].strftime('%Y-%m-%d')
                }
                
                # Cache for 24 hours (si Redis disponible)
                if self.redis_client:
                    try:
                        self.redis_client.setex(cache_key, 86400, json.dumps(result))
                    except:
                        pass
                
                return result
        
        except Exception as e:
            print(f"Error checking yield curve: {e}")
        
        return {}
    
    def get_inflation_summary(self) -> Dict:
        """Get comprehensive inflation picture"""
        try:
            cpi = self.get_indicator('CPIAUCSL', days_back=365)
            pce = self.get_indicator('PCEPILFE', days_back=365)
            
            summary = {
                'cpi': cpi.get('latest_value') if cpi else None,
                'pce': pce.get('latest_value') if pce else None,
                'updated': datetime.utcnow().strftime('%Y-%m-%d')
            }
            
            return summary
        
        except Exception as e:
            print(f"Error getting inflation summary: {e}")
            return {}