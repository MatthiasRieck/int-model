# # dictlist = {
# #     "owner/repo#1": {"title": "title1", "body": "body1"},
# #     "owner/repo#2": {"title": "title2", "body": "body2"},
# #     "owner/repo#3": {"title": "title3", "body": "body3"},
# # }

# # k = next(iter(dictlist))

# # # (, dictlist.pop(k))

# # print(dictlist.popitem)

# import ast

# print(ast.dump(ast.parse('pr.participants.contains(sdjksjd, sdkjsd, ksdj) or "sdkjk" in title'), ))

from datetime import timedelta

from gitaudit.github import Github

github = Github("token")

from intm.collectors.github_pull_requests import (
    const_queries_from_list,
    RecentlyUpdatedPullRequests,
    GithubPullRequestCollector,
)


collector = GithubPullRequestCollector(
    github,
    const_queries_from_list(
        [
            "org:flutter is:pr is:open",
        ]
    ),
    timedelta(minutes=1),
)
