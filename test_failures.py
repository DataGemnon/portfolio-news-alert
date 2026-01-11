from services.ai_analyzer import AIAnalyzer
import json

def test_failed_cases():
    analyzer = AIAnalyzer()
    
    cases = [
        {
            "title": "Qualcomm Stock Falls After Mizuho Downgrade Flags Apple Risk",
            "text": "..."
        },
        {
            "title": "Westend Capital Management LLC Boosts Holdings in Apple Inc. $AAPL",
            "text": "..."
        }
    ]
    
    for case in cases:
        print(f"\nTesting Headline: {case['title']}")
        try:
            result = analyzer.extract_broker_rating(case['title'], case['text'])
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_failed_cases()
