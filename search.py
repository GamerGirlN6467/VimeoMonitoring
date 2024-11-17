import os
import time
import requests
from datetime import datetime, timezone, timedelta
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SEARCH_QUERIES = os.getenv("SEARCH_QUERIES").split(",")
MONITORED_USERS = os.getenv("MONITORED_USERS").split(",")
KNOWN_LINKS_FILE = os.getenv("KNOWN_LINKS_FILE")
DATE_FORMAT = "%Y-%m-%d"
DISCORD_CHAR_LIMIT = 1950  # Discord's character limit
# Updated FIELDS to include duration and user.pictures.sizes
FIELDS = "uri,name,link,description,pictures.sizes,user.link,user.name,user.pictures.sizes,width,height,created_time,duration"
RETRY_LIMIT = 5
DEFAULT_SLEEP_INTERVAL = 2  # Default rate limiting interval
LOCK_FILE = "/tmp/vimeo_script.lock"

def read_known_links():
    if not os.path.exists(KNOWN_LINKS_FILE):
        print("No known links file found. Starting with an empty set.")
        return set()
    with open(KNOWN_LINKS_FILE, 'r') as file:
        return set(line.strip() for line in file)

def write_known_links(links):
    with open(KNOWN_LINKS_FILE, 'w') as file:
        for link in links:
            file.write(f"{link}\n")

