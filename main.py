#!/usr/bin/env python3
"""
Portfolio News Alert - Main Application
Monitors financial news and alerts users about portfolio-relevant updates
"""

import schedule
import time
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session

from models.database import (
    init_db, get_db, User, UserHolding, NewsArticle, 
    NewsAnalysis, Notification
)
from services.fmp_client import FMPClient
from services.ai_analyzer import AIAnalyzer
from services.analyst_analyzer import AnalystUpdateAnalyzer
from services.macro_monitor import MacroMonitor
from services.correlation_analyzer import CorrelationAnalyzer
from services.news_deduplicator import NewsDeduplicator
from services.notification_service import NotificationService
from services.broker_upgrades_service import BrokerUpgradesService
from config.settings import settings


class PortfolioNewsMonitor:
    def __init__(self):
        self.fmp = FMPClient()
        self.ai_analyzer = AIAnalyzer()
        self.analyst_analyzer = AnalystUpdateAnalyzer()
        self.macro_monitor = MacroMonitor()
        self.correlation_analyzer = CorrelationAnalyzer()
        self.deduplicator = NewsDeduplicator()
        self.notifier = NotificationService()
        self.broker_upgrades = BrokerUpgradesService()
        
    def get_user_portfolio_symbols(self, db: Session, user_id: int) -> List[str]:
        """Get all symbols in user's portfolio"""
        holdings = db.query(UserHolding).filter(
            UserHolding.user_id == user_id
        ).all()
        return [h.symbol for h in holdings]
    
    def get_user_holdings_dict(self, db: Session, user_id: int) -> Dict[str, Dict]:
        """Get user holdings as a dict keyed by symbol"""
        holdings = db.query(UserHolding).filter(
            UserHolding.user_id == user_id
        ).all()
        
        return {
            h.symbol: {
                'quantity': float(h.quantity) if h.quantity else 0,
                'avg_cost': float(h.avg_cost) if h.avg_cost else 0,
                'asset_type': h.asset_type
            }
            for h in holdings
        }
    
    def save_news_article(self, db: Session, news_item: Dict, analysis: Dict) -> NewsArticle:
        """Save news article and analysis to database"""
        
        # Check if article already exists
        existing = db.query(NewsArticle).filter(
            NewsArticle.url == news_item.get('url')
        ).first()
        
        if existing:
            return existing
        
        # Parse published date
        pub_date_str = news_item.get('publishedDate', '')
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
        except:
            pub_date = datetime.utcnow()
        
        # Create article
        article = NewsArticle(
            symbol=news_item.get('symbol', ''),
            title=news_item.get('title', ''),
            content=news_item.get('text', ''),
            published_date=pub_date,
            source=news_item.get('site', ''),
            url=news_item.get('url', '')
        )
        db.add(article)
        db.flush()  # Get the article ID
        
        # Create analysis
        analysis_record = NewsAnalysis(
            article_id=article.id,
            impact_score=analysis.get('impact_score', 0),
            sentiment=analysis.get('sentiment', 0),
            urgency=analysis.get('urgency', 'Days'),
            category=analysis.get('category', 'Other'),
            summary=analysis.get('summary', ''),
            affected_sector=analysis.get('affected_sector', 'Individual Stock Only')
        )
        db.add(analysis_record)
        db.commit()
        
        return article
    
    def create_notification_record(self, db: Session, user_id: int, article_id: int):
        """Create notification record"""
        notification = Notification(
            user_id=user_id,
            article_id=article_id,
            notification_type='email'
        )
        db.add(notification)
        db.commit()
    
    def process_user_portfolio(self, db: Session, user: User):
        """Process news for a single user's portfolio"""
        print(f"Processing portfolio for user: {user.email}")
        
        # Get user's holdings
        symbols = self.get_user_portfolio_symbols(db, user.id)
        if not symbols:
            print(f"  No holdings found for user {user.email}")
            return
        
        print(f"  Monitoring {len(symbols)} symbols: {', '.join(symbols)}")
        
        # Get user holdings details (needed for all analysis)
        holdings_dict = self.get_user_holdings_dict(db, user.id)
        
        # 1. MACRO MONITORING - Check first as it can affect entire portfolio
        print(f"  Checking macro conditions...")
        macro_snapshot = self.macro_monitor.get_comprehensive_macro_snapshot()
        high_impact_macro = self.macro_monitor.filter_high_impact_macro_events(macro_snapshot)
        
        analyzed_macro_events = []
        if high_impact_macro:
            print(f"  Found {len(high_impact_macro)} significant macro events")
            analyzed_macro = self.correlation_analyzer.batch_analyze_macro_events(
                high_impact_macro, holdings_dict
            )
            
            # Filter to only notify-worthy events
            for macro_item in analyzed_macro:
                if self.correlation_analyzer.should_notify_macro(macro_item['analysis']):
                    analyzed_macro_events.append(macro_item)
            
            print(f"  {len(analyzed_macro_events)} macro events meet notification threshold")
        
        # 2. COMPANY NEWS
        news_items = self.fmp.get_portfolio_news(symbols, hours=settings.news_lookback_hours)
        print(f"  Found {len(news_items)} news items")
        
        # DEDUPLICATE news (e.g., multiple outlets reporting same NVDA earnings)
        print(f"  Deduplicating news...")
        news_items = self.deduplicator.deduplicate(news_items)
        print(f"  After deduplication: {len(news_items)} unique items")
        
        # Analyze news items
        analyzed_news = []
        for news in news_items:
            symbol = news.get('symbol', '')
            holding = holdings_dict.get(symbol)
            
            # Analyze with AI
            analysis = self.ai_analyzer.analyze_news_impact(news, holding)
            
            # Save to database
            article = self.save_news_article(db, news, analysis)
            
            # Check if we should notify
            if self.ai_analyzer.should_notify(analysis):
                news['analysis'] = analysis
                news['article_id'] = article.id
                analyzed_news.append(news)
        
        # 3. ANALYST UPDATES (Price Targets & Ratings)
        print(f"  Checking analyst updates...")
        analyst_updates = self.fmp.get_portfolio_analyst_updates(symbols, hours=24)
        
        analyzed_analyst_updates = []
        for symbol, updates in analyst_updates.items():
            # Get current price
            quote = self.fmp.get_stock_quote(symbol)
            current_price = quote.get('price', 0)
            
            # Analyze all updates for this symbol
            analyzed = self.analyst_analyzer.batch_analyze_analyst_updates(
                symbol, updates, current_price
            )
            
            # Filter important ones
            for update in analyzed:
                impact_score = update['analysis'].get('impact_score', 0)
                if impact_score >= settings.impact_threshold:
                    analyzed_analyst_updates.append(update)
        
        print(f"  Found {len(analyzed_analyst_updates)} important analyst updates")
        
        # 4. BROKER UPGRADES (for sidebar)
        print(f"  Fetching recent broker upgrades...")
        broker_upgrades_data = self.broker_upgrades.get_recent_upgrades(symbols, hours=168)
        upgrade_stats = self.broker_upgrades.get_upgrade_summary_stats(broker_upgrades_data)
        
        if upgrade_stats['has_upgrades']:
            print(f"  Found {upgrade_stats['total_portfolio_upgrades']} portfolio upgrades, "
                  f"{upgrade_stats['total_market_upgrades']} market opportunities")
        
        # 5. Combine ALL alerts: macro + news + analyst
        all_alerts = analyzed_macro_events + analyzed_news + analyzed_analyst_updates
        
        # Send notifications if there are important items OR if there are upgrades to show
        if all_alerts or upgrade_stats['has_upgrades']:
            print(f"  Sending notification:")
            if all_alerts:
                print(f"    - {len(analyzed_macro_events)} macro events")
                print(f"    - {len(analyzed_news)} company news")
                print(f"    - {len(analyzed_analyst_updates)} analyst updates")
            if upgrade_stats['has_upgrades']:
                print(f"    - Broker upgrades sidebar included")
            
            # Pass broker upgrades to the email formatter
            success = self.notifier.send_email(
                user.email, 
                user.name or user.email, 
                all_alerts,
                broker_upgrades=broker_upgrades_data if upgrade_stats['has_upgrades'] else None
            )
            
            if success:
                # Record notifications for news articles
                for news in analyzed_news:
                    self.create_notification_record(db, user.id, news['article_id'])
        else:
            print(f"  No items met notification threshold and no upgrades to report")
    
    def run_monitoring_cycle(self):
        """Run one complete monitoring cycle for all users"""
        print(f"\n{'='*60}")
        print(f"Starting monitoring cycle at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")
        
        db = next(get_db())
        
        try:
            # Get all active users
            users = db.query(User).filter(User.active == True).all()
            print(f"Found {len(users)} active users")
            
            for user in users:
                try:
                    self.process_user_portfolio(db, user)
                except Exception as e:
                    print(f"Error processing user {user.email}: {e}")
                    continue
            
            print(f"Monitoring cycle completed")
            
        except Exception as e:
            print(f"Error in monitoring cycle: {e}")
        finally:
            db.close()
    
    def start_scheduler(self):
        """Start the scheduled monitoring"""
        print(f"Portfolio News Monitor Starting...")
        print(f"Polling interval: {settings.polling_interval_minutes} minutes")
        print(f"Impact threshold: {settings.impact_threshold}/10")
        
        # Run immediately on start
        self.run_monitoring_cycle()
        
        # Schedule regular runs
        schedule.every(settings.polling_interval_minutes).minutes.do(self.run_monitoring_cycle)
        
        print("Scheduler started. Press Ctrl+C to stop.")
        
        while True:
            schedule.run_pending()
            time.sleep(60)


