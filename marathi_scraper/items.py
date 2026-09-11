import scrapy

class ArticleItem(scrapy.Item):
    url = scrapy.Field()
    source = scrapy.Field()
    scraped_at = scrapy.Field()
    title = scrapy.Field()
    html = scrapy.Field()
    text = scrapy.Field()
    devanagari_ratio = scrapy.Field()
    content_hash = scrapy.Field()