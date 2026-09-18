# Mercari USA Marketplace Scraper

Extract product listings from Mercari.com USA marketplace with Cloudflare bypass capabilities.

## Features

- Search by keyword
- Filter by price range
- Filter by item condition
- Extract prices, titles, images, shipping info
- Cloudflare bypass with stealth techniques
- Fast and reliable scraping

## Input

```json
{
  "searchKeyword": "iphone",
  "maxResults": 50,
  "minPrice": 100,
  "maxPrice": 500,
  "condition": "like_new"
}
```

## Output

Each product includes:
- Title
- Price (text and numeric)
- URL
- Image URL
- Condition
- Shipping information
- Search keyword
- Scraped timestamp

## Use Cases

- Price monitoring and tracking
- Market research and analysis
- Inventory sourcing
- Competitive intelligence
- Product availability tracking

## Notes

This actor uses stealth techniques to bypass Cloudflare protection. Scraping should be done responsibly and in accordance with Mercari's terms of service.
