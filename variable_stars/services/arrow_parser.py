"""
arrow_parser.py - Utility per parsing Apache Arrow IPC stream

Funzioni helper per conversione:
- Request Flask → Arrow Table
- Python data → Arrow Table → IPC stream
"""

import pyarrow as pa
import pyarrow.ipc as ipc
from flask import request


def read_arrow_table_from_request() -> pa.Table:
    """
    Legge tabella Arrow da body della richiesta POST.

    Utility per endpoint che accettano Arrow IPC stream come input.

    Returns:
        pa.Table: Tabella Arrow deserializzata

    Raises:
        ValueError: Se body vuoto o formato non valido
    """
    raw = request.get_data(cache=False)  # Leggi bytes raw

    if not raw:
        raise ValueError("Body richiesta vuoto")

    # Deserializza Arrow IPC stream
    reader = ipc.open_stream(pa.BufferReader(raw))
    return reader.read_all()


def create_arrow_response(table: pa.Table, mimetype: str = "application/vnd.apache.arrow.stream") -> bytes:
    """
    Crea response Arrow IPC stream da tabella PyArrow.

    Args:
        table: Tabella PyArrow da serializzare
        mimetype: MIME type per response (default: Arrow stream)

    Returns:
        bytes: Buffer serializzato pronto per Response Flask
    """
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    buf = sink.getvalue()
    return buf.to_pybytes()
