from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config.settings import settings

Base = declarative_base()


class NewsArticle(Base):
    __tablename__ = 'news_articles'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), index=True)
    title = Column(Text, nullable=False)
    content = Column(Text)
    published_date = Column(DateTime, index=True)
    source = Column(String(100))
    url = Column(String(500), unique=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    analysis = relationship("NewsAnalysis", back_populates="article", uselist=False)
    notifications = relationship("Notification", back_populates="article")


class NewsAnalysis(Base):
    __tablename__ = 'news_analysis'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('news_articles.id'), unique=True)
    impact_score = Column(Integer)  # 0-10
    sentiment = Column(Integer)  # -2 to +2
    urgency = Column(String(20))  # Immediate/Hours/Days/Long-term
    category = Column(String(50))
    summary = Column(Text)
    affected_sector = Column(String(100))
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    article = relationship("NewsArticle", back_populates="analysis")


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    
    # Relationships
    holdings = relationship("UserHolding", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class UserHolding(Base):
    __tablename__ = 'user_holdings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    symbol = Column(String(10), nullable=False)
    quantity = Column(DECIMAL(18, 8))
    avg_cost = Column(DECIMAL(18, 2))
    asset_type = Column(String(20))  # stock, etf, crypto
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="holdings")


class Notification(Base):
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    article_id = Column(Integer, ForeignKey('news_articles.id'))
    notification_type = Column(String(20))  # email, push, sms
    sent_at = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    article = relationship("NewsArticle", back_populates="notifications")


# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()