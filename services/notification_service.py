import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List
from datetime import datetime
from config.settings import settings


class NotificationService:
    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
    
    def format_notification_email(self, user_name: str, items: List[Dict], broker_upgrades: Dict = None) -> str:
        """
        Format news items, analyst updates, and macro events into an HTML email
        
        Args:
            user_name: User's name
            items: List of news/analyst/macro items
            broker_upgrades: Optional dict with 'portfolio' and 'market' upgrades
        """
        
        # Separate different types of alerts
        news_items = [item for item in items if 'analysis' in item and 'type' not in item and 'event' not in item]
        analyst_items = [item for item in items if 'type' in item and item.get('type') in ['price_target', 'rating_change']]
        macro_items = [item for item in items if 'event' in item]
        
        # Group by urgency
        urgent_news = [n for n in news_items if n.get('analysis', {}).get('urgency') in ['Immediate', 'Hours']]
        normal_news = [n for n in news_items if n.get('analysis', {}).get('urgency') not in ['Immediate', 'Hours']]
        
        urgent_analyst = [a for a in analyst_items if a.get('analysis', {}).get('urgency') in ['Immediate', 'Hours']]
        normal_analyst = [a for a in analyst_items if a.get('analysis', {}).get('urgency') not in ['Immediate', 'Hours']]
        
        urgent_macro = [m for m in macro_items if m.get('analysis', {}).get('urgency') in ['Immediate', 'Hours']]
        normal_macro = [m for m in macro_items if m.get('analysis', {}).get('urgency') not in ['Immediate', 'Hours']]
        
        # Generate sidebar HTML for broker upgrades
        sidebar_html = ""
        if broker_upgrades:
            sidebar_html = self._format_broker_upgrades_sidebar(broker_upgrades)
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .email-wrapper {{ display: table; width: 100%; max-width: 900px; margin: 0 auto; }}
                .main-content {{ display: table-cell; width: 65%; padding: 20px; vertical-align: top; }}
                .sidebar {{ display: table-cell; width: 35%; padding: 20px; background: #f8f9fa; vertical-align: top; border-left: 3px solid #e0e0e0; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
                .news-item {{ border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; background: #f8f9fa; }}
                .analyst-item {{ border-left: 4px solid #9b59b6; padding: 15px; margin: 15px 0; background: #f9f5ff; }}
                .macro-item {{ border-left: 4px solid #e67e22; padding: 15px; margin: 15px 0; background: #fff5ee; }}
                .urgent {{ border-left-color: #e74c3c; background: #fee; }}
                .impact-high {{ color: #e74c3c; font-weight: bold; }}
                .impact-medium {{ color: #f39c12; font-weight: bold; }}
                .impact-low {{ color: #27ae60; }}
                .sentiment-positive {{ color: #27ae60; }}
                .sentiment-negative {{ color: #e74c3c; }}
                .sentiment-neutral {{ color: #7f8c8d; }}
                .analyst-badge {{ background: #9b59b6; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.85em; }}
                .macro-badge {{ background: #e67e22; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.85em; }}
                .risk-badge {{ padding: 2px 8px; border-radius: 3px; font-size: 0.85em; font-weight: bold; }}
                .risk-high {{ background: #e74c3c; color: white; }}
                .risk-medium {{ background: #f39c12; color: white; }}
                .risk-low {{ background: #27ae60; color: white; }}
                .sidebar-section {{ background: white; padding: 15px; margin-bottom: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .sidebar-title {{ font-size: 1.1em; font-weight: bold; color: #2c3e50; margin-bottom: 10px; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
                .upgrade-item {{ padding: 10px; margin: 8px 0; background: #e8f5e9; border-left: 3px solid #27ae60; border-radius: 3px; font-size: 0.9em; }}
                .upgrade-item.portfolio {{ background: #e3f2fd; border-left-color: #2196f3; }}
                .upgrade-symbol {{ font-weight: bold; color: #1976d2; font-size: 1.05em; }}
                .upgrade-broker {{ color: #666; font-size: 0.85em; }}
                .upgrade-rating {{ display: inline-block; background: #27ae60; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin-top: 3px; }}
                .upgrade-target {{ color: #27ae60; font-weight: bold; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9em; color: #777; }}
                
                @media only screen and (max-width: 600px) {{
                    .email-wrapper {{ display: block; }}
                    .main-content, .sidebar {{ display: block; width: 100%; }}
                    .sidebar {{ border-left: none; border-top: 3px solid #e0e0e0; margin-top: 20px; }}
                }}
            </style>
        </head>
        <body>
            <div class="email-wrapper">
                <div class="main-content">
                    <div class="header">
                        <h2>📊 Portfolio Alert</h2>
                        <p>Hi {user_name}, here are important updates for your portfolio</p>
                    </div>
        """
        
        # CRITICAL/URGENT section - all urgent items together
        urgent_all = urgent_macro + urgent_news + urgent_analyst
        if urgent_all:
            html += "<h3>🚨 Urgent Updates</h3>"
            for item in urgent_all:
                if 'event' in item:  # Macro
                    html += self._format_macro_item(item, urgent=True)
                elif 'type' in item:  # Analyst
                    html += self._format_analyst_item(item, urgent=True)
                else:  # News
                    html += self._format_news_item(item, urgent=True)
        
        # Macro events section (normal priority)
        if normal_macro:
            html += "<h3>🌍 Market-Wide Events</h3>"
            for macro in normal_macro:
                html += self._format_macro_item(macro, urgent=False)
        
        # Analyst updates section
        if normal_analyst:
            html += "<h3>📈 Analyst Updates</h3>"
            for analyst in normal_analyst:
                html += self._format_analyst_item(analyst, urgent=False)
        
        # Company news section
        if normal_news:
            html += "<h3>📰 Company News</h3>"
            for news in normal_news:
                html += self._format_news_item(news, urgent=False)
        
        html += f"""
                    <div class="footer">
                        <p>This is an automated notification from your Portfolio News Alert system.</p>
                        <p>Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
                    </div>
                </div>
                
                {sidebar_html}
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_broker_upgrades_sidebar(self, broker_upgrades: Dict) -> str:
        """Format the sidebar with recent broker upgrades"""
        portfolio_upgrades = broker_upgrades.get('portfolio', [])
        market_upgrades = broker_upgrades.get('market', [])
        
        sidebar = '<div class="sidebar">'
        
        # Portfolio stocks upgrades
        if portfolio_upgrades:
            sidebar += '''
            <div class="sidebar-section">
                <div class="sidebar-title">📈 Your Stocks - Recent Upgrades</div>
            '''
            for upgrade in portfolio_upgrades[:5]:  # Top 5
                symbol = upgrade.get('symbol', 'N/A')
                broker = upgrade.get('broker', 'Unknown')
                new_rating = upgrade.get('new_rating', 'N/A')
                price_target = upgrade.get('price_target')
                date = upgrade.get('date', '')
                
                target_html = f'<div class="upgrade-target">Target: ${price_target:.2f}</div>' if price_target else ''
                
                sidebar += f'''
                <div class="upgrade-item portfolio">
                    <div class="upgrade-symbol">{symbol}</div>
                    <div class="upgrade-broker">{broker}</div>
                    <span class="upgrade-rating">{new_rating}</span>
                    {target_html}
                    <div style="font-size: 0.75em; color: #999; margin-top: 3px;">{date}</div>
                </div>
                '''
            sidebar += '</div>'
        
        # Market opportunities (stocks not in portfolio)
        if market_upgrades:
            sidebar += '''
            <div class="sidebar-section">
                <div class="sidebar-title">💡 Market Opportunities</div>
                <p style="font-size: 0.85em; color: #666; margin-bottom: 10px;">Recent upgrades on other stocks</p>
            '''
            for upgrade in market_upgrades[:8]:  # Top 8
                symbol = upgrade.get('symbol', 'N/A')
                broker = upgrade.get('broker', 'Unknown')
                new_rating = upgrade.get('new_rating', 'N/A')
                price_target = upgrade.get('price_target')
                date = upgrade.get('date', '')
                
                target_html = f'<div class="upgrade-target">Target: ${price_target:.2f}</div>' if price_target else ''
                
                sidebar += f'''
                <div class="upgrade-item">
                    <div class="upgrade-symbol">{symbol}</div>
                    <div class="upgrade-broker">{broker}</div>
                    <span class="upgrade-rating">{new_rating}</span>
                    {target_html}
                    <div style="font-size: 0.75em; color: #999; margin-top: 3px;">{date}</div>
                </div>
                '''
            sidebar += '</div>'
        
        sidebar += '</div>'
        return sidebar
    
    def _format_news_item(self, news: Dict, urgent: bool = False) -> str:
        """Format a single news item"""
        analysis = news.get('analysis', {})
        
        impact = analysis.get('impact_score', 0)
        sentiment = analysis.get('sentiment', 0)
        
        # Impact styling
        if impact >= 7:
            impact_class = "impact-high"
            impact_label = "High Impact"
        elif impact >= 5:
            impact_class = "impact-medium"
            impact_label = "Moderate Impact"
        else:
            impact_class = "impact-low"
            impact_label = "Low Impact"
        
        # Sentiment styling
        if sentiment > 0:
            sentiment_class = "sentiment-positive"
            sentiment_label = "Positive" if sentiment == 1 else "Very Positive"
        elif sentiment < 0:
            sentiment_class = "sentiment-negative"
            sentiment_label = "Negative" if sentiment == -1 else "Very Negative"
        else:
            sentiment_class = "sentiment-neutral"
            sentiment_label = "Neutral"
        
        item_class = "news-item urgent" if urgent else "news-item"
        
        # Get keywords if available
        keywords = analysis.get('keywords', '')
        keywords_html = ''
        if keywords:
            keyword_list = [kw.strip() for kw in keywords.split(',')]
            keywords_html = '<p><strong>🏷️ Keywords:</strong> ' + ', '.join(
                f'<span style="background:#e3f2fd;padding:2px 6px;border-radius:3px;font-size:0.9em">{kw}</span>'
                for kw in keyword_list[:5]
            ) + '</p>'
        
        # Get sources count if available
        sources_note = ''
        sources_count = analysis.get('sources_count', 0)
        if sources_count and sources_count > 1:
            other_sources = analysis.get('other_sources', [])
            sources_str = ', '.join(other_sources[:2])
            sources_note = f'<p style="font-size:0.85em;color:#666;"><em>Also reported by: {sources_str}</em></p>'
        
        return f"""
        <div class="{item_class}">
            <h4>{news.get('symbol', 'N/A')}: {news.get('title', 'No title')}</h4>
            <p><strong>📰 {analysis.get('summary', 'No summary')}</strong></p>
            {keywords_html}
            <p>
                <span class="{impact_class}">Impact: {impact}/10 ({impact_label})</span> | 
                <span class="{sentiment_class}">Sentiment: {sentiment_label}</span> | 
                <strong>Category:</strong> {analysis.get('category', 'N/A')} | 
                <strong>Urgency:</strong> {analysis.get('urgency', 'N/A')}
            </p>
            <p><strong>Source:</strong> {news.get('site', 'Unknown')} | 
               <strong>Published:</strong> {news.get('publishedDate', 'N/A')}</p>
            {sources_note}
            <p><a href="{news.get('url', '#')}">Read full article →</a></p>
        </div>
        """
    
    def _format_analyst_item(self, analyst_update: Dict, urgent: bool = False) -> str:
        """Format a single analyst update (price target or rating change)"""
        analysis = analyst_update.get('analysis', {})
        symbol = analyst_update.get('symbol', 'N/A')
        update_type = analyst_update.get('type', 'unknown')
        
        impact = analysis.get('impact_score', 0)
        sentiment = analysis.get('sentiment', 0)
        
        # Impact styling
        if impact >= 7:
            impact_class = "impact-high"
            impact_label = "High Impact"
        elif impact >= 5:
            impact_class = "impact-medium"
            impact_label = "Moderate Impact"
        else:
            impact_class = "impact-low"
            impact_label = "Low Impact"
        
        # Sentiment styling
        if sentiment > 0:
            sentiment_class = "sentiment-positive"
            sentiment_label = "Positive" if sentiment == 1 else "Very Positive"
        elif sentiment < 0:
            sentiment_class = "sentiment-negative"
            sentiment_label = "Negative" if sentiment == -1 else "Very Negative"
        else:
            sentiment_class = "sentiment-neutral"
            sentiment_label = "Neutral"
        
        item_class = "analyst-item urgent" if urgent else "analyst-item"
        
        # Build analyst-specific details
        analyst_company = analysis.get('analyst_company', 'Unknown Firm')
        analyst_name = analysis.get('analyst_name', 'Unknown Analyst')
        
        if update_type == 'price_target':
            price_target = analysis.get('price_target', 0)
            change_pct = analysis.get('change_percent', 0)
            details = f"""
                <p><strong>💰 Price Target:</strong> ${price_target:.2f} 
                   <span class="{'sentiment-positive' if change_pct > 0 else 'sentiment-negative'}">
                   ({change_pct:+.1f}% from current)
                   </span>
                </p>
            """
        elif update_type == 'rating_change':
            action = analysis.get('action', 'Unknown')
            new_rating = analysis.get('new_rating', 'Unknown')
            previous_rating = analysis.get('previous_rating', 'N/A')
            details = f"""
                <p><strong>📊 Rating Change:</strong> {action}</p>
                <p><strong>New Rating:</strong> {new_rating} 
                   (Previous: {previous_rating})
                </p>
            """
        else:
            details = ""
        
        return f"""
        <div class="{item_class}">
            <h4>
                {symbol}: <span class="analyst-badge">ANALYST UPDATE</span> {analysis.get('summary', 'Analyst Update')}
            </h4>
            <p><strong>Analyst:</strong> {analyst_name} at {analyst_company}</p>
            {details}
            <p>
                <span class="{impact_class}">Impact: {impact}/10 ({impact_label})</span> | 
                <span class="{sentiment_class}">Sentiment: {sentiment_label}</span> | 
                <strong>Urgency:</strong> {analysis.get('urgency', 'N/A')}
            </p>
            <p><strong>Published:</strong> {analyst_update.get('published_date', 'N/A')}</p>
        </div>
        """
    
    def _format_macro_item(self, macro_event: Dict, urgent: bool = False) -> str:
        """Format a macro event alert"""
        analysis = macro_event.get('analysis', {})
        event = macro_event.get('event', {})
        event_type = event.get('type', 'unknown')
        event_data = event.get('data', {})
        
        impact = analysis.get('impact_score', 0)
        impact_direction = analysis.get('impact_direction', 0)
        
        # Impact styling
        if impact >= 8:
            impact_class = "impact-high"
            impact_label = "Critical Impact"
        elif impact >= 7:
            impact_class = "impact-medium"
            impact_label = "High Impact"
        else:
            impact_class = "impact-low"
            impact_label = "Moderate Impact"
        
        # Direction styling
        if impact_direction > 0:
            direction_class = "sentiment-positive"
            direction_label = "Positive" if impact_direction == 1 else "Very Positive"
        elif impact_direction < 0:
            direction_class = "sentiment-negative"
            direction_label = "Negative" if impact_direction == -1 else "Very Negative"
        else:
            direction_class = "sentiment-neutral"
            direction_label = "Mixed/Neutral"
        
        # Risk badge
        risk_level = analysis.get('risk_level', 'Medium')
        risk_class = f"risk-{risk_level.lower()}"
        
        item_class = "macro-item urgent" if urgent else "macro-item"
        
        # Build event-specific details
        if event_type == 'macro_news':
            title = event_data.get('title', 'Market Event')
            category = event_data.get('macro_category', 'Economic')
            source = event_data.get('site', 'Unknown')
            url = event_data.get('url', '#')
            details = f"""
                <p><strong>Source:</strong> {source}</p>
                <p><a href="{url}">Read full article →</a></p>
            """
        elif event_type == 'market_anomaly':
            title = event_data.get('description', 'Market Movement')
            category = 'Market Sentiment'
            details = f"""
                <p><strong>Type:</strong> {event_data.get('type', 'Unknown').replace('_', ' ').title()}</p>
            """
        elif event_type == 'economic_surprise':
            indicator = event_data.get('event', 'Economic Data')
            title = f"{indicator} Data Surprise"
            category = 'Economic Data'
            actual = event_data.get('actual', 'N/A')
            estimate = event_data.get('estimate', 'N/A')
            details = f"""
                <p><strong>Actual:</strong> {actual} | <strong>Expected:</strong> {estimate}</p>
            """
        else:
            title = "Macro Event"
            category = "Market Event"
            details = ""
        
        # Affected symbols
        affected = analysis.get('most_affected_symbols', [])
        affected_str = ', '.join(affected[:3]) if affected else 'Entire portfolio'
        
        return f"""
        <div class="{item_class}">
            <h4>
                <span class="macro-badge">MACRO</span> {title}
            </h4>
            <p><strong>Category:</strong> {category}</p>
            <p><strong>📊 Portfolio Impact:</strong> {analysis.get('actionable_insight', 'Monitor situation')}</p>
            <p><strong>Most Affected Holdings:</strong> {affected_str}</p>
            {details}
            <p>
                <span class="{impact_class}">Impact: {impact}/10 ({impact_label})</span> | 
                <span class="{direction_class}">Direction: {direction_label}</span> | 
                <span class="risk-badge {risk_class}">Risk: {risk_level}</span> | 
                <strong>Urgency:</strong> {analysis.get('urgency', 'N/A')}
            </p>
        </div>
        """
    
    def send_email(self, to_email: str, user_name: str, news_items: List[Dict], broker_upgrades: Dict = None) -> bool:
        """
        Send email notification
        
        Args:
            to_email: Recipient email
            user_name: Recipient name
            news_items: List of news/analyst/macro items
            broker_upgrades: Optional dict with broker upgrades for sidebar
        """
        if not self.smtp_user or not self.smtp_password:
            print("Email credentials not configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Portfolio Alert: {len(news_items)} important update(s)"
            msg['From'] = self.smtp_user
            msg['To'] = to_email
            
            # Generate HTML content
            html_content = self.format_notification_email(user_name, news_items, broker_upgrades)
            
            # Attach HTML
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            print(f"Email sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
    
    def create_push_notification(self, news_item: Dict) -> Dict:
        """
        Format news for push notification
        Returns dict suitable for push notification service
        """
        analysis = news_item.get('analysis', {})
        
        return {
            'title': f"{news_item.get('symbol')} - {analysis.get('category', 'News')}",
            'body': analysis.get('summary', news_item.get('title', '')),
            'url': news_item.get('url', ''),
            'priority': 'high' if analysis.get('urgency') in ['Immediate', 'Hours'] else 'normal',
            'data': {
                'symbol': news_item.get('symbol'),
                'impact_score': analysis.get('impact_score'),
                'sentiment': analysis.get('sentiment')
            }
        }