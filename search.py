import os
import requests

# Get environment variables
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SEARCH_QUERIES = os.getenv("SEARCH_QUERIES")

# Prepare the raw and split data
raw_data = f"Raw SEARCH_QUERIES: {SEARCH_QUERIES}"
split_data = f"Split SEARCH_QUERIES: {SEARCH_QUERIES.split(',') if SEARCH_QUERIES else []}"

# Send to Discord webhook
data = {
    "content": f"{raw_data}\n{split_data}"
}

requests.post(DISCORD_WEBHOOK_URL, json=data)
