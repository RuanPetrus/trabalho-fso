import os

matutino   = ["A", "B", "C", "D"]
vespertino = ["E", "F", "G", "H"]
ordem_turmas = ["A", "B", "C", "D",
                "E", "F", "G", "H"]

TURMA_CHOOSE_TIME = 60
TURNO_CHOOSE_TIME = 60

SEP = os.path.sep
DIR_PATH = os.path.dirname(os.path.realpath(__file__)) + SEP
DATA_DIR = DIR_PATH + "data" + SEP
ALUNO_DIR = DATA_DIR + "aluno" + SEP


MATUTINO_FILE_PATH = DATA_DIR + "matutino"
VESPERTINO_FILE_PATH = DATA_DIR + "vespertino"
