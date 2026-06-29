#!/usr/bin/env python3
"""
survey.py — Spacecraft systems readout for KarthikSubramanian07's GitHub profile.

Pulls LIVE data and writes it into light_mode.svg / dark_mode.svg:
  - GitHub GraphQL API v4: total commits (incl. collaborator repos), total stars,
    total repos, total lines of code (+additions / -deletions), account age.
  - Open-Meteo (no key): current temperature (F) + sky description at Soda Hall.
  - Age computed from birthday with dateutil.relativedelta.

LOC is cached in cache/ under SHA-256-hashed filenames so only changed repos are
re-scanned. Caching / GraphQL / SVG-overwrite logic follows Andrew6rant's today.py:
  https://github.com/Andrew6rant/Andrew6rant/blob/main/today.py

Environment variables:
  ACCESS_TOKEN  GitHub personal access token (repo + read:user scope)
  USER_NAME     GitHub login, e.g. KarthikSubramanian07
"""

import os
import time
import hashlib
import datetime
from datetime import timezone

import requests
from dateutil import relativedelta
from lxml import etree

# Transient HTTP statuses worth retrying (GitHub occasionally 502s mid-scan).
RETRY_STATUS = {502, 503, 504, 429}
MAX_RETRIES = 5

# ── Configuration ──────────────────────────────────────────────────────────
HEADERS = {"authorization": "token " + os.environ.get("ACCESS_TOKEN", "")}
USER_NAME = os.environ.get("USER_NAME") or "KarthikSubramanian07"
BIRTHDAY = datetime.datetime(2007, 6, 19)

# Soda Hall, Berkeley
WEATHER_LAT = 37.8755
WEATHER_LON = -122.2596

QUERY_COUNT = {
    "user_getter": 0,
    "follower_getter": 0,
    "graph_repos_stars": 0,
    "recursive_loc": 0,
    "graph_commits": 0,
    "loc_query": 0,
}


# ── Small helpers ──────────────────────────────────────────────────────────
def query_count(funct_id):
    """Track how many times each GraphQL function is called (for debugging)."""
    QUERY_COUNT[funct_id] += 1


def post_graphql(query, variables):
    """POST a GraphQL query, retrying transient errors with exponential backoff.

    Returns the requests.Response. Raises only after MAX_RETRIES on a transient
    status, or immediately on a non-transient failure.
    """
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": variables},
                headers=HEADERS,
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            # A 200 can still carry GraphQL errors (e.g. rate limit) — surface them.
            body = resp.json()
            if "errors" in body and body.get("data") is None:
                raise Exception("GraphQL error", body["errors"], QUERY_COUNT)
            return resp
        if resp.status_code in RETRY_STATUS:
            last = resp
            time.sleep(2 ** attempt)
            continue
        # Non-transient (4xx auth/query errors): fail fast.
        return resp
    if isinstance(last, requests.Response):
        return last
    raise Exception("post_graphql exhausted retries", str(last), QUERY_COUNT)


def simple_request(func_name, query, variables):
    """POST a GraphQL query; raise with context on non-200 responses."""
    request = post_graphql(query, variables)
    if request.status_code == 200:
        return request
    raise Exception(
        func_name,
        " has failed with a",
        request.status_code,
        request.text,
        QUERY_COUNT,
    )


# ── Age ────────────────────────────────────────────────────────────────────
def daily_readme(birthday):
    """Return age as 'XX years, XX months, XX days' (handles singular/plural)."""
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return "{} {}, {} {}, {} {}".format(
        diff.years, "year" + format_plural(diff.years),
        diff.months, "month" + format_plural(diff.months),
        diff.days, "day" + format_plural(diff.days),
    )


def format_plural(unit):
    """'s' unless the value is exactly 1."""
    return "s" if unit != 1 else ""


def account_age_years(birthday=None, created_at=None):
    """Whole years since GitHub account creation (fallback: birthday)."""
    anchor = created_at if created_at is not None else birthday
    diff = relativedelta.relativedelta(datetime.datetime.today(), anchor)
    return diff.years


