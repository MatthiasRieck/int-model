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
    pull_request_url_to_uri,
    zuul_dependencies_from_pull_request,
    PullRequestContainer,
    open_pull_request_last_update_30_minutes_ago,
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


class TestPullRequestUrlToUri(TestCase):
    def test_normal(self):
        self.assertEqual(
            pull_request_url_to_uri(
                "https://github.com/MatthiasRieck/int-model/pull/5"
            ),
            "MatthiasRieck/int-model#5",
        )

    def test_just_enough_parts(self):
        self.assertEqual(
            pull_request_url_to_uri("MatthiasRieck/int-model/pull/5"),
            "MatthiasRieck/int-model#5",
        )

    def test_not_enough_parts(self):
        with self.assertRaises(AssertionError) as ctx:
            pull_request_url_to_uri("int-model/pull/5")

        self.assertEqual(
            str(ctx.exception),
            "Pull request url int-model/pull/5 does not have enough parts",
        )

    def test_does_not_end_with_number(self):
        with self.assertRaises(AssertionError) as ctx:
            pull_request_url_to_uri("MatthiasRieck/int-model/pull/abc")

        self.assertEqual(
            str(ctx.exception),
            "Pull request url MatthiasRieck/int-model/pull/abc does not end with a number",
        )

    def test_does_not_contains_pull_in_url(self):
        with self.assertRaises(AssertionError) as ctx:
            pull_request_url_to_uri("https://github.com/MatthiasRieck/int-model/5")

        self.assertEqual(
            str(ctx.exception),
            "Pull request url https://github.com/MatthiasRieck/int-model/5 does not end with /pull/<number>",
        )


class TestZuulDependenciesFromPullRequest(TestCase):
    def test_normal(self):
        self.assertEqual(
            zuul_dependencies_from_pull_request(PullRequest(body="")),
            ([], []),
        )

    def test_dependency(self):
        self.assertEqual(
            zuul_dependencies_from_pull_request(
                PullRequest(
                    body="Depends-On: https://github.com/MatthiasRieck/int-model/pull/5",
                ),
            ),
            ([], ["MatthiasRieck/int-model#5"]),
        )

    def test_invalid_dependency(self):
        self.assertEqual(
            zuul_dependencies_from_pull_request(
                PullRequest(
                    body="Depends-On: httpgithub.com/MatthiasRieck/int-model/pull/5",
                ),
            ),
            ([], []),
        )

    def test_formerly_dependency(self):
        self.assertEqual(
            zuul_dependencies_from_pull_request(
                PullRequest(
                    body="Formerly-Depends-On: https://github.com/MatthiasRieck/int-model/pull/5",
                ),
            ),
            ([], []),
        )

    def test_multiple_dependencies(self):
        self.assertEqual(
            zuul_dependencies_from_pull_request(
                PullRequest(
                    body=(
                        "Depends-On: https://github.com/MatthiasRieck/int-model/pull/5"
                        "\n"
                        "Depends-On: https://github.com/MatthiasRieck/int-model/pull/3 (This is a comment)"
                        "\n"
                        "Depends-On: https://github.com/MatthiasRieck/int-model/pull/1"
                    ),
                ),
            ),
            (
                [],
                [
                    "MatthiasRieck/int-model#5",
                    "MatthiasRieck/int-model#3",
                    "MatthiasRieck/int-model#1",
                ],
            ),
        )


