"""Collects pull requests from github"""

from threading import Thread
from typing import List, Dict, Set, Tuple, Optional, Callable
import time
import re

from datetime import timedelta, datetime


from pydantic import Field


from gitaudit.github.instance import Github
from gitaudit.github.graphql_objects import PullRequest
import validators

from intm.base import RootModel


PR_QUERY_DATA = """title"""


class PullRequestContainer(RootModel):
    """Container for pull requests"""

    pull_request: PullRequest
    dependencies: List[str] = Field(default_factory=list)
    last_data_pull_at: datetime


class CollectQuery:
    """Base class for collect queries"""

    @property
    def query(self):
        """Query to collect pull requests"""
        raise NotImplementedError


class ConstantCollectQuery(CollectQuery):
    """Query that is constant"""

    def __init__(self, query):
        self._query = query

    @property
    def query(self):
        return self._query


class RecentlyUpdatedPullRequests(CollectQuery):
    """Query that collects pull requests that were updated recently"""

    def __init__(self, base_query, time_delta: timedelta):
        self.base_query = base_query
        self.time_delta = time_delta

    @property
    def query(self):
        return f"{self.base_query} updated:>={(datetime.utcnow() - self.time_delta).isoformat()}"


def const_queries_from_list(query_texts: List[str]) -> List[ConstantCollectQuery]:
    """
    Creates a list of ConstantCollectQuery from a list of query texts

    Args:
        query_texts: List of query texts

    Returns:
        List[ConstantCollectQuery]: List of ConstantCollectQuery
    """

    return [ConstantCollectQuery(q) for q in query_texts]


def _internal_sleep(seconds: int) -> None:
    time.sleep(seconds)


def pull_request_url_to_uri(url: str) -> str:
    """
    Converts a pull request url to a uri

    Args:
        url: Pull request url

    Returns:
        str: Pull request uri
    """

    split_url = url.split("/")

    assert len(split_url) >= 4, f"Pull request url {url} does not have enough parts"
    assert re.fullmatch(
        r"\d+", split_url[-1]
    ), f"Pull request url {url} does not end with a number"
    assert (
        split_url[-2] == "pull"
    ), f"Pull request url {url} does not end with /pull/<number>"

    return f"{split_url[-4]}/{split_url[-3]}#{split_url[-1]}"


def zuul_dependencies_from_pull_request(
    pull_request: PullRequest,
) -> Tuple[List[str], List[str]]:
    """
    Gets zuul dependencies from a pull request

    Args:
        pull_request: Pull request to get zuul dependencies from

    Returns:
        Tuple[List[str], List[str]]: Dependencies as two lists, first list of IDs and second list of URIs
    """

    deps = re.findall(r"^Depends-On:\s?(.*?)$", pull_request.body, re.MULTILINE)

    deps = list(map(lambda x: re.split(r"\s+", x)[0].strip(), deps))

    valid_deps: List[str] = list(filter(validators.url, deps))

    return [], list(map(pull_request_url_to_uri, valid_deps))


DependencyCallback = Callable[[PullRequest], Tuple[List[str], List[str]]]


class GithubPullRequestCollector(Thread):
    """Collects pull requests from github"""

    def __init__(
        self,
        github: Github,
        queries: List[CollectQuery],
        update_query: Optional[CollectQuery] = None,
        dependencies_callback: Optional[DependencyCallback] = None,
        wait_time: timedelta = timedelta(minutes=5),
    ) -> None:
        super().__init__(target=self._run)

        self.github = github
        self.wait_time = wait_time
        self.dependencies_callback = dependencies_callback
        self._keep_running: bool = True

        self.pull_requests_map: Dict[str, PullRequestContainer] = {}
        self.queries: List[CollectQuery] = queries
        self.update_query: Optional[CollectQuery] = update_query

        self.pull_requests_needing_update_ids: Set[str] = set()
        self.pull_requests_needing_update_uris: Set[str] = set()

    def _run(self):
        keep_running = True

        while keep_running:
            for query in self.queries:
                self._update_pull_requests(
                    self.github.search_pull_requests(query.query, PR_QUERY_DATA)
                )

            if self.update_query:
                self._update_pull_requests(
                    self.github.search_pull_requests(self.update_query, PR_QUERY_DATA)
                )

            self._need_update_collect()

            _internal_sleep(self.wait_time.total_seconds())

            # This is done this way to make sure in testing that the thread is run at least once
            keep_running = self._keep_running

    def stop(self) -> None:
        """Stops the collector"""
        self._keep_running = False

    def _need_update_collect(self):
        # Update PRs based on their id
        if self.pull_requests_needing_update_ids:
            update_ids = sorted(list(self.pull_requests_needing_update_ids)[:50])
            self._update_pull_requests(
                self.github.get_pull_requests_by_ids(update_ids, PR_QUERY_DATA)
            )

        # Update PRs based on their uri
        pr_uris = list(self.pull_requests_needing_update_uris)

        if pr_uris:
            owner_with_name = pr_uris[0].split("#")[0]
            pr_uris_with_correct_owner_with_name = list(
                filter(lambda x: x.split("#")[0] == owner_with_name, pr_uris)
            )
            update_uris = pr_uris_with_correct_owner_with_name[:50]
            update_numbers = sorted([uri.split("#")[1] for uri in update_uris], key=int)
            self._update_pull_requests(
                self.github.search_pull_requests(
                    f'repo:{owner_with_name} is:pr {" ".join(update_numbers)}',
                    PR_QUERY_DATA,
                )
            )

    def _update_pull_requests(self, pull_requests: List[PullRequest]):
        all_ids = set(
            map(lambda x: x.pull_request.id, self.pull_requests_map.values())
        ) | set(map(lambda x: x.id, pull_requests))

        for pull_request in pull_requests:
            dep_ids, dep_uris = (
                self.dependencies_callback(pull_request)
                if self.dependencies_callback
                else ([], [])
            )

            self.pull_requests_map[pull_request.uri] = PullRequestContainer(
                pull_request=pull_request,
                last_data_pull_at=datetime.utcnow(),
                dependencies=dep_ids + dep_uris,
            )

            self.pull_requests_needing_update_ids.update(
                filter(lambda x: x not in all_ids, dep_ids)
            )
            self.pull_requests_needing_update_uris.update(
                filter(lambda x: x not in self.pull_requests_map, dep_uris)
            )

            self.pull_requests_needing_update_ids.discard(pull_request.id)
            self.pull_requests_needing_update_uris.discard(pull_request.uri)
