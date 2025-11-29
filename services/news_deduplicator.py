from typing import List, Dict
from datetime import datetime
import re


class NewsDeduplicator:
    """
    Deduplicates similar news articles
    Handles cases like multiple outlets reporting same earnings
    """
    
    def __init__(self):
        # Common words to ignore when comparing titles
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were',
            'stock', 'stocks', 'shares', 'news', 'report', 'reports', 'announces'
        }
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison"""
        # Convert to lowercase
        title = title.lower()
        
        # Remove punctuation
        title = re.sub(r'[^\w\s]', ' ', title)
        
        # Remove stop words
        words = title.split()
        words = [w for w in words if w not in self.stop_words]
        
        # Sort words (order doesn't matter for similarity)
        words.sort()
        
        return ' '.join(words)
    
    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles
        Returns 0.0 (completely different) to 1.0 (identical)
        """
        norm1 = set(self._normalize_title(title1).split())
        norm2 = set(self._normalize_title(title2).split())
        
        if not norm1 or not norm2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(norm1 & norm2)
        union = len(norm1 | norm2)
        
        return intersection / union if union > 0 else 0.0
    
    def _are_similar(self, news1: Dict, news2: Dict, threshold: float = 0.6) -> bool:
        """
        Check if two news items are about the same event
        
        Args:
            news1, news2: News items to compare
            threshold: Similarity threshold (0.6 = 60% similar)
        """
        # Must be about same symbol
        if news1.get('symbol') != news2.get('symbol'):
            return False
        
        # Check title similarity
        title_sim = self._calculate_similarity(
            news1.get('title', ''),
            news2.get('title', '')
        )
        
        if title_sim >= threshold:
            return True
        
        # Check if both mention same key events
        text1 = (news1.get('title', '') + ' ' + news1.get('text', '')).lower()
        text2 = (news2.get('title', '') + ' ' + news2.get('text', '')).lower()
        
        # Key event patterns
        events = [
            'earnings', 'revenue', 'profit', 'eps', 'guidance',
            'beats', 'misses', 'upgraded', 'downgraded',
            'acquisition', 'merger', 'ceo', 'layoff',
            'product launch', 'recall', 'lawsuit'
        ]
        
        # Check if both mention same events
        events1 = {event for event in events if event in text1}
        events2 = {event for event in events if event in text2}
        
        if events1 and events2:
            overlap = len(events1 & events2) / max(len(events1), len(events2))
            if overlap >= 0.5:  # 50% of events overlap
                return True
        
        return False
    
    def deduplicate(self, news_items: List[Dict]) -> List[Dict]:
        """
        Remove duplicate news, keeping the best source
        
        Args:
            news_items: List of news items
            
        Returns:
            Deduplicated list with best sources
        """
        if not news_items:
            return []
        
        # Source quality ranking
        source_quality = {
            'reuters': 10,
            'bloomberg': 10,
            'the wall street journal': 9,
            'financial times': 9,
            'cnbc': 8,
            'marketwatch': 7,
            'yahoo finance': 6,
            'seeking alpha': 5,
            'benzinga': 4
        }
        
        # Sort by published date (most recent first)
        sorted_news = sorted(
            news_items,
            key=lambda x: x.get('publishedDate', ''),
            reverse=True
        )
        
        unique_news = []
        seen_groups = []
        
        for news in sorted_news:
            # Check if similar to any already added
            is_duplicate = False
            
            for i, group in enumerate(seen_groups):
                if self._are_similar(news, group[0]):
                    # Duplicate found - add to group
                    is_duplicate = True
                    seen_groups[i].append(news)
                    break
            
            if not is_duplicate:
                # New unique news - start new group
                seen_groups.append([news])
        
        # For each group, pick the best source
        for group in seen_groups:
            if len(group) == 1:
                unique_news.append(group[0])
            else:
                # Multiple similar articles - pick best source
                best = max(
                    group,
                    key=lambda x: source_quality.get(
                        x.get('site', '').lower(),
                        0
                    )
                )
                
                # Add note about multiple sources
                if 'analysis' in best:
                    best['analysis']['sources_count'] = len(group)
                    best['analysis']['other_sources'] = [
                        g.get('site') for g in group if g != best
                    ][:3]  # Max 3 other sources
                
                unique_news.append(best)
        
        return unique_news
    
    def group_by_symbol(self, news_items: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group news by symbol, then deduplicate within each group
        
        Returns:
            Dict mapping symbol -> deduplicated news list
        """
        grouped = {}
        
        for news in news_items:
            symbol = news.get('symbol', 'UNKNOWN')
            if symbol not in grouped:
                grouped[symbol] = []
            grouped[symbol].append(news)
        
        # Deduplicate each group
        for symbol in grouped:
            grouped[symbol] = self.deduplicate(grouped[symbol])
        
        return grouped