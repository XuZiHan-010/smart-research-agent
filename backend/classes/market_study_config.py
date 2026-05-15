"""Fixed market study themes, geography options, and source preferences."""

from typing import Dict, List

MARKET_THEMES: List[Dict[str, str]] = [
    {"key": "market_size", "label_zh": "市场规模与增长趋势"},
    {"key": "industry_chain", "label_zh": "产业链分析"},
    {"key": "products_applications", "label_zh": "主要产品、服务与应用场景"},
    {"key": "competitive_landscape", "label_zh": "竞争格局"},
    {"key": "policy", "label_zh": "政策与监管环境"},
    {"key": "tech_trend", "label_zh": "技术趋势"},
    {"key": "investment", "label_zh": "投融资、并购与战略合作动态"},
]

THEME_LABELS_ZH: Dict[str, str] = {theme["key"]: theme["label_zh"] for theme in MARKET_THEMES}

THEME_TABLE_SCHEMAS: Dict[str, str] = {
    "market_size": "必选表格（每行一个年份×地区，至少3行，必须包含具体金额数字）：年份 | 市场规模 | 增速 | 地区/范围 | 数据来源 | 备注",
    "industry_chain": "必选表格（每行一个具体产业链环节，至少5行）：产业链环节 | 主要内容 | 代表性参与者 | 价值贡献 | 关键壁垒 | 风险点 | 来源",
    "products_applications": "必选表格（每行一个具体产品/服务类型，至少5行）：产品/服务类型 | 主要功能 | 典型应用场景 | 目标客户/用户 | 成熟度 | 来源",
    "competitive_landscape": "必选表格（每行一家具体公司，至少5家公司）：公司 | 国家/地区 | 核心产品/服务 | 主要客户/市场 | 竞争优势 | 劣势或风险 | 近期动态 | 来源",
    "policy": "必选表格（每行一份具体政策/法规/标准文件，至少5份）：政策/法规/标准 | 发布机构 | 发布时间 | 适用范围 | 核心内容 | 对市场的影响 | 来源",
    "tech_trend": "必选表格（每行一个具体技术方向，至少5行）：技术方向 | 当前成熟度 | 主要应用 | 代表性公司/机构 | 发展趋势 | 主要瓶颈 | 来源",
    "investment": "必选表格（每行一笔具体投融资/并购/战略合作事件，至少5笔，包含具体日期与金额）：时间 | 公司 | 事件类型 | 金额 | 投资方/收购方/合作方 | 事件说明 | 来源",
}

AUTHORITATIVE_DOMAINS_BY_THEME: Dict[str, List[str]] = {
    "market_size": ["stats.gov.cn", "caixin.com", "reuters.com", "bloomberg.com", "mckinsey.com"],
    "industry_chain": ["miit.gov.cn", "ndrc.gov.cn", "sina.com.cn", "36kr.com"],
    "products_applications": ["gartner.com", "idc.com", "ieee.org", "forrester.com"],
    "competitive_landscape": ["reuters.com", "bloomberg.com", "ft.com", "wsj.com", "36kr.com"],
    "policy": ["gov.cn", "ndrc.gov.cn", "miit.gov.cn", "samr.gov.cn", "mofcom.gov.cn"],
    "tech_trend": ["ieee.org", "gartner.com", "idc.com", "nature.com", "sciencedirect.com"],
    "investment": ["crunchbase.com", "pitchbook.com", "itjuzi.com", "36kr.com", "reuters.com"],
}

GEOGRAPHY_OPTIONS: List[Dict[str, str | bool]] = [
    {"key": "cn", "label_zh": "中国大陆", "checked": True},
    {"key": "us", "label_zh": "美国", "checked": False},
    {"key": "eu", "label_zh": "欧盟", "checked": False},
    {"key": "jp", "label_zh": "日本", "checked": False},
    {"key": "kr", "label_zh": "韩国", "checked": False},
    {"key": "in", "label_zh": "印度", "checked": False},
    {"key": "sea", "label_zh": "东南亚", "checked": False},
    {"key": "global", "label_zh": "全球", "checked": False},
]

GEOGRAPHY_LABELS_ZH: Dict[str, str] = {
    str(option["key"]): str(option["label_zh"]) for option in GEOGRAPHY_OPTIONS
}
