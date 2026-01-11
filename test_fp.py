from services.ai_analyzer import AIAnalyzer
import json

def test_false_positive():
    analyzer = AIAnalyzer()
    
    # confirmed false positive from user
    headline = "Qualcomm Stock Falls After Mizuho Downgrade Flags Apple Risk"
    symbol = "AAPL" # The user is tracking AAPL
    
    print(f"Testing Headline: {headline}")
    print(f"Target Symbol: {symbol}")
    
    # Updated behavior (passing symbol)
    result = analyzer.extract_broker_rating(headline, symbol=symbol)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_false_positive()
