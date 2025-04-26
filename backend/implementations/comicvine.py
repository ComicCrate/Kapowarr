# -*- coding: utf-8 -*-

"""
Search for volumes/issues and fetch metadata for them on ComicVine
"""

from asyncio import gather, run, sleep
from json import JSONDecodeError
from re import IGNORECASE, compile
from typing import Any, Dict, List, Sequence, Union

from aiohttp import ContentTypeError
from aiohttp.client_exceptions import ClientError
from bs4 import BeautifulSoup, Tag

from backend.base.custom_exceptions import (CVRateLimitReached,
                                            InvalidComicVineApiKey,
                                            VolumeNotMatched)
from backend.base.definitions import (Constants, FilenameData, IssueMetadata,
                                      SpecialVersion, T, VolumeMetadata)
from backend.base.file_extraction import (process_issue_number,
                                          process_volume_number, volume_regex)
from backend.base.helpers import (AsyncSession, DictKeyedDict, Session,
                                  batched, create_range, force_suffix,
                                  normalize_string, normalize_year,
                                  to_full_string_cv_id, to_string_cv_id)
from backend.base.logging import LOGGER
from backend.implementations.matching import _match_title, _match_year
from backend.internals.db import get_db
from backend.internals.settings import Settings # Ensure this import is correct

translation_regex = compile(
    r'^<p>\s*\w+ publication(\.?</p>$|,\s| \(in the \w+ language\)|, translates )|' +
    r'^<p>\s*published by the \w+ wing of|' +
    r'^<p>\s*\w+ translations? of|' +
    r'from \w+</p>$|' +
    r'^<p>\s*published in \w+|' +
    r'^<p>\s*\w+ language|' +
    r'^<p>\s*\w+ edition of|' +
    r'^<p>\s*\w+ reprint of|' +
    r'^<p>\s*\w+ trade collection of',
    IGNORECASE)
headers = {'h2', 'h3', 'h4', 'h5', 'h6'}
lists = {'ul', 'ol'}


def _clean_description(description: str, short: bool = False) -> str:
    """Reduce size of description (written in html) to only essential
    information.

    Args:
        description (str): The description (written in html) to clean.
        short (bool, optional): Only remove images and fix links.
            Defaults to False.

    Returns:
        str: The cleaned description (written in html).
    """
    if not description:
        return description

    soup = BeautifulSoup(description, 'html.parser')

    # Remove images
    for el in soup.find_all(["figure", "img"]):
        el.decompose()

    if not short:
        # Remove everything after the first title with list
        removed_elements = []
        for el in soup:
            if not isinstance(el, Tag):
                continue
            if el.name is None:
                continue

            if (
                removed_elements
                or el.name in headers
            ):
                removed_elements.append(el)
                continue

            if el.name in lists:
                removed_elements.append(el)
                prev_sib = el.previous_sibling
                if (
                    prev_sib is not None
                    and prev_sib.text.endswith(':')
                ):
                    removed_elements.append(prev_sib)
                continue

            if el.name == 'p':
                children = list(getattr(el, 'children', []))
                if (
                    1 <= len(children) <= 2
                    and children[0].name in ('b', 'i', 'strong')
                ):
                    removed_elements.append(el)

        for el in removed_elements:
            if isinstance(el, Tag):
                el.decompose()

    # Fix links
    for link in soup.find_all('a'):
        link: Tag
        link.attrs = {
            k: v for k, v in link.attrs.items() if not k.startswith('data-')
        }
        link['target'] = '_blank'
        link['href'] = link.attrs.get('href', '').lstrip('.').lstrip('/')
        if not link.attrs.get('href', 'http').startswith('http'):
            link['href'] = (
                Constants.CV_SITE_URL
                + '/'
                + link.attrs.get('href', '')
            )

    result = str(soup)
    return result


