import sys
print(f"Python {sys.version}", flush=True)
print("Importing modules...", flush=True)

from apify import Actor
print("Apify imported", flush=True)
from playwright.async_api import async_playwright
print("Playwright imported", flush=True)
import json
print("JSON imported", flush=True)

async def main():
    print("Main function called", flush=True)
    async with Actor:
        print("=== ACTOR STARTED ===", flush=True)
        
        # Get input
        actor_input = await Actor.get_input() or {}
        search_keyword = actor_input.get('searchKeyword', 'iphone')
        max_results = actor_input.get('maxResults', 20)
        
        print(f"Input: keyword={search_keyword}, maxResults={max_results}")
        
        # Build search URL (for initial Cloudflare bypass)
        search_url = f"https://www.mercari.com/search/?keyword={search_keyword}"
        print(f"URL: {search_url}")
        
        items_scraped = 0
        
        try:
            print("Starting Playwright...")
            async with async_playwright() as playwright:
                print("Playwright context created")
                
                # Launch browser
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox']
                )
                print("Browser launched")
                
                # Create context with realistic settings
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                print("Context created")
                
                page = await context.new_page()
                print("Page created")
                
                # Hide webdriver
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)
                print("Anti-detection applied")
                
                # Navigate to search page (this will trigger Cloudflare challenge)
                print(f"Navigating to: {search_url}")
                response = await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                print(f"Page loaded: {response.status}")
                
                # Wait for Cloudflare challenge to complete + cookie dialog
                await page.wait_for_timeout(5000)
                print("Waited 5s for Cloudflare")
                
                # Handle cookie consent if present
                try:
                    cookie_button = page.locator('button:has-text("Got it")')
                    if await cookie_button.is_visible(timeout=2000):
                        await cookie_button.click()
                        print("Clicked cookie button")
                        await page.wait_for_timeout(1000)
                except Exception:
                    print("No cookie dialog (OK)")
                
                # Now intercept the API call or call it directly with the cookies
                print("Setting up API response listener...")
                
                # Collect API responses
                api_responses = []
                
                async def handle_response(response):
                    if '/v1/api' in response.url and response.status == 200:
                        print(f"Captured API call: {response.url[:80]}")
                        api_responses.append(response)
                
                page.on('response', handle_response)
                
                # Trigger page load/scroll to fire API calls
                print("Scrolling to trigger API...")
                await page.evaluate('window.scrollTo(0, 500)')
                await page.wait_for_timeout(3000)
                await page.evaluate('window.scrollTo(0, 1000)')
                await page.wait_for_timeout(3000)
                
                print(f"Captured {len(api_responses)} API responses")
                
                if not api_responses:
                    print("ERROR: No API responses captured")
                    print("Page might still be loading or blocked")
                    await browser.close()
                    return
                
                api_response = api_responses[0]
                print(f"Using API response: {api_response.url[:100]}")
                
                # Parse JSON
                try:
                    data = await api_response.json()
                    print(f"JSON parsed successfully")
                    
                    # Extract items from the response
                    # Mercari API structure: data > search > itemsList
                    items_list = data.get('data', {}).get('search', {}).get('itemsList', [])
                    print(f"Found {len(items_list)} items in API response")
                    
                    for item_data in items_list[:max_results]:
                        try:
                            item = {
                                'title': item_data.get('name', ''),
                                'price': item_data.get('price', ''),
                                'priceNumeric': float(item_data.get('price', '0').replace('$', '').replace(',', '')) if item_data.get('price') else None,
                                'url': f"https://www.mercari.com/us/item/{item_data.get('id', '')}",
                                'condition': item_data.get('itemCondition', {}).get('name', ''),
                                'imageUrl': item_data.get('thumbnails', [{}])[0].get('imageUrl', ''),
                                'itemId': item_data.get('id', ''),
                                'sellerId': item_data.get('seller', {}).get('id', ''),
                                'sellerName': item_data.get('seller', {}).get('name', ''),
                                'status': item_data.get('status', '')
                            }
                            
                            await Actor.push_data(item)
                            items_scraped += 1
                            print(f"Pushed item {items_scraped}: {item.get('title', 'N/A')[:40]}")
                            
                            if items_scraped >= max_results:
                                break
                        except Exception as e:
                            print(f"Error parsing item: {e}")
                            continue
                    
                except Exception as e:
                    print(f"Error parsing API response: {e}")
                
                print(f"Total items scraped: {items_scraped}")
                await browser.close()
                print("Browser closed")
                
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"=== ACTOR FINISHED: {items_scraped} items ===")

# Run the actor
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())

