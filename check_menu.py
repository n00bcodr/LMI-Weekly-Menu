import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime
import re
import json
from urllib.parse import urljoin
from io import BytesIO

try:
    import pytesseract
    from PIL import Image
    OCR_ENABLED = True
except ImportError:
    print("OCR libraries (pytesseract, Pillow) not found. OCR check will be skipped.")
    OCR_ENABLED = False

# --- Configuration ---
BASE_URL = "https://www.ericssondining.ie"
NEWS_PAGE_URL = f"{BASE_URL}/news"
IMAGE_SAVE_PATH = "weekly_menu.jpg"
REQUEST_TIMEOUT = 30

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
}

# Expanded Keyword List (lowercase)
OCR_MENU_KEYWORDS = [
    "menu", "week", "soup", "main", "salad", "daily", "special",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fries", "chips",
    "chicken", "beef", "pork", "fish", "vegetarian", "vegan", "halal",
    "potatoes", "rice", "pasta", "noodles", "burger", "curry", "roast",
    "kitchen", "mash", "enrich"
]
# --- End Configuration ---


# --- Helper Functions ---
def calculate_hash(file_path):
    """Calculate the SHA-256 hash of the given file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except FileNotFoundError:
        return None


def send_telegram_photo(photo_path, caption):
    """Send a photo to a Telegram chat."""
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    if not bot_token or not chat_id:
        print("Error: BOT_TOKEN or CHAT_ID environment variables not set.")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': chat_id, 'caption': caption}
            response_tg = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT + 30)
            response_tg.raise_for_status()
        print("Photo sent successfully to Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send photo to Telegram: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: Photo file not found at {photo_path} for Telegram.")
        return False


def get_current_monday(date):
    """Get the Monday of the week in which the given date falls."""
    return date - datetime.timedelta(days=date.weekday())


def construct_menu_url(monday_date):
    """
    Construct the expected menu post URL based on the Monday date.
    Pattern: /post/menu-DD-MM-YY
    """
    slug = monday_date.strftime("menu-%d-%m-%y")
    return f"{BASE_URL}/post/{slug}"


def try_url(url, use_bot_ua=False):
    """Check if a URL returns a valid page (HTTP 200)."""
    try:
        req_headers = HEADERS.copy()
        if use_bot_ua:
            # Wix does SSR (Server-Side Rendering) for known bots/crawlers,
            # returning full HTML with images. Regular browsers get a JS shell.
            req_headers['User-Agent'] = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
        resp = requests.get(url, headers=req_headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return resp
        else:
            print(f"  URL returned status {resp.status_code}: {url}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching {url}: {e}")
        return None


def find_menu_post_url():
    """
    Strategy 1: Construct the URL directly from the date pattern.
    Try current week's Monday, then previous Monday (in case it's posted late).

    Strategy 2: Fallback - fetch the news page and look for menu links in the
    rendered HTML (works if Wix pre-renders or if the site structure changes).

    Strategy 3: Use Wix's internal blog API to list posts.
    """
    today = datetime.date.today()
    current_monday = get_current_monday(today)
    previous_monday = current_monday - datetime.timedelta(days=7)

    # Strategy 1: Direct URL construction
    print("Strategy 1: Constructing menu URL from date pattern...")
    for monday in [current_monday, previous_monday]:
        url = construct_menu_url(monday)
        print(f"  Trying: {url}")
        # First try with bot UA to get SSR content (full HTML with images)
        resp = try_url(url, use_bot_ua=True)
        if resp:
            print(f"  Found valid menu page (SSR): {url}")
            return url, resp
        # Fallback to normal UA
        resp = try_url(url, use_bot_ua=False)
        if resp:
            print(f"  Found valid menu page: {url}")
            return url, resp

    # Strategy 2: Try Wix blog feed/sitemap for post discovery
    print("\nStrategy 2: Checking Wix blog sitemap/feed...")
    sitemap_urls = [
        f"{BASE_URL}/sitemap.xml",
        f"{BASE_URL}/blog-sitemap.xml",
        f"{BASE_URL}/post-sitemap.xml",
    ]
    for sitemap_url in sitemap_urls:
        try:
            resp = requests.get(sitemap_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and 'menu' in resp.text.lower():
                # Parse sitemap XML for menu post URLs
                menu_urls = re.findall(r'<loc>(https?://[^<]*?/post/menu[^<]*?)</loc>', resp.text, re.IGNORECASE)
                if menu_urls:
                    # Sort by URL (which contains date) and take the latest
                    menu_urls.sort(reverse=True)
                    latest_url = menu_urls[0]
                    print(f"  Found menu URL in sitemap: {latest_url}")
                    resp = try_url(latest_url)
                    if resp:
                        return latest_url, resp
        except requests.exceptions.RequestException:
            continue

    # Strategy 3: Scrape the news page HTML (may work if Wix SSR is enabled)
    print("\nStrategy 3: Scraping news page for menu links...")
    try:
        news_resp = requests.get(NEWS_PAGE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        news_resp.raise_for_status()
        news_soup = BeautifulSoup(news_resp.content, 'html.parser')

        # Look for any link containing '/post/menu' in href
        all_links = news_soup.find_all('a', href=re.compile(r'/post/menu', re.IGNORECASE))
        if all_links:
            href = all_links[0].get('href', '')
            if not href.startswith(('http://', 'https://')):
                href = urljoin(BASE_URL, href)
            print(f"  Found menu link on news page: {href}")
            resp = try_url(href)
            if resp:
                return href, resp

        # Broader search: any link with '/post/' that mentions 'menu' in text or href
        all_post_links = news_soup.find_all('a', href=re.compile(r'/post/'))
        for link in all_post_links:
            href = link.get('href', '').lower()
            text = link.get_text(strip=True).lower()
            if 'menu' in href or 'menu' in text:
                full_url = link.get('href', '')
                if not full_url.startswith(('http://', 'https://')):
                    full_url = urljoin(BASE_URL, full_url)
                print(f"  Found menu link on news page: {full_url}")
                resp = try_url(full_url)
                if resp:
                    return full_url, resp

        # Check for JSON data embedded in the page (Wix often embeds blog data)
        scripts = news_soup.find_all('script', type='application/json')
        for script in scripts:
            if script.string and '/post/menu' in script.string.lower():
                urls_in_json = re.findall(r'/post/menu[^"\'\\<>\s]*', script.string, re.IGNORECASE)
                if urls_in_json:
                    # Take the first (likely most recent)
                    candidate = urljoin(BASE_URL, urls_in_json[0])
                    print(f"  Found menu URL in embedded JSON: {candidate}")
                    resp = try_url(candidate)
                    if resp:
                        return candidate, resp

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching news page: {e}")

    return None, None


def extract_image_urls(soup, page_url):
    """
    Extract all menu image URLs from the post page.
    Returns a list of full-resolution image URLs.
    
    The Wix blog post typically contains multiple images:
    - First image: weekly overview/cover (landscape 1754x1240)
    - Remaining images: daily menus (portrait 1240x1754)
    """
    image_urls = []
    page_text = str(soup)

    # Method 1: data-pin-media attributes — these contain full-res URLs
    # and are the most reliable source when the page is SSR'd by Wix.
    pin_media_imgs = soup.find_all('img', {'data-pin-media': True})
    for img in pin_media_imgs:
        pin_url = img.get('data-pin-media', '')
        if pin_url and 'logo' not in pin_url.lower():
            full_url = urljoin(page_url, pin_url)
            if full_url not in image_urls:
                image_urls.append(full_url)

    if image_urls:
        print(f"Found {len(image_urls)} image(s) using 'data-pin-media' attributes")
        return image_urls

    # Method 2: wow-image elements with data-image-info JSON
    # Wix uses <wow-image> custom elements with image metadata in a JSON attribute
    wow_images = soup.find_all('wow-image', {'data-image-info': True})
    for wow in wow_images:
        try:
            info = json.loads(wow.get('data-image-info', '{}'))
            image_data = info.get('imageData', {})
            uri = image_data.get('uri', '')
            if uri and '~mv2' in uri and 'logo' not in uri.lower():
                width = image_data.get('width', 1240)
                height = image_data.get('height', 1754)
                full_url = f"https://static.wixstatic.com/media/{uri}/v1/fill/w_{width},h_{height},al_c,q_90/{uri}"
                if full_url not in image_urls:
                    image_urls.append(full_url)
        except (json.JSONDecodeError, KeyError):
            continue

    if image_urls:
        print(f"Found {len(image_urls)} image(s) using wow-image data-image-info")
        return image_urls

    # Method 3: og:image meta tag (single image, usually the cover)
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        img_url = og_img['content']
        img_url = re.sub(r'/v1/fill/[^/]+/', '/v1/fill/w_1754,h_1240,al_c,q_90/', img_url)
        print(f"Found image URL from og:image meta tag: {img_url}")
        return [img_url]

    # Method 4: Wix static media URLs in page source (regex fallback)
    wix_media_urls = re.findall(
        r'(https://static\.wixstatic\.com/media/[a-f0-9_]+~mv2\.[a-z]+(?:/v1/fill/[^"\'<>\s]+)?)',
        page_text
    )
    if wix_media_urls:
        # Deduplicate by base URI (strip fill params for comparison)
        seen_uris = set()
        for url in wix_media_urls:
            if 'logo' in url.lower():
                continue
            # Extract base URI
            uri_match = re.search(r'/media/([a-f0-9_]+~mv2\.[a-z]+)', url)
            if uri_match:
                uri = uri_match.group(1)
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    # Construct full-res URL
                    full_url = f"https://static.wixstatic.com/media/{uri}/v1/fill/w_1240,h_1754,al_c,q_90/{uri}"
                    image_urls.append(full_url)

        if image_urls:
            print(f"Found {len(image_urls)} image(s) from Wix static media URLs in source")
            return image_urls

    # Method 5: Any large img src (last resort)
    all_imgs = soup.find_all('img', {'src': True})
    for img in all_imgs:
        src = img.get('src', '')
        if 'logo' in src.lower() or 'avatar' in src.lower():
            continue
        # Check for reasonable size in URL params
        width_match = re.search(r'w_(\d+)', src)
        if width_match and int(width_match.group(1)) > 400:
            full_url = urljoin(page_url, src)
            if full_url not in image_urls:
                image_urls.append(full_url)

    if image_urls:
        print(f"Found {len(image_urls)} image(s) using img src fallback")

    return image_urls


def perform_ocr_check(image_content):
    """Run OCR on image and check for menu keywords."""
    if not OCR_ENABLED:
        print("OCR libraries not available, skipping content check.")
        return True  # Assume menu if OCR disabled

    print("Performing OCR check on the downloaded image...")
    try:
        img_from_bytes = Image.open(BytesIO(image_content))
        img_gray = img_from_bytes.convert('L')
        custom_config = r'--psm 6'
        extracted_text = pytesseract.image_to_string(img_gray, config=custom_config).lower()
        print(f"Extracted text (first 200 chars): {extracted_text[:200]}...")

        found_keywords = [kw for kw in OCR_MENU_KEYWORDS if kw in extracted_text]
        if len(found_keywords) > 4:
            print(f"OCR check passed. Found {len(found_keywords)} keywords: {found_keywords}")
            return True
        else:
            print(f"OCR check failed. Only found {len(found_keywords)} keywords: {found_keywords}. Does not seem like a menu.")
            return False
    except Exception as ocr_error:
        print(f"Error during OCR processing: {ocr_error}")
        return False


# --- Main Execution ---
def main():
    print(f"{'='*60}")
    print(f"Menu Checker - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Step 1: Find the menu post URL
    menu_post_url, page_response = find_menu_post_url()

    if not menu_post_url:
        print("\nFailed to find the menu post URL using all strategies. Exiting.")
        exit(1)

    print(f"\nUsing menu post URL: {menu_post_url}")

    # Step 2: Parse the page and extract image
    if page_response:
        soup = BeautifulSoup(page_response.content, 'html.parser')
    else:
        try:
            response = requests.get(menu_post_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch menu post page: {e}")
            exit(1)

    image_urls = extract_image_urls(soup, menu_post_url)

    if not image_urls:
        print(f"\nCould not find any menu image URLs on the post page: {menu_post_url}")
        exit(1)

    print(f"\nFound {len(image_urls)} image(s) to process")

    # Step 3: Download images and find the best menu image
    # The first image is typically the weekly overview (landscape),
    # try it first, then fall back to subsequent images
    image_content = None
    used_url = None

    for i, img_url in enumerate(image_urls):
        try:
            print(f"\nDownloading image {i+1}/{len(image_urls)}: {img_url}")
            img_response = requests.get(img_url, headers=HEADERS, timeout=60)
            img_response.raise_for_status()
            content = img_response.content
            print(f"Downloaded {len(content)} bytes")

            # Skip very small files (likely broken or placeholder)
            if len(content) < 10000:
                print(f"  Skipping - too small ({len(content)} bytes), likely not a menu image")
                continue

            # Step 4: OCR verification on this image
            if perform_ocr_check(content):
                image_content = content
                used_url = img_url
                print(f"  This image passed OCR check - using it!")
                break
            else:
                print(f"  OCR check failed for this image, trying next...")
        except requests.exceptions.RequestException as e:
            print(f"  Error downloading: {e}")
            continue

    if not image_content:
        # If OCR failed on all images but we have content, use the first large one
        # (OCR might fail due to image format issues but the image could still be valid)
        print("\nOCR check failed on all images. Trying first large image without OCR...")
        for img_url in image_urls:
            try:
                img_response = requests.get(img_url, headers=HEADERS, timeout=60)
                img_response.raise_for_status()
                if len(img_response.content) > 50000:  # At least 50KB
                    image_content = img_response.content
                    used_url = img_url
                    print(f"Using first large image ({len(image_content)} bytes): {img_url}")
                    break
            except requests.exceptions.RequestException:
                continue

    if not image_content:
        print("\nFailed to download any valid menu image. Exiting.")
        exit(1)

    # Step 5: Hash comparison and notification
    existing_hash = calculate_hash(IMAGE_SAVE_PATH)
    new_hash = hashlib.sha256(image_content).hexdigest()

    if existing_hash == new_hash:
        print("\nThe menu image is unchanged. No update needed.")
        exit(0)

    print("\nNew menu detected! Updating and sending notification.")
    with open(IMAGE_SAVE_PATH, 'wb') as img_file:
        img_file.write(image_content)
    print(f"Image saved as '{IMAGE_SAVE_PATH}'")

    # Generate caption
    today = datetime.date.today()
    current_monday = get_current_monday(today)
    caption_date_str = current_monday.strftime('%d %b %Y')
    caption = f"Menu of the week starting {caption_date_str}\nSource: {menu_post_url}"
    print(f"\n{caption}")

    # Send to Telegram
    print("\nSending notification via Telegram...")
    send_telegram_photo(IMAGE_SAVE_PATH, caption)


if __name__ == "__main__":
    main()
