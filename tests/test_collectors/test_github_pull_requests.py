from unittest import TestCase
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
import time

from gitaudit.github.instance import Github

from intm.collectors.github_pull_requests import (
    ConstantCollectQuery,
    RecentlyUpdatedPullRequests,
    const_queries_from_list,
    GithubPullRequestCollector,
)


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


class TestGithubPullRequestCollector(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.patch_sleep = patch("intm.collectors.github_pull_requests._internal_sleep")
        self.mock_sleep = self.patch_sleep.start()

    def tearDown(self) -> None:
        self.patch_sleep.stop()

        super().tearDown()

    # def test_run_empty(self):
    #     github = Mock(spec=Github)
    #     collector = GithubPullRequestCollector(
    #         github, queries=[], wait_time=timedelta(seconds=1)
    #     )

    #     collector.start()

    #     time.sleep(0.1)

    #     self.mock_sleep.assert_called_with(60 * 5)
