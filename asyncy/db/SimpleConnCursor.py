# -*- coding: utf-8 -*-
from collections import namedtuple

from psycopg2.extras import RealDictCursor

ConnAndCursor = namedtuple('ConnAndCursor', ['conn', 'cur'])


class SimpleConnCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self) -> ConnAndCursor:
        self.cur = self.conn.cursor(cursor_factory=RealDictCursor)
        return ConnAndCursor(conn=self.conn, cur=self.cur)

    def __exit__(self, exc_type, exc_value, traceback):
        self.cur.close()
        self.conn.close()