class ComicVine:

    volume_field_list = ','.join((
        'aliases',
        'count_of_issues',
        'deck',
        'description',
        'id',
        'image',
        'issues', #
        'name',
        'publisher',
        'site_detail_url',
        'start_year'
    ))
    issue_field_list = ','.join((
        'id',
        'issue_number',
        'name',
        'cover_date',
        'description',
        'volume'
    ))
    search_field_list = ','.join((
        'aliases',
        'count_of_issues',
        'deck',
        'description',
        'id',
        'image',
        'name',
        'publisher',
        'site_detail_url',
        'start_year'
    ))

    one_issue_match = (
        SpecialVersion.TPB,
        SpecialVersion.ONE_SHOT,
        SpecialVersion.HARD_COVER
    )
    """
    If a volume is one of these types, it can only match to CV search results
    with one issue.
    """

    def __init__(self, comicvine_api_keys: Union[List[str], None] = None) -> None:
        """Start interacting with ComicVine.

        Args:
            comicvine_api_keys (Union[List[str], None], optional): Override the API keys
            that are used.
                Defaults to None.

        Raises:
            InvalidComicVineApiKey: No ComicVine API key is set in the settings.
        """
        self.api_url = Constants.CV_API_URL
        # Use provided keys or get from settings. Ensure it's a list.
        self.api_keys = comicvine_api_keys if comicvine_api_keys is not None else Settings().sv.comicvine_api_keys
        if not self.api_keys or not isinstance(self.api_keys, list) or not all(isinstance(key, str) for key in self.api_keys):
            raise InvalidComicVineApiKey("No valid ComicVine API key(s) set.")

        self._current_key_index = 0
        self.ssn = Session()
        # Initial params will use the first key
        self._params = {'format': 'json', 'api_key': self.current_key}
        self.ssn.params.update(self._params) # type: ignore
        return

    @property
    def current_key(self) -> str:
        # Return the API key at the current index
        if not self.api_keys:
             raise InvalidComicVineApiKey("No ComicVine API key(s) available.")
        return self.api_keys[self._current_key_index]

    def _next_key(self) -> None:
        # Move to the next API key in the list, cycling back to the start if necessary
        if not self.api_keys:
            # This should ideally not happen if checked in __init__, but as a safeguard
            LOGGER.error("Attempted to cycle API keys but no keys are available.")
            return
        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        # Update the API key in the instance's parameters
        self._params['api_key'] = self.current_key
        LOGGER.debug(f"Switching to ComicVine API key index: {self._current_key_index}")

    async def __call_request(
        self,
        session: AsyncSession,
        url: str
    ) -> Union[bytes, None]:
        """Fetch a URL and get it's content async (with error handling).

        Args:
            session (AsyncSession): The aiohttp session to make the request with.
            url (str): The URL to make the request to.

        Returns:
            Union[bytes, None]: The content in bytes.
                `None` in case of error.
        """
        try:
            return await session.get_content(url)
        except ClientError:
            return None

    async def __call_api(
        self,
        session: AsyncSession,
        url_path: str,
        params: Dict[str, Any] = {},
        default: Union[T, None] = None
    ) -> Union[Dict[str, Any], T]:
        """Make an CV API call asynchronously (with error handling and retry).

        Args:
            session (AsyncSession): The aiohttp session to make the request with.

            url_path (str): The path of the url to make the call to (e.g.
            '/volumes').

            params (Dict[str, Any], optional): The URL params that should go
            with the request. Standard params (api key, format, etc.) not
            needed.
                Defaults to {}.

            default (Union[T, None], optional): Return value in case of error,
            instead of raising error.
                Defaults to None.

        Raises:
            CVRateLimitReached: The CV rate limit for this endpoint has been
            reached, and no `default` was supplied.
            InvalidComicVineApiKey: The CV api key is not valid.
            VolumeNotMatched: The volume with the given ID is not found.
            ClientError: A persistent error occurred after retries.

        Returns:
            Union[Dict[str, Any], T]: The raw API response or the value of
            `default` on error.
        """
        url_path = force_suffix('/' + url_path.lstrip('/'), '/')
        # Merge default parameters with request-specific parameters
        # Ensure the current key is always used for the request attempt
        full_params = {**params}

        retries = 0
        # Define a maximum number of retries, e.g., a few times the number of keys
        max_retries = len(self.api_keys) * 3 # Increased retry attempts
        base_delay = 5 # seconds

        initial_key_index = self._current_key_index # Remember the starting key index for this call

        while retries < max_retries:
            try:
                full_params['api_key'] = self.current_key # Use the current key from the cycle
                response = await session.get(
                    self.api_url + url_path,
                    params=full_params
                )
                result: Dict[str, Any] = await response.json()

                status_code = result.get('status_code')
                if status_code == 107:
                    LOGGER.warning(f"ComicVine API rate limit reached with key index {self._current_key_index}. Retrying...")
                    retries += 1
                    self._next_key() # Switch to the next API key
                    # Implement increasing delay with retries, especially after cycling through all keys
                    # Delay increases based on the number of full cycles attempted
                    delay = base_delay * (retries // len(self.api_keys) + 1)
                    await sleep(delay)
                    continue # Continue to the next retry attempt

                elif status_code == 101:
                    # Volume not matched error - not a temporary issue, so raise immediately
                    raise VolumeNotMatched
                elif status_code == 100:
                    # Invalid API key error - indicates a problem with the specific key
                    # For multiple keys, we might just want to switch and try the next one
                    LOGGER.warning(f"Invalid ComicVine API key used (index {self._current_key_index}). Switching key.")
                    retries += 1
                    self._next_key()
                    # Add a small delay before trying the next key
                    await sleep(base_delay)
                    continue # Continue to the next retry attempt
                elif status_code is not None and status_code != 1: # Assuming status_code 1 is success
                     # Other ComicVine API errors - treat as potentially transient or specific to the key
                     LOGGER.error(f"ComicVine API returned status code {status_code}: {result.get('error')}")
                     retries += 1
                     self._next_key() # Try next key
                     await sleep(base_delay * (retries // len(self.api_keys) + 1))
                     continue # Continue to next retry attempt

                # Success (status_code == 1)
                return result

            except (ClientError, ContentTypeError, JSONDecodeError) as e:
                # Handle network errors, JSON errors, etc.
                LOGGER.warning(f"Error calling ComicVine API with key index {self._current_key_index}: {e}. Retrying...")
                retries += 1
                self._next_key() # Switch key on general errors as well, just in case
                await sleep(base_delay * (retries // len(self.api_keys) + 1)) # Implement increasing delay

        # If the loop finishes without returning, all retry attempts were exhausted
        # Determine the most likely cause for the failure
        final_status_code = result.get('status_code') if 'result' in locals() and isinstance(result, dict) else None

        if final_status_code == 107 or (initial_key_index != self._current_key_index and retries > len(self.api_keys)):
             # If we encountered rate limits or cycled through all keys multiple times
             raise CVRateLimitReached("All ComicVine API keys attempted or rate limit persists after multiple retries.")
        elif final_status_code == 100:
             # If the last error was an invalid key, and we cycled, it might indicate all keys are invalid or a persistent issue
              raise InvalidComicVineApiKey("All provided ComicVine API keys failed validation or a persistent authentication error occurred.")
        else:
            # For other errors or if default is provided
            if default is not None:
                return default
            # Re-raise the last caught exception or raise a general client error if no exception was caught
            # Note: It's better to re-raise the actual exception if available, but requires storing it.
            # For simplicity here, raising a generic ClientError if no specific CV error code was the final issue.
            raise ClientError(f"ComicVine API call failed after {retries} retries with last status code: {final_status_code}")


    def __format_volume_output(
        self,
        volume_data: Dict[str, Any]
    ) -> VolumeMetadata:
        """Format the ComicVine API output containing the info
        about the volume.

        Args:
            volume_data (Dict[str, Any]): The ComicVine API output.

        Returns:
            VolumeMetadata: The formatted version.
        """
        result: VolumeMetadata = {
            'comicvine_id': int(volume_data['id']),
            'title': normalize_string(volume_data['name']),
            'year': normalize_year(volume_data.get('start_year', '')),
            'volume_number': 1,
            'cover_link': volume_data['image']['small_url'],
            'cover': None,
            'description': _clean_description(volume_data['description']),
            'site_url': volume_data['site_detail_url'],

            'aliases': [
                a
                for a in (volume_data.get('aliases') or '').split('\r\n')
                if a
            ],

            'publisher': (
                volume_data.get('publisher') or {}
            ).get('name'),

            'issue_count': int(volume_data['count_of_issues']),

            'translated': False,
            'already_added': None, # Only used when searching
            'issues': None # Only used for certain fetches
        }

        if translation_regex.match(
            result['description'] or ''
        ) is not None:
            result['translated'] = True

        volume_result = volume_regex.search(volume_data['deck'] or '')
        if volume_result:
            result['volume_number'] = create_range(process_volume_number(
                volume_result.group(1)
            ))[0] or 1

        return result

    def __format_issue_output(
        self,
        issue_data: Dict[str, Any]
    ) -> IssueMetadata:
        """Format the ComicVine API output containing the info
        about the issue.

        Args:
            issue_data (Dict[str, Any]): The ComicVine API output.

        Returns:
            VolumeMetadata: The formatted version.
        """
        cin = create_range(process_issue_number(
            issue_data['issue_number']
        ))[0]

        result: IssueMetadata = {
            'comicvine_id': int(issue_data['id']),
            'volume_id': int(issue_data['volume']['id']),
            'issue_number': issue_data['issue_number'],
            'calculated_issue_number': cin if cin is not None else 0.0,
            'title': issue_data['name'] or None,
            'date': issue_data['cover_date'] or None,
            'description': _clean_description(
                issue_data['description'],
                short=True
            )
        }
        return result

    def __format_search_output(
        self,
        search_results: List[Dict[str, Any]]
    ) -> List[VolumeMetadata]:
        """Format the search results from the ComicVine API.

        Args:
            search_results (List[Dict[str, Any]]): The unformatted search
            results.

        Returns:
            List[VolumeMetadata]: The formatted search results.
        """
        cursor = get_db()

        formatted_results = [
            self.__format_volume_output(r)
            for r in search_results
        ]

        # Mark entries that are already added
        # Optimize this query if formatted_results is large
        cv_ids_to_check = [str(r['comicvine_id']) for r in formatted_results]
        if cv_ids_to_check:
             volume_ids: Dict[int, int] = dict(cursor.execute(f"""
                 SELECT comicvine_id, id
                 FROM volumes
                 WHERE comicvine_id IN ({','.join(cv_ids_to_check)});
             """))
        else:
            volume_ids = {}


        for r in formatted_results:
            r['already_added'] = volume_ids.get(r["comicvine_id"])

        LOGGER.debug(
            f'Searching for volumes with query result: {formatted_results}')
        return formatted_results

    def test_token(self) -> bool:
        """Test if the token works by attempting a simple API call.
           This will now also cycle through keys and retry.

        Returns:
            bool: Whether at least one key works.
        """
        async def _test_token():
            try:
                async with AsyncSession() as session:
                    # Use a call that requires authentication but is simple
                    await self.__call_api(
                        session,
                        '/publisher/4010-31',
                        {'field_list': 'id'}
                        # Do not provide a default, so errors are raised
                    )
                # If __call_api returns without raising an exception, at least one key worked
                return True
            except (CVRateLimitReached, InvalidComicVineApiKey, ClientError):
                # Catch specific exceptions from __call_api indicating failure
                return False
            except Exception as e:
                 # Catch any unexpected errors during the test
                 LOGGER.error(f"Unexpected error during ComicVine API key test: {e}")
                 return False


        return run(_test_token())

    async def fetch_volume(self, cv_id: Union[str, int]) -> VolumeMetadata:
        """Get the metadata of a volume from ComicVine, including it's issues.

        Args:
            cv_id (Union[str, int]): The CV ID of the volume.

        Raises:
            VolumeNotMatched: No volume found with given ID in CV DB.
            CVRateLimitReached: The ComicVine rate limit is reached after retries.
            InvalidComicVineApiKey: All provided API keys are invalid.
            ClientError: A persistent error occurred after retries.

        Returns:
            VolumeMetadata: The metadata of the volume, including issues.
        """
        try:
            cv_id_str = to_full_string_cv_id((cv_id,))[0]
        except ValueError:
            raise VolumeNotMatched("Invalid ComicVine ID format provided.")

        LOGGER.debug(f'Fetching volume data for {cv_id_str}')

        async with AsyncSession() as session:
            # This call_api will handle retries and key cycling
            result = await self.__call_api(
                session,
                f'/volume/{cv_id_str}',
                {'field_list': self.volume_field_list}
            )

            # Assuming 'results' key is present on success based on existing code
            volume_info = self.__format_volume_output(result.get('results', {}))
            if not volume_info or not volume_info.get('comicvine_id'):
                 # Handle cases where API call succeeded but returned no volume data
                 raise VolumeNotMatched(f"No volume data returned for ID {cv_id_str}.")


            LOGGER.debug(f'Fetching issue data for volume {cv_id_str}')
            # This fetch_issues call will also use the updated __call_api with retries
            volume_info['issues'] = await self.fetch_issues((cv_id_str,))

            LOGGER.debug(f'Fetching volume data result: {volume_info}')

            # Fetch cover image (also uses an async session and handles potential errors)
            volume_info['cover'] = await self.__call_request(
                session,
                volume_info['cover_link']
            )
            return volume_info

    async def fetch_volumes(
        self,
        cv_ids: Sequence[Union[str, int]]
    ) -> List[VolumeMetadata]:
        """Get the metadata of the volumes from ComicVine, without their issues.

        Args:
            cv_ids (Sequence[Union[str, int]]): The CV ID's of the volumes.

        Returns:
            List[VolumeMetadata]: The metadata of the volumes, without issues.
        """
        try:
            formatted_cv_ids = to_string_cv_id(cv_ids)
        except ValueError:
            # Handle invalid ID format for multiple IDs
             raise VolumeNotMatched("Invalid ComicVine ID format provided in sequence.")


        if not formatted_cv_ids:
            return [] # Return empty list if no valid IDs provided

        LOGGER.debug(f'Fetching volume data for {formatted_cv_ids}')

        volume_infos = []
        async with AsyncSession() as session:
            # Process IDs in batches suitable for the API filter
            # The existing batching logic seems reasonable, but each __call_api
            # within the loop will now handle its own retries and key cycling.
            # Consider adding an outer retry logic if entire batches consistently fail.

            # Example: Adjust batching to ensure filter fits within URL limits if necessary
            api_filter_batch_size = 100 # As used in the original code
            request_batch_size = 1000 # As used in the original code, seems high for robustness

            for request_batch_ids in batched(formatted_cv_ids, request_batch_size):

                # Introduce a delay between larger batches to be more polite to the API
                # This is separate from the retry delay within __call_api
                if formatted_cv_ids and request_batch_ids[0] != formatted_cv_ids[0]:
                    LOGGER.debug(f"Waiting {Constants.CV_BRAKE_TIME}s between volume request batches.")
                    await sleep(Constants.CV_BRAKE_TIME)

                tasks = []
                for api_filter_batch_ids in batched(request_batch_ids, api_filter_batch_size):
                    # __call_api handles retries and key cycling for each individual API request
                    tasks.append(
                        self.__call_api(
                            session,
                            '/volumes',
                            {
                                'field_list': self.volume_field_list,
                                'filter': f'id:{"|".join(api_filter_batch_ids)}'
                            },
                            # Provide a default empty list for results in case of retry failure for a batch
                            # This allows processing of other batches even if one fails
                            {'results': []}
                        )
                    )

                responses = await gather(*tasks)

                # Process responses and prep cover requests concurrently
                cover_map: Dict[int, Any] = {}
                current_infos: List[VolumeMetadata] = []
                cover_tasks = {} # Dictionary to hold cover fetch tasks keyed by ComicVine ID

                for batch in responses:
                    # Check if the batch response itself indicates an error despite retries
                    # This might happen if the default {'results': []} was returned due to failure
                    if not isinstance(batch, dict) or 'results' not in batch:
                         LOGGER.warning("Skipping a volume batch due to previous API call failure.")
                         continue # Skip processing this batch if it doesn't have 'results'

                    for result in batch.get('results', []): # Safely access results
                        volume_info = self.__format_volume_output(result)
                        current_infos.append(volume_info)

                        # Prepare cover fetch task for each volume
                        if volume_info.get('cover_link'):
                             cover_tasks[volume_info['comicvine_id']] = self.__call_request(
                                 session, volume_info['cover_link']
                             )

                # Execute cover fetch tasks concurrently for this request batch
                if cover_tasks:
                    cover_responses = dict(zip(
                        cover_tasks.keys(),
                        await gather(*cover_tasks.values())
                    ))
                else:
                    cover_responses = {}

                # Add fetched covers to the corresponding volume info objects
                for vi in current_infos:
                    vi['cover'] = cover_responses.get(vi['comicvine_id'])

                # Add formatted volume info of this request batch to total list
                volume_infos.extend(current_infos)

            return volume_infos # Return the accumulated list of volume infos

    async def fetch_issues(
        self,
        cv_ids: Sequence[Union[str, int]]
    ) -> List[IssueMetadata]:
        """Get the metadata of the issues of volumes from ComicVine.

        Args:
            cv_ids (Sequence[Union[str, int]]): The CV ID's of the volumes.

        Returns:
            List[IssueMetadata]: The metadata of all the issues inside the
            volumes (assuming the rate limit wasn't reached).
        """
        try:
            formatted_cv_ids = to_string_cv_id(cv_ids)
        except ValueError:
            # Handle invalid ID format for multiple IDs
             raise VolumeNotMatched("Invalid ComicVine ID format provided in sequence.")


        if not formatted_cv_ids:
            return [] # Return empty list if no valid IDs provided

        LOGGER.debug(f'Fetching issue data for volumes {formatted_cv_ids}')

        issue_infos = []
        async with AsyncSession() as session:
            # Process volume IDs in batches for the filter parameter
            api_filter_batch_size = 50 # As used in the original code
            request_batch_size = 500 # Example: Process batches of filter batches

            for volume_filter_batch_ids in batched(formatted_cv_ids, api_filter_batch_size):

                # Introduce a delay between batches of volume filters
                if formatted_cv_ids and volume_filter_batch_ids[0] != formatted_cv_ids[0]:
                    LOGGER.debug(f"Waiting {Constants.CV_BRAKE_TIME}s between issue request batches.")
                    await sleep(Constants.CV_BRAKE_TIME)


                # Initial call for the first page of issues for this batch of volumes
                try:
                    initial_results = await self.__call_api(
                        session,
                        '/issues',
                        {
                            'field_list': self.issue_field_list,
                            'filter': f'volume:{"|".join(volume_filter_batch_ids)}',
                            'limit': 100 # Fetch first 100 issues
                        },
                        # Provide a default empty list for results in case of failure
                        {'results': []}
                    )
                except CVRateLimitReached:
                    # If even the first call fails after retries, stop processing this batch
                    LOGGER.warning(f"Failed to fetch initial issue batch for volumes {volume_filter_batch_ids} after retries.")
                    continue # Move to the next batch of volume filters


                issue_infos.extend([
                    self.__format_issue_output(r)
                    for r in initial_results.get('results', []) # Safely access results
                ])

                total_results = initial_results.get('number_of_total_results', 0)
                if total_results > 100:
                    # If there are more than 100 issues, fetch subsequent pages
                    # Batch the offsets for subsequent requests
                    offset_batch_size = 10 # As used in original code

                    for offset_batch in batched(
                        range(100, total_results, 100), # Start from 100, step by 100
                        offset_batch_size # Number of offset requests to make concurrently
                    ):

                        # Introduce a delay between batches of offset requests for this volume filter batch
                        if offset_batch[0] != 100:
                            LOGGER.debug(f"Waiting {Constants.CV_BRAKE_TIME}s between issue offset batches.")
                            await sleep(Constants.CV_BRAKE_TIME)


                        tasks = []
                        for offset in offset_batch:
                            # __call_api handles retries and key cycling for each request
                            tasks.append(
                                self.__call_api(
                                    session,
                                    '/issues',
                                    {
                                        'field_list': self.issue_field_list,
                                        'filter': f'volume:{"|".join(volume_filter_batch_ids)}',
                                        'offset': offset,
                                        'limit': 100 # Fetch 100 issues per request
                                    },
                                    # Provide a default empty list for results in case of failure
                                    {'results': []}
                                )
                            )

                        responses = await gather(*tasks)

                        for batch in responses:
                             if not isinstance(batch, dict) or 'results' not in batch:
                                  LOGGER.warning("Skipping an issue offset batch due to previous API call failure.")
                                  continue # Skip processing this batch if it doesn't have 'results'

                             issue_infos.extend([
                                 self.__format_issue_output(r)
                                 for r in batch.get('results', [])
                             ])

            return issue_infos # Return the accumulated list of issue infos

    async def search_volumes(
        self,
        query: str
    ) -> List[VolumeMetadata]:
        """Search for volumes in CV.

        Args:
            query (str): The query to use when searching.

        Returns:
            List[VolumeMetadata]: A list with search results.
        """
        LOGGER.debug(f'Searching for volumes with the query {query}')

        try:
            # Check if the query looks like a ComicVine ID and format it
            if query.startswith(('4050-', 'cv:')):
                try:
                    query_id_str = to_full_string_cv_id((query,))[0]
                    if not query_id_str:
                         return [] # Return empty list if conversion results in empty string

                    async with AsyncSession() as session:
                        # Directly fetch the volume by ID using __call_api (with retries)
                        result = await self.__call_api(
                            session,
                            f'/volume/{query_id_str}',
                            {'field_list': self.search_field_list}
                            # Do not provide a default, so VolumeNotMatched or other errors are raised
                        )
                        # Wrap the single result in a list to match expected format
                        results = [result.get('results')] if result and result.get('results') else []

                except ValueError:
                    # Invalid ID format that doesn't match to_full_string_cv_id
                    LOGGER.warning(f"Invalid ComicVine ID format for direct volume fetch: {query}")
                    return [] # Return empty list for invalid ID format


            else:
                # Standard search using the search endpoint
                async with AsyncSession() as session:
                    # Use __call_api for the search request (with retries)
                    result = await self.__call_api(
                        session,
                        '/search',
                        {
                            'query': query,
                            'resources': 'volume',
                            'limit': 50, # Limit search results
                            'field_list': self.search_field_list
                        }
                        # Provide a default empty list for results in case of failure
                        , {'results': []}
                    )
                    results = result.get('results', []) # Safely access results

        except (CVRateLimitReached, InvalidComicVineApiKey, ClientError) as e:
             # Catch exceptions from __call_api and return empty list for search
             LOGGER.warning(f"Search volumes failed after retries for query '{query}': {e}")
             return []


        if not results:
            return [] # Return empty list if no results found


        return self.__format_search_output(results)


    async def filenames_to_cvs(self,
        file_datas: Sequence[FilenameData],
        only_english: bool
    ) -> DictKeyedDict:
        """Match filenames to CV volumes.

        Args:
            file_datas (Sequence[FilenameData]): The filename data's to find CV
            volumes for.
            only_english (bool): Only match to english volumes.

        Returns:
            DictKeyedDict: A map of the filename to it's CV match.
        """
        results = DictKeyedDict()

        # If multiple filenames have the same series title, avoid searching for
        # it multiple times. Instead search for all unique titles and then later
        # match the filename back to the title's search results. This makes it
        # one search PER SERIES TITLE instead of one search PER FILENAME.
        titles_to_files: Dict[str, List[FilenameData]] = {}
        for file_data in file_datas:
            (titles_to_files
                .setdefault(file_data['series'].lower(), [])
                .append(file_data)
            )

        # Titles to search results concurrently. search_volumes now handles retries.
        responses = await gather(*(
            self.search_volumes(title)
            for title in titles_to_files
        ))

        # Filter search results for each title based on initial matching criteria
        titles_to_results: Dict[str, List[VolumeMetadata]] = {}
        for title, response in zip(titles_to_files.keys(), responses): # Use keys() to iterate through titles
            titles_to_results[title] = [
                r for r in response # response is already a List[VolumeMetadata] from search_volumes
                if _match_title(title, r['title'])
                and (
                    only_english and not r.get('translated', False) # Safely access translated
                    or
                    not only_english
                )
            ]

        # Match filenames to the filtered search results
        for title, files in titles_to_files.items():
            for file in files:
                # Further filter results based on Special Version and issue count
                filtered_results = [
                    r for r in titles_to_results.get(title, []) # Safely access results for the title
                    if file.get('special_version') not in self.one_issue_match # Safely access special_version
                    or r.get('issue_count', 0) == 1 # Safely access issue_count
                ]

                if not filtered_results:
                    # No matching result found for this file
                    results[file] = {
                        'id': None,
                        'title': None,
                        'issue_count': None,
                        'link': None
                    }
                    continue

                # Sort remaining results based on matching criteria preference
                filtered_results.sort(key=lambda r:
                    int(r.get('year') == file.get('year')) # Safely access year
                    + int(_match_year(r.get('year'), file.get('year'))) # Safely access year for _match_year
                    + int(
                        file.get('volume_number') is not None and r.get('volume_number') == file.get('volume_number') # Safely access volume_number
                    ) * 2,
                    reverse=True
                )

                # Select the best matched result
                matched_result = filtered_results[0]
                results[file] = {
                    'id': matched_result.get('comicvine_id'), # Safely access comicvine_id
                    'title': f"{matched_result.get('title', 'Unknown')} ({matched_result.get('year', 'Unknown')})", # Provide defaults
                    'issue_count': matched_result.get('issue_count'), # Safely access issue_count
                    'link': matched_result.get('site_detail_url')} # Safely access site_detail_url


        return results