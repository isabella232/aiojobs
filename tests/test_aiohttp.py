import asyncio

import pytest
from aiohttp import web

# isort: off

from aiojobs.aiohttp import (
    atomic,
    get_scheduler,
    get_scheduler_from_app,
    get_scheduler_from_request,
    setup as aiojobs_setup,
    spawn,
)

# isort: on


async def test_plugin(aiohttp_client):
    job = None

    async def coro():
        await asyncio.sleep(10)

    async def handler(request):
        nonlocal job

        job = await spawn(request, coro())
        assert not job.closed
        return web.Response()

    app = web.Application()
    app.router.add_get("/", handler)
    aiojobs_setup(app)

    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert resp.status == 200

    assert job.active
    await client.close()
    assert job.closed


async def test_no_setup(aiohttp_client):
    async def handler(request):
        with pytest.raises(RuntimeError):
            get_scheduler(request)
        return web.Response()

    app = web.Application()
    app.router.add_get("/", handler)

    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert resp.status == 200


async def test_atomic(aiohttp_client):
    @atomic
    async def handler(request):
        await asyncio.sleep(0)
        return web.Response()

    app = web.Application()
    app.router.add_get("/", handler)
    aiojobs_setup(app)

    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert resp.status == 200

    scheduler = get_scheduler_from_app(app)

    assert scheduler.active_count == 0
    assert scheduler.pending_count == 0


async def test_atomic_from_view(aiohttp_client):
    app = web.Application()

    class MyView(web.View):
        @atomic
        async def get(self):
            return web.Response()

    app.router.add_route("*", "/", MyView)
    aiojobs_setup(app)

    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert resp.status == 200

    scheduler = get_scheduler_from_app(app)

    assert scheduler.active_count == 0
    assert scheduler.pending_count == 0


async def test_nested_application(aiohttp_client):
    app = web.Application()
    aiojobs_setup(app)

    app2 = web.Application()

    class MyView(web.View):
        async def get(self):
            assert get_scheduler_from_request(self.request) == get_scheduler_from_app(
                app
            )
            return web.Response()

    app2.router.add_route("*", "/", MyView)
    app.add_subapp("/sub/", app2)

    client = await aiohttp_client(app)
    resp = await client.get("/sub/")
    assert resp.status == 200


async def test_nested_application_separate_scheduler(aiohttp_client):
    app = web.Application()
    aiojobs_setup(app)

    app2 = web.Application()
    aiojobs_setup(app2)

    class MyView(web.View):
        async def get(self):
            assert get_scheduler_from_request(self.request) != get_scheduler_from_app(
                app
            )
            assert get_scheduler_from_request(self.request) == get_scheduler_from_app(
                app2
            )
            return web.Response()

    app2.router.add_route("*", "/", MyView)
    app.add_subapp("/sub/", app2)

    client = await aiohttp_client(app)
    resp = await client.get("/sub/")
    assert resp.status == 200


async def test_nested_application_not_set(aiohttp_client):
    app = web.Application()
    app2 = web.Application()

    class MyView(web.View):
        async def get(self):
            assert get_scheduler_from_request(self.request) is None
            return web.Response()

    app2.router.add_route("*", "/", MyView)
    app.add_subapp("/sub/", app2)

    client = await aiohttp_client(app)
    resp = await client.get("/sub/")
    assert resp.status == 200
