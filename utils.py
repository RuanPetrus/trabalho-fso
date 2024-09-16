import aiofiles, aiofiles.os
from config import ALUNO_DIR

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
