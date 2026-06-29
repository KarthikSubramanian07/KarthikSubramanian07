#!/usr/bin/env python3
"""
survey.py — Spacecraft systems readout for KarthikSubramanian07's GitHub profile.

Pulls LIVE data and writes it into light_mode.svg / dark_mode.svg:
  - GitHub GraphQL API v4: total commit contributions (all time, incl. org/
    collaborator repos), total stars across owned repos, total repos,
    account age in years.
  - Open-Meteo (no key): current temperature (F) + sky description at Soda Hall.
  - Age computed from birthday with dateutil.relativedelta.

GraphQL pagination / retry / SVG-overwrite approach follows Andrew6rant's today.py:
  https://github.com/Andrew6rant/Andrew6rant/blob/main/today.py

Environment variables:
  ACCESS_TOKEN  GitHub personal access token (repo + read:user scope)
  USER_NAME     GitHub login, e.g. KarthikSubramanian07
"""

import os
import time
import datetime
from datetime import timezone

import requests
from dateutil import relativedelta
from lxml import etree

HEADERS = {"authorization": "token " + os.environ.get("ACCESS_TOKEN", "")}
USER_NAME = os.environ.get("USER_NAME") or "KarthikSubramanian07"
BIRTHDAY = datetime.datetime(2007, 6, 19)

# Soda Hall, Berkeley
WEATHER_LAT = 37.8755
WEATHER_LON = -122.2596

RETRY_STATUS = {502, 503, 504, 429}
MAX_RETRIES = 5
QUERY_COUNT = {"user_getter": 0, "graph_commits": 0, "graph_repos_stars": 0}


def query_count(funct_id):
    QUERY_COUNT[funct_id] += 1


def post_graphql(query, variables):
    """POST a GraphQL query, retrying transient errors with exponential backoff."""
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
            body = resp.json()
            if "errors" in body and body.get("data") is None:
                raise Exception("GraphQL error", body["errors"], QUERY_COUNT)
            return resp
        if resp.status_code in RETRY_STATUS:
            last = resp
            time.sleep(2 ** attempt)
            continue
        return resp
    if isinstance(last, requests.Response):
        return last
    raise Exception("post_graphql exhausted retries", str(last), QUERY_COUNT)


def simple_request(func_name, query, variables):
    request = post_graphql(query, variables)
    if request.status_code == 200:
        return request
    raise Exception(func_name, "failed with", request.status_code, request.text, QUERY_COUNT)


# ── Age ──────────────────────────────────────────────────────────────────────
def format_plural(unit):
    return "s" if unit != 1 else ""


def daily_readme(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return "{} {}, {} {}, {} {}".format(
        diff.years, "year" + format_plural(diff.years),
        diff.months, "month" + format_plural(diff.months),
        diff.days, "day" + format_plural(diff.days),
    )


def account_age_years(created_at):
    diff = relativedelta.relativedelta(datetime.datetime.today(), created_at)
    return diff.years


# ── GitHub ────────────────────────────────────────────────────────────────────
def user_getter(username):
    """Return the account's createdAt timestamp."""
    query_count("user_getter")
    query = """
    query($login: String!){ user(login: $login) { createdAt } }"""
    request = simple_request(user_getter.__name__, query, {"login": username})
    return request.json()["data"]["user"]["createdAt"]


def graph_commits(start_date, end_date):
    """Total contributions in [start_date, end_date] (commits, PRs, issues, reviews)."""
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
    """Sum contributions year-by-year from account creation to now."""
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


def total_repos():
    """Total number of repositories the user owns."""
    query_count("graph_repos_stars")
    query = """
    query ($login: String!) {
        user(login: $login) {
            repositories(ownerAffiliations: OWNER) { totalCount }
        }
    }"""
    request = simple_request("total_repos", query, {"login": USER_NAME})
    return request.json()["data"]["user"]["repositories"]["totalCount"]


# ── Weather (Open-Meteo, no API key) ──────────────────────────────────────────
WMO_CODES = {
    0: ("☀️", "clear sky"), 1: ("🌤️", "mainly clear"), 2: ("⛅", "partly cloudy"),
    3: ("☁️", "overcast"), 45: ("🌫️", "fog"), 48: ("🌫️", "rime fog"),
    51: ("🌦️", "light drizzle"), 53: ("🌦️", "drizzle"), 55: ("🌧️", "dense drizzle"),
    56: ("🌧️", "freezing drizzle"), 57: ("🌧️", "freezing drizzle"),
    61: ("🌦️", "light rain"), 63: ("🌧️", "rain"), 65: ("🌧️", "heavy rain"),
    66: ("🌧️", "freezing rain"), 67: ("🌧️", "freezing rain"),
    71: ("🌨️", "light snow"), 73: ("🌨️", "snow"), 75: ("❄️", "heavy snow"),
    77: ("❄️", "snow grains"), 80: ("🌦️", "light showers"), 81: ("🌧️", "showers"),
    82: ("⛈️", "violent showers"), 85: ("🌨️", "snow showers"), 86: ("🌨️", "snow showers"),
    95: ("⛈️", "thunderstorm"), 96: ("⛈️", "thunderstorm w/ hail"), 99: ("⛈️", "thunderstorm w/ hail"),
}


def get_weather():
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


# ── SVG writing ────────────────────────────────────────────────────────────────
def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = str(new_text)
    else:
        print(f"  [warn] no SVG element with id='{element_id}'")


def svg_overwrite(filename, age_data, commit_data, contrib_data, repo_data, years_data, weather_data):
    tree = etree.parse(filename)
    root = tree.getroot()
    find_and_replace(root, "age_data", age_data)
    find_and_replace(root, "commit_data", commit_data)
    find_and_replace(root, "contrib_data", contrib_data)
    find_and_replace(root, "repo_data", repo_data)
    find_and_replace(root, "years_data", years_data)
    find_and_replace(root, "weather_data", weather_data)
    tree.write(filename, encoding="utf-8", xml_declaration=True)


def format_number(n):
    return "{:,}".format(int(n))


def main():
    print("Querying GitHub…")
    created_at = user_getter(USER_NAME)
    created_dt = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")

    age_data = daily_readme(BIRTHDAY)
    years_data = str(account_age_years(created_dt))
    commit_data = format_number(total_commits(created_at))
    now = datetime.datetime.now(timezone.utc)
    year_ago = (now - relativedelta.relativedelta(years=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    contrib_data = format_number(graph_commits(year_ago, now.strftime("%Y-%m-%dT%H:%M:%SZ")))
    repo_data = format_number(total_repos())

    print("Fetching weather…")
    weather_data = get_weather()

    for svg in ("light_mode.svg", "dark_mode.svg"):
        if os.path.exists(svg):
            svg_overwrite(svg, age_data, commit_data, contrib_data, repo_data, years_data, weather_data)
            print(f"Updated {svg}")
        else:
            print(f"  [warn] {svg} not found; skipping")

    print("\nDone.")
    print(f"  Age:       {age_data}")
    print(f"  Commits:   {commit_data}")
    print(f"  This year: {contrib_data}")
    print(f"  Repos:     {repo_data}")
    print(f"  Years:     {years_data}")
    print(f"  Weather:   {weather_data}")
    print(f"  Queries:   {QUERY_COUNT}")


if __name__ == "__main__":
    main()
