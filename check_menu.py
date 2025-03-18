import os
import requests
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from io import BytesIO
from datetime import datetime

# Scrape all images from the site
site_url = "https://www.ericssondining.ie/"
response = requests.get(site_url)
soup = BeautifulSoup(response.content, "html.parser")

image_urls = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]

# Ensure output folder exists
os.makedirs("downloaded_images", exist_ok=True)

# Download images
for idx, img_url in enumerate(image_urls):
    if not img_url.startswith("http"):
        img_url = site_url + img_url

    img_data = requests.get(img_url).content
    img_path = f"downloaded_images/image_{idx}.jpg"
    with open(img_path, 'wb') as img_file:
        img_file.write(img_data)

# OCR to find the correct week's menu
current_week_date = datetime.now().strftime("%d.%m.%Y")
valid_menu_image = None

for img_file in os.listdir("downloaded_images"):
    img_path = os.path.join("downloaded_images", img_file)
    try:
        img = Image.open(img_path)
        text = pytesseract.image_to_string(img)
        if current_week_date in text:
            valid_menu_image = img_path
            break
    except Exception as e:
        print(f"Failed to process {img_file}: {e}")

if valid_menu_image:
    print(f"✅ Found valid menu image: {valid_menu_image}")
else:
    print("❌ No valid menu image found yet — retrying later!")
