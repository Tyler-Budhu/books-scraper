# books-scraper

An interactive scraper for [books.toscrape.com](https://books.toscrape.com), a practice site built
for scraping. Run it, answer a few questions (how many pages, a maximum price, a minimum star rating),
and it scrapes the listing pages, compares sequential vs. concurrent scraping, and prints the cheapest
books that match. It uses `requests`, small pure functions (functional programming), and
`concurrent.futures.ThreadPoolExecutor`.

Everything is in one file: `scraper.py`.

## How to use

```
python3 scraper.py
```

On Windows PowerShell, use `py scraper.py` if `python3` isn't found.

The program asks four questions. Press Enter to accept the value in brackets.

| question | meaning |
|---|---|
| How many pages to scrape (1-50) | the site has 50 listing pages of 20 books each |
| Maximum price in GBP | only show books at or under this price |
| Minimum star rating (1-5) | only show books with at least this many stars |
| Threads for the concurrent run (2-16) | how many workers the thread pool uses |

Then it scrapes the pages twice (once one at a time, once with the thread pool), prints how long each
took and the speedup, checks that both runs found the same books, and lists up to 10 matching books,
cheapest first. Bad answers are asked again, it offers to scrape again when it finishes, and Ctrl+C
exits. If a page fails (network error or the site layout changes), the error is printed and the other
pages are still used.

## Real OUTPUT

A real run against books.toscrape.com using the defaults (10 pages, up to £20, 4+ stars, 8 threads),
then scraping again:

![The scraper running in a terminal: sequential vs. concurrent timings and the cheapest matching books](screenshot.png)

## Performance impacts

Both runs in the screenshot scraped 10 pages (200 books) from the live site. The concurrent run used
8 threads.

| run | sequential (s) | concurrent (s) | speedup (x) |
|---|---|---|---|
| 1 | 1.754 | 0.791 | 2.22 |
| 2 | 1.762 | 0.783 | 2.25 |

**concurrent.futures:** Sequentially, each page took about 0.18 s, and most of that is waiting for the
server's response. A thread pool lets those waits overlap, so the same 10 pages took under half the
time with 8 threads. The speedup is well below 8x for a few likely reasons: 10 pages across 8 threads
still takes two rounds (8 pages, then 2), parsing each page uses CPU time and Python's GIL lets only
one thread run Python code at a time, and each request opens its own connection. Scraping more pages
(try 50) should show a bigger gain, since that last partly empty round matters less. Threads are the
right tool for network-bound work like this, but more threads only help until the CPU work or the
server becomes the bottleneck, and too many threads is rude to a server. With only one page there is
nothing to overlap, so the program just runs the sequential version.

**functional programming:** The parsing code (`parse_book`, `parse_books`, `page_url`, `matches`) is
made of pure functions with no shared state, and the results are immutable `NamedTuple`s. `scrape_page`
returns errors as data instead of raising, so one bad page can't break a whole run. Because of that,
the sequential version is `map(scrape_one, pages)` and the concurrent version is
`pool.map(scrape_one, pages)` with the exact same function, so going parallel was a one-line change
that needed no locks. Functional style doesn't make the scraper faster by itself; it is what makes the
threaded version safe and easy to reason about. The filtering uses `filter` and `sorted`, and
`partial` builds the per-page function.
