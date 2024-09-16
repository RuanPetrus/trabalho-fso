from __future__ import annotations

from config import MATUTINO_FILE_PATH, VESPERTINO_FILE_PATH
from utils import file_read
from dataclasses import dataclass

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
