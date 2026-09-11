SOURCES = [
    {
        "name": "economic_times_marathi",
        "type": "listing",
        "start_urls": [
            "https://marathi.economictimes.com/wealth",
            "https://marathi.economictimes.com/markets",
            "https://marathi.economictimes.com/industry",
        ],
        "allowed_domains": ["marathi.economictimes.com"],
        "article_url_pattern": r"marathi\.economictimes\.com/(wealth|markets|industry)/.+",
        "enabled": True,
    },
    {
        "name": "loksatta_business",
        "type": "listing",
        "start_urls": [
            "https://www.loksatta.com/business/",
        ],
        "allowed_domains": ["loksatta.com"],
        "article_url_pattern": r"loksatta\.com/business/.+",
        "enabled": True,
    },
    {
        "name": "sakal_finance",
        "type": "listing",
        "start_urls": [
            "https://www.esakal.com/topic/finance",
            "https://www.esakal.com/topic/economics",
        ],
        "allowed_domains": ["esakal.com"],
        "article_url_pattern": r"esakal\.com/(topic/finance|topic/economics)/.+",
        "enabled": True,
    },
    {
        "name": "mr_wikipedia_finance",
        "type": "listing",
        "start_urls": [
            "https://mr.wikipedia.org/wiki/वर्ग:वित्त",
            "https://mr.wikipedia.org/wiki/वर्ग:अर्थशास्त्र",
            "https://mr.wikipedia.org/wiki/वर्ग:बँक",
            "https://mr.wikipedia.org/wiki/वर्ग:व्यापार",
        ],
        "allowed_domains": ["mr.wikipedia.org"],
        "article_url_pattern": r"^https://mr\.wikipedia\.org/wiki/[^:]+$",
        "exclude_url_patterns": [
            r"/wiki/विशेष:",
            r"/wiki/साचा:",
            r"/wiki/चर्चा:",
            r"/wiki/सहाय्य:",
            r"/wiki/प्रवेशद्वार:",
            r"/wiki/वापरकर्ता:",
            r"action=edit",
            r"action=history",
            r"redlink=1",
        ],
        "enabled": True,
    },
]