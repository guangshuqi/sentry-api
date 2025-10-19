#!/usr/bin/env python3
"""
Sentry API Client

A Python client for interacting with the Sentry API.
Supports listing projects, issues, events, and paginated queries.

Usage:
    export SENTRY_AUTH_TOKEN="your_token_here"
    python sentry_client.py
"""

import os
import sys
from typing import Optional, List, Dict, Any
import requests


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

    def list_organizations(self) -> List[Dict[str, Any]]:
        """List all organizations the authenticated user has access to"""
        url = f"{self.base_url}/organizations/"
        response = self._get(url)
        return response.json()

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects in the organization"""
        url = f"{self.base_url}/organizations/{self.org_slug}/projects/"
        response = self._get(url)
        return response.json()

    def get_project(self, project_slug: str) -> Dict[str, Any]:
        """Get details for a specific project"""
        url = f"{self.base_url}/projects/{self.org_slug}/{project_slug}/"
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

    def update_issue(self,
                     issue_id: str,
                     status: Optional[str] = None,
                     assigned_to: Optional[str] = None,
                     has_seen: Optional[bool] = None,
                     is_bookmarked: Optional[bool] = None,
                     is_subscribed: Optional[bool] = None) -> Dict[str, Any]:
        """
        Update an issue

        Args:
            issue_id: Issue ID
            status: New status ('resolved', 'unresolved', 'ignored', 'resolvedInNextRelease')
            assigned_to: User or team to assign to
            has_seen: Mark as seen/unseen
            is_bookmarked: Bookmark/unbookmark
            is_subscribed: Subscribe/unsubscribe

        Returns:
            Updated issue data
        """
        url = f"{self.base_url}/issues/{issue_id}/"
        data = {}

        if status:
            data["status"] = status
        if assigned_to is not None:
            data["assignedTo"] = assigned_to
        if has_seen is not None:
            data["hasSeen"] = has_seen
        if is_bookmarked is not None:
            data["isBookmarked"] = is_bookmarked
        if is_subscribed is not None:
            data["isSubscribed"] = is_subscribed

        response = requests.put(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()


def print_issue_summary(issue: Dict[str, Any]):
    """Pretty print an issue summary"""
    print(f"\n{issue['shortId']}: {issue['title'][:100]}")
    print(f"  Status: {issue['status']}")
    print(f"  Count: {issue['count']}")
    print(f"  Users: {issue['userCount']}")
    print(f"  First seen: {issue['firstSeen']}")
    print(f"  Last seen: {issue['lastSeen']}")
    print(f"  Link: {issue['permalink']}")


def main():
    """Example usage of the Sentry API client"""

    # Get auth token from environment
    token = os.environ.get("SENTRY_AUTH_TOKEN")
    if not token:
        print("Error: SENTRY_AUTH_TOKEN environment variable not set", file=sys.stderr)
        print("Please set it with: export SENTRY_AUTH_TOKEN='your_token'", file=sys.stderr)
        sys.exit(1)

    # Initialize client
    org_slug = "square-inc"
    client = SentryClient(token, org_slug)

    print(f"Sentry API Client - Organization: {org_slug}\n")
    print("=" * 80)

    # Example 1: List projects
    print("\n📦 Listing projects...")
    try:
        projects = client.list_projects()
        print(f"Found {len(projects)} projects")
        for project in projects[:5]:
            print(f"  - {project['slug']}: {project['name']}")
    except Exception as e:
        print(f"Error listing projects: {e}")

    # Example 2: List issues for billing-service
    print("\n🐛 Listing recent issues for billing-service...")
    try:
        issues = client.list_issues("billing-service", stats_period="24h", limit=10)
        print(f"Found {len(issues)} issues in the last 24h")

        for issue in issues[:3]:
            print_issue_summary(issue)
    except Exception as e:
        print(f"Error listing issues: {e}")

    # Example 3: Get issue details
    if issues:
        print("\n🔍 Getting details for first issue...")
        try:
            issue_id = issues[0]['id']
            details = client.get_issue(issue_id)
            print(f"\nDetailed info for {details['shortId']}:")
            print(f"  Culprit: {details.get('culprit', 'N/A')}")
            print(f"  Level: {details.get('level', 'N/A')}")
            print(f"  Platform: {details.get('platform', 'N/A')}")

            # Get latest event
            print("\n📨 Getting latest event...")
            latest_event = client.get_latest_event(issue_id)
            print(f"  Event ID: {latest_event.get('eventID', 'N/A')}")
            print(f"  Date: {latest_event.get('dateCreated', 'N/A')}")

        except Exception as e:
            print(f"Error getting issue details: {e}")

    print("\n" + "=" * 80)
    print("✅ Done!")


if __name__ == "__main__":
    main()
