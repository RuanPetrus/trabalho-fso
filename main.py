from fastapi import FastAPI, HTTPException, WebSocketException, WebSocket, status, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
import asyncio, os 

from connection import ConnectionManager, ClientConnection 
from config import DATA_DIR, ALUNO_DIR, MATUTINO_FILE_PATH, VESPERTINO_FILE_PATH, ordem_turmas, matutino, vespertino
from model import Aluno, Turno
from utils import file_read, file_write, file_count_files_in_dir, path_from_cpf, file_exist


def start_db():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    if not os.path.exists(ALUNO_DIR):
        os.makedirs(ALUNO_DIR)

    if not os.path.exists(MATUTINO_FILE_PATH):
        content = "\n".join([f"{t} 0 0" for t in matutino])
        with open(MATUTINO_FILE_PATH, "w") as f:
            f.write(content)

    if not os.path.exists(VESPERTINO_FILE_PATH):
        content = "\n".join([f"{t} 0 0" for t in vespertino])
        with open(VESPERTINO_FILE_PATH, "w") as f:
            f.write(content)

start_db()

app = FastAPI()

origins = [
    "*",
]

app.add_middleware (
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

@app.get("/{cpf}")
async def get_root(cpf: str):
    """Permite testar a implementação do websocket"""
    html = f"""
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws/matricula/{cpf}");
            ws.onmessage = function(event) {{
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            }};
            function sendMessage(event) {{
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }}
        </script>
    </body>
</html>
"""
    
    return HTMLResponse(html)


@app.get("/api/vagas/turno")
async def api_vagas_turno():
    """Retorna as vagas dos turnos"""
    matutino = Turno.from_string(await file_read(MATUTINO_FILE_PATH))
    matutino_vagas = 0
    for t in matutino.turmas:
        matutino_vagas += t.verde

    vespertino = Turno.from_string(await file_read(VESPERTINO_FILE_PATH))
    vespertino_vagas = 0
    for t in vespertino.turmas:
        vespertino_vagas += t.verde

    return {
            "matutino": matutino_vagas,
            "vespertino": vespertino_vagas,
    }


@app.get("/api/vagas/matutino")
async def api_vagas_matutino():
    """Retorna as vagas da turma do matutino"""
    turno = Turno.from_string(await file_read(MATUTINO_FILE_PATH))
    vagas = {}
    for idx, t in enumerate(turno.turmas):
        vagas[chr(ord("A")+idx)] = t.verde

    return vagas

@app.get("/api/vagas/vespertino")
async def api_vagas_vespertino():
    """Retorna as vagas da turma do vespertino"""
    turno = Turno.from_string(await file_read(VESPERTINO_FILE_PATH))
    vagas = {}
    for idx, t in enumerate(turno.turmas):
        vagas[chr(ord("E")+idx)] = t.verde

    return vagas


@app.post("/api/cadastro/{cpf}", status_code=status.HTTP_201_CREATED)
async def api_cadastro(cpf: str):
    """Cadastra cpf"""
    student_path = path_from_cpf(cpf)
    if await file_exist(student_path):
        raise HTTPException(status_code=404, detail="Estudante ja cadastrado")

    student = Aluno(turma="X")
    cnt = await file_count_files_in_dir(ALUNO_DIR)

    turma = ordem_turmas[cnt % len(ordem_turmas)]

    turno_path = (
        MATUTINO_FILE_PATH
        if turma in matutino
        else VESPERTINO_FILE_PATH
    )

    turno = Turno.from_string(await file_read(turno_path))
    t_idx = -1
    for idx, t in enumerate(turno.turmas):
        if t.name == turma:
            t_idx  = idx

    turno.turmas[t_idx].verde += 1
    await file_write(student_path, student.to_string())
    await file_write(turno_path, turno.to_string())

@app.websocket("/ws/matricula/{cpf}")
async def ws_matricula(websocket: WebSocket, cpf: str):
    student_path = path_from_cpf(cpf)
    if not await file_exist(student_path):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="CPF nao foi cadastrado")

    student = Aluno.from_string(await file_read(student_path))
    if student.turma != "X":
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="CPF ja foi matriculado")

    client_connection = ClientConnection(socket=websocket, cpf=cpf)
    await manager.connect(client_connection)
    try:
        while True:
            data = await websocket.receive_text()

            student = Aluno.from_string(await file_read(student_path))
            if student.turma != "X":
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="CPF ja foi matriculado")

            if data == "turno":
                await manager.matricula_turno(client_connection)
            elif data == "matutino":
                await manager.matricula_matutino(client_connection)
            elif data == "vespertino":
                await manager.matricula_vespertino(client_connection)
            elif data.startswith("turma:"):
                _, turma = data.split(":")
                await manager.matricula_turma(client_connection, turma.strip())
            else:
                await manager.command_not_found(client_connection, data)

    except WebSocketDisconnect:
        await manager.disconnect(client_connection)
