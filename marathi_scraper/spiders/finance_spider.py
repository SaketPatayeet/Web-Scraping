"""Generic, config-driven Marathi business, finance, and banking spider."""

import re
from datetime import datetime, timezone
from urllib.parse import urldefrag, urlparse

import scrapy
from scrapy.utils.gz import gunzip
from scrapy.utils.sitemap import Sitemap

from marathi_scraper.items import ArticleItem
from marathi_scraper.sources import SOURCES

# MediaWiki category links (e.g. mr.wikipedia.org "वर्ग:" pages) are
# followed as listing pages, never scraped as articles.
CATEGORY_LINK_RE = re.compile(r"/wiki/वर्ग:")


class FinanceSpider(scrapy.Spider):
    name = "finance_spider"

    # No DEPTH_LIMIT override here — it's disabled globally in
    # settings.py (DEPTH_LIMIT = 0). Listing pagination and
    # article-to-article recursion are tracked separately below
    # (via `page` and `depth` in cb_kwargs) instead of sharing one
    # counter, since DEPTH_LIMIT previously capped both together.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.sources = [
            source
            for source in SOURCES
            if source.get("enabled", True)
        ]

        # Dedup for category/listing pages discovered mid-crawl
        # (e.g. Wikipedia subcategories), so a category cycle can't
        # cause the same listing page to be re-queued indefinitely.
        self._visited_categories = set()

        self.logger.info(
            "Loaded %d enabled source(s)",
            len(self.sources),
        )

        self.logger.info(
            "ENABLED SOURCES: %s",
            [source["name"] for source in self.sources],
        )

    @staticmethod
    def _canonical_request_url(url: str) -> str:
        """Remove URL fragments from a URL."""
        return urldefrag(url)[0]

    @staticmethod
    def _compile_article_patterns(source):
        """
        Compile one or more article URL patterns.

        Supports both:
            article_url_pattern: "..."
        and:
            article_url_patterns: ["...", "..."]
        """

        patterns = source.get("article_url_patterns")

        if patterns is None:
            pattern = source.get("article_url_pattern")
            patterns = [pattern] if pattern else []

        return [
            re.compile(pattern)
            for pattern in patterns
            if pattern
        ]

    @staticmethod
    def _compile_exclude_patterns(source):
        """Compile optional URL exclusion patterns."""

        patterns = source.get("exclude_url_patterns", [])

        return [
            re.compile(pattern)
            for pattern in patterns
            if pattern
        ]

    def _is_allowed_domain(self, url, source):
        """Check whether a URL belongs to an allowed domain."""

        allowed_domains = source.get("allowed_domains", [])

        # If no domains are configured, do not apply a domain restriction.
        if not allowed_domains:
            return True

        hostname = urlparse(url).hostname

        if not hostname:
            return False

        hostname = hostname.lower()

        return any(
            hostname == domain.lower()
            or hostname.endswith("." + domain.lower())
            for domain in allowed_domains
        )

    def _is_article_url(self, url, source, patterns=None):
        """
        Return True when a URL should be scraped as an article.

        Checks:
        1. Allowed domain
        2. Excluded URL patterns
        3. Article URL patterns
        """

        if not self._is_allowed_domain(url, source):
            return False

        exclude_patterns = self._compile_exclude_patterns(source)

        if any(
            pattern.search(url)
            for pattern in exclude_patterns
        ):
            return False

        if patterns is None:
            patterns = self._compile_article_patterns(source)

        # If no article pattern is configured, allow the URL after
        # domain and exclusion checks.
        if not patterns:
            return True

        return any(
            pattern.search(url)
            for pattern in patterns
        )

    def _is_sitemap_url(self, url):
        """Return True when a URL looks like another sitemap."""

        path = urlparse(url).path.lower()

        return (
            path.endswith(".xml")
            or path.endswith(".xml.gz")
            or path.endswith("sitemap.xml")
            or "sitemap" in path
        )

    async def start(self):
        """
        Start all configured sources.

        Listing sources:
            start_urls -> parse_listing_page (page=1)

        Sitemap sources:
            sitemap_urls -> parse_sitemap

        A source may contain both start_urls and sitemap_urls.
        """

        for source in self.sources:
            patterns = self._compile_article_patterns(source)

            source_type = source.get("type", "listing")

            # Process explicitly configured sitemap URLs.
            for sitemap_url in source.get("sitemap_urls", []):
                sitemap_url = self._canonical_request_url(
                    sitemap_url
                )

                if not sitemap_url:
                    continue

                yield scrapy.Request(
                    sitemap_url,
                    callback=self.parse_sitemap,
                    cb_kwargs={
                        "source": source,
                        "patterns": patterns,
                    },
                    dont_filter=False,
                )

            # Process explicitly configured listing/start URLs.
            for start_url in source.get("start_urls", []):
                start_url = self._canonical_request_url(
                    start_url
                )

                if not start_url:
                    continue

                if source_type == "sitemap":
                    callback = self.parse_sitemap
                    cb_kwargs = {"source": source, "patterns": patterns}
                else:
                    callback = self.parse_listing_page
                    cb_kwargs = {"source": source, "patterns": patterns, "page": 1}

                self.logger.info(
                    "START SOURCE: source=%s url=%s",
                    source["name"],
                    start_url,
                )

                yield scrapy.Request(
                    start_url,
                    callback=callback,
                    cb_kwargs=cb_kwargs,
                    dont_filter=False,
                )

    def parse_listing_page(self, response, source, patterns, page=1):
        """
        Process a category/listing page.

        Listing pages are used for discovery. They are not saved as
        ArticleItems unless they also match an article URL pattern.

        `page` tracks pagination depth for THIS listing only — it is
        independent of article-to-article recursion depth.
        """

        self.logger.info(
            "PARSE LISTING: source=%s url=%s page=%d",
            source["name"],
            response.url,
            page,
        )

        # Discover article links on this listing page. Articles found
        # directly on a listing page start article-recursion at depth 0.
        yield from self._follow_matching_links(
            response,
            source,
            patterns,
            depth=0,
        )

        # Discover and follow the next listing page.
        yield from self._follow_pagination(
            response,
            source,
            patterns,
            page,
        )

    def parse_article_page(self, response, source, patterns, depth=0):
        """
        Scrape a discovered article page.

        Article pages are saved as ArticleItems. Their internal links
        are only followed if the source opts in via
        `max_article_depth` (default: 0, i.e. off).
        """

        yield from self.parse_article(
            response,
            source,
        )

        max_depth = source.get("max_article_depth", 0)

        if depth < max_depth:
            yield from self._follow_matching_links(
                response,
                source,
                patterns,
                depth=depth + 1,
            )

    def _follow_matching_links(self, response, source, patterns, depth=0):
        """
        Extract links from the current page and follow URLs matching
        the configured article URL patterns. Category/listing links
        (e.g. Wikipedia "वर्ग:" pages) are followed as listing pages
        instead, deduplicated via self._visited_categories.
        """

        seen_on_page = set()

        current_url = self._canonical_request_url(
            response.url
        )

        for href in response.css("a::attr(href)").getall():
            if not href:
                continue

            full_url = self._canonical_request_url(
                response.urljoin(href)
            )

            if not full_url:
                continue

            if full_url in seen_on_page:
                continue

            seen_on_page.add(full_url)

            # Do not request the current page again.
            if full_url == current_url:
                continue

            if not self._is_allowed_domain(full_url, source):
                continue

            # Category/subcategory links are discovery, not articles.
            if CATEGORY_LINK_RE.search(full_url):
                if full_url in self._visited_categories:
                    continue

                self._visited_categories.add(full_url)

                self.logger.debug(
                    "FOLLOW CATEGORY: source=%s url=%s",
                    source["name"],
                    full_url,
                )

                yield scrapy.Request(
                    full_url,
                    callback=self.parse_listing_page,
                    cb_kwargs={
                        "source": source,
                        "patterns": patterns,
                        "page": 1,
                    },
                    dont_filter=False,
                )
                continue

            # Only follow URLs that look like article URLs.
            if not self._is_article_url(
                full_url,
                source,
                patterns,
            ):
                continue

            self.logger.debug(
                "FOLLOW ARTICLE: source=%s url=%s depth=%d",
                source["name"],
                full_url,
                depth,
            )

            yield scrapy.Request(
                full_url,
                callback=self.parse_article_page,
                cb_kwargs={
                    "source": source,
                    "patterns": patterns,
                    "depth": depth,
                },
                dont_filter=False,
            )

    def _follow_pagination(self, response, source, patterns, page):
        """
        Discover the next listing/category page.

        Different websites use different pagination markup, so this
        checks several common selectors, plus MediaWiki's
        `pagefrom=` query-string pagination.

        Bounded by `max_listing_pages` (per-source, default 50) so a
        single section can't page forever.
        """

        max_pages = source.get("max_listing_pages", 50)

        if page >= max_pages:
            self.logger.info(
                "PAGINATION CAP: source=%s url=%s reached max_listing_pages=%d",
                source["name"],
                response.url,
                max_pages,
            )
            return

        next_urls = response.css(
            'a[rel="next"]::attr(href), '
            'link[rel="next"]::attr(href), '
            'a.next::attr(href), '
            'a.next-page::attr(href), '
            'a.pagination-next::attr(href), '
            'a.page-numbers.next::attr(href)'
        ).getall()

        next_urls += response.css('a::attr(href)').re(r'.*pagefrom=.*')

        seen = set()

        for href in next_urls:
            if not href:
                continue

            next_url = self._canonical_request_url(
                response.urljoin(href)
            )

            if not next_url:
                continue

            if next_url in seen:
                continue

            seen.add(next_url)

            if next_url == response.url:
                continue

            if not self._is_allowed_domain(
                next_url,
                source,
            ):
                continue

            self.logger.debug(
                "FOLLOW PAGINATION: source=%s url=%s page=%d",
                source["name"],
                next_url,
                page + 1,
            )

            yield scrapy.Request(
                next_url,
                callback=self.parse_listing_page,
                cb_kwargs={
                    "source": source,
                    "patterns": patterns,
                    "page": page + 1,
                },
                dont_filter=False,
            )

    def parse_sitemap(self, response, source, patterns):
        """
        Parse a sitemap or sitemap index.

        Sitemap indexes are followed recursively.
        Matching article URLs are scraped as content pages.
        """

        self.logger.info(
            "PARSE SITEMAP: source=%s url=%s",
            source["name"],
            response.url,
        )

        body = response.body

        if response.url.lower().endswith(".gz"):
            body = gunzip(body)

        sitemap = Sitemap(body)

        for entry in sitemap:
            loc = self._canonical_request_url(
                entry.get("loc", "")
            )

            if not loc:
                continue

            # Follow nested sitemap indexes.
            if entry["type"] == "sitemap":
                if not self._is_allowed_domain(loc, source):
                    continue

                self.logger.debug(
                    "FOLLOW SITEMAP: source=%s url=%s",
                    source["name"],
                    loc,
                )

                yield scrapy.Request(
                    loc,
                    callback=self.parse_sitemap,
                    cb_kwargs={
                        "source": source,
                        "patterns": patterns,
                    },
                    dont_filter=False,
                )

                continue

            # Some sitemap formats may not identify the type reliably.
            if self._is_sitemap_url(loc):
                if not self._is_allowed_domain(loc, source):
                    continue

                yield scrapy.Request(
                    loc,
                    callback=self.parse_sitemap,
                    cb_kwargs={
                        "source": source,
                        "patterns": patterns,
                    },
                    dont_filter=False,
                )

                continue

            # Process matching article URLs.
            if not self._is_article_url(
                loc,
                source,
                patterns,
            ):
                continue

            self.logger.debug(
                "SITEMAP ARTICLE: source=%s url=%s",
                source["name"],
                loc,
            )

            yield scrapy.Request(
                loc,
                callback=self.parse_article_page,
                cb_kwargs={
                    "source": source,
                    "patterns": patterns,
                },
                dont_filter=False,
            )

    def parse_article(self, response, source):
        """
        Create an ArticleItem from a fetched article page.

        Trafilatura extraction happens later in ExtractPipeline.
        """

        self.logger.info(
            "PARSE ARTICLE: source=%s url=%s",
            source["name"],
            response.url,
        )

        item = ArticleItem()

        item["url"] = response.url

        item["source"] = source["name"]

        item["scraped_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        item["title"] = (
            response.css(
                'meta[property="og:title"]::attr(content)'
            ).get()
            or response.css("h1::text").get()
            or response.css("title::text").get()
            or ""
        ).strip()

        item["html"] = response.text

        yield item