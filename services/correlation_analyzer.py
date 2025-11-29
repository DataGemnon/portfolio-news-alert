import anthropic
import json
from typing import Dict, List
from config.settings import settings


class CorrelationAnalyzer:
    """Analyze how macro events impact a specific portfolio"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Common sector characteristics
        self.sector_profiles = {
            'technology': {
                'rate_sensitive': True,
                'growth_oriented': True,
                'characteristics': 'High valuations, sensitive to interest rates, benefits from innovation'
            },
            'financial': {
                'rate_sensitive': True,
                'growth_oriented': False,
                'characteristics': 'Benefits from rising rates, sensitive to credit conditions'
            },
            'energy': {
                'rate_sensitive': False,
                'growth_oriented': False,
                'characteristics': 'Commodity-driven, inflation hedge, geopolitically sensitive'
            },
            'consumer_discretionary': {
                'rate_sensitive': True,
                'growth_oriented': True,
                'characteristics': 'Economic cycle sensitive, consumer spending dependent'
            },
            'utilities': {
                'rate_sensitive': True,
                'growth_oriented': False,
                'characteristics': 'Defensive, dividend-focused, bond-like behavior'
            }
        }
    
    def analyze_portfolio_composition(self, holdings: Dict[str, Dict]) -> Dict:
        """
        Analyze portfolio characteristics to understand macro sensitivities
        
        Args:
            holdings: Dict of {symbol: {quantity, avg_cost, asset_type}}
            
        Returns:
            Portfolio profile with sector exposure, growth vs value, etc.
        """
        # Simplified sector mapping (in production, use FMP sector data)
        tech_stocks = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'NVDA', 'AMD', 'TSLA', 'AMZN']
        financial_stocks = ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C']
        energy_stocks = ['XOM', 'CVX', 'COP', 'SLB', 'OXY']
        
        tech_count = sum(1 for s in holdings if s in tech_stocks)
        financial_count = sum(1 for s in holdings if s in financial_stocks)
        energy_count = sum(1 for s in holdings if s in energy_stocks)
        total = len(holdings)
        
        profile = {
            'total_positions': total,
            'tech_heavy': tech_count / total > 0.5 if total > 0 else False,
            'financial_exposure': financial_count / total if total > 0 else 0,
            'energy_exposure': energy_count / total if total > 0 else 0,
            'tech_exposure': tech_count / total if total > 0 else 0,
            'rate_sensitive': tech_count / total > 0.4 if total > 0 else False,
            'growth_oriented': tech_count / total > 0.3 if total > 0 else False
        }
        
        return profile
    
    def analyze_macro_impact(self, macro_event: Dict, holdings: Dict[str, Dict]) -> Dict:
        """
        Analyze how a specific macro event impacts the user's portfolio
        
        Args:
            macro_event: The macro event to analyze
            holdings: User's portfolio holdings
            
        Returns:
            Analysis with impact score, affected symbols, and recommendations
        """
        event_type = macro_event.get('type')
        event_data = macro_event.get('data', {})
        
        # Get portfolio composition
        portfolio_profile = self.analyze_portfolio_composition(holdings)
        
        # Build context for AI
        if event_type == 'macro_news':
            event_description = f"""
News: {event_data.get('title', 'Unknown')}
Category: {event_data.get('macro_category', 'Unknown')}
Summary: {event_data.get('text', '')[:500]}
Source: {event_data.get('site', 'Unknown')}
"""
        elif event_type == 'market_anomaly':
            event_description = f"""
Market Event: {event_data.get('description', 'Unknown')}
Type: {event_data.get('type', 'Unknown')}
Severity: {event_data.get('severity', 'Unknown')}
"""
        elif event_type == 'economic_surprise':
            event_description = f"""
Economic Data: {event_data.get('event', 'Unknown')}
Actual: {event_data.get('actual', 'N/A')}
Expected: {event_data.get('estimate', 'N/A')}
Surprise Magnitude: {event_data.get('surprise_magnitude', 0)}
"""
        else:
            event_description = f"Event: {json.dumps(event_data)[:500]}"
        
        # Portfolio summary for AI
        symbols_list = ', '.join(holdings.keys())
        
        prompt = f"""You are analyzing how a macroeconomic event impacts a specific investment portfolio.

MACRO EVENT:
{event_description}

USER'S PORTFOLIO:
Symbols: {symbols_list}
Total Positions: {portfolio_profile['total_positions']}
Tech Exposure: {portfolio_profile['tech_exposure']*100:.0f}%
Financial Exposure: {portfolio_profile['financial_exposure']*100:.0f}%
Profile: {'Growth-oriented, rate-sensitive' if portfolio_profile['growth_oriented'] else 'Value-oriented, defensive'}

