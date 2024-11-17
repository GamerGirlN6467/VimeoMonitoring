# Vimeo Video Monitor

This project is a Python script that monitors Vimeo videos based on specific search queries and user uploads. It sends updates to a Discord channel using a webhook. The script is intended to run periodically using GitHub Actions and persist information about the videos it has seen.

## Features

- **Monitor Vimeo Videos**: Search Vimeo by keywords or user uploads.
- **Discord Integration**: Notify about new videos via Discord webhook.
- **Automated Execution**: GitHub Actions runs the script on a schedule.
- **Persistent Data**: Keeps track of known videos to avoid duplicates.

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/vimeo-video-monitor.git
cd vimeo-video-monitor
```

### 2. Python Environment Setup

Ensure you have Python 3.10.12 or later installed. You can use a virtual environment for managing dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file by copying `example.env`:

```bash
cp example.env .env
```

Edit `.env` and add your credentials:

- `ACCESS_TOKEN`: Your Vimeo API access token.
- `DISCORD_WEBHOOK_URL`: The URL for your Discord webhook.
- `SEARCH_QUERIES`: Comma-separated list of search keywords.
- `MONITORED_USERS`: Comma-separated list of user IDs to monitor.
- `KNOWN_LINKS_FILE`: The file name for storing known links (e.g., `known_links.txt`).

### 5. Run the Script Locally

To test the script locally before using GitHub Actions:

```bash
python main.py
```

### 6. GitHub Actions Automation

The project includes a GitHub Actions workflow (`.github/workflows/main.yml`) that automatically runs the script on a schedule.

#### Steps to Set Up GitHub Actions:

1. **Add Secrets**: Navigate to your GitHub repository's **Settings** > **Secrets and variables** > **Actions** and add the following secrets:

   - `ACCESS_TOKEN`
   - `DISCORD_WEBHOOK_URL`
   - `SEARCH_QUERIES`
   - `MONITORED_USERS`
   - `KNOWN_LINKS_FILE`

2. **Workflow Configuration**: The workflow is configured to run daily at midnight (UTC). You can adjust the schedule by modifying the `cron` expression in `.github/workflows/main.yml`.

### 7. Handling Persistent Data

The script uses a text file (`known_links.txt`) to track videos that have already been processed. This file is updated with new links each time the script runs, and changes are committed back to the repository automatically using GitHub Actions.

## File Structure

- **main.py**: The primary Python script that performs Vimeo searches and sends notifications.
- **requirements.txt**: Lists the Python dependencies.
- **example.env**: Sample environment file to help set up the required environment variables.
- **known\_links.txt**: Stores URLs of videos that have already been processed to avoid duplicate notifications.
- **.github/workflows/main.yml**: The GitHub Actions workflow configuration to automate script execution.

## Contributing

Contributions are welcome! Feel free to fork this repository and submit pull requests. Please ensure your changes do not expose any sensitive information or credentials.

### Guidelines

1. **Branch Naming**: Use descriptive branch names (e.g., `feature/add-user-monitoring` or `bugfix/handle-rate-limit`).
2. **Pull Requests**: Provide clear descriptions for PRs and explain the purpose of your changes.

## Security

- **Environment Variables**: Sensitive information is handled through environment variables and GitHub Secrets. Never commit the `.env` file with real credentials.
- **Logs**: Ensure that the script does not log sensitive information.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

If you have any questions or suggestions, feel free to open an issue or reach out directly.

Happy Monitoring!
