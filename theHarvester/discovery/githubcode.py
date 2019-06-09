from theHarvester.discovery.constants import *
from theHarvester.lib.core import *
from theHarvester.parsers import myparser
import requests
from requests import Response
import time
from typing import List, Dict, Any, Optional, NamedTuple
import urllib.parse as urlparse


class RetryResult(NamedTuple):
    time: float


class SuccessResult(NamedTuple):
    fragments: List[str]
    next_page: Optional[int]
    last_page: Optional[int]


class ErrorResult(NamedTuple):
    status_code: int
    message: str


class SearchGithubCode:

    def __init__(self, word, limit):
        self.word = word
        self.total_results = ""
        self.server = 'api.github.com'
        self.hostname = 'api.github.com'
        self.limit = limit
        self.counter = 0
        self.page = 1
        self.key = Core.github_key()
        # If you don't have a personal access token, github narrows your search capabilities significantly
        # and rate limits you more severely
        # https://developer.github.com/v3/search/#rate-limit
        if self.key is None:
            raise MissingKey(True)

    @staticmethod
    def fragments_from_response(response: Response) -> List[str]:
        items: List[Dict[str, Any]] = response.json().get('items')
        fragments = []
        if items is not None:
            for i in items:
                match = i.get("text_matches")
                for m in match:
                    fragments.append(m.get("fragment"))
        return fragments

    @staticmethod
    def next_page_from_response(response: Response) -> Optional[int]:
        next_link = response.links.get("next")
        if next_link:
            parsed = urlparse.urlparse(next_link.get("url"))
            params = urlparse.parse_qs(parsed.query)
            page = params.get('page') or [None]
            next_page = page[0] and int(page[0])
            return next_page
        else:
            return None

    @staticmethod
    def last_page_from_response(response: Response) -> Optional[int]:
        next_link = response.links.get("last")
        if next_link:
            parsed = urlparse.urlparse(next_link.get("url"))
            params = urlparse.parse_qs(parsed.query)
            page = params.get('page') or [None]
            last_page = page[0] and int(page[0])
            return last_page
        else:
            return None

    def handle_response(self, response: Response) -> Optional[Any]:
        if response.ok:
            fragments = self.fragments_from_response(response)
            next_page = self.next_page_from_response(response)
            last_page = self.last_page_from_response(response)
            return SuccessResult(fragments, next_page, last_page)
        elif response.status_code == 429 or response.status_code == 403:
            return RetryResult(60)
        else:
            return ErrorResult(response.status_code, response.reason)

    def do_search(self, page: Optional[int]) -> Optional[Any]:
        if page is None:
            url = 'https://api.github.com/search/code?q={}'.format(self.word)
        else:
            url = 'https://api.github.com/search/code?q={}&page={}'.format(self.word, page)
        headers = {
            'Host': self.hostname,
            'User-agent': Core.get_user_agent(),
            'Accept': "application/vnd.github.v3.text-match+json",
            'Authorization': 'token {}'.format(self.key)
        }
        try:
            h = requests.get(url=url, headers=headers, verify=False)
            result = self.handle_response(h)
            return result
        except Exception as e:
            print(f'Error Occurred: {e}')

    @staticmethod
    def next_page_or_end(page: Optional[int], result: SuccessResult) -> Optional[int]:
        if page is not None and result.last_page is not None and page < result.last_page:
            return page + 1
        else:
            return None

    def process(self):
        while self.counter <= self.limit and self.page is not None:
            result = self.do_search(self.page)
            if type(result) == SuccessResult:
                print(f'\tSearching {self.counter} results.')
                for f in result.fragments:
                    self.total_results += f
                    self.counter = self.counter + 1

                self.page = self.next_page_or_end(self.page, result)
                time.sleep(getDelay())
            elif type(result) == RetryResult:
                sleepy_time = getDelay() + result.time
                print(f'\tRetrying page in {sleepy_time} seconds...')
                time.sleep(sleepy_time)
            else:
                raise Exception("Exception occurred: status_code: {} reason: {}".format(result.status_code,
                                                                                        result.message))

    def get_emails(self):
        rawres = myparser.Parser(self.total_results, self.word)
        return rawres.emails()

    def get_hostnames(self):
        rawres = myparser.Parser(self.total_results, self.word)
        return rawres.hostnames()
