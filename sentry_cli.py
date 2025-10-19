#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
# ]
# ///
"""
Sentry CLI - Command-line interface for Sentry API

Usage:
    uv run sentry_cli.py fetch-issues -p PROJECT [OPTIONS]
    uv run sentry_cli.py fetch-issue -i ISSUE_ID
    uv run sentry_cli.py fetch-events -i ISSUE_ID [OPTIONS]

Or run directly from GitHub:
    uv run https://github.com/squareup/sentry-api/blob/main/sentry_cli.py fetch-issues -p billing-service

Examples:
    # First run will prompt for bootstrap if not configured
    uv run sentry_cli.py fetch-issues -p billing-service

    # Fetch issues with filters
    uv run sentry_cli.py fetch-issues -p sub2 --environment production --limit 20
    uv run sentry_cli.py fetch-issues -p sub2 --text-filter "set in the past"

    # Get issue details and stack traces
    uv run sentry_cli.py fetch-issue -i 6872665417
    uv run sentry_cli.py fetch-events -i 6872665417 --latest -v
"""

import os
import sys
import argparse
import json
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests


# ============================================================================
# Configuration Management
# ============================================================================

CONFIG_DIR = Path.home() / ".sentry-script"
CONFIG_FILE = CONFIG_DIR / "config.json"
ORG_SLUG = "square-inc"


def load_config() -> Optional[Dict[str, str]]:
    """Load configuration from ~/.sentry-script/config.json"""
    if not CONFIG_FILE.exists():
        return None

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)

        # Validate required fields
        if 'auth_token' not in config or 'org_slug' not in config:
            return None

        return config
    except Exception as e:
        print(f"⚠️  Warning: Failed to load config: {e}", file=sys.stderr)
        return None