def handle_rate_limiting(headers):
    if 'X-RateLimit-Remaining' in headers and 'X-RateLimit-Reset' in headers:
        remaining = int(headers['X-RateLimit-Remaining'])
        reset_time = headers['X-RateLimit-Reset']

        try:
            reset_datetime = datetime.fromtimestamp(int(reset_time), tz=timezone.utc)
        except ValueError:
            reset_datetime = datetime.strptime(reset_time, '%Y-%m-%dT%H:%M:%S%z')

        current_time = datetime.now(timezone.utc)
        if remaining <= 1:
            sleep_time = (reset_datetime - current_time).total_seconds() + 1
            print(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds.")
            time.sleep(max(sleep_time, 0))
        else:
            time.sleep(DEFAULT_SLEEP_INTERVAL)
    else:
        time.sleep(DEFAULT_SLEEP_INTERVAL)

def request_with_retries(url, headers, params=None, json=None, method="get"):
    for attempt in range(RETRY_LIMIT):
        try:
            if method == "get":
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                handle_rate_limiting(response.headers)
                return response.json()
            elif method == "post":
                response = requests.post(url, headers=headers, json=json)
                response.raise_for_status()
                handle_rate_limiting(response.headers)
                return None  # Webhook does not return JSON
        except requests.exceptions.RequestException as e:
            print(f"Request error ({attempt + 1}/{RETRY_LIMIT}): {e}")
            time.sleep(DEFAULT_SLEEP_INTERVAL)
        except ValueError as e:
            print(f"JSON decode error ({attempt + 1}/{RETRY_LIMIT}): {e}")
            time.sleep(DEFAULT_SLEEP_INTERVAL)
    return None

def search_vimeo(keyword, per_page=10):
    url = "https://api.vimeo.com/videos"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    params = {
        "query": keyword,
        "per_page": per_page,
        "fields": FIELDS,
        "sort": "date",  # Sort by latest
        "direction": "desc"  # Ensure descending order
    }
    return request_with_retries(url, headers, params=params)

def get_user_uploads(user_id, per_page=10):
    url = f"https://api.vimeo.com/users/{user_id}/videos"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    params = {
        "per_page": per_page,
        "fields": FIELDS,
        "sort": "date",
        "direction": "desc"
    }
    return request_with_retries(url, headers, params=params)

def extract_video_links(data):
    links = set()
    if data:
        for item in data['data']:
            links.add(item['link'])
    return links

def trim_text(text, max_length, ellipsis=True):
    if text is None:
        return ""
    if len(text) > max_length:
        return text[:max_length - 3] + "..." if ellipsis else text[:max_length]
    return text

def format_duration(seconds):
    """Format duration from seconds to HH:MM:SS."""
    try:
        seconds = int(seconds)
        return str(timedelta(seconds=seconds))
    except (TypeError, ValueError):
        return "N/A"

def send_detailed_to_discord(video_data, keyword):
    for video in video_data:
        headers = {"Content-Type": "application/json"}

        description = video.get('description', 'No description available')
        description = trim_text(description, 4096)

        user = video.get('user', {})
        user_name = user.get('name', 'Unknown User')
        user_link = user.get('link', '')

        # Attempt to get user's profile picture
        user_avatar_url = None
        if user.get('pictures') and user['pictures'].get('sizes'):
            # Use the highest resolution profile picture
            user_avatar_url = user['pictures']['sizes'][-1]['link']
            print(f"User Avatar URL: {user_avatar_url}")  # Debugging line

        # Format duration
        duration_seconds = video.get('duration')
        formatted_duration = format_duration(duration_seconds)

        fields = [
            {
                "name": "Matched Keyword",
                "value": trim_text(keyword, 1024),
                "inline": True
            },
            {
                "name": "Resolution",
                "value": trim_text(f"{video.get('width', 'N/A')}x{video.get('height', 'N/A')}", 1024),
                "inline": True
            },
            {
                "name": "Duration",
                "value": trim_text(formatted_duration, 1024),
                "inline": True
            }
        ]

        title = trim_text(video.get('name', 'No Title'), 256)

        # Extract and format the upload timestamp
        created_time = video.get('created_time')
        timestamp = None
        if created_time:
            try:
                timestamp = datetime.fromisoformat(created_time.rstrip('Z')).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                print(f"Failed to parse created_time: {created_time}")

        embed = {
            "title": title,
            "url": video['link'],
            "description": description,
            "image": {
                "url": video['pictures']['sizes'][-1]['link']  # Use highest resolution thumbnail
            },
            "fields": fields,
            "author": {
                "name": user_name,
                "url": user_link,
                "icon_url": user_avatar_url  # Add the avatar icon to the author field
            }
        }

        # Only include the timestamp if it's valid
        if timestamp:
            embed['timestamp'] = timestamp

        # Calculate total embed length to ensure it doesn't exceed Discord's limit
        total_embed_length = len(title) + len(description)
        for field in fields:
            total_embed_length += len(field['name']) + len(field['value'])

        if total_embed_length > 6000:
            # Reduce description if total length exceeds 6000
            max_desc_length = 6000 - (total_embed_length - len(description))
            description = trim_text(description, max_desc_length)
            embed['description'] = description

        data = {"embeds": [embed]}
        
        # Send the request to Discord Webhook
        request_with_retries(DISCORD_WEBHOOK_URL, headers, json=data, method="post")


def create_lock():
    if os.path.exists(LOCK_FILE):
        print("Script is already running. Exiting.")
        sys.exit(0)
    else:
        open(LOCK_FILE, 'w').close()

def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def main():
    create_lock()
    try:
        known_links = read_known_links()
        new_links = set()
        new_video_data = []

        # Step 1: Search for videos by keywords
        for query in SEARCH_QUERIES:
            response = search_vimeo(query)
            if response:
                video_links = extract_video_links(response)
                for item in response['data']:
                    if item['link'] not in known_links:
                        item['matched_keyword'] = query
                        new_video_data.append(item)
                        new_links.add(item['link'])

        # Step 2: Check for videos uploaded by monitored users
        for user_id in MONITORED_USERS:
            response = get_user_uploads(user_id)
            if response:
                for item in response['data']:
                    if item['link'] not in known_links:
                        item['matched_keyword'] = f"User: {user_id}"
                        new_video_data.append(item)
                        new_links.add(item['link'])

        # Filter new links to avoid duplicates
        filtered_new_links = new_links - known_links

        if filtered_new_links:
            for video in new_video_data:
                send_detailed_to_discord([video], video['matched_keyword'])
            known_links.update(filtered_new_links)
            write_known_links(known_links)
        else:
            print("No new links found.")
    finally:
        remove_lock()

if __name__ == "__main__":
    main()