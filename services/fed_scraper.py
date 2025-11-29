import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict
import redis
import json
from config.settings import settings


class FedScraper:
    """
    Scrape official Federal Reserve announcements
    Direct from the source - no middleman
    """
    
    def __init__(self):
        self.base_url = "https://www.federalreserve.gov"
        
        # Redis optionnel
        if settings.redis_url:
            try:
                self.redis_client = redis.from_url(settings.redis_url)
            except:
                self.redis_client = None
        else:
            self.redis_client = None
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_press_releases(self, days_back: int = 7) -> List[Dict]:
        """
        Get recent Fed press releases
        These are official announcements - highest priority
        """
        cache_key = f"fed_releases:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        url = f"{self.base_url}/newsevents/pressreleases.htm"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            releases = []
            
            # Find press release items
            items = soup.find_all('div', class_='row eventlist__event')
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            for item in items[:20]:  # Limit to recent 20
                try:
                    # Extract date
                    date_elem = item.find('time')
                    if not date_elem:
                        continue
                    
                    date_str = date_elem.get('datetime', '')
                    if not date_str:
                        continue
                    
                    pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    
                    # Check if within timeframe
                    if pub_date < cutoff_date:
                        continue
                    
                    # Extract title and link
                    title_elem = item.find('em', class_='eventlist__event__title')
                    if not title_elem:
                        continue
                    
                    link_elem = title_elem.find('a')
                    if not link_elem:
                        continue
                    
                    title = link_elem.get_text(strip=True)
                    href = link_elem.get('href', '')
                    
                    # Make absolute URL
                    if href.startswith('/'):
                        full_url = self.base_url + href
                    else:
                        full_url = href
                    
                    # Get description if available
                    desc_elem = item.find('p', class_='eventlist__event__description')
                    description = desc_elem.get_text(strip=True) if desc_elem else ''
                    
                    releases.append({
                        'title': title,
                        'url': full_url,
                        'description': description,
                        'published_date': pub_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'source': 'Federal Reserve',
                        'type': 'press_release',
                        'importance': self._classify_importance(title)
                    })
                
                except Exception as e:
                    print(f"Error parsing press release item: {e}")
                    continue
            
            # Cache for 6 hours (si Redis disponible)
            if self.redis_client and releases:
                try:
                    self.redis_client.setex(cache_key, 21600, json.dumps(releases))
                except:
                    pass
            
            return releases
        
        except Exception as e:
            print(f"Error fetching Fed press releases: {e}")
            return []
    
    def get_fomc_calendar(self) -> List[Dict]:
        """
        Get FOMC meeting calendar
        These are scheduled rate decision dates - critical events
        """
        cache_key = f"fed_fomc_calendar:{datetime.utcnow().strftime('%Y%m')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        url = f"{self.base_url}/monetarypolicy/fomccalendars.htm"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            meetings = []
            
            # Find meeting dates
            # This is simplified - actual Fed website structure may vary
            panels = soup.find_all('div', class_='panel panel-default')
            
            for panel in panels:
                try:
                    # Find year
                    year_elem = panel.find('a', class_='panel-heading')
                    if not year_elem:
                        continue
                    
                    year = year_elem.get_text(strip=True)
                    
                    # Find meeting dates in this year's panel
                    meeting_items = panel.find_all('li')
                    
                    for item in meeting_items:
                        date_text = item.get_text(strip=True)
                        
                        # Try to parse date
                        # Format is typically "January 30-31" or "March 19-20"
                        if '-' in date_text or len(date_text) > 5:
                            meetings.append({
                                'date': date_text,
                                'year': year,
                                'type': 'fomc_meeting',
                                'importance': 'critical',
                                'description': f'FOMC Meeting - Rate Decision Expected'
                            })
                
                except Exception as e:
                    print(f"Error parsing FOMC calendar item: {e}")
                    continue
            
            # Cache for 1 month (si Redis disponible)
            if self.redis_client and meetings:
                try:
                    self.redis_client.setex(cache_key, 2592000, json.dumps(meetings))
                except:
                    pass
            
            return meetings
        
        except Exception as e:
            print(f"Error fetching FOMC calendar: {e}")
            return []
    
    def get_chair_speeches(self, days_back: int = 30) -> List[Dict]:
        """
        Get Fed Chair speeches
        Jerome Powell's speeches often move markets
        """
        cache_key = f"fed_speeches:{datetime.utcnow().strftime('%Y%m%d')}"
        
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        
        url = f"{self.base_url}/newsevents/speeches.htm"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            speeches = []
            
            # Find speech items (similar structure to press releases)
            items = soup.find_all('div', class_='row eventlist__event')
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            for item in items[:15]:  # Limit to recent 15
                try:
                    # Extract date
                    date_elem = item.find('time')
                    if not date_elem:
                        continue
                    
                    date_str = date_elem.get('datetime', '')
                    if not date_str:
                        continue
                    
                    pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    
                    if pub_date < cutoff_date:
                        continue
                    
                    # Extract title
                    title_elem = item.find('em', class_='eventlist__event__title')
                    if not title_elem:
                        continue
                    
                    link_elem = title_elem.find('a')
                    if not link_elem:
                        continue
                    
                    title = link_elem.get_text(strip=True)
                    href = link_elem.get('href', '')
                    
                    # Check if it's a Chair speech
                    speaker_elem = item.find('span', class_='speaker')
                    speaker = speaker_elem.get_text(strip=True) if speaker_elem else ''
                    
                    is_chair = 'powell' in speaker.lower() or 'chair' in speaker.lower()
                    
                    if href.startswith('/'):
                        full_url = self.base_url + href
                    else:
                        full_url = href
                    
                    speeches.append({
                        'title': title,
                        'url': full_url,
                        'speaker': speaker,
                        'published_date': pub_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'source': 'Federal Reserve',
                        'type': 'speech',
                        'importance': 'critical' if is_chair else 'high',
                        'is_chair': is_chair
                    })
                
                except Exception as e:
                    print(f"Error parsing speech item: {e}")
                    continue
            
            # Cache for 6 hours (si Redis disponible)
            if self.redis_client and speeches:
                try:
                    self.redis_client.setex(cache_key, 21600, json.dumps(speeches))
                except:
                    pass
            
            return speeches
        
        except Exception as e:
            print(f"Error fetching Fed speeches: {e}")
            return []
    
    def _classify_importance(self, title: str) -> str:
        """
        Classify importance of Fed announcement based on title
        """
        title_lower = title.lower()
        
        # Critical keywords
        critical_keywords = [
            'fomc', 'interest rate', 'federal funds rate',
            'monetary policy', 'rate decision', 'policy statement'
        ]
        
        # High importance keywords
        high_keywords = [
            'financial stability', 'emergency', 'intervention',
            'liquidity', 'facility', 'program'
        ]
        
        if any(kw in title_lower for kw in critical_keywords):
            return 'critical'
        elif any(kw in title_lower for kw in high_keywords):
            return 'high'
        else:
            return 'medium'
    
    def get_all_fed_updates(self, days_back: int = 7) -> Dict:
        """
        Get comprehensive Fed updates
        Returns all types of Fed communications
        """
        return {
            'press_releases': self.get_press_releases(days_back),
            'speeches': self.get_chair_speeches(days_back),
            'fomc_calendar': self.get_fomc_calendar(),
            'timestamp': datetime.utcnow().isoformat()
        }