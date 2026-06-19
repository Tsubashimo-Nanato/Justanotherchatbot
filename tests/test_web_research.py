import asyncio

from local_qq_agent.web.research import WebResearcher


class FailingSearch:
    async def search(self, query, limit=5):
        raise AssertionError("local time queries should not call search")


class FailingBrowser:
    async def read(self, url):
        raise AssertionError("local time queries should not open browser pages")


def test_local_time_context_does_not_trigger_search():
    researcher = WebResearcher(FailingSearch(), FailingBrowser())

    context = asyncio.run(researcher.answer_context("what time is it now"))

    assert not context.used
    assert context.local_time_used
    assert not context.search_used
    assert not context.browser_used
    assert context.query == ""
    assert "Asia/Tokyo" in context.context