def save_config(auth_token: str, org_slug: str):
    """Save configuration to ~/.sentry-script/config.json"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        'auth_token': auth_token,
        'org_slug': org_slug
    }

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    # Set restrictive permissions (owner read/write only)
    CONFIG_FILE.chmod(0o600)
    print(f"✅ Configuration saved to {CONFIG_FILE}")


def bootstrap_config():
    """Interactive bootstrap flow to set up configuration"""
    print("\n" + "="*80)
    print("🚀 Sentry CLI Bootstrap")
    print("="*80)
    print("\nThis is your first time running the Sentry CLI.")
    print("Let's set up your authentication token.\n")

    # Open browser to token creation page
    token_url = "https://square-inc.sentry.io/settings/account/api/auth-tokens/new-token"
    print(f"📱 Opening browser to create a new Sentry auth token...")
    print(f"   URL: {token_url}\n")

    try:
        webbrowser.open(token_url)
        print("✅ Browser opened. Please create a new token with these scopes:")
        print("   - org:read")
        print("   - project:read")
        print("   - event:read")
    except Exception as e:
        print(f"⚠️  Failed to open browser: {e}")
        print(f"   Please manually visit: {token_url}")

    print("\n" + "-"*80)

    # Prompt for auth token
    while True:
        auth_token = input("\nPaste your Sentry auth token: ").strip()
        if auth_token:
            break
        print("❌ Auth token cannot be empty. Please try again.")

    # Save configuration
    print(f"\nUsing organization: {ORG_SLUG}")
    save_config(auth_token, ORG_SLUG)

    print("\n" + "="*80)
    print("✅ Bootstrap complete! You can now use the Sentry CLI.")
    print("="*80 + "\n")


def ensure_configured() -> Dict[str, str]:
    """Ensure configuration exists, bootstrap if needed"""
    config = load_config()

    if config is None:
        bootstrap_config()
        config = load_config()

        if config is None:
            print("❌ Bootstrap failed. Configuration not found.", file=sys.stderr)
            sys.exit(1)

    return config


# ============================================================================
# Sentry API Client
# ============================================================================

class SentryClient:
    """Client for interacting with the Sentry API"""

    def __init__(self, auth_token: str, org_slug: str, base_url: str = "https://sentry.io/api/0"):
        """
        Initialize the Sentry API client

        Args:
            auth_token: Sentry authentication token
            org_slug: Organization slug (e.g., 'square-inc')
            base_url: Base URL for Sentry API (default: https://sentry.io/api/0)
        """
        self.base_url = base_url
        self.auth_token = auth_token
        self.org_slug = org_slug
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Make a GET request to the Sentry API"""
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response

    def _get_paginated(self, url: str, params: Optional[Dict[str, Any]] = None,
                       max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch all pages from a paginated endpoint

        Args:
            url: Initial URL to fetch
            params: Query parameters
            max_pages: Maximum number of pages to fetch (None for unlimited)

        Returns:
            List of all items from all pages
        """
        all_items = []
        page_count = 0

        while url:
            response = self._get(url, params)
            all_items.extend(response.json())

            # Check for next page
            if 'next' in response.links and \
               response.links['next'].get('results') == 'true':
                url = response.links['next']['url']
                params = None  # URL already has params
                page_count += 1

                if max_pages and page_count >= max_pages:
                    break
            else:
                break

        return all_items

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects in the organization"""
        url = f"{self.base_url}/organizations/{self.org_slug}/projects/"
        response = self._get(url)
        return response.json()

    def list_issues(self,
                   project_slug: Optional[str] = None,
                   stats_period: str = "24h",
                   limit: int = 100,
                   sort: str = "date",
                   query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List issues for a project or organization

        Args:
            project_slug: Project slug (None for organization-wide)
            stats_period: Time period for stats (e.g., '24h', '14d')
            limit: Maximum number of results per page
            sort: Sort order ('date', 'freq', 'new', 'trends', 'user')
            query: Search query string

        Returns:
            List of issues
        """
        if project_slug:
            url = f"{self.base_url}/projects/{self.org_slug}/{project_slug}/issues/"
        else:
            url = f"{self.base_url}/organizations/{self.org_slug}/issues/"

        params = {
            "statsPeriod": stats_period,
            "limit": limit,
            "sort": sort
        }

        if query:
            params["query"] = query

        response = self._get(url, params)
        return response.json()

    def get_issue(self, issue_id: str) -> Dict[str, Any]:
        """Get details for a specific issue"""
        url = f"{self.base_url}/issues/{issue_id}/"
        response = self._get(url)
        return response.json()

    def list_issue_events(self,
                          issue_id: str,
                          limit: int = 100,
                          paginate: bool = False,
                          max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List events for an issue

        Args:
            issue_id: Issue ID
            limit: Maximum number of results per page
            paginate: If True, fetch all pages
            max_pages: Maximum number of pages to fetch (None for unlimited)

        Returns:
            List of events
        """
        url = f"{self.base_url}/issues/{issue_id}/events/"
        params = {"limit": limit}

        if paginate:
            return self._get_paginated(url, params, max_pages)
        else:
            response = self._get(url, params)
            return response.json()

    def get_latest_event(self, issue_id: str) -> Dict[str, Any]:
        """Get the latest event for an issue"""
        url = f"{self.base_url}/issues/{issue_id}/events/latest/"
        response = self._get(url)
        return response.json()


# ============================================================================
# Output Formatting
# ============================================================================

def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to human-readable format"""
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except:
        return ts


def print_issue_summary(issue: dict, verbose: bool = False):
    """Pretty print an issue summary"""
    print(f"\n{'='*80}")
    print(f"ID: {issue['shortId']} | Status: {issue['status']} | Level: {issue.get('level', 'N/A')}")
    print(f"{'='*80}")
    print(f"\n{issue['title']}\n")

    count_val = int(issue['count'])
    print(f"Count:      {count_val:,d}")
    print(f"Users:      {issue['userCount']}")
    print(f"First Seen: {format_timestamp(issue['firstSeen'])}")
    print(f"Last Seen:  {format_timestamp(issue['lastSeen'])}")

    if issue.get('culprit'):
        print(f"Culprit:    {issue['culprit']}")

    if verbose:
        if issue.get('assignedTo'):
            print(f"Assigned:   {issue['assignedTo'].get('name', 'N/A')}")

        # Show 24h stats
        stats_24h = issue.get('stats', {}).get('24h', [])
        if stats_24h:
            total_24h = sum(point[1] for point in stats_24h)
            print(f"24h Count:  {total_24h:,d}")

    print(f"\nLink: {issue['permalink']}")


def print_event_summary(event: dict):
    """Pretty print an event summary"""
    print(f"\n{'='*80}")
    print(f"Event ID: {event.get('eventID', 'N/A')}")
    print(f"{'='*80}")

    print(f"Date:     {format_timestamp(event.get('dateCreated', 'N/A'))}")
    print(f"Platform: {event.get('platform', 'N/A')}")

    if event.get('user'):
        user = event['user']
        print(f"User:     {user.get('username') or user.get('email') or user.get('id', 'N/A')}")

    # Show tags
    tags = event.get('tags', [])
    if tags:
        print("\nTags:")
        for tag in tags[:10]:  # Show first 10 tags
            print(f"  {tag['key']}: {tag['value']}")


def matches_text_filter(issue: dict, text_filter: str) -> bool:
    """Check if an issue matches the text filter (case-insensitive search)"""
    text_filter_lower = text_filter.lower()

    # Search in title
    if text_filter_lower in issue.get('title', '').lower():
        return True

    # Search in culprit
    if text_filter_lower in issue.get('culprit', '').lower():
        return True

    # Search in metadata
    metadata = issue.get('metadata', {})
    if text_filter_lower in str(metadata.get('value', '')).lower():
        return True
    if text_filter_lower in str(metadata.get('type', '')).lower():
        return True

    return False


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_fetch_issues(args, client: SentryClient):
    """Fetch issues for a project"""
    print(f"\n🔍 Fetching issues for project: {args.project}")

    # Build query string
    query_parts = []

    # Add environment filter
    if args.environment:
        query_parts.append(f"environment:{args.environment}")

    # Add date filters
    if args.start_at:
        # Convert to ISO format for Sentry
        start_dt = datetime.fromisoformat(args.start_at)
        query_parts.append(f"firstSeen:>{start_dt.isoformat()}Z")

    if args.end_at:
        end_dt = datetime.fromisoformat(args.end_at)
        query_parts.append(f"firstSeen:<{end_dt.isoformat()}Z")

    # Add user query
    if args.query:
        query_parts.append(args.query)

    query = " ".join(query_parts) if query_parts else None

    # Determine stats period
    stats_period = args.stats_period or "24h"

    try:
        issues = client.list_issues(
            project_slug=args.project,
            stats_period=stats_period,
            limit=args.limit,
            sort=args.sort,
            query=query
        )

        # Apply text filter locally if provided
        if args.text_filter:
            original_count = len(issues)
            issues = [issue for issue in issues if matches_text_filter(issue, args.text_filter)]
            print(f"✅ Found {len(issues)} issues (filtered from {original_count} by text: '{args.text_filter}')")
        else:
            print(f"✅ Found {len(issues)} issues")

        if args.json:
            print(json.dumps(issues, indent=2))
        else:
            for issue in issues:
                print_issue_summary(issue, verbose=args.verbose)

        # Summary stats
        if not args.json:
            total_count = sum(int(issue['count']) for issue in issues)
            unresolved = sum(1 for issue in issues if issue['status'] == 'unresolved')
            print(f"\n{'='*80}")
            print(f"Summary: {len(issues)} issues | {unresolved} unresolved | {total_count:,d} total occurrences")
            print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Error fetching issues: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_fetch_issue(args, client: SentryClient):
    """Fetch details for a specific issue"""
    print(f"\n🔍 Fetching issue: {args.issue}")

    try:
        issue = client.get_issue(args.issue)

        if args.json:
            print(json.dumps(issue, indent=2))
        else:
            print_issue_summary(issue, verbose=True)

            # Show metadata
            metadata = issue.get('metadata', {})
            if metadata:
                print(f"\n{'='*80}")
                print("Metadata:")
                print(f"{'='*80}")
                print(f"Type:     {metadata.get('type', 'N/A')}")
                print(f"Value:    {metadata.get('value', 'N/A')}")
                if metadata.get('filename'):
                    print(f"File:     {metadata['filename']}")
                if metadata.get('function'):
                    print(f"Function: {metadata['function']}")

            # Show tags
            tags = issue.get('tags', [])
            if tags:
                print(f"\n{'='*80}")
                print("Tags:")
                print(f"{'='*80}")
                for tag in tags[:15]:
                    print(f"  {tag['key']}: ({tag['totalValues']} values)")

    except Exception as e:
        print(f"❌ Error fetching issue: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_fetch_events(args, client: SentryClient):
    """Fetch events for an issue"""
    print(f"\n🔍 Fetching events for issue: {args.issue}")

    try:
        if args.latest:
            events = [client.get_latest_event(args.issue)]
            print("✅ Fetched latest event")
        else:
            events = client.list_issue_events(
                issue_id=args.issue,
                limit=args.limit,
                paginate=args.paginate,
                max_pages=args.max_pages
            )
            print(f"✅ Found {len(events)} events")

        if args.json:
            print(json.dumps(events, indent=2))
        else:
            for event in events:
                print_event_summary(event)

                # Show stacktrace for latest event if verbose
                if args.verbose and event == events[0]:
                    entries = event.get('entries', [])
                    for entry in entries:
                        if entry.get('type') == 'exception':
                            values = entry.get('data', {}).get('values', [])
                            if values:
                                exc = values[0]
                                stacktrace = exc.get('stacktrace', {}).get('frames', [])
                                if stacktrace:
                                    print(f"\n{'='*80}")
                                    print("Stack Trace (last 5 frames):")
                                    print(f"{'='*80}")
                                    for frame in stacktrace[-5:]:
                                        filename = frame.get('filename', 'N/A')
                                        function = frame.get('function', 'N/A')
                                        lineno = frame.get('lineNo', 'N/A')
                                        print(f"  {filename}:{lineno} in {function}")

    except Exception as e:
        print(f"❌ Error fetching events: {e}", file=sys.stderr)
        sys.exit(1)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Sentry CLI - Command-line interface for Sentry API',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # fetch-issues command
    issues_parser = subparsers.add_parser(
        'fetch-issues',
        help='Fetch issues for a project',
        aliases=['issues']
    )
    issues_parser.add_argument('-p', '--project', required=True, help='Project slug (e.g., billing-service, sub2)')
    issues_parser.add_argument('--environment', '-e', help='Environment filter (production, staging, sandbox)')
    issues_parser.add_argument('--start-at', help='Start date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    issues_parser.add_argument('--end-at', help='End date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    issues_parser.add_argument('--query', '-q', help='Search query (e.g., "is:unresolved error_type:RuntimeError")')
    issues_parser.add_argument('--text-filter', '-t', help='Filter results by text in title/culprit/metadata (local search)')
    issues_parser.add_argument('--stats-period', help='Stats period (24h, 14d, 30d) - default: 24h')
    issues_parser.add_argument('--limit', '-l', type=int, default=50, help='Max results (default: 50)')
    issues_parser.add_argument('--sort', '-s', default='date', choices=['date', 'freq', 'new', 'trends', 'user'],
                              help='Sort order (default: date)')
    issues_parser.add_argument('--json', action='store_true', help='Output as JSON')
    issues_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    # fetch-issue command
    issue_parser = subparsers.add_parser(
        'fetch-issue',
        help='Fetch details for a specific issue',
        aliases=['issue']
    )
    issue_parser.add_argument('-i', '--issue', required=True, help='Issue ID (e.g., 6872665417 or BILLING-SERVICE-26S)')
    issue_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # fetch-events command
    events_parser = subparsers.add_parser(
        'fetch-events',
        help='Fetch events for an issue',
        aliases=['events']
    )
    events_parser.add_argument('-i', '--issue', required=True, help='Issue ID')
    events_parser.add_argument('--limit', '-l', type=int, default=100, help='Max events per page (default: 100)')
    events_parser.add_argument('--latest', action='store_true', help='Fetch only the latest event')
    events_parser.add_argument('--paginate', action='store_true', help='Fetch all pages')
    events_parser.add_argument('--max-pages', type=int, help='Max pages to fetch')
    events_parser.add_argument('--json', action='store_true', help='Output as JSON')
    events_parser.add_argument('--verbose', '-v', action='store_true', help='Show stack traces')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure configuration exists (bootstrap if needed)
    config = ensure_configured()

    # Initialize client
    client = SentryClient(config['auth_token'], config['org_slug'])

    # Route to command handler
    if args.command in ['fetch-issues', 'issues']:
        cmd_fetch_issues(args, client)
    elif args.command in ['fetch-issue', 'issue']:
        cmd_fetch_issue(args, client)
    elif args.command in ['fetch-events', 'events']:
        cmd_fetch_events(args, client)


if __name__ == '__main__':
    main()
