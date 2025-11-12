"""
Wrapper around the Supabase Python client for domain-specific queries.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Iterable, List, Mapping

import json
import ssl
import urllib.request
import urllib.parse
import httpx
from supabase import Client, create_client

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Encapsulates data access operations used by the bot.
    """

    def __init__(
        self,
        *,
        supabase_url: str,
        supabase_key: str,
        schema: str | None = None,
    ) -> None:
        # Filter out non-ASCII schema values before creating client
        # Always set to None to avoid any encoding issues with Supabase client
        safe_schema: str | None = None
        if schema:
            try:
                schema.encode("ascii")
                # Even if ASCII, don't use schema() as it's not supported
                # and may cause encoding issues in PostgREST client
                safe_schema = None
                logger.info(
                    "Schema provided but not used (schema() not supported by Supabase Python client)"
                )
            except UnicodeEncodeError:
                logger.warning(
                    "Supabase schema '%s' contains non-ASCII characters; "
                    "schema scoping will be disabled to avoid encoding issues.",
                    schema[:50] if len(schema) > 50 else schema,
                )
        # Create client without schema to avoid encoding issues
        # Always use default schema (usually 'public')
        # Remove SUPABASE_SCHEMA from environment to prevent Supabase client
        # from reading it and causing UnicodeEncodeError
        # NOTE: Only remove SUPABASE_SCHEMA, not other SUPABASE_* variables
        # like SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY which are critical
        import os
        
        # Remove SUPABASE_SCHEMA from environment before creating client
        # NOTE: Only remove SUPABASE_SCHEMA, not other SUPABASE_* variables
        # like SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY which are critical
        removed_vars = {}
        if "SUPABASE_SCHEMA" in os.environ:
            value = os.environ.pop("SUPABASE_SCHEMA", None)
            if value:
                removed_vars["SUPABASE_SCHEMA"] = value
                try:
                    value.encode("ascii")
                    logger.info(
                        "Removed SUPABASE_SCHEMA from environment to avoid encoding issues (will not be restored)"
                    )
                except UnicodeEncodeError:
                    logger.warning(
                        "Removed SUPABASE_SCHEMA from environment (contains non-ASCII characters, will not be restored)"
                    )
        
        logger.info("Creating Supabase client (schema will not be used)")
        try:
            self._client: Client = create_client(supabase_url, supabase_key)
            logger.info("Supabase client created successfully")
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when creating Supabase client: %s. "
                "This may be caused by non-ASCII characters in environment variables. "
                "Trying to create client again...",
                e,
                exc_info=True,
            )
            # Make sure SUPABASE_SCHEMA is still removed
            if "SUPABASE_SCHEMA" in os.environ:
                os.environ.pop("SUPABASE_SCHEMA", None)
            # Try to create client again
            self._client: Client = create_client(supabase_url, supabase_key)
            logger.info("Supabase client created successfully after removing problematic variables")
        finally:
            # Never restore removed variables to avoid encoding issues
            # Even if they're ASCII, they can cause problems with Supabase client
            # The Supabase client reads them during initialization and caches them
            if removed_vars:
                logger.info(
                    "Removed SUPABASE_SCHEMA from environment to avoid encoding issues. "
                    "It will not be restored. Please remove SUPABASE_SCHEMA from Railway environment variables."
                )
        
        self._schema: str | None = None  # Always None to avoid encoding issues
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key
        
        # Store parameters for direct HTTP requests using requests library
        # We use requests instead of httpx to avoid UnicodeEncodeError issues
        # with environment variables containing non-ASCII characters
        self._http_base_url = f"{supabase_url}/rest/v1"
        self._http_headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._http_timeout = 30.0

    def _safe_table_access(self, table_name: str):
        """
        Safely access a Supabase table by temporarily removing SUPABASE_SCHEMA
        from environment to prevent UnicodeEncodeError.
        
        Note: Even though we remove SUPABASE_SCHEMA from environment, the Supabase
        client may have already cached it during initialization. We catch the error
        and re-create the client without SUPABASE_SCHEMA in environment.
        """
        import os
        
        # Remove SUPABASE_SCHEMA from environment before any operation
        # This must be done before accessing the client, as the client
        # may read it during initialization
        # NOTE: Only remove SUPABASE_SCHEMA, not other SUPABASE_* variables
        # like SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY which are critical
        original_schema = os.environ.pop("SUPABASE_SCHEMA", None)
        problematic_vars = {}
        if original_schema:
            problematic_vars["SUPABASE_SCHEMA"] = original_schema
            logger.debug("Removed SUPABASE_SCHEMA from environment")
        
        try:
            return self._client.table(table_name)
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when accessing table '%s': %s. "
                "This is likely caused by SUPABASE_SCHEMA environment variable "
                "containing non-ASCII characters that were cached during client initialization. "
                "Re-creating client without SUPABASE_SCHEMA...",
                table_name,
                e,
                exc_info=True,
            )
            # Re-create client without SUPABASE_SCHEMA in environment
            # Make sure SUPABASE_SCHEMA is still removed before creating new client
            # NOTE: Only remove SUPABASE_SCHEMA, not other SUPABASE_* variables
            if "SUPABASE_SCHEMA" in os.environ:
                problematic_vars["SUPABASE_SCHEMA"] = os.environ.pop("SUPABASE_SCHEMA", None)
            
            # Create a completely fresh client
            self._client = create_client(self._supabase_url, self._supabase_key)
            logger.info("Supabase client re-created successfully without SUPABASE_SCHEMA")
            # Try again - should work now
            try:
                return self._client.table(table_name)
            except UnicodeEncodeError as e2:
                logger.error(
                    "UnicodeEncodeError still occurs after re-creating client: %s. "
                    "This suggests SUPABASE_SCHEMA is being set elsewhere or "
                    "the Supabase Python client has a bug with non-ASCII environment variables. "
                    "Please remove SUPABASE_SCHEMA from Railway environment variables.",
                    e2,
                    exc_info=True,
                )
                raise
        finally:
            # Never restore SUPABASE_SCHEMA or other problematic variables
            # Even if they're ASCII, they can cause problems with Supabase client
            # The Supabase client reads them during initialization and caches them
            if original_schema or problematic_vars:
                logger.debug(
                    "Not restoring SUPABASE_SCHEMA or other problematic variables "
                    "to avoid encoding issues with Supabase client"
                )

    def get_daily_containers_count(self, target_date: dt.date) -> int:
        """
        Count containers unloaded on a specific date.
        """
        logger.debug("Fetching container count for %s", target_date.isoformat())
        try:
            query = self._safe_table_access("containers")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            # Convert date to YYYYMMDD format for comparison
            date_str = target_date.strftime("%Y%m%d")
            response = (
                query.select("SHANA", count="exact")
                .gte("TARICH_PRIKA", date_str)
                .lte("TARICH_PRIKA", date_str)
                .execute()
            )

            count = getattr(response, "count", None)
            if count is not None:
                logger.info("Container count for %s is %s", target_date.isoformat(), count)
                return int(count)

            items: list[dict[str, Any]] = getattr(response, "data", [])
            total = len(items)
            logger.info(
                "Container count for %s derived from row count=%s",
                target_date.isoformat(),
                total,
            )
            return int(total)
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching daily containers count: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning 0.",
                e,
            )
            return 0


    def get_containers_count_between(
        self, start_date: dt.date, end_date: dt.date
    ) -> int:
        """
        Count containers unloaded between the provided dates (inclusive).
        
        Note: TARICH_PRIKA is stored as YYYYMMDD format (string) in the database.
        """
        logger.info(
            "Fetching container count between %s and %s (YYYYMMDD: %s to %s)",
            start_date.isoformat(),
            end_date.isoformat(),
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
        )
        try:
            # Use httpx directly to avoid UnicodeEncodeError from Supabase client
            # Convert dates to YYYYMMDD format for comparison
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            logger.debug("Query: TARICH_PRIKA >= %s AND TARICH_PRIKA <= %s", start_str, end_str)
            
            # Use PostgREST API directly via httpx to avoid schema encoding issues
            # PostgREST uses query parameters like: TARICH_PRIKA=gte.20240101&TARICH_PRIKA=lte.20240131
            # We need to use a list for multiple values with the same key
            from urllib.parse import urlencode
            query_params = urlencode([
                ("select", "SHANA"),
                ("TARICH_PRIKA", f"gte.{start_str}"),
                ("TARICH_PRIKA", f"lte.{end_str}"),
            ], doseq=True)
            url = f"/containers?{query_params}"
            logger.info("PostgREST URL: %s", url)
            
            # Use httpx with explicit headers to avoid encoding issues
            # httpx doesn't read environment variables like urllib.request/http.client does
            import os
            # Remove ALL SUPABASE_* variables except URL and KEY to be safe
            # This ensures no environment variable with non-ASCII characters
            # is read by any library
            all_removed = {}
            for key in list(os.environ.keys()):
                if key.startswith("SUPABASE_") and key not in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
                    removed = os.environ.pop(key, None)
                    if removed:
                        all_removed[key] = removed
                        logger.debug("Removed %s from environment before request", key)
            
            # Also check for any other environment variables that might contain non-ASCII
            # and remove them temporarily
            # NOTE: We only remove variables that contain actual non-ASCII characters (not ASCII that can't be encoded as latin-1)
            problematic_vars = {}
            for key, value in list(os.environ.items()):
                if isinstance(value, str):
                    try:
                        # Check if it's ASCII (not latin-1) - ASCII is a subset of latin-1
                        value.encode('ascii')
                    except UnicodeEncodeError:
                        # This variable contains actual non-ASCII characters (like Hebrew)
                        # Only remove if it's not a critical variable
                        if key not in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
                            problematic_vars[key] = os.environ.pop(key, None)
                            logger.warning("Removed problematic environment variable %s (contains non-ASCII): %s", key, value[:50] if len(value) > 50 else value)
            
            # Log all remaining SUPABASE_* variables for debugging
            remaining_supabase_vars = {k: v[:20] + "..." if len(v) > 20 else v for k, v in os.environ.items() if k.startswith("SUPABASE_")}
            if remaining_supabase_vars:
                logger.info("Remaining SUPABASE_* environment variables: %s", list(remaining_supabase_vars.keys()))
            
            try:
                request_headers = {
                    **self._http_headers,
                    "Range-Unit": "items",
                    "Prefer": "count=exact",
                }
                # Ensure all header values are ASCII-safe
                # NOTE: HTTP headers must be ASCII, but JWT tokens are ASCII (base64-encoded)
                # So we check for ASCII, not latin-1
                safe_headers = {}
                for k, v in request_headers.items():
                    if isinstance(v, str):
                        try:
                            # Check if it's ASCII (HTTP headers must be ASCII)
                            v.encode('ascii')
                            safe_headers[k] = v
                        except UnicodeEncodeError as e:
                            # Log the actual value to debug
                            logger.error(
                                "Header %s contains non-ASCII characters. "
                                "Value length: %d, First 50 chars: %s, Error: %s",
                                k, len(v), v[:50] if len(v) > 50 else v, e
                            )
                            # Skip non-ASCII headers
                            logger.warning("Skipping header %s with non-ASCII value", k)
                    else:
                        safe_headers[k] = v
                
                # Log what headers we're actually sending
                logger.info("Sending headers: %s", list(safe_headers.keys()))
                if 'apikey' not in safe_headers or 'Authorization' not in safe_headers:
                    logger.error("CRITICAL: Missing required headers! apikey: %s, Authorization: %s", 
                               'apikey' in safe_headers, 'Authorization' in safe_headers)
                
                full_url = f"{self._http_base_url}{url}"
                logger.info("Making GET request to: %s", full_url)
                
                # Use httpx with explicit headers to avoid encoding issues
                # httpx doesn't read environment variables during client creation
                with httpx.Client(timeout=self._http_timeout, verify=True) as client:
                    response = client.get(full_url, headers=safe_headers)
                    
                    status_code = response.status_code
                    response_headers = dict(response.headers)
                    response_data = response.content
                    
                    logger.info("Response status: %s", status_code)
                    logger.info("Response headers: %s", response_headers)
                    
                    if status_code >= 400:
                        error_msg = f"HTTP {status_code}: {response_data[:500].decode('utf-8', errors='replace')}"
                        logger.error("HTTP error when fetching containers count: %s. Returning 0.", error_msg)
                        return 0
                    
                    # Get count from Content-Range header if available
                    content_range = response_headers.get("Content-Range", "")
                    logger.info("Content-Range header: %s", content_range)
                    if content_range:
                        # Format: "0-9/100" where 100 is the total count
                        parts = content_range.split("/")
                        if len(parts) == 2 and parts[1].isdigit():
                            count = int(parts[1])
                            logger.info("Query response count from Content-Range header: %s", count)
                            return count
                        else:
                            logger.warning("Content-Range header format unexpected: %s", content_range)
                    
                    # Fallback to counting items in response
                    try:
                        data = response.json()
                        logger.info("Response data type: %s, length: %s", type(data), len(data) if isinstance(data, list) else "N/A")
                        if isinstance(data, list):
                            count = len(data)
                            logger.info("Query response count from data length: %s", count)
                            # If we got a limited result set, the count might be in Content-Range
                            # But if Content-Range wasn't available, we return the length
                            # NOTE: This might not be accurate if PostgREST limits results
                            if count > 0:
                                logger.warning(
                                    "Got %d items in response but no Content-Range header. "
                                    "This might be a partial result. Consider using count=exact header.",
                                    count
                                )
                            return count
                        else:
                            logger.warning("Response data is not a list: %s", type(data))
                            logger.warning("Response data content: %s", str(data)[:500])
                            return 0
                    except json.JSONDecodeError as e:
                        logger.error("Failed to parse JSON response: %s. Response: %s", e, response_data[:500])
                        return 0
            except UnicodeEncodeError as e:
                logger.error(
                    "UnicodeEncodeError when making request: %s. "
                    "This suggests SUPABASE_SCHEMA or another environment variable "
                    "contains non-ASCII characters. Returning 0.",
                    e,
                    exc_info=True,
                )
                return 0
            except Exception as e:
                logger.error(
                    "Error when making request: %s. Returning 0.",
                    e,
                    exc_info=True,
                )
                return 0
            finally:
                # Never restore SUPABASE_SCHEMA or other removed variables
                # Restoring them would cause encoding issues in future requests
                if all_removed or problematic_vars:
                    logger.debug(
                        "Removed %d SUPABASE_* variables and %d problematic variables before making request, will not be restored",
                        len(all_removed),
                        len(problematic_vars)
                    )
        except Exception as e:
            logger.error(
                "Error when fetching containers count between dates: %s. "
                "Returning 0.",
                e,
                exc_info=True,
            )
            return 0

    def get_vehicle_count_between(
        self, start_date: dt.date, end_date: dt.date
    ) -> int:
        """
        Sum vehicles_count from ramp_operations table across the date range.
        """
        logger.debug(
            "Fetching vehicle count between %s and %s",
            start_date.isoformat(),
            end_date.isoformat(),
        )
        try:
            query = self._safe_table_access("ramp_operations")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            response = query.select("vehicles_count, operation_date").gte(
                "operation_date", start_date.isoformat()
            ).lte("operation_date", end_date.isoformat()).execute()

            items: list[dict[str, Any]] = getattr(response, "data", [])
            total = sum(int(item.get("vehicles_count") or 0) for item in items)
            return total
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching vehicle count between dates: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning 0.",
                e,
            )
            return 0

    def get_containers_count_monthly(self, month: int, year: int) -> int:
        """
        Count containers unloaded in a specific month and year.
        """
        logger.info("Fetching monthly container count for month=%d, year=%d", month, year)
        try:
            # Calculate first and last day of the month
            if month == 12:
                start_date = dt.date(year, month, 1)
                end_date = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
            else:
                start_date = dt.date(year, month, 1)
                end_date = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            
            logger.info("Monthly date range: %s to %s (YYYYMMDD: %s to %s)", 
                       start_date.isoformat(), end_date.isoformat(),
                       start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
            count = self.get_containers_count_between(start_date, end_date)
            logger.info("Monthly container count result: %d", count)
            return count
        except Exception as e:
            logger.error(
                "Error fetching monthly containers count for %d/%d: %s",
                month,
                year,
                e,
            )
            return 0

    def get_metrics_summary(
        self,
        *,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        max_rows: int = 2000,
    ) -> Mapping[str, Any]:
        """
        Fetch operational metrics for the provided period to feed LLM analysis.
        """
        if end_date is None:
            end_date = dt.date.today()
        if start_date is None:
            start_date = end_date - dt.timedelta(days=30)

        logger.info("Fetching metrics summary: %s to %s", start_date.isoformat(), end_date.isoformat())
        containers = self._fetch_containers(start_date, end_date, max_rows)
        vehicles = self._fetch_vehicles(start_date, end_date, max_rows)
        logger.info("Metrics summary: %d containers, %d vehicles", len(containers), len(vehicles))

        container_daily: dict[str, int] = {}
        container_by_line: dict[str, int] = {}
        container_quantity = 0.0

        for row in containers:
            date_str = row.get("TARICH_PRIKA")
            if date_str:
                container_daily[date_str] = container_daily.get(date_str, 0) + 1
            line = row.get("SUG_ARIZA_MITZ") or row.get("SHEM_IZ")
            if line:
                container_by_line[line] = container_by_line.get(line, 0) + 1
            kmut = row.get("KMUT")
            if kmut is not None:
                container_quantity += float(kmut)

        vehicle_daily: dict[str, int] = {}
        for row in vehicles:
            date_str = row.get("operation_date")
            if date_str:
                vehicle_daily[date_str] = (
                    vehicle_daily.get(date_str, 0)
                    + int(row.get("vehicles_count") or 0)
                )

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "containers": {
                "total_records": len(containers),
                "total_quantity": container_quantity,
                "daily_counts": container_daily,
                "by_line_code": container_by_line,
            },
            "vehicles": {
                "total_records": len(vehicles),
                "daily_vehicle_counts": vehicle_daily,
            },
            "sample": {
                "containers": containers[:50],
                "vehicles": vehicles[:50],
            },
        }

    def _fetch_containers(
        self, start_date: dt.date, end_date: dt.date, limit: int
    ) -> list[dict[str, Any]]:
        try:
            query = self._safe_table_access("containers")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            # Convert dates to YYYYMMDD format for comparison
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            response = (
                query.select(
                    "KMUT,SUG_ARIZA_MITZ,SHEM_IZ,SHEM_AR,TARICH_PRIKA,TARGET,SHIPNAME,PEULA,MANIFEST"
                )
                .gte("TARICH_PRIKA", start_str)
                .lte("TARICH_PRIKA", end_str)
                .order("TARICH_PRIKA", desc=False)
                .limit(limit)
                .execute()
            )
            return list(getattr(response, "data", []))
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching containers: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning empty result.",
                e,
            )
            return []

    def _fetch_vehicles(
        self, start_date: dt.date, end_date: dt.date, limit: int
    ) -> list[dict[str, Any]]:
        try:
            query = self._safe_table_access("ramp_operations")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            response = (
                query.select("vehicles_count,containers_count,operation_date,ramp_id,shift")
                .gte("operation_date", start_date.isoformat())
                .lte("operation_date", end_date.isoformat())
                .order("operation_date", desc=False)
                .limit(limit)
                .execute()
            )
            return list(getattr(response, "data", []))
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when fetching vehicles: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Returning empty result.",
                e,
            )
            return []

    def log_query(
        self,
        *,
        user_phone: str,
        user_text: str,
        intent: str,
        parameters: dict[str, Any],
        response_text: str,
    ) -> None:
        """
        Persist interactions for auditing and analytics.
        """
        logger.debug("Logging query for user %s intent %s", user_phone, intent)
        try:
            # Convert parameters to JSON-serializable format
            safe_parameters = {}
            for key, value in parameters.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    safe_parameters[key] = value
                elif isinstance(value, dt.date):
                    safe_parameters[key] = value.isoformat()
                else:
                    safe_parameters[key] = str(value)
            
            # Use table without schema to avoid encoding issues
            query = self._safe_table_access("bot_queries_log")
            # Note: schema() is not supported by Supabase Python client
            # All queries use the default schema (usually 'public')
            
            query.insert(
                {
                    "user_phone": user_phone,
                    "user_text": user_text,
                    "intent": intent,
                    "parameters": safe_parameters,
                    "response_text": response_text,
                }
            ).execute()
        except UnicodeEncodeError as e:
            logger.error(
                "UnicodeEncodeError when logging query: %s. "
                "This may be caused by non-ASCII characters in Supabase configuration. "
                "Skipping log entry.",
                e,
            )
        except Exception as e:
            logger.error("Failed to log query: %s", e, exc_info=True)

    def bulk_insert(
        self,
        *,
        table: str,
        rows: Iterable[dict[str, Any]],
        batch_size: int = 500,
    ) -> None:
        """
        Insert CSV-derived rows into Supabase in batches to avoid timeouts.
        """
        for index, batch in enumerate(_chunked(rows, batch_size), start=1):
            logger.info("Uploading batch %s to table %s", index, table)
            self._safe_table_access(table).insert(batch).execute()


def _chunked(iterable: Iterable[dict[str, Any]], size: int) -> Iterable[List[dict[str, Any]]]:
    batch: List[dict[str, Any]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch

