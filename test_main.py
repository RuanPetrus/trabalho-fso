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




async def populate_db(cadastro_count: int):
    reset_db()
    CADASTRO_ROUTE = "/api/cadastro/"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        for i in range(cadastro_count):
            response = await ac.post(CADASTRO_ROUTE + str(i))
            assert response.status_code == 201

    
@pytest.mark.asyncio
async def test_single_user_matricula():
    await populate_db(1)
    client = TestClient(app)
    with client.websocket_connect("/ws/matricula/0") as websocket:
        websocket.send_text("turno")
        assert websocket.receive_text() == "ok"
        assert websocket.receive_text() == "vez"

        websocket.send_text("matutino")
        assert websocket.receive_text() == "ok"
        assert websocket.receive_text() == "vez"

        websocket.send_text("turma: A")
        assert websocket.receive_text() == "ok"

        assert websocket.receive_text() == "remove"
        assert websocket.receive_text() == "remove"


@pytest.mark.asyncio
async def test_double_user_matricula_all_matutino():
    await populate_db(2)
    client = TestClient(app)
    with client.websocket_connect("/ws/matricula/0") as ws1:
        with client.websocket_connect("/ws/matricula/1") as ws2:
            ws1.send_text("turno")
            assert ws1.receive_text() == "ok"
            assert ws1.receive_text() == "vez"

            ws2.send_text("turno")
            assert ws2.receive_text() == "ok"
            assert ws2.receive_text() == "vez"

            ws1.send_text("matutino")
            assert ws1.receive_text() == "ok"
            assert ws1.receive_text() == "vez"

            ws2.send_text("vespertino")
            assert ws2.receive_text().startswith("error:")
            ws2.send_text("matutino")
            assert ws2.receive_text() == "ok"

            ws1.send_text("turma: A")
            assert ws1.receive_text() == "ok"
            assert ws1.receive_text() == "remove"
            assert ws1.receive_text() == "remove"

            assert ws2.receive_text() == "vez"
            ws2.send_text("turma: A")
            assert ws2.receive_text().startswith("error:")

            ws2.send_text("turma: B")
            assert ws2.receive_text() == "ok"
            assert ws2.receive_text() == "remove"
            assert ws2.receive_text() == "remove"


CADASTRO_COUNT = 10

@pytest.mark.asyncio
async def test_cadastro():
    reset_db()
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
