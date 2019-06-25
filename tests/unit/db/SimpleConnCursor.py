# -*- coding: utf-8 -*-
from asyncy.db.SimpleConnCursor import SimpleConnCursor

from psycopg2.extras import RealDictCursor

import pytest


def test_simple(magic):
    conn = magic()
    with SimpleConnCursor(conn) as db:
        assert db.conn == conn
        conn.cursor.assert_called_with(cursor_factory=RealDictCursor)
        assert db.cur == conn.cursor()

    conn.cursor().close.assert_called_once()
    conn.close.assert_called_once()


def test_close_on_error(magic):
    conn = magic()
    with pytest.raises(Exception):
        try:
            with SimpleConnCursor(conn):
                raise Exception('test exception')
        finally:
            conn.cursor().close.assert_called_once()
            conn.close.assert_called_once()
