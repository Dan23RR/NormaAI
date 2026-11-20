"""The validation runner asks for each golden v2 answer in the question's language.

The API writes the answer in the request's ``language``: a runner that sent
Italian for every record would get Italian answers to the English questions.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.validation.golden_v2 import load_golden_v2_test_cases
from tests.validation.runner import _call_normaai_api, _call_normaai_direct


def _first_case(lang: str):
    return next(tc for tc in load_golden_v2_test_cases() if tc.document.language == lang)


@pytest.mark.parametrize("lang", ["it", "en"])
async def test_api_mode_sends_the_record_language(lang):
    client = AsyncMock()
    client.run_qa.return_value = {"status": "success", "data": {"answer": "x", "citations": []}}
    await _call_normaai_api(_first_case(lang), client)
    assert client.run_qa.await_args.kwargs["language"] == lang


async def test_direct_mode_sends_the_record_language():
    with patch("src.agents.graph.arun_qa", AsyncMock(return_value={})) as arun_qa:
        await _call_normaai_direct(_first_case("en"))
    assert arun_qa.await_args.kwargs["language"] == "en"