# ── GitHub: user id / account creation ──────────────────────────────────────
def user_getter(username):
    """Return (account id+createdAt dict) for the given login."""
    query_count("user_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }"""
    variables = {"login": username}
    request = simple_request(user_getter.__name__, query, variables)
    user = request.json()["data"]["user"]
    return {"id": user["id"]}, user["createdAt"]


def follower_getter(username):
    """Total followers (not displayed by default but cheap to fetch)."""
    query_count("follower_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            followers { totalCount }
        }
    }"""
    request = simple_request(follower_getter.__name__, query, {"login": username})
    return int(request.json()["data"]["user"]["followers"]["totalCount"])


# ── GitHub: commits (all time, incl. collaborator/org repos) ─────────────────
def graph_commits(start_date, end_date):
    """Total commit contributions in [start_date, end_date] for the user."""
    query_count("graph_commits")
    query = """
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar { totalContributions }
            }
        }
    }"""
    variables = {"start_date": start_date, "end_date": end_date, "login": USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(
        request.json()["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]["totalContributions"]
    )


def total_commits(created_at):
    """Sum commit contributions year-by-year from account creation to now.

    contributionsCollection only spans up to one year, so we walk in yearly
    windows. This counts commits across owned, org, and collaborator repos.
    """
    created = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    now = datetime.datetime.now(timezone.utc)
    total = 0
    window_start = created
    while window_start < now:
        window_end = min(window_start + relativedelta.relativedelta(years=1), now)
        total += graph_commits(
            window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        window_start = window_end
    return total


# ── GitHub: repos + stars ────────────────────────────────────────────────────
def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    """Count owned repos or sum their stargazers, paginating with a cursor."""
    query_count("graph_repos_stars")
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers { totalCount }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""
    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }
    request = simple_request(graph_repos_stars.__name__, query, variables)
    repos = request.json()["data"]["user"]["repositories"]
    if count_type == "repos":
        return repos["totalCount"]
    if count_type == "stars":
        return stars_counter(repos["edges"], owner_affiliation, repos["pageInfo"])


def stars_counter(edges, owner_affiliation, page_info, running_total=0):
    """Recursively sum stargazers across all pages of repositories."""
    for node in edges:
        running_total += node["node"]["stargazers"]["totalCount"]
    if page_info["hasNextPage"]:
        next_edges = graph_repos_stars(
            "stars_page", owner_affiliation, page_info["endCursor"]
        )
        # graph_repos_stars("stars_page", ...) returns the raw repos block:
        return running_total  # handled below via _stars_paged
    return running_total


def total_stars():
    """Sum stars across all repositories the user owns (paginating manually)."""
    cursor = None
    running_total = 0
    while True:
        query_count("graph_repos_stars")
        query = """
        query ($login: String!, $cursor: String) {
            user(login: $login) {
                repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
                    edges { node { ... on Repository { stargazers { totalCount } } } }
                    pageInfo { endCursor hasNextPage }
                }
            }
        }"""
        variables = {"login": USER_NAME, "cursor": cursor}
        request = simple_request("total_stars", query, variables)
        repos = request.json()["data"]["user"]["repositories"]
        for node in repos["edges"]:
            running_total += node["node"]["stargazers"]["totalCount"]
        if repos["pageInfo"]["hasNextPage"]:
            cursor = repos["pageInfo"]["endCursor"]
        else:
            break
    return running_total


def total_repos():
    """Total count of repositories the user owns."""
    return graph_repos_stars("repos", ["OWNER"])


# ── GitHub: lines of code (with caching) ─────────────────────────────────────
COMMENT_SIZE = 7  # number of header comment lines in each cache file


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=None):
    """Fetch every repo (with default-branch commit counts), then build LOC cache."""
    if edges is None:
        edges = []
    query_count("loc_query")
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef {
                                target {
                                    ... on Commit { history { totalCount } }
                                }
                            }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""
    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }
    request = simple_request(loc_query.__name__, query, variables)
    repos = request.json()["data"]["user"]["repositories"]
    edges += repos["edges"]
    if repos["pageInfo"]["hasNextPage"]:
        return loc_query(
            owner_affiliation,
            comment_size,
            force_cache,
            repos["pageInfo"]["endCursor"],
            edges,
        )
    return cache_builder(edges, comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """Read/refresh the per-repo LOC cache; only re-scan repos whose commit count changed."""
    cached = True
    filename = (
        "cache/"
        + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest()
        + ".txt"
    )
    try:
        with open(filename, "r") as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            with open(filename, "w") as f:
                f.writelines(
                    "This line is a comment block. Write whatever you want here.\n"
                    * comment_size
                )
        with open(filename, "r") as f:
            data = f.readlines()

    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, "r") as f:
            data = f.readlines()

    cache_comment = data[:comment_size]
    data = data[comment_size:]

    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        node = edges[index]["node"]
        branch = node.get("defaultBranchRef")
        repo_commit_count = (
            branch["target"]["history"]["totalCount"] if branch else 0
        )
        expected_hash = hashlib.sha256(
            node["nameWithOwner"].encode("utf-8")
        ).hexdigest()
        if repo_hash == expected_hash:
            try:
                if int(commit_count) != repo_commit_count:
                    # Commit count changed → rescan this repo's LOC.
                    owner, repo_name = node["nameWithOwner"].split("/")
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = (
                        repo_hash
                        + " "
                        + str(repo_commit_count)
                        + " "
                        + str(loc[2])
                        + " "
                        + str(loc[0])
                        + " "
                        + str(loc[1])
                        + "\n"
                    )
            except TypeError:
                data[index] = (
                    repo_hash + " 0 0 0 0\n"
                )

    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)

    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    """Rewrite the cache header + one zeroed line per repo (forces full rescan)."""
    with open(filename, "r") as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]
    with open(filename, "w") as f:
        f.writelines(data)
        for node in edges:
            f.write(
                hashlib.sha256(node["node"]["nameWithOwner"].encode("utf-8")).hexdigest()
                + " 0 0 0 0\n"
            )


def recursive_loc(
    owner,
    repo_name,
    data,
    cache_comment,
    addition_total=0,
    deletion_total=0,
    my_commits=0,
    cursor=None,
):
    """Walk a repo's commit history page by page, summing LOC for the user's commits."""
    query_count("recursive_loc")
    query = """
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                        author { user { id } }
                                        deletions
                                        additions
                                    }
                                }
                            }
                            pageInfo { endCursor hasNextPage }
                        }
                    }
                }
            }
        }
    }"""
    variables = {"repo_name": repo_name, "owner": owner, "cursor": cursor}
    request = post_graphql(query, variables)
    if request.status_code == 200:
        repo = request.json()["data"]["repository"]
        if repo["defaultBranchRef"] is not None:
            history = repo["defaultBranchRef"]["target"]["history"]
            for node in history["edges"]:
                if (
                    node["node"]["author"]["user"]
                    and node["node"]["author"]["user"]["id"] == OWNER_ID
                ):
                    my_commits += 1
                    addition_total += node["node"]["additions"]
                    deletion_total += node["node"]["deletions"]
            if history["pageInfo"]["hasNextPage"]:
                return recursive_loc(
                    owner,
                    repo_name,
                    data,
                    cache_comment,
                    addition_total,
                    deletion_total,
                    my_commits,
                    history["pageInfo"]["endCursor"],
                )
            return [addition_total, deletion_total, my_commits]
        return [0, 0, 0]
    # On error, persist whatever we have so the run can continue next time.
    force_close_file(data, cache_comment)
    raise Exception(
        "recursive_loc() has failed with a",
        request.status_code,
        request.text,
        QUERY_COUNT,
    )


def force_close_file(data, cache_comment):
    """Save partial cache data if the API fails mid-scan, so progress isn't lost."""
    filename = (
        "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"
    )
    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)


