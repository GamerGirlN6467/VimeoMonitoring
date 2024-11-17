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
    """
    Send a single Discord message with multiple embeds, one for each video in video_data.
    """
    if not video_data:
        return  # No videos to send

    embeds = []
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

        embeds.append(embed)

    # Ensure the number of embeds does not exceed Discord's limit
    if len(embeds) > 10:
        print(f"Number of embeds ({len(embeds)}) exceeds Discord's limit. Trimming to 10.")
        embeds = embeds[:10]

    data = {"embeds": embeds}

    # Send the request to Discord Webhook
    response = None
    for attempt in range(RETRY_LIMIT):
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, json=data)
            if response.status_code == 204 or response.status_code == 200:
                print(f"Sent {len(embeds)} embed(s) to Discord successfully.")
                break
            elif response.status_code == 429:
                retry_after = response.json().get('retry_after', DEFAULT_SLEEP_INTERVAL)
                print(f"Rate limited by Discord. Retrying after {retry_after} seconds.")
                time.sleep(retry_after + 1)  # Adding 1 second buffer
            else:
                print(f"Failed to send embeds to Discord: {response.status_code} - {response.text}")
                break  # Do not retry for other HTTP errors
        except requests.exceptions.RequestException as e:
            print(f"Request exception on attempt {attempt + 1}/{RETRY_LIMIT}: {e}")
            time.sleep(DEFAULT_SLEEP_INTERVAL)
    else:
        print("Exceeded maximum retries. Failed to send embeds to Discord.")

def main():
    try:
        known_links = read_known_links()
        new_links = set()
        # Dictionary to hold new videos per query or user
        new_videos_per_query = {}
        new_videos_per_user = {}

        # Step 1: Search for videos by keywords
        for query in SEARCH_QUERIES:
            query = query.strip()
            if not query:
                continue
            response = search_vimeo(query)
            if response:
                video_links = extract_video_links(response)
                for item in response['data']:
                    if item['link'] not in known_links:
                        # Initialize list for this query if not already
                        if query not in new_videos_per_query:
                            new_videos_per_query[query] = []
                        new_videos_per_query[query].append(item)
                        new_links.add(item['link'])

        # Step 2: Check for videos uploaded by monitored users
        for user_id in MONITORED_USERS:
            user_id = user_id.strip()
            if not user_id:
                continue
            response = get_user_uploads(user_id)
            if response:
                for item in response['data']:
                    if item['link'] not in known_links:
                        # Initialize list for this user if not already
                        if user_id not in new_videos_per_user:
                            new_videos_per_user[user_id] = []
                        new_videos_per_user[user_id].append(item)
                        new_links.add(item['link'])

        # Step 3: Send Discord messages grouped by query
        for query, videos in new_videos_per_query.items():
            if videos:
                print(f"Found {len(videos)} new video(s) for query '{query}'. Sending to Discord...")
                send_detailed_to_discord(videos, query)

        # Step 4: Send Discord messages grouped by user
        for user_id, videos in new_videos_per_user.items():
            if videos:
                print(f"Found {len(videos)} new video(s) from user '{user_id}'. Sending to Discord...")
                send_detailed_to_discord(videos, f"User: {user_id}")

        # Step 5: Update known links
        if new_links:
            known_links.update(new_links)
            write_known_links(known_links)
        else:
            print("No new links found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
