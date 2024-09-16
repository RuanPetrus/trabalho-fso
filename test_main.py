import pytest, asyncio, os, shutil
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient

from main import app, DATA_DIR, start_db

def clear_db():
    path = DATA_DIR
    if os.path.isfile(path) or os.path.islink(path):
        os.remove(path)  # remove the file
    elif os.path.isdir(path):
        shutil.rmtree(path)  # remove dir and all contains
    else:
        print(path)

def reset_db():
    clear_db()
    start_db()


@pytest.mark.asyncio
async def test_cadastro():
    reset_db()
    CADASTRO_COUNT = 10
    CADASTRO_ROUTE = "/api/cadastro/"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        for i in range(CADASTRO_COUNT):
            response = await ac.post(CADASTRO_ROUTE + str(i))
            assert response.status_code == 201

        for i in range(CADASTRO_COUNT):
            response = await ac.post(CADASTRO_ROUTE + str(i))
            assert response.status_code == 404