class TestOpenPullRequestLastUpdate30MinutesAgo(TestCase):
    def test_needs_update_open(self):
        self.assertTrue(
            open_pull_request_last_update_30_minutes_ago(
                PullRequestContainer(
                    pull_request=PullRequest(state="OPEN"),
                    updated_at=datetime.utcnow() - timedelta(minutes=31),
                ),
            ),
        )

    def test_does_not_need_update_merged(self):
        self.assertFalse(
            open_pull_request_last_update_30_minutes_ago(
                PullRequestContainer(
                    pull_request=PullRequest(state="MERGED"),
                    updated_at=datetime.utcnow() - timedelta(minutes=31),
                ),
            ),
        )

    def test_does_not_need_update_open(self):
        self.assertFalse(
            open_pull_request_last_update_30_minutes_ago(
                PullRequestContainer(
                    pull_request=PullRequest(state="OPEN"),
                    updated_at=datetime.utcnow() - timedelta(minutes=29),
                ),
            ),
        )


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
                self.assertEqual(pull_request.updated_at, datetime(2010, 10, 8, 11, 43))

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

    def test_generate_new_updates_due_to_dependencies(self):
        """
        In case a pull request has dependencies there is the need to check if this
        requires the collector to pull additional dependencies.

        What shall be tested is the following.
        - a pull request is queried by the collector, it has 4 dependencies
        - two are ID based where one exists
        - two are URI based where one exists
        - So in the end we should have 2 additional pull requests that need to be queried
        """
        repo = Repository(name_with_owner="owner/name")

        github = Mock(spec=Github)
        github.get_pull_requests_by_ids.side_effect = [
            [
                PullRequest(number=2, id="id2", repository=repo),
            ],
        ]
        github.search_pull_requests.side_effect = [
            [
                PullRequest(number=0, id="id0", repository=repo),
            ],
            [
                PullRequest(number=4, id="id4", repository=repo),
            ],
        ]

        dependency_mock = Mock()
        dependency_mock.side_effect = [
            (
                ["id1", "id2"],
                ["owner/name#3", "owner/name#4"],
            ),
            ([], []),
            ([], []),
        ]

        collector = GithubPullRequestCollector(
            github,
            queries=const_queries_from_list(["query"]),
            dependencies_callback=dependency_mock,
        )

        collector.pull_requests_map = {
            "owner/name#1": PullRequestContainer(
                pull_request=PullRequest(id="id1", repository=repo, number=1),
                updated_at=datetime.utcnow(),
            ),
            "owner/name#3": PullRequestContainer(
                pull_request=PullRequest(id="id3", repository=repo, number=3),
                updated_at=datetime.utcnow(),
            ),
        }

        collector.start()
        collector.stop()

        collector.join()

        github.search_pull_requests.mock_calls[0] == call("query", PR_QUERY_DATA)
        github.search_pull_requests.mock_calls[1] == call(
            "repo:owner/name is:pr 4", PR_QUERY_DATA
        )
        github.get_pull_requests_by_ids.assert_called_once_with(
            ["id2"],
            PR_QUERY_DATA,
        )

    def test_calculate_pull_request_needs_update(self):
        """
        In case of it can be that a pull request has not been updated in a long time, therefore,
        there is the ability to specify externally through functions in case a pull request shall be
        updated.
        """
        repo = Repository(name_with_owner="owner/name")
        pr_one = PullRequest(id="id1", repository=repo, number=1)
        pr_two = PullRequest(id="id2", repository=repo, number=2)
        pr_three = PullRequest(id="id3", repository=repo, number=3)

        github = Mock(spec=Github)
        github.get_pull_requests_by_ids.side_effect = [
            [
                pr_one,
                pr_two,
            ],
        ]

        callback_need_update_one = Mock()
        callback_need_update_one.side_effect = [
            True,
            False,
            False,
        ]
        callback_need_update_two = Mock()
        callback_need_update_two.side_effect = [
            False,
            True,
            False,
        ]

        collector = GithubPullRequestCollector(
            github,
            need_update_callbacks=[
                callback_need_update_one,
                callback_need_update_two,
            ],
        )

        collector.pull_requests_map = {
            "owner/name#1": PullRequestContainer(
                pull_request=pr_one,
                updated_at=datetime.utcnow(),
            ),
            "owner/name#2": PullRequestContainer(
                pull_request=pr_two,
                updated_at=datetime.utcnow(),
            ),
            "owner/name#3": PullRequestContainer(
                pull_request=pr_three,
                updated_at=datetime.utcnow(),
            ),
        }

        collector.start()
        collector.stop()

        collector.join()

        github.get_pull_requests_by_ids.assert_called_once_with(
            ["id1", "id2"],
            PR_QUERY_DATA,
        )
