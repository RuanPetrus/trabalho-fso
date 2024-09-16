from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from fastapi import WebSocket
import asyncio
from typing import Callable

from config import MATUTINO_FILE_PATH, VESPERTINO_FILE_PATH, TURNO_CHOOSE_TIME, TURMA_CHOOSE_TIME, matutino, vespertino
from utils import file_read, file_write, path_from_cpf
from model import Turno, Aluno, get_matutino_capacity, get_vespertino_capacity, get_turnos_capacity


class AlunoStatus(Enum):
    WAITING = 0
    CHOOSING = 1

@dataclass
class ClientConnection:
    socket: WebSocket
    cpf: str

    def __hash__(self):
        return hash(self.cpf)

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


class TurnoManager:
    def __init__(self, choose_time: int, get_capacity_fn: Callable[[], int], parent_turno: TurnoManager | None = None):
        self.queue: asyncio.Queue[ClientConnection] = asyncio.Queue()
        self.status: dict[ClientConnection, AlunoStatus] = {}
        self.stop_status: dict[ClientConnection, int] = {}
        self.choosing = 0
        self.choose_time = choose_time
        self.get_capacity = get_capacity_fn
        self.parent_turno = parent_turno

    async def add(self, client_connection: ClientConnection):
        self.status[client_connection] = AlunoStatus.WAITING
        self.queue.put_nowait(client_connection)
        await client_connection.socket.send_text("ok")
        asyncio.create_task(self.check())

    async def remove(self, client_connection: ClientConnection):
        if client_connection in self.status:
            if self.status[client_connection] == AlunoStatus.CHOOSING:
                self.choosing -= 1
            self.status.pop(client_connection)

            if self.parent_turno is not None:
                await self.parent_turno.remove(client_connection)

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

            self.add_client_remove_status(client)
            asyncio.create_task(self.remove_after_time(client, self.choose_time))

            await client.socket.send_text("vez")

class ConnectionManager:
    def __init__(self):
        self.turno = TurnoManager(TURNO_CHOOSE_TIME, get_turnos_capacity)
        self.matutino = TurnoManager(TURMA_CHOOSE_TIME, get_matutino_capacity, self.turno)
        self.vespertino = TurnoManager(TURMA_CHOOSE_TIME, get_vespertino_capacity, self.turno)

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

        self.turno.add_client_remove_status(client_connection)
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
