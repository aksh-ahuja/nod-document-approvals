from dataclasses import dataclass
from typing import Any


@dataclass
class GenericFuncResp:
    success: bool
    message: str = ''
    data: Any = None
    status_code: int = 200
