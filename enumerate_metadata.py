#!/usr/bin/env python3

import json
import re
import sys

import requests

BASE_URL_V4 = "http://169.254.169.254/latest"
BASE_URL_V6 = "http://[fd00:ec2::254]/latest"

TIMEOUT = 5
EXPECTED_PATH_PATTERN = re.compile(r"^(([A-Za-z0-9-]+)|(([\da-f]{2}:?)+)|((\d{1,3}.?){4})+)\/?$")

def get_token(base):
    print(f"Fetching token for {base}", file=sys.stderr)
    response = requests.put(
        f"{base}/api/token",
        headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.text

def make_request(url, token):
    print(f"Requesting {url}", file=sys.stderr)
    response = requests.get(
        url,
        headers={'X-aws-ec2-metadata-token': token},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    try:
        return response.json(parse_int=str, parse_float=str)
    except Exception:
        return response.text

def walk(base, token=None):
    try:
        if token is None:
            token = get_token(base)
    except Exception:
        print("Failed to fetch token; falling back to IMDSv1", file=sys.stderr)

    # Avoid requesting something that very much doesn't look like a correct
    # value. This prevents making requests for things that are proably actually
    # just keys.
    if not EXPECTED_PATH_PATTERN.match(base.split('/')[-1]):
        return None

    try:
        response = make_request(base, token)
    except Exception as e:
        print(e, file=sys.stderr)
        return None

    if not isinstance(response, str):
        return response

    print(f"{response!r}", file=sys.stderr)

    if response.startswith('#!'):
        print("Looks like shell script", file=sys.stderr)
        return response

    paths = response.splitlines()
    data = {}
    for path in paths:
        path = path.strip()
        print(f"{path=!r}", file=sys.stderr)
        if path.endswith('/'):
            path = path[:-1]
        next = path
        if path[0].isdigit() and (len(path) == 1 or path[1] == '='):
            next = path[0]
        if '/' in next:
            data[path] = None
        data[path] = walk(f"{base}/{next}", token)

    # If there are any non-null children, data is already clean
    if [value for value in data.values() if value]:
        return data

    # The nested fields may be null if there's never been
    # maintenance and there is none planned
    if base.endswith('maintenance'):
        return data

    # Try to cleanup/format the nested data, guessing whether it
    # should be a single string or the original string
    if base.endswith('s'):
        return response.splitlines()
    return response


def walk_all():
    return {
        'v4': walk(BASE_URL_V4),
        'v6': walk(BASE_URL_V6),
    }

def main():
    print(json.dumps(walk_all(), indent=2))


if __name__ == '__main__':
    main()
