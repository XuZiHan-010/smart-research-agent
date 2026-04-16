from .product_pricing    import ProductPricingResearcher
from .market_position    import MarketPositionResearcher
from .traction_growth    import TractionGrowthResearcher
from .customer_sentiment import CustomerSentimentResearcher
from .content_gtm        import ContentGTMResearcher
from .recent_activity    import RecentActivityResearcher

RESEARCHER_REGISTRY = {
    "product_pricing":    ProductPricingResearcher,
    "market_position":    MarketPositionResearcher,
    "traction_growth":    TractionGrowthResearcher,
    "customer_sentiment": CustomerSentimentResearcher,
    "content_gtm":        ContentGTMResearcher,
    "recent_activity":    RecentActivityResearcher,
}
