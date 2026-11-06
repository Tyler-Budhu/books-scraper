#!/usr/bin/env python3

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import NamedTuple, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com"
HEADERS = {"User-Agent": "books-scraper/1.0 (class project)"}
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class Book(NamedTuple):
    page: int
    title: str
    price: float  # in GBP
    rating: int  # 1 to 5 stars
    url: str


class PageResult(NamedTuple):
    page: int
    books: tuple
    error: Optional[str] = None


def page_url(page: int, base_url: str = BASE_URL) -> str:
    return f"{base_url}/catalogue/page-{page}.html"


def parse_book(page_link: str, page: int, card) -> Book:
    """Turn one <article class="product_pod"> into a Book."""
    link = card.h3.a
    price = float(re.search(r"\d+(?:\.\d+)?", card.select_one("p.price_color").get_text()).group())
    stars = max(RATINGS.get(name, 0) for name in card.select_one("p.star-rating")["class"])
    return Book(page, link["title"], price, stars, urljoin(page_link, link["href"]))


def parse_books(html: str, page: int, base_url: str = BASE_URL) -> tuple:
    cards = BeautifulSoup(html, "html.parser").select("article.product_pod")
    if not cards:
        raise ValueError("no books found on page; the site layout may have changed")
    return tuple(map(partial(parse_book, page_url(page, base_url), page), cards))


def matches(max_price: float, min_rating: int, books) -> list:
    """Books at or under max_price with at least min_rating stars, cheapest first."""
    wanted = filter(lambda b: b.price <= max_price and b.rating >= min_rating, books)
    return sorted(wanted, key=lambda b: (b.price, b.title))


def flatten(results) -> tuple:
    return tuple(book for result in results for book in result.books)


def scrape_page(page: int, base_url: str = BASE_URL) -> PageResult:
    """Fetch and parse one listing page. Errors come back as data, not exceptions."""
    try:
        response = requests.get(page_url(page, base_url), headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.content.decode("utf-8")  # the site sends no charset, so "£" would break
        return PageResult(page, parse_books(html, page, base_url))
    except (requests.RequestException, ValueError) as error:
        return PageResult(page, (), f"{type(error).__name__}: {error}")


def run(scrape_one, pages, workers: int) -> tuple:
    """Apply scrape_one to every page; one worker means a plain sequential map."""
    if workers == 1:
        return tuple(map(scrape_one, pages))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return tuple(pool.map(scrape_one, pages))  # map keeps results in page order


def timed(fn, *args):
    start = time.perf_counter()
    result = fn(*args)
    return result, time.perf_counter() - start


def ask(question: str, default, convert, is_valid, hint: str):
    """Keep asking until the answer converts and passes is_valid. Enter = default."""
    while True:
        answer = input(f"{question} [{default}]: ").strip() or str(default)
        try:
            value = convert(answer)
            if is_valid(value):
                return value
        except ValueError:
            pass
        print(f"  Please enter {hint}.")


def search(base_url: str, pages: int, max_price: float, min_rating: int, workers: int) -> None:
    scrape_one = partial(scrape_page, base_url=base_url)
    page_numbers = range(1, pages + 1)
    modes = [("Sequential", 1)] + ([("Concurrent", min(workers, pages))] if pages > 1 else [])

    runs = []
    for name, count in modes:
        print(f"\n{name}: fetching {pages} page(s) with {count} worker(s)...", flush=True)
        results, elapsed = timed(run, scrape_one, page_numbers, count)
        print(f"{len(flatten(results))} books in {elapsed:.3f} seconds")
        runs.append((results, elapsed))

    if len(runs) == 2:
        same = flatten(runs[0][0]) == flatten(runs[1][0])
        print(f"\n{'Same results' if same else 'Results differ'}. "
              f"Speedup: {runs[0][1] / runs[1][1]:.2f}x")

    results = runs[-1][0]
    for failed in filter(lambda r: r.error, results):
        print(f"page {failed.page} failed: {failed.error}", file=sys.stderr)

    found = matches(max_price, min_rating, flatten(results))
    print(f"\n{len(found)} books cost £{max_price:g} or less with {min_rating}+ stars. "
          "Showing up to 10, cheapest first:")
    for book in found[:10]:
        print(f"  £{book.price:>6.2f} | {book.rating}/5 | {book.title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive books.toscrape.com scraper")
    parser.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)  # for testing
    args = parser.parse_args()

    print("Books scraper: answer a few questions (press Enter for the [default]).\n")
    try:
        while True:
            pages = ask("How many pages to scrape (1-50)", 10, int,
                        lambda n: 1 <= n <= 50, "a whole number from 1 to 50")
            max_price = ask("Maximum price in GBP", 20, float,
                            lambda p: p > 0, "a price above 0")
            min_rating = ask("Minimum star rating (1-5)", 4, int,
                             lambda r: 1 <= r <= 5, "a whole number from 1 to 5")
            workers = ask("Threads for the concurrent run (2-16)", 8, int,
                          lambda w: 2 <= w <= 16, "a whole number from 2 to 16")
            search(args.base_url, pages, max_price, min_rating, workers)
            if input("\nScrape again? [y/N]: ").strip().lower() not in ("y", "yes"):
                break
    except (EOFError, KeyboardInterrupt):
        print("\nBye!")


if __name__ == "__main__":
    main()
