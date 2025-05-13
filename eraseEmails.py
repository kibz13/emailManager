#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import sys
import time
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from src.api.gmail_client import GmailClient
from src.api.auth import Auth
from src.config import SCOPES, CLIENT_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_credentials():
    """Set up and return Gmail credentials."""
    creds = None
    try:
        # Try to load existing credentials
        creds = Credentials.from_authorized_user_file('user_credentials.json', SCOPES)
    except Exception:
        logger.info("No valid credentials found.")
    
    # If credentials don't exist or are invalid
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully")
            except Exception as e:
                logger.error(f"Error refreshing credentials: {e}")
                creds = None
        
        # If still no valid credentials, need new ones
        if not creds:
            try:
                flow = InstalledAppFlow.from_client_config(
                    CLIENT_CONFIG,
                    SCOPES,
                    redirect_uri=CLIENT_CONFIG['installed']['redirect_uris'][0]
                )
                auth = Auth(flow)
                oauth_creds = auth.get_client_credentials()
                auth.write_credentials_to_json(oauth_creds)
                creds = oauth_creds.to_google_credentials()
                logger.info("New credentials obtained and saved")
            except Exception as e:
                logger.error(f"Error obtaining new credentials: {e}")
                raise

    return creds

def validate_date(date_str):
    """Validate date string format."""
    try:
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")

def main():
    parser = argparse.ArgumentParser(
        description='Delete Gmail messages by category within a date range.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--category',
        type=str,
        required=True,
        choices=['promotions', 'social', 'primary'],
        help='Email category to delete (promotions/social/primary)'
    )
    
    parser.add_argument(
        '--start-date',
        type=validate_date,
        help='Start date (YYYY-MM-DD)',
        default=(datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    )
    
    parser.add_argument(
        '--end-date',
        type=validate_date,
        help='End date (YYYY-MM-DD)',
        default=datetime.datetime.now().strftime('%Y-%m-%d')
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )

    args = parser.parse_args()

    try:
        # Set up credentials and client
        credentials = setup_credentials()
        gmail_client = GmailClient(credentials)
        
        # Fetch emails
        logger.info(f"Fetching {args.category} emails from {args.start_date} to {args.end_date}")
        emails = gmail_client.fetch_user_emails(
            start_date=args.start_date,
            end_date=args.end_date,
            category=args.category
        )
        
        if not emails:
            logger.info("No emails found matching the criteria")
            return
        
        # Show summary
        email_count = len(emails)
        logger.info(f"Found {email_count} emails in the {args.category} category")
        
        if args.dry_run:
            logger.info("DRY RUN - No emails will be deleted")
            return
        
        # Confirm deletion
        confirm = input(f"Are you sure you want to delete {email_count} emails? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Operation cancelled by user")
            return
        
        # Create a simple cache structure expected by delete_user_emails
        cache = {args.category: emails}
        deleted_count = gmail_client.delete_user_emails(cache, args.category)
        
        logger.info(f"Successfully deleted {deleted_count} emails")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
