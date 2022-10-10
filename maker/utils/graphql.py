# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import time

import requests


def run_query(uri, query, statusCode=200):
    response = requests.post(uri, json={"query": query})
    response.raise_for_status()
    if response.status_code == statusCode:
        content = response.json()
        if not content.get("data"):
            time.sleep(5)
            print("Error, Try again")
            return run_query(uri, query, statusCode=200)
        return response.json()
    else:
        time.sleep(5)
        print("Error, Try again")
        return run_query(uri, query, statusCode=200)
