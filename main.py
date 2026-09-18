"""
Mercari USA Marketplace Scraper
Extracts product listings from mercari.com with Cloudflare bypass
"""
from apify import Actor
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import json

async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        max_results = actor_input.get('maxResults', 50)
        search_keyword = actor_input.get('searchKeyword', 'iphone')
        min_price = actor_input.get('minPrice')
        max_price = actor_input.get('maxPrice')
        condition = actor_input.get('condition')  # new, like_new, good, fair
        
        Actor.log.info(f'Starting Mercari scraper for keyword: {search_keyword}')
        Actor.log.info(f'Max results: {max_results}')
        
        # Build search URL
        search_url = f'https://www.mercari.com/search/?keyword={search_keyword}'
        if min_price:
            search_url += f'&minPrice={min_price}'
        if max_price:
            search_url += f'&maxPrice={max_price}'
        if condition:
            search_url += f'&itemCondition={condition}'
        
        items_scraped = 0
        
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0'
                    }
                )
                
                page = await context.new_page()
                
                # Hide webdriver detection
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)
                
                Actor.log.info(f'Navigating to: {search_url}')
                
                # Navigate with retries
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                        Actor.log.info(f'Page loaded, status: {response.status}')
                        break
                    except PlaywrightTimeout:
                        if attempt == max_retries - 1:
                            raise
                        Actor.log.warning(f'Timeout on attempt {attempt + 1}, retrying...')
                        await page.wait_for_timeout(2000)
                
                # Wait for content
                await page.wait_for_timeout(3000)
                
                # Check for Cloudflare
                page_title = await page.title()
                if 'just a moment' in page_title.lower() or 'cloudflare' in page_title.lower():
                    Actor.log.warning('Cloudflare challenge detected, waiting...')
                    await page.wait_for_timeout(10000)
                    page_title = await page.title()
                
                Actor.log.info(f'Page title: {page_title}')
                
                # Scroll to load more items
                for i in range(3):
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(1500)
                
                # Extract data - Mercari uses simple link structure
                items = await page.evaluate("""() => {
                    const results = [];
                    
                    // Mercari product links are: a[href*="/us/item/m"]
                    const itemLinks = document.querySelectorAll('a[href*="/us/item/m"]');
                    
                    itemLinks.forEach((link, idx) => {
                        try {
                            const url = link.href;
                            if (!url || url.includes('ref=search_results') === false) return;
                            
                            // Title and price are in the link's inner text
                            const textContent = link.innerText.trim();
                            const lines = textContent.split('\\n').filter(l => l.trim());
                            
                            // Usually: [Brand, Title, Price, OldPrice?]
                            let title = '';
                            let price = '';
                            
                            for (const line of lines) {
                                const trimmed = line.trim();
                                if (trimmed.startsWith('$')) {
                                    price = trimmed.split('$')[0] + '$' + trimmed.split('$')[1].split('$')[0];
                                    break;
                                } else if (trimmed && !title && trimmed !== 'SOLD') {
                                    title = trimmed;
                                }
                            }
                            
                            // Extract image
                            const img = link.querySelector('img');
                            const image = img ? img.src : '';
                            
                            if (title && price && url) {
                                results.push({
                                    title: title,
                                    price: price,
                                    url: url,
                                    image: image,
                                    position: results.length + 1
                                });
                            }
                        } catch (err) {
                            console.error('Error extracting item:', err);
                        }
                    });
                    
                    return results;
                }""")
                
                Actor.log.info(f'Extracted {len(items)} items from page')
                
                # Push data to dataset
                for item in items:
                    if items_scraped >= max_results:
                        break
                    
                    # Clean price
                    if item.get('price'):
                        price_str = item['price'].replace('$', '').replace(',', '').strip()
                        try:
                            item['priceNumeric'] = float(price_str)
                        except:
                            item['priceNumeric'] = None
                    
                    # Add metadata
                    item['searchKeyword'] = search_keyword
                    item['scrapedAt'] = Actor.apify_client.now().isoformat()
                    
                    await Actor.push_data(item)
                    items_scraped += 1
                
                Actor.log.info(f'Successfully scraped {items_scraped} items')
                
                await browser.close()
        
        except Exception as e:
            Actor.log.exception(f'Error during scraping: {e}')
            raise

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
