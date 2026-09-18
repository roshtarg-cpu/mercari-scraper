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
                # Use playwright-with-fingerprints for Cloudflare bypass
                from playwright_stealth import stealth_async
                
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York'
                )
                
                page = await context.new_page()
                
                # Apply stealth
                try:
                    await stealth_async(page)
                except:
                    Actor.log.warning('playwright-stealth not available, proceeding without it')
                
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
                
                # Extract data using page.evaluate for better reliability
                items = await page.evaluate("""() => {
                    const results = [];
                    
                    // Try multiple selectors
                    let itemElements = document.querySelectorAll('[data-testid="SearchResults"] > div');
                    
                    if (itemElements.length === 0) {
                        // Fallback: look for product links
                        itemElements = document.querySelectorAll('a[href*="/product/"]');
                    }
                    
                    itemElements.forEach((el, idx) => {
                        if (idx >= """ + str(max_results) + """) return;
                        
                        try {
                            // Extract product URL
                            let link = el.querySelector('a[href*="/product/"]');
                            if (!link && el.tagName === 'A') link = el;
                            
                            const url = link ? link.href : null;
                            if (!url) return;
                            
                            // Extract title
                            const titleEl = el.querySelector('[data-testid="ItemName"]') || 
                                           el.querySelector('span[class*="Name"]') ||
                                           link.querySelector('span');
                            const title = titleEl ? titleEl.innerText.trim() : '';
                            
                            // Extract price
                            const priceEl = el.querySelector('[aria-label*="price"]') || 
                                           el.querySelector('[data-testid="ItemPrice"]') ||
                                           el.querySelector('[class*="price"]');
                            let price = priceEl ? priceEl.innerText.trim() : '';
                            
                            // Extract image
                            const imgEl = el.querySelector('img');
                            const image = imgEl ? imgEl.src : '';
                            
                            // Extract condition if available
                            const conditionEl = el.querySelector('[data-testid="ItemCondition"]');
                            const condition = conditionEl ? conditionEl.innerText.trim() : '';
                            
                            // Extract shipping info
                            const shippingEl = el.querySelector('[aria-label*="shipping"]');
                            const shipping = shippingEl ? shippingEl.innerText.trim() : '';
                            
                            if (title && url) {
                                results.push({
                                    title,
                                    price,
                                    url,
                                    image,
                                    condition,
                                    shipping,
                                    position: idx + 1
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
