# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import pytest
import responses as responses_


def pytest_runtest_setup(item):
    responses_.start()


def pytest_runtest_teardown(item):
    try:
        responses_.stop()
        responses_.reset()
    except (AttributeError, RuntimeError):
        # patcher was already uninstalled (or not installed at all) and
        # responses doesnt let us force maintain it
        pass


@pytest.fixture
def responses():
    with responses_.RequestsMock() as rsps:
        yield rsps
