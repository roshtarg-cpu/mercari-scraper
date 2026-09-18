"""
Mercari USA Marketplace Scraper
Extracts product listings from mercari.com with Cloudflare bypass
"""
from apify import Actor
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import json

async def main():
    async with Actor:
        print("=== ACTOR STARTED ===")
        actor_input = await Actor.get_input() or {}
        max_results = actor_input.get('maxResults', 50)
        search_keyword = actor_input.get('searchKeyword', 'iphone')
        
        print(f"Input: keyword={search_keyword}, maxResults={max_results}")
        
        Actor.log.info(f'Starting Mercari scraper for keyword: {search_keyword}')
        Actor.log.info(f'Max results: {max_results}')
        
        # Build search URL
        search_url = f'https://www.mercari.com/search/?keyword={search_keyword}'
        print(f"URL: {search_url}")
        
        items_scraped = 0
        
        try:
            print("Starting Playwright...")
            async with async_playwright() as playwright:
                print("Playwright context created")
                
                # Simple browser launch without proxy for now
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
                print("Browser launched")
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York'
                )
                print("Context created")
                
                page = await context.new_page()
                print("Page created")
                
                # Hide webdriver detection
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)
                print("Anti-detection applied")
                
                Actor.log.info(f'Navigating to: {search_url}')
                print(f"Navigating to: {search_url}")
                
                # Navigate
                response = await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                print(f"Page loaded: {response.status}")
                
                # Wait for page
                await page.wait_for_timeout(2000)
                
                # Handle cookie consent - click "Got it" button
                try:
                    # Try multiple possible selectors for cookie button
                    cookie_selectors = [
                        'button:has-text("Got it")',
                        'button:has-text("Accept")',
                        '[aria-label*="cookie"]',
                        'button[class*="consent"]'
                    ]
                    for selector in cookie_selectors:
                        try:
                            await page.click(selector, timeout=2000)
                            print(f"Clicked cookie button: {selector}")
                            await page.wait_for_timeout(1000)
                            break
                        except:
                            continue
                except Exception as e:
                    print(f"No cookie dialog or couldn't click: {e}")
                
                # Wait for content to load after cookie acceptance
                await page.wait_for_timeout(3000)
                print("Waited for content after cookie handling")
                
                # Wait for search results to appear (React app might take time)
                try:
                    await page.wait_for_selector('a[href*="/us/item/m"]', timeout=10000)
                    print("Search results appeared!")
                except:
                    print("Search results didn't appear in 10s")
                    # Try scrolling to trigger lazy load
                    for i in range(5):
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await page.wait_for_timeout(1000)
                    print("Scrolled to trigger lazy loading")
                
                # Check title
                page_title = await page.title()
                print(f"Page title: {page_title}")
                
                # Take screenshot for debugging
                screenshot_path = '/tmp/mercari.png'
                await page.screenshot(path=screenshot_path)
                print(f"Screenshot saved: {screenshot_path}")
                
                # Check what links exist
                link_count = await page.evaluate('document.querySelectorAll("a[href*=\\"/us/item/m\\"]").length')
                print(f"Links with '/us/item/m': {link_count}")
                
                # Check all links
                all_links = await page.evaluate('document.querySelectorAll("a[href]").length')
                print(f"Total links: {all_links}")
                
                # Get page text to see if there's content
                body_text = await page.evaluate('document.body.innerText')
                print(f"Body text length: {len(body_text)}")
                print(f"Body preview: {body_text[:200]}")
                
                # Scroll
                for i in range(2):
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(1000)
                print("Scrolled page")
                
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
                print(f"Extracted {len(items)} items")
                
                # Push data to dataset
                for item in items:
                    if items_scraped >= max_results:
                        break
                    
                    # Clean price
                    if item.get('price'):
                        price_str = item['price'].replace('$', '').replace(',', '').strip()
                        # Handle price ranges like "$100$150"
                        if price_str:
                            price_str = price_str.split('$')[0]
                        try:
                            item['priceNumeric'] = float(price_str) if price_str else None
                        except:
                            item['priceNumeric'] = None
                    
                    # Add metadata
                    item['searchKeyword'] = search_keyword
                    
                    await Actor.push_data(item)
                    items_scraped += 1
                    print(f"Pushed item {items_scraped}: {item.get('title', 'N/A')[:30]}")
                
                Actor.log.info(f'Successfully scraped {items_scraped} items')
                print(f"Total items scraped: {items_scraped}")
                
                await browser.close()
                print("Browser closed")
        
        except Exception as e:
            print(f"ERROR: {e}")
            Actor.log.exception(f'Error during scraping: {e}')
            raise

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