def setup_sample_data(db: Session):
    """Create sample user and portfolio for testing"""
    
    # Check if sample user exists
    existing_user = db.query(User).filter(User.email == "demo@example.com").first()
    if existing_user:
        print("Sample user already exists")
        return
    
    # Create sample user
    user = User(
        email="demo@example.com",
        name="Demo User",
        active=True
    )
    db.add(user)
    db.flush()
    
    # Add sample holdings
    sample_holdings = [
        UserHolding(user_id=user.id, symbol="AAPL", quantity=10, avg_cost=150.00, asset_type="stock"),
        UserHolding(user_id=user.id, symbol="MSFT", quantity=5, avg_cost=300.00, asset_type="stock"),
        UserHolding(user_id=user.id, symbol="GOOGL", quantity=3, avg_cost=120.00, asset_type="stock"),
        UserHolding(user_id=user.id, symbol="TSLA", quantity=8, avg_cost=200.00, asset_type="stock"),
        UserHolding(user_id=user.id, symbol="NVDA", quantity=15, avg_cost=400.00, asset_type="stock"),
    ]
    
    for holding in sample_holdings:
        db.add(holding)
    
    db.commit()
    print(f"Created sample user: {user.email} with {len(sample_holdings)} holdings")


def main():
    """Main entry point"""
    import sys
    
    # Initialize database
    print("Initializing database...")
    init_db()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "setup":
            # Setup sample data
            db = next(get_db())
            setup_sample_data(db)
            db.close()
            print("Setup complete!")
            return
        
        elif command == "test":
            # Run one monitoring cycle and exit
            monitor = PortfolioNewsMonitor()
            monitor.run_monitoring_cycle()
            return
    
    # Start the monitor
    monitor = PortfolioNewsMonitor()
    monitor.start_scheduler()


if __name__ == "__main__":
    main()