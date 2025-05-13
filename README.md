# Gmail Category Cleaner

A Python tool for efficiently managing and cleaning up Gmail categories (Promotions, Social, etc.) with built-in rate limiting and batch processing.

## Features

- Delete emails by category (Promotions, Social, Primary)
- Batch processing with smart rate limiting
- Dry-run mode for safe testing
- Detailed progress logging
- OAuth2 authentication with Gmail API

## Prerequisites

- Python 3.8+
- Gmail API access and credentials
- Google Cloud Project with Gmail API enabled

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd emailEraser
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Gmail API credentials:
   - Create a project in Google Cloud Console
   - Enable Gmail API
   - Create OAuth 2.0 credentials
   - Save credentials as `client_secrets.json` in the project root

## Usage

Basic usage:
```bash
python eraseEmails.py --category promotions --dry-run
```

Options:
- `--category`: Email category to process (promotions/social/primary)
- `--start-date`: Start date for email range (YYYY-MM-DD)
- `--end-date`: End date for email range (YYYY-MM-DD)
- `--dry-run`: Run without actually deleting emails

## Configuration

The tool includes several configurable parameters in `src/api/gmail_client.py`:
- Batch size (default: 20)
- Rate limiting parameters
- Retry settings

## Security

- OAuth2 credentials are stored locally
- Credentials are never committed to the repository
- All sensitive files are included in .gitignore

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - See LICENSE file for details 