ANALYSIS REQUIRED:

1. **Overall Portfolio Impact** (0-10 scale):
   - 9-10: Extremely significant, portfolio-wide impact
   - 7-8: Significant impact on major holdings
   - 5-6: Moderate impact on some holdings
   - 3-4: Minor impact, limited exposure
   - 0-2: Negligible impact on this portfolio

2. **Impact Direction** (-2 to +2):
   - +2: Very positive for portfolio
   - +1: Somewhat positive
   - 0: Neutral or mixed
   - -1: Somewhat negative
   - -2: Very negative for portfolio

3. **Most Affected Symbols** (list 1-3 symbols from portfolio):
   - Which specific holdings are most impacted?
   - Why are they particularly sensitive?

4. **Urgency** (Immediate/Hours/Days/Long-term):
   - Immediate: Market reaction happening now
   - Hours: Impact within 24 hours
   - Days: Impact over several days
   - Long-term: Weeks to months

5. **Actionable Insight** (one sentence, max 150 chars):
   - What should the investor know or consider?
   - No generic advice - specific to THIS event and portfolio

6. **Risk Level** (Low/Medium/High):
   - How much portfolio value could be at risk?

IMPORTANT CONTEXT:
- Rate-sensitive stocks (tech, growth) hurt by rate hikes, helped by cuts
- Financial stocks benefit from rising rates
- Inflation data impacts all stocks but especially growth stocks
- Market-wide moves (S&P ±2%) affect entire portfolio
- VIX spikes indicate increased volatility = higher risk

Respond ONLY with valid JSON:
{{
    "impact_score": <0-10>,
    "impact_direction": <-2 to +2>,
    "most_affected_symbols": ["SYM1", "SYM2", ...],
    "urgency": "<Immediate|Hours|Days|Long-term>",
    "actionable_insight": "<insight>",
    "risk_level": "<Low|Medium|High>",
    "category": "Macroeconomic Event"
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(response_text)
            
            # Validate and set defaults
            result.setdefault('impact_score', 5)
            result.setdefault('impact_direction', 0)
            result.setdefault('most_affected_symbols', [])
            result.setdefault('urgency', 'Days')
            result.setdefault('actionable_insight', 'Monitor market reaction')
            result.setdefault('risk_level', 'Medium')
            result.setdefault('category', 'Macroeconomic Event')
            
            return result
            
        except Exception as e:
            print(f"Correlation analysis error: {e}")
            # Return conservative default
            return {
                'impact_score': 6,
                'impact_direction': 0,
                'most_affected_symbols': list(holdings.keys())[:3],
                'urgency': 'Hours',
                'actionable_insight': 'Macro event detected - review portfolio exposure',
                'risk_level': 'Medium',
                'category': 'Macroeconomic Event'
            }
    
    def batch_analyze_macro_events(self, events: List[Dict], holdings: Dict[str, Dict]) -> List[Dict]:
        """
        Analyze multiple macro events for portfolio impact
        Only returns events with significant impact
        
        Args:
            events: List of macro events
            holdings: User's portfolio
            
        Returns:
            List of analyzed events that meet significance threshold
        """
        analyzed_events = []
        
        for event in events:
            analysis = self.analyze_macro_impact(event, holdings)
            
            # Only include if impact score is significant
            # For macro events, we want higher threshold (7+) since they're already pre-filtered
            if analysis.get('impact_score', 0) >= 7:
                analyzed_events.append({
                    'event': event,
                    'analysis': analysis,
                    'timestamp': event.get('timestamp')
                })
        
        # Sort by impact score (highest first)
        analyzed_events.sort(key=lambda x: x['analysis'].get('impact_score', 0), reverse=True)
        
        return analyzed_events
    
    def should_notify_macro(self, analysis: Dict) -> bool:
        """
        Determine if macro event warrants immediate notification
        Stricter criteria than company news since macro is less frequent but higher impact
        """
        impact_score = analysis.get('impact_score', 0)
        urgency = analysis.get('urgency', 'Days')
        risk_level = analysis.get('risk_level', 'Low')
        
        # High impact always notifies
        if impact_score >= 8:
            return True
        
        # Medium-high impact with urgency
        if impact_score >= 7 and urgency in ['Immediate', 'Hours']:
            return True
        
        # High risk scenarios
        if risk_level == 'High' and impact_score >= 7:
            return True
        
        return False