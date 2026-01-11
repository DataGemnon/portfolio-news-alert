from services.ai_analyzer import AIAnalyzer
import json

def test_target_price():
    analyzer = AIAnalyzer()
    
    cases = [
        {
            "title": "Mizuho raises target on Apple to $250 from $230 while maintaining Buy rating",
            "text": "..."
        },
        {
            "title": "Barclays cuts price target on Tesla to $180 from $200",
            "text": "..."
        }
    ]
    
    for case in cases:
        print(f"\nTesting Headline: {case['title']}")
        try:
            result = analyzer.extract_broker_rating(case['title'], case['text'])
            print(json.dumps(result, indent=2))
            
            if result.get('new_target') != 'N/A' and result.get('old_target') != 'N/A':
                 print("✅ SUCCESS: Extracted targets")
            else:
                 print("❌ FAILURE: Missing targets")
                 
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_target_price()
