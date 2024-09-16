from __future__ import annotations
from enum import Enum

from fastapi import FastAPI, HTTPException, WebSocketException, WebSocket, status, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio, aiofiles, aiofiles.os, os 

TURMA_CHOOSE_TIME = 60
TURNO_CHOOSE_TIME = 60

SEP = os.path.sep
DIR_PATH = os.path.dirname(os.path.realpath(__file__)) + SEP
DATA_DIR = DIR_PATH + "data" + SEP
ALUNO_DIR = DATA_DIR + "aluno" + SEP


MATUTINO_FILE_PATH = DATA_DIR + "matutino"
VESPERTINO_FILE_PATH = DATA_DIR + "vespertino"


matutino   = ["A", "B", "C", "D"]
vespertino = ["E", "F", "G", "H"]
ordem_turmas = ["A", "B", "C", "D",
                "E", "F", "G", "H"]

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
    "http://localhost:*",
]

app.add_middleware (
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@dataclass
class Aluno:
    turma: str

    @staticmethod
    def from_string(content: str) -> Aluno:
        lines = content.split()
        assert(len(lines) == 1)
        return Aluno(
            turma = lines[0],
        )

    def to_string(self) -> str:
        return f"""{self.turma}"""

@dataclass
class Turma:
    name: str
    verde: int
    vermelho: int

    @staticmethod
    def from_string(content: str) -> Turma:
        [name, verde, vermelho] = content.split()
        return Turma(name=name, verde=int(verde), vermelho=int(vermelho))

    def to_string(self) -> str:
        return f"{self.name} {self.verde} {self.vermelho}"

@dataclass
class Turno:
    turmas: list[Turma]

    @staticmethod
    def from_string(content: str) -> Turno:
        return Turno(turmas=[
            Turma.from_string(line) for line in content.split("\n")    
        ])

    def to_string(self) -> str:
        return "\n".join([t.to_string() for t in self.turmas])



async def file_read(path: str) -> str:
    async with aiofiles.open(path, mode='r') as f:
        contents = await f.read()
    return contents

async def file_write(path: str, content: str):
    async with aiofiles.open(path, mode='w') as f:
        await f.write(content)

async def file_exist(path: str):
    return await aiofiles.os.path.isfile(path)

async def file_count_files_in_dir(path: str) -> int:
    files = await aiofiles.os.listdir(path)
    return len(files)

def path_from_cpf(cpf: str) -> str:
    return ALUNO_DIR + cpf

async def get_turnos_capacity() -> int:
    def cnt_capacity(turno: Turno) -> int:
        sum = 0
        for t in turno.turmas:
            sum += t.verde
        return sum
    cap_mat = cnt_capacity(Turno.from_string(await file_read(MATUTINO_FILE_PATH)))
    cap_vesp = cnt_capacity(Turno.from_string(await file_read(VESPERTINO_FILE_PATH)))
    if cap_mat == 0 and cap_vesp == 0: return 0
    elif cap_mat == 0 : return cap_vesp
    elif cap_vesp == 0: return cap_mat

    return min(cap_mat, cap_vesp)

def get_turno_capacity(turno: Turno) -> int:
    values = [t.verde for t in turno.turmas if t.verde != 0]
    if len(values) == 0: return 0
    cap = values[0]
    for c in values: cap = min(cap, c)
    return cap


async def get_matutino_capacity() -> int:
    return get_turno_capacity(Turno.from_string(await file_read(MATUTINO_FILE_PATH)))

async def get_vespertino_capacity() -> int:
    return get_turno_capacity(Turno.from_string(await file_read(VESPERTINO_FILE_PATH)))

async def matricula_aluno(cpf: str, turma: str) -> bool:
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

    if turno.turmas[t_idx].verde == 0:
        return False

    turno.turmas[t_idx].verde -= 1
    turno.turmas[t_idx].vermelho += 1
    student = Aluno(turma=turma)
    student_path = path_from_cpf(cpf)
    await file_write(student_path, student.to_string())
    await file_write(turno_path, turno.to_string())
    return True

class AlunoStatus(Enum):
    WAITING = 0
    CHOOSING = 1

@dataclass
class ClientConnection:
    socket: WebSocket
    cpf: str

    def __hash__(self):
        return hash(self.cpf)

class TurnoManager:
    def __init__(self, choose_time: int, get_capacity_fn):
        self.queue = asyncio.Queue()
        self.status: dict[ClientConnection, AlunoStatus] = {}
        self.stop_status = {}
        self.choosing = 0
        self.choose_time = choose_time
        self.get_capacity = get_capacity_fn

    async def add(self, client_connection: ClientConnection):
        self.status[client_connection] = AlunoStatus.WAITING
        self.queue.put_nowait(client_connection)
        await client_connection.socket.send_text("ok")
        asyncio.create_task(self.check())
        self.add_client_remove_status(client_connection)
        asyncio.create_task(self.remove_after_time(client_connection, self.choose_time))

    async def remove(self, client_connection: ClientConnection):
        if client_connection in self.status:
            if self.status[client_connection] == AlunoStatus.CHOOSING:
                self.choosing -= 1
            self.status.pop(client_connection)
            try:
                await client_connection.socket.send_text("remove")
            except Exception:
                pass

        asyncio.create_task(self.check())

    def is_choosing(self, client_connection: ClientConnection):
        return (client_connection in self.status) and (self.status[client_connection] == AlunoStatus.CHOOSING)

    def add_client_remove_status(self, client_connection: ClientConnection):
        if client_connection in self.stop_status:
            self.stop_status[client_connection] += 1
        else:
            self.stop_status[client_connection] = 1

    async def remove_after_time(self, client_connection: ClientConnection, time: int):
        await asyncio.sleep(time)
        self.stop_status[client_connection] -= 1
        if self.stop_status[client_connection] == 0:
            self.stop_status.pop(client_connection)
            await self.remove(client_connection)

    async def check(self):
        while(self.choosing < await self.get_capacity() and not self.queue.empty()):
            self.choosing += 1
            client = await self.queue.get()
            self.status[client] = AlunoStatus.CHOOSING
            await client.socket.send_text("vez")

class ConnectionManager:
    def __init__(self):
        self.matutino = TurnoManager(TURMA_CHOOSE_TIME, get_matutino_capacity)
        self.vespertino = TurnoManager(TURMA_CHOOSE_TIME, get_vespertino_capacity)
        self.turno = TurnoManager(TURNO_CHOOSE_TIME, get_turnos_capacity)

    async def connect(self, client_connection: ClientConnection):
        await client_connection.socket.accept()

    async def disconnect(self, client_connection: ClientConnection):
        await self.turno.remove(client_connection)
        await self.matutino.remove(client_connection)
        await self.vespertino.remove(client_connection)

    async def matricula_turno(self, client_connection: ClientConnection):
        if client_connection in self.turno.status:
            await client_connection.socket.send_text("error: cpf ja esta na fila de turnos")
            return
        elif client_connection in self.matutino.status or client_connection in self.vespertino.status:
            await client_connection.socket.send_text("error: cpf ja esta na fila outro turno")
            return

        await self.turno.add(client_connection)

    async def matricula_matutino(self, client_connection: ClientConnection):
        if await get_matutino_capacity() == 0:
            await client_connection.socket.send_text("error: turno cheio")
            return

        if not self.turno.is_choosing(client_connection):
            await client_connection.socket.send_text("error: nao esta na sua vez")
            return

        if client_connection in self.matutino.status or client_connection in self.vespertino.status:
            await client_connection.socket.send_text("error: cpf ja esta na fila de outro turno")
            return

        self.turno.add_client_remove_status(client_connection)
        asyncio.create_task(self.turno.remove_after_time(client_connection, self.matutino.choose_time))
        await self.matutino.add(client_connection)

    async def matricula_vespertino(self, client_connection: ClientConnection):
        if await get_vespertino_capacity() == 0:
            await client_connection.socket.send_text("error: turno cheio")
            return

        if (not client_connection in self.turno.status) or (self.turno.status[client_connection] != AlunoStatus.CHOOSING):
            await client_connection.socket.send_text("error: nao esta na sua vez")
            return

        if client_connection in self.matutino.status or client_connection in self.vespertino.status:
            await client_connection.socket.send_text("error: cpf ja esta na fila de outro turno")
            return

        turno.add_client_remove_status(client_connection)
        asyncio.create_task(self.turno.remove_after_time(client_connection, self.vespertino.choose_time))
        await self.vespertino.add(client_connection)

    async def matricula_turma(self, client_connection: ClientConnection, turma: str):
        if turma in matutino:
            if not self.matutino.is_choosing(client_connection):
                await client_connection.socket.send_text("error: nao esta na sua vez")
                return

            if not await matricula_aluno(client_connection.cpf, turma):
                await client_connection.socket.send_text("error: turma cheia")
                return

            await client_connection.socket.send_text("ok")
            await self.turno.remove(client_connection)
            await self.matutino.remove(client_connection)
            await self.vespertino.remove(client_connection)

        elif turma in vespertino:
            if not self.vespertino.is_choosing(client_connection):
                await client_connection.socket.send_text("error: nao esta na sua vez")
                return

            if not await matricula_aluno(client_connection.cpf, turma):
                await client_connection.socket.send_text("error: turma cheia")
                return
                                
            await client_connection.socket.send_text("ok")
            await self.turno.remove(client_connection)
            await self.matutino.remove(client_connection)
            await self.vespertino.remove(client_connection)

        else:
            await client_connection.socket.send_text("error: turma invalida")
            return

    async def command_not_found(self, client_connection: ClientConnection, command: str):
        await client_connection.socket.send_text(f"error: command not found {command}")

manager = ConnectionManager()

@app.get("/{cpf}")
async def get_root(cpf: str):
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
    turno = Turno.from_string(await file_read(MATUTINO_FILE_PATH))
    vagas = {}
    for idx, t in enumerate(turno.turmas):
        vagas[chr(ord("A")+idx)] = t.verde

    return vagas

@app.get("/api/vagas/vespertino")
async def api_vagas_vespertino():
    turno = Turno.from_string(await file_read(VESPERTINO_FILE_PATH))
    vagas = {}
    for idx, t in enumerate(turno.turmas):
        vagas[chr(ord("E")+idx)] = t.verde

    return vagas


@app.post("/api/cadastro/{cpf}", status_code=status.HTTP_201_CREATED)
async def api_cadastro(cpf: str):
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