# ── Weather (Open-Meteo, no API key) ─────────────────────────────────────────
WMO_CODES = {
    0: ("☀️", "clear sky"),
    1: ("🌤️", "mainly clear"),
    2: ("⛅", "partly cloudy"),
    3: ("☁️", "overcast"),
    45: ("🌫️", "fog"),
    48: ("🌫️", "rime fog"),
    51: ("🌦️", "light drizzle"),
    53: ("🌦️", "drizzle"),
    55: ("🌧️", "dense drizzle"),
    56: ("🌧️", "freezing drizzle"),
    57: ("🌧️", "freezing drizzle"),
    61: ("🌦️", "light rain"),
    63: ("🌧️", "rain"),
    65: ("🌧️", "heavy rain"),
    66: ("🌧️", "freezing rain"),
    67: ("🌧️", "freezing rain"),
    71: ("🌨️", "light snow"),
    73: ("🌨️", "snow"),
    75: ("❄️", "heavy snow"),
    77: ("❄️", "snow grains"),
    80: ("🌦️", "light showers"),
    81: ("🌧️", "showers"),
    82: ("⛈️", "violent showers"),
    85: ("🌨️", "snow showers"),
    86: ("🌨️", "snow showers"),
    95: ("⛈️", "thunderstorm"),
    96: ("⛈️", "thunderstorm w/ hail"),
    99: ("⛈️", "thunderstorm w/ hail"),
}


