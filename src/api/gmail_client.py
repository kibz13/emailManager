from googleapiclient.discovery import build
import logging
from src.models.ouath_credentials import OAuthCredentials
import time
from typing import List, Dict
from googleapiclient.http import BatchHttpRequest
from googleapiclient.errors import HttpError
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GmailError(Exception):
    """Custom exception for Gmail-related errors"""
    pass

class RateLimitError(GmailError):
    """Raised when rate limit is hit"""
    pass

class GmailClient:
    # Gmail API quotas (https://developers.google.com/gmail/api/reference/quota)
    QUOTA_USER_QUERIES_PER_SEC = 25
    QUOTA_USER_QUERIES_PER_DAY = 1000000
    MAX_RETRIES = 5
    MIN_BACKOFF_TIME = 2  # Increased initial backoff time
    MAX_BACKOFF_TIME = 120  # Increased maximum backoff time
    BATCH_DELAY = 2  # Increased delay between batches
    
    def __init__(self, client_credentials, batch_size: int = 20):  # Reduced default batch size
        if isinstance(client_credentials, OAuthCredentials):
            client_credentials = client_credentials.to_google_credentials()
        self.gmail_client = build('gmail', 'v1', credentials=client_credentials)
        self.batch_size = min(batch_size, 25)  # More conservative batch size limit
        self.current_batch_success = 0
        self.current_batch_errors = 0
        self.total_requests = 0
        self.rate_limit_hits = 0
        self.last_request_time = 0

    def _wait_for_quota(self):
        """Ensure we don't exceed quota by waiting if needed"""
        now = time.time()
        if self.last_request_time > 0:
            elapsed = now - self.last_request_time
            if elapsed < 0.1:  # Ensure minimum 100ms between requests
                time.sleep(0.1 - elapsed)
        self.last_request_time = time.time()

    def _handle_rate_limit(self, retry_count: int) -> float:
        """
        Implements exponential backoff with jitter for rate limit handling.
        Returns the time to sleep in seconds.
        """
        self.rate_limit_hits += 1
        if retry_count >= self.MAX_RETRIES:
            raise RateLimitError(f"Maximum retry attempts reached. Total rate limits hit: {self.rate_limit_hits}")
        
        # Calculate exponential backoff with jitter
        backoff = min(self.MAX_BACKOFF_TIME, self.MIN_BACKOFF_TIME * (2 ** retry_count))
        jitter = random.uniform(0, 0.1 * backoff)  # Add 0-10% jitter
        total_delay = backoff + jitter
        
        logger.warning(f"Rate limit hit #{self.rate_limit_hits}. Backing off for {total_delay:.1f} seconds "
                      f"(retry {retry_count + 1}/{self.MAX_RETRIES})")
        return total_delay

    def fetch_user_emails(self, start_date="2024-09-01", end_date="2024-10-16", category="promotions"):
        query = f"category:{category} after:{start_date} before:{end_date}"
        emails = []
        page_token = None
        retry_count = 0

        try:
            while True:
                try:
                    results = self.gmail_client.users().messages().list(
                        userId='me',
                        q=query,
                        pageToken=page_token,
                        maxResults=100  # Limit results per page
                    ).execute()
                    
                    self.total_requests += 1
                    messages = results.get('messages', [])
                    if not messages:
                        break

                    emails.extend(messages)
                    page_token = results.get('nextPageToken')
                    
                    if not page_token:
                        break

                    # Add delay between pages to respect rate limits
                    time.sleep(2)  # Increased delay between pages

                except HttpError as e:
                    if e.resp.status == 429:  # Rate limit exceeded
                        retry_count += 1
                        sleep_time = self._handle_rate_limit(retry_count)
                        time.sleep(sleep_time)
                        continue
                    raise

            n = len(emails)
            logger.info(f"Successfully retrieved {n} emails from gmail")
            return emails

        except Exception as e:
            logger.error(f"Error retrieving emails: {str(e)}")
            raise GmailError(f"Failed to fetch emails: {str(e)}")

    def _callback_success(self, request_id, response, exception):
        """Callback for batch request success"""
        if exception is not None:
            if isinstance(exception, HttpError) and exception.resp.status == 429:
                # Don't count rate limit errors as permanent failures
                logger.warning(f"Rate limit hit in batch for message {request_id}")
                self.current_batch_errors += 1
            else:
                logger.error(f"Error in batch request {request_id}: {str(exception)}")
                self.current_batch_errors += 1
        else:
            self.current_batch_success += 1

    def delete_user_emails(self, cache: Dict[str, List[dict]], category: str) -> int:
        """
        Delete emails in batches with rate limit handling.
        
        Args:
            cache: Dictionary containing email messages by category
            category: The category of emails to delete
            
        Returns:
            int: Number of successfully deleted messages
        """
        messages = cache.get(category)
        if not messages:
            logger.warning(f"No messages found in cache for category: {category}")
            return 0
            
        msg_count = len(messages)
        deleted_count = 0
        batch_count = 0
        retry_count = 0
        logger.info(f"Starting batch deletion of {msg_count} messages with batch size {self.batch_size}")
        
        # Process in batches
        for i in range(0, len(messages), self.batch_size):
            batch = messages[i:i + self.batch_size]
            batch_count += 1
            
            while True:  # Retry loop for rate limits
                try:
                    # Reset batch counters
                    self.current_batch_success = 0
                    self.current_batch_errors = 0
                    
                    # Create new batch request
                    batch_request = self.gmail_client.new_batch_http_request(callback=self._callback_success)
                    
                    # Add each message to the batch
                    for message in batch:
                        self._wait_for_quota()
                        batch_request.add(
                            self.gmail_client.users().messages().trash(
                                userId='me',
                                id=message['id']
                            ),
                            request_id=message['id']
                        )
                    
                    # Execute batch request
                    self._wait_for_quota()
                    batch_request.execute()
                    self.total_requests += len(batch)
                    
                    # Update counts
                    deleted_count += self.current_batch_success
                    logger.info(f"Batch {batch_count}: Successfully moved {self.current_batch_success} messages to trash "
                              f"({self.current_batch_errors} errors). Total rate limits hit: {self.rate_limit_hits}")
                    
                    # Reset retry count on success
                    retry_count = 0
                    
                    # Add a delay between batches
                    if i + self.batch_size < len(messages):
                        time.sleep(self.BATCH_DELAY)
                    
                    break  # Break the retry loop on success
                    
                except HttpError as e:
                    if e.resp.status == 429:  # Rate limit exceeded
                        retry_count += 1
                        sleep_time = self._handle_rate_limit(retry_count)
                        time.sleep(sleep_time)
                        continue
                    raise
                except Exception as e:
                    logger.error(f"Error processing batch {batch_count}: {str(e)}")
                    # If batch fails, try individual deletions as fallback
                    for message in batch:
                        for individual_retry in range(self.MAX_RETRIES):
                            try:
                                self._wait_for_quota()
                                self.gmail_client.users().messages().trash(
                                    userId='me',
                                    id=message['id']
                                ).execute()
                                self.total_requests += 1
                                deleted_count += 1
                                logger.info(f"Fallback: Successfully deleted message {message['id']}")
                                break
                            except HttpError as inner_e:
                                if inner_e.resp.status == 429:
                                    sleep_time = self._handle_rate_limit(individual_retry)
                                    logger.warning(f"Rate limit hit during fallback, backing off for {sleep_time:.1f} seconds")
                                    time.sleep(sleep_time)
                                    continue
                                logger.error(f"Failed to delete message {message['id']}: {str(inner_e)}")
                                break
                            except Exception as inner_e:
                                logger.error(f"Failed to delete message {message['id']}: {str(inner_e)}")
                                break
                        time.sleep(2)  # Increased delay between individual retries
                    break  # Break the retry loop after fallback attempts
            
            # Log progress
            progress = (deleted_count / msg_count) * 100
            logger.info(f"Progress: {progress:.1f}% ({deleted_count}/{msg_count} messages deleted). "
                       f"Total requests: {self.total_requests}, Rate limits hit: {self.rate_limit_hits}")

        logger.info(f"Deletion complete. Successfully deleted {deleted_count} out of {msg_count} messages. "
                   f"Total rate limits hit: {self.rate_limit_hits}")
        return deleted_count
