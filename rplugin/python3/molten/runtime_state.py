from enum import Enum


class RuntimeState(Enum):
    FAILED = -1
    STARTING = 0
    IDLE = 1
    RUNNING = 2