def get_weather():
    """Current temp (°F) + description at Soda Hall from Open-Meteo (free, no key)."""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
            "&current=temperature_2m,weather_code&temperature_unit=fahrenheit"
        )
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        current = resp.json()["current"]
        temp = round(current["temperature_2m"])
        code = int(current["weather_code"])
        emoji, desc = WMO_CODES.get(code, ("🛰️", "unknown"))
        return f"{emoji} {temp}°F · {desc}"
    except Exception:
        return "🛰️ unavailable"


# ── SVG writing ──────────────────────────────────────────────────────────────
def svg_overwrite(
    filename,
    age_data,
    commit_data,
    star_data,
    repo_data,
    loc_add,
    loc_del,
    years_data,
    weather_data,
):
    """Parse the SVG, replace each tracked element's text by id, write it back."""
    tree = etree.parse(filename)
    root = tree.getroot()
    find_and_replace(root, "age_data", age_data)
    find_and_replace(root, "commit_data", commit_data)
    find_and_replace(root, "star_data", star_data)
    find_and_replace(root, "repo_data", repo_data)
    find_and_replace(root, "loc_add", loc_add)
    find_and_replace(root, "loc_del", loc_del)
    find_and_replace(root, "years_data", years_data)
    find_and_replace(root, "weather_data", weather_data)
    tree.write(filename, encoding="utf-8", xml_declaration=True)


def find_and_replace(root, element_id, new_text):
    """Find an element by its id attribute and overwrite its text content."""
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = str(new_text)
    else:
        print(f"  [warn] no SVG element with id='{element_id}'")


def format_number(n):
    """Thousands separator, e.g. 2116 -> '2,116'."""
    return "{:,}".format(int(n))


# ── Main ──────────────────────────────────────────────────────────────────────
OWNER_ID = None  # filled in main()


def main():
    global OWNER_ID
    print("Querying GitHub…")
    user_data, created_at = user_getter(USER_NAME)
    OWNER_ID = user_data["id"]
    created_dt = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")

    age_data = daily_readme(BIRTHDAY)
    years_data = str(account_age_years(created_at=created_dt))
    commit_data = format_number(total_commits(created_at))
    star_data = format_number(total_stars())
    repo_data = format_number(total_repos())

    print("Counting lines of code (cached)…")
    loc = loc_query(["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"], COMMENT_SIZE)
    loc_add = "+" + format_number(loc[0])
    loc_del = "−" + format_number(loc[1])

    print("Fetching weather…")
    weather_data = get_weather()

    for svg in ("light_mode.svg", "dark_mode.svg"):
        if os.path.exists(svg):
            svg_overwrite(
                svg,
                age_data,
                commit_data,
                star_data,
                repo_data,
                loc_add,
                loc_del,
                years_data,
                weather_data,
            )
            print(f"Updated {svg}")
        else:
            print(f"  [warn] {svg} not found; skipping")

    print("\nDone.")
    print(f"  Age:      {age_data}")
    print(f"  Commits:  {commit_data}")
    print(f"  Stars:    {star_data}")
    print(f"  Repos:    {repo_data}")
    print(f"  LOC:      {loc_add}  {loc_del}")
    print(f"  Years:    {years_data}")
    print(f"  Weather:  {weather_data}")
    print(f"  Queries:  {QUERY_COUNT}")


if __name__ == "__main__":
    main()
