"""
SPDX-FileCopyrightText: 2024-present Luiz Eduardo Amaral <luizamaral306@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later

ESB - Script your way to rescue Christmas as part of the ElfScript Brigade team.

`esb` is a CLI tool to help us _elves_ to save christmas for the
[Advent Of Code](https://adventofcode.com/) yearly events
(Thank you [Eric 😉!](https://twitter.com/ericwastl)).
"""

from dataclasses import dataclass, replace

import pytest

from esb import db
from tests.lib.temporary import TestWithTemporaryDirectory


class TestSqlConnection(TestWithTemporaryDirectory):
    db_path: str = "my_test.sqlite"

    def test_context_manager(self):
        with db.SqlConnection(self.db_path) as sql:
            sql.cur.execute("CREATE TABLE ctx_man (value)")
            sql.con.commit()
            tables_after = sql.list_all_tables()
            assert len(tables_after) == 1

    def test_list_all_tables(self):
        sql = db.SqlConnection(self.db_path)
        tables_before = sql.list_all_tables()
        assert len(tables_before) == 0
        sql.cur.execute("CREATE TABLE list_all_1 (value)")
        sql.cur.execute("CREATE TABLE list_all_2 (value)")
        sql.con.commit()
        tables_after = sql.list_all_tables()
        assert len(tables_after) == 2
        sql.close()

    def test_calling_close_twice_doesnt_raise_an_exception(self):
        sql = db.SqlConnection(self.db_path)
        sql.close()
        sql.close()


class TestTable(TestWithTemporaryDirectory):
    @dataclass(unsafe_hash=True)
    class TestSqlTable(db.Table):
        idx: int
        value: int
        text: str

    db_path: str = "my_test.sqlite"
    row0: TestSqlTable = TestSqlTable(idx=1, value=123, text="abc")
    row1: TestSqlTable = TestSqlTable(idx=2, value=456, text="def")
    row2: TestSqlTable = TestSqlTable(idx=3, value=789, text="ghi")

    def setUp(self):
        super().setUp()
        self.sql = db.SqlConnection(self.db_path)
        self.TestSqlTable.bind_connection(self.sql)
        self.sql.cur.execute("CREATE TABLE TestSqlTable (idx INTEGER NOT NULL PRIMARY KEY, value, text)")
        self.sql.con.commit()

    def test_unbound_table_shoud_raise_exception(self):
        self.TestSqlTable.disconnect()
        with pytest.raises(ValueError, match="Table not bound"):
            self.row0.insert()

    def test_insert(self):
        assert len(list(self.TestSqlTable.fetch_all())) == 0
        self.row0.insert()
        assert len(list(self.TestSqlTable.fetch_all())) == 1
        self.row1.insert()
        assert len(list(self.TestSqlTable.fetch_all())) == 2

    def test_insert_with_replace(self):
        self.row0.insert(replace=True)
        row0_copy = replace(self.row0, value=321)
        row0_copy.insert(replace=True)
        frow0 = self.TestSqlTable.fetch_single()
        assert self.row0 != frow0
        assert row0_copy == frow0

    def test_update(self):
        self.row0.insert(replace=True)
        row0_copy = replace(self.row0, value=321)
        row0_copy.update(key={"idx": self.row0.idx})
        frow0 = self.TestSqlTable.fetch_single()
        assert self.row0 != frow0
        assert row0_copy == frow0

    def test_fetch_all(self):
        self.row0.insert()
        self.row1.insert()
        self.row2.insert()
        assert set(self.TestSqlTable.fetch_all()) == {
            self.row0,
            self.row1,
            self.row2,
        }

    def test_fetch_one(self):
        assert self.TestSqlTable.fetch_one() is None
        self.row0.insert()
        self.row1.insert()
        frow0 = self.TestSqlTable.fetch_one()
        assert frow0 == self.row0
        assert id(frow0) != id(self.row0)

    def test_fetch_single(self):
        self.row0.insert()
        frow0 = self.TestSqlTable.fetch_single()
        assert frow0 == self.row0
        assert id(frow0) != id(self.row0)

    def test_fetch_single_cannot_have_no_rows(self):
        with pytest.raises(RuntimeError, match="should have one row"):
            self.TestSqlTable.fetch_single()

    def test_fetch_single_cannot_have_more_than_one_row(self):
        self.row0.insert()
        self.row1.insert()
        with pytest.raises(RuntimeError, match="should have one row"):
            self.TestSqlTable.fetch_single()

    def test_find_int(self):
        self.row0.insert()
        row0_copy = replace(self.row0, idx=4)
        row0_copy.insert()
        self.row1.insert()

        find0 = list(self.TestSqlTable.find({"value": 123}))
        assert len(find0) == 2
        assert set(find0) == {self.row0, row0_copy}

    def test_find_str(self):
        self.row0.insert()
        row0_copy = replace(self.row0, idx=4)
        row0_copy.insert()
        self.row1.insert()

        find0 = list(self.TestSqlTable.find({"text": "abc"}))
        assert len(find0) == 2
        assert set(find0) == {self.row0, row0_copy}

    def test_find_cannot_pass_empty_dictionary(self):
        with pytest.raises(ValueError, match="empty dictionary"):
            list(self.TestSqlTable.find({}))

    def test_find_one(self):
        self.row0.insert()
        replace(self.row0, idx=4).insert()
        self.row1.insert()

        row0 = self.TestSqlTable.find_one({"text": "abc"})
        assert self.row0 == row0

    def test_find_one_no_match(self):
        self.row0.insert()
        self.row1.insert()

        row0 = self.TestSqlTable.find_one({"text": "no-match"})
        assert row0 is None

    def test_find_one_cannot_pass_empty_dictionary(self):
        with pytest.raises(ValueError, match="empty dictionary"):
            self.TestSqlTable.find_one({})

    def test_find_single(self):
        self.row0.insert()
        self.row1.insert()

        row0 = self.TestSqlTable.find_single({"text": "abc"})
        assert self.row0 == row0

    def test_find_single_no_match(self):
        self.row0.insert()
        self.row1.insert()

        row0 = self.TestSqlTable.find_single({"text": "no-match"})
        assert row0 is None

    def test_find_single_cannot_pass_empty_dictionary(self):
        with pytest.raises(ValueError, match="empty dictionary"):
            self.TestSqlTable.find_single({})

    def test_find_single_cannot_have_more_than_one_row(self):
        self.row0.insert()
        replace(self.row0, idx=4).insert()
        with pytest.raises(RuntimeError, match="should have found one or zero rows"):
            self.TestSqlTable.find_single({"text": "abc"})


class TestElvenCrisisArchive(TestWithTemporaryDirectory):
    def setUp(self):
        super().setUp()
        db.Table.disconnect()

    def test_has_db(self):
        assert db.ElvenCrisisArchive.has_db() is False
        db.ElvenCrisisArchive()
        assert db.ElvenCrisisArchive.has_db() is True

    def test_create_tables(self):
        archive = db.ElvenCrisisArchive()
        archive.create_tables()
        assert len(archive.sql.list_all_tables()) > 0
