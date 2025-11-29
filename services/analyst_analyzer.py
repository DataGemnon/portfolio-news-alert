import anthropic
import json
from typing import Dict, List
from config.settings import settings


class AnalystUpdateAnalyzer:
    """Specialized analyzer for analyst price targets and rating changes"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
    
    def analyze_price_target_change(self, symbol: str, target_data: Dict, current_price: float = None) -> Dict:
        """
        Analyze a price target change for significance
        
        Args:
            symbol: Stock ticker
            target_data: Price target data from FMP
            current_price: Current stock price
            
        Returns:
            Analysis with impact score and summary
        """
        analyst_name = target_data.get('analystName', 'Unknown Analyst')
        company = target_data.get('analystCompany', 'Unknown Firm')
        new_target = target_data.get('priceTarget', 0)
        previous_target = target_data.get('priceWhenPosted', current_price)
        
        # Calculate percentage change
        if previous_target and previous_target > 0:
            change_pct = ((new_target - previous_target) / previous_target) * 100
        else:
            change_pct = 0
        
        prompt = f"""Analyze this analyst price target update:

Symbol: {symbol}
Analyst: {analyst_name} from {company}
New Price Target: ${new_target}
Current/Previous Price: ${previous_target}
Implied Change: {change_pct:+.1f}%

Published: {target_data.get('publishedDate', 'Unknown')}

Assess the significance:

1. **Impact Score** (0-10):
   - Consider: magnitude of change, analyst reputation, how far from current price
   - 8-10: Very significant (>20% change, major analyst)
   - 5-7: Moderately significant (10-20% change)
   - 0-4: Minor update (<10% change)

2. **Sentiment** (-2 to +2):
   - Positive targets = positive sentiment
   - Degree based on magnitude

3. **Urgency**: 
   - Large changes (>15%) = Immediate or Hours
   - Medium changes (10-15%) = Hours or Days
   - Small changes (<10%) = Days

4. **Summary**: One sentence for notification (max 120 chars)
   - Include: Analyst firm, direction, and percentage

Respond ONLY with valid JSON:
{{
    "impact_score": <0-10>,
    "sentiment": <-2 to +2>,
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "summary": "<summary>",
    "category": "Analyst Price Target"
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Add metadata
            result['analyst_name'] = analyst_name
            result['analyst_company'] = company
            result['price_target'] = new_target
            result['change_percent'] = change_pct
            
            return result
            
        except Exception as e:
            print(f"Analyst analysis error: {e}")
            return {
                'impact_score': 6,
                'sentiment': 1 if change_pct > 0 else -1,
                'urgency': 'Hours',
                'summary': f'{company} sets ${new_target} price target ({change_pct:+.1f}%)',
                'category': 'Analyst Price Target',
                'analyst_name': analyst_name,
                'analyst_company': company,
                'price_target': new_target,
                'change_percent': change_pct
            }
    
    def analyze_rating_change(self, symbol: str, rating_data: Dict) -> Dict:
        """
        Analyze an analyst rating upgrade/downgrade
        
        Args:
            symbol: Stock ticker
            rating_data: Rating change data from FMP
            
        Returns:
            Analysis with impact score and summary
        """
        analyst_name = rating_data.get('analystName', 'Unknown')
        company = rating_data.get('analystCompany', 'Unknown')
        action = rating_data.get('action', 'Unknown')  # Upgrade, Downgrade, Initiated, Reiterated
        new_rating = rating_data.get('newGrade', 'Unknown')
        previous_rating = rating_data.get('previousGrade', 'Unknown')
        
        prompt = f"""Analyze this analyst rating change:

Symbol: {symbol}
Analyst: {analyst_name} from {company}
Action: {action}
Previous Rating: {previous_rating}
New Rating: {new_rating}

Published: {rating_data.get('publishedDate', 'Unknown')}

Assess the significance:

1. **Impact Score** (0-10):
   - Upgrade: 6-9 (higher for Buy/Strong Buy from Sell/Hold)
   - Downgrade: 7-10 (higher for Sell from Buy)
   - Initiated: 4-6
   - Reiterated: 2-4

2. **Sentiment** (-2 to +2):
   - Upgrade to Buy/Outperform = +2
   - Upgrade to Hold = +1
   - Downgrade to Sell/Underperform = -2
   - Downgrade to Hold = -1

3. **Urgency**:
   - Upgrade/Downgrade to/from Buy/Sell = Immediate or Hours
   - Other changes = Hours or Days

4. **Summary**: One sentence (max 120 chars)

Respond ONLY with valid JSON:
{{
    "impact_score": <0-10>,
    "sentiment": <-2 to +2>,
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "summary": "<summary>",
    "category": "Analyst Rating Change"
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Add metadata
            result['analyst_name'] = analyst_name
            result['analyst_company'] = company
            result['action'] = action
            result['new_rating'] = new_rating
            result['previous_rating'] = previous_rating
            
            return result
            
        except Exception as e:
            print(f"Rating analysis error: {e}")
            # Determine basic sentiment from action
            sentiment = 0
            if 'upgrade' in action.lower():
                sentiment = 1
            elif 'downgrade' in action.lower():
                sentiment = -1
            
            return {
                'impact_score': 7,
                'sentiment': sentiment,
                'urgency': 'Hours',
                'summary': f'{company} {action.lower()}s to {new_rating}',
                'category': 'Analyst Rating Change',
                'analyst_name': analyst_name,
                'analyst_company': company,
                'action': action,
                'new_rating': new_rating,
                'previous_rating': previous_rating
            }
    
    def batch_analyze_analyst_updates(self, symbol: str, updates: Dict, current_price: float = None) -> List[Dict]:
        """
        Analyze all analyst updates for a symbol
        
        Returns list of analyzed updates ready for notification
        """
        results = []
        
        # Analyze price targets
        for target in updates.get('price_targets', []):
            analysis = self.analyze_price_target_change(symbol, target, current_price)
            results.append({
                'symbol': symbol,
                'type': 'price_target',
                'data': target,
                'analysis': analysis,
                'published_date': target.get('publishedDate')
            })
        
        # Analyze rating changes
        for rating in updates.get('rating_changes', []):
            analysis = self.analyze_rating_change(symbol, rating)
            results.append({
                'symbol': symbol,
                'type': 'rating_change',
                'data': rating,
                'analysis': analysis,
                'published_date': rating.get('publishedDate')
            })
        
        return results