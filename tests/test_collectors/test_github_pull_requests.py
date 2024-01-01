from unittest import TestCase
from unittest.mock import patch, Mock, call
from datetime import datetime, timedelta
import time

from gitaudit.github.instance import Github
from gitaudit.github.graphql_objects import PullRequest, Repository

from intm.collectors.github_pull_requests import (
    CollectQuery,
    ConstantCollectQuery,
    RecentlyUpdatedPullRequests,
    const_queries_from_list,
    _internal_sleep,
    GithubPullRequestCollector,
    PR_QUERY_DATA,
)


class TestCollectQuery(TestCase):
    def test_query(self):
        with self.assertRaises(NotImplementedError):
            CollectQuery().query


class TestConstantCollectQuery(TestCase):
    def test_query(self):
        self.assertEqual(ConstantCollectQuery("query").query, "query")


class TestRecentlyUpdatedPullRequests(TestCase):
    def test_query(self):
        with patch("intm.collectors.github_pull_requests.datetime") as mock_utc_now:
            mock_utc_now.utcnow.return_value = datetime(2010, 10, 8, 11, 43)
            # mock_utc_now.side_effect = lambda *args, **kw: datetime(*args, **kw)

            self.assertAlmostEqual(
                RecentlyUpdatedPullRequests("query", timedelta(minutes=1)).query,
                "query updated:>=2010-10-08T11:42:00",
            )


class TestConstQueriesFromList(TestCase):
    def test_const_queries_from_list(self):
        self.assertEqual(
            list(map(lambda x: x.query, const_queries_from_list(["query1", "query2"]))),
            ["query1", "query2"],
        )


class TestInternalSleep(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.patch_time_sleep = patch("intm.collectors.github_pull_requests.time.sleep")
        self.mock_time_sleep = self.patch_time_sleep.start()

    def tearDown(self) -> None:
        self.patch_time_sleep.stop()

        super().tearDown()

    def test_internal_sleep(self):
        _internal_sleep(5)

        self.mock_time_sleep.assert_called_with(5)


class TestGithubPullRequestCollector(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.patch_sleep = patch("intm.collectors.github_pull_requests._internal_sleep")
        self.mock_sleep = self.patch_sleep.start()

    def tearDown(self) -> None:
        self.patch_sleep.stop()

        super().tearDown()

    def test_run_empty_check_wait(self):
        github = Mock(spec=Github)
        collector = GithubPullRequestCollector(
            github,
            queries=[],
        )

        collector.start()
        collector.stop()

        collector.join()

        self.mock_sleep.assert_called_with(60 * 5)

    def test_run_queries(self):
        with patch("intm.collectors.github_pull_requests.datetime") as mock_utc_now:
            mock_utc_now.utcnow.return_value = datetime(2010, 10, 8, 11, 43)

            github = Mock(spec=Github)
            collector = GithubPullRequestCollector(
                github,
                queries=const_queries_from_list(["query1", "query2"]),
                update_query=ConstantCollectQuery("update"),
            )

            repo = Repository(name_with_owner="owner/name")
            github.search_pull_requests.side_effect = [
                [
                    PullRequest(number=1, title="title1", id="id1", repository=repo),
                    PullRequest(number=2, title="title2", id="id2", repository=repo),
                ],
                [
                    PullRequest(number=3, title="title3", id="id3", repository=repo),
                    PullRequest(number=4, title="title4", id="id4", repository=repo),
                ],
                [],
            ]

            collector.start()
            collector.stop()

            collector.join()

            github.search_pull_requests.mock_calls[0] == call("query1", PR_QUERY_DATA)
            github.search_pull_requests.mock_calls[1] == call("query2", PR_QUERY_DATA)
            github.search_pull_requests.mock_calls[2] == call("update", PR_QUERY_DATA)

            for pull_request in collector.pull_requests_map.values():
                self.assertEqual(
                    pull_request.last_data_pull_at, datetime(2010, 10, 8, 11, 43)
                )

    def test_need_update(self):
        github = Mock(spec=Github)

        repo = Repository(name_with_owner="owner/name")
        github.get_pull_requests_by_ids.side_effect = [
            [
                PullRequest(number=1, title="title1", id="id1", repository=repo),
                PullRequest(number=4, title="title4", id="id4", repository=repo),
                PullRequest(number=67, title="title67", id="id67", repository=repo),
            ],
        ]
        github.search_pull_requests.side_effect = [
            [
                PullRequest(number=8, title="title8", id="id8", repository=repo),
                PullRequest(number=9, title="title9", id="id9", repository=repo),
                PullRequest(number=45, title="title45", id="id45", repository=repo),
            ],
        ]

        collector = GithubPullRequestCollector(
            github,
            queries=[],
        )

        collector.pull_requests_needing_update_ids.add("id1")
        collector.pull_requests_needing_update_ids.add("id4")
        collector.pull_requests_needing_update_ids.add("id67")
        collector.pull_requests_needing_update_uris.add("owner/name#8")
        collector.pull_requests_needing_update_uris.add("owner/name#9")
        collector.pull_requests_needing_update_uris.add("owner/name#45")

        collector.start()
        collector.stop()

        collector.join()

        github.get_pull_requests_by_ids.assert_called_once_with(
            ["id1", "id4", "id67"],
            PR_QUERY_DATA,
        )
        github.search_pull_requests.assert_called_once_with(
            "repo:owner/name is:pr 8 9 45",
            PR_QUERY_DATA,
        )
