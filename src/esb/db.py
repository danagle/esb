"""
SPDX-FileCopyrightText: 2024-present Luiz Eduardo Amaral <luizamaral306@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later

Script your way to rescue Christmas as part of the ElfScript Brigade team.

`info` is a CLI tool to help us _elves_ to store christmas for the
[Advent Of Code](https://adventofcode.com/) yearly events
(Thank you [Eric 😉!](https://twitter.com/ericwastl)).
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from esb.config import ESBConfig
from esb.protocol.fireplacev1_0 import MetricPrefix

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Any, ClassVar, Self

    from esb.protocol.fireplacev1_0 import FPPart


@dataclass
class SqlConnection:
    """
    Sql Connection singleton

    Initializes once with an optional
    """

    db_path: Path
    con: sqlite3.Connection = field(init=False, hash=False, repr=False)
    cur: sqlite3.Cursor = field(init=False, hash=False, repr=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __post_init__(self):
        self.con = sqlite3.connect(self.db_path)
        self.cur = self.con.cursor()

    def close(self):
        self.con.commit()
        self.cur.close()
        if hasattr(self, "db_path"):
            delattr(self, "db_path")

    def list_all_tables(self) -> list[tuple[str, ...]]:
        return [table for (table,) in self.cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


@dataclass(init=False)
class Table:
    """
    Base Table Class

    This class depends on an SqlConnection as
    """

    _sql: SqlConnection = field(init=False, hash=False, repr=False)
    _bound: bool = field(init=False, hash=False, repr=False)
    _columns: set[str] = field(init=False, hash=False, repr=False)

    def __post_init__(self):
        self._columns = set(self.__annotations__.keys())

    def to_dict(self) -> dict[str, Any]:
        return {column: getattr(self, column, None) for column in self._columns}

    @classmethod
    def bind_connection(cls, sql: SqlConnection):
        cls._sql = sql
        cls._bound = True

    @classmethod
    def disconnect(cls):
        if hasattr(cls, "_sql"):
            delattr(cls, "_sql")
            delattr(cls, "_bound")

    @classmethod
    def build_class(cls, row: tuple) -> Self:
        return cls(**dict(zip(cls.__annotations__.keys(), row)))

    @staticmethod
    def check_connection(fn):
        def wrapper(cls, *args, **kwargs):
            if not hasattr(cls, "_bound"):
                message = "Table not bound to any SqlConnection. Call 'bind_connection' before using table"
                raise ValueError(message)
            return fn(cls, *args, **kwargs)

        return wrapper

    @staticmethod
    def non_empty_dictionary(arg):
        if len(arg) == 0:
            message = "find received an empty dictionary"
            raise ValueError(message)

    @staticmethod
    def query_named_placeholders(values: dict[str, Any], sep: str = ", ") -> str:
        return sep.join(f"{column} = :{column}" for column in values)

    @staticmethod
    def query_insert_placeholders(values: dict[str, Any]) -> tuple[str, str]:
        insert_columns = ", ".join(values.keys())
        insert_placeholders = ", ".join([f":{column}" for column in values])
        return insert_columns, insert_placeholders

    #######################################################
    # SQL operations
    #######################################################
    @classmethod
    @check_connection
    def fetch_all(cls) -> Iterator[Self]:
        query = f"SELECT * FROM {cls.__name__}"  # noqa: S608
        cls._sql.cur.execute(query)
        for row in cls._sql.cur.fetchall():
            yield cls.build_class(row)

    @classmethod
    @check_connection
    def fetch_one(cls) -> Self | None:
        query = f"SELECT * FROM {cls.__name__} LIMIT 1"  # noqa: S608
        cls._sql.cur.execute(query)
        row = cls._sql.cur.fetchone()
        if row is None:
            return None
        return cls.build_class(row)

    @classmethod
    @check_connection
    def fetch_single(cls) -> Self:
        rows = list(cls.fetch_all())
        if len(rows) != 1:
            message = f"Table {cls.__name__} should have one row and one row only. Got {rows}. Something is wrong."
            raise RuntimeError(message)
        return rows[0]

    @classmethod
    @check_connection
    def find(cls, match: dict) -> Iterator[Self]:
        cls.non_empty_dictionary(match)
        where_params = cls.query_named_placeholders(match, sep=" AND ")
        query = f"SELECT * FROM {cls.__name__} WHERE {where_params}"  # noqa: S608
        cls._sql.cur.execute(query, match)
        for row in cls._sql.cur.fetchall():
            yield cls.build_class(row)

    @classmethod
    @check_connection
    def find_one(cls, match: dict) -> Self | None:
        cls.non_empty_dictionary(match)
        where_params = cls.query_named_placeholders(match, sep=" AND ")
        query = f"SELECT * FROM {cls.__name__} WHERE {where_params} LIMIT 1"  # noqa: S608
        cls._sql.cur.execute(query, match)
        match cls._sql.cur.fetchone():
            case None:
                return None
            case row:
                return cls.build_class(row)

    @classmethod
    @check_connection
    def find_single(cls, match: dict) -> Self | None:
        rows = list(cls.find(match))
        match len(rows):
            case 0:
                return None
            case 1:
                return rows[0]
            case _:
                message = f"Table {cls.__name__} should have found one or zero rows. Got {rows}. Something is wrong."
                raise RuntimeError(message)

    @check_connection
    def insert(self, *, replace=False):
        d = self.to_dict()
        ins_cols, ins_plac = self.query_insert_placeholders(d)
        query = (
            f"INSERT INTO {self.__class__.__name__} ({ins_cols}) VALUES ({ins_plac})"  # noqa: S608
            if not replace
            else f"INSERT OR REPLACE INTO {self.__class__.__name__} ({ins_cols}) VALUES ({ins_plac})"  # noqa: S608
        )
        self._sql.cur.execute(query, d)
        self._sql.con.commit()
        return self

    @check_connection
    def update(self, key: dict):
        d = self.to_dict() | key
        where_values = {k: v for k, v in d.items() if k not in key}

        where_params = self.query_named_placeholders(where_values, sep=" AND ")
        set_params = self.query_named_placeholders(key, sep=", ")

        query = f"UPDATE {self.__class__.__name__} SET {set_params} WHERE {where_params}"  # noqa: S608
        self._sql.cur.execute(query, d)
        self._sql.con.commit()


###########################################################
# Main DB Interface
###########################################################
@dataclass(unsafe_hash=True)
class ECABrigadista(Table):
    brigadista_id: str
    creation_date: datetime


@dataclass(unsafe_hash=True)
class ECASolution(Table):
    year: int
    day: int
    pt1_answer: str | None
    pt2_answer: str | None

    def get_answer(self, part: FPPart):
        match part:
            case 1:
                return self.pt1_answer
            case 2:
                return self.pt2_answer
            case _:
                message = f"Part {part} does not exist"
                raise KeyError(message)


@dataclass(unsafe_hash=True)
class ECAProblem(Table):
    year: int
    day: int
    title: str
    url: str


@dataclass(unsafe_hash=True)
class ECALanguage(Table):
    year: int
    day: int
    language: str
    started: bool
    finished_pt1: bool
    finished_pt2: bool

    def __post_init__(self):
        super().__post_init__()
        self.started = bool(self.started)
        self.finished_pt1 = bool(self.finished_pt1)
        self.finished_pt2 = bool(self.finished_pt2)

    def set_solved(self, part: FPPart):
        self.update({f"finished_pt{part}": True})

    def set_unsolved(self, part: FPPart):
        self.update({f"finished_pt{part}": False})


@dataclass(unsafe_hash=True)
class ECARun(Table):
    id: int | None  # noqa: A003
    datetime: datetime
    year: int
    day: int
    language: str
    part: FPPart
    answer: str | None = None
    time: int | None = None
    unit: MetricPrefix | None = None

    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.unit, int):
            self.unit = MetricPrefix(self.unit)


class ElvenCrisisArchive:
    repo_root: Path
    db_path: Path

    tables: ClassVar[dict[type[Table], str]] = {
        ECABrigadista: """CREATE TABLE {table_name} (
                                brigadista_id CHARACTER(36),
                                creation_date TIMESTAMP NOT NULL
                            )""",
        ECAProblem: """CREATE TABLE {table_name} (
                                year INTEGER NOT NULL,
                                day INTEGER NOT NULL,
                                title TEXT,
                                url TEXT,
                                PRIMARY KEY (year, day)
                            )""",
        ECASolution: """CREATE TABLE {table_name} (
                                year INTEGER NOT NULL,
                                day INTEGER NOT NULL,
                                pt1_answer TEXT,
                                pt2_answer TEXT,
                                PRIMARY KEY (year, day)
                            )""",
        ECALanguage: """CREATE TABLE {table_name} (
                                year INTEGER NOT NULL,
                                day INTEGER NOT NULL,
                                language TEXT NOT NULL,
                                started INT,
                                finished_pt1 INT,
                                finished_pt2 INT,
                                PRIMARY KEY (year, day, language)
                            )""",
        ECARun: """CREATE TABLE {table_name} (
                                id INTEGER PRIMARY KEY NOT NULL,
                                datetime TIMESTAMP NOT NULL,
                                year INTEGER NOT NULL,
                                day INTEGER NOT NULL,
                                language TEXT NOT NULL,
                                part INTEGER NOT NULL,
                                answer TEXT,
                                time INTEGER,
                                unit INTEGER
                            )""",
    }
    ECABrigadista = ECABrigadista
    ECAProblem = ECAProblem
    ECASolution = ECASolution
    ECALanguage = ECALanguage
    ECARun = ECARun

    def __init__(self, repo_root: Path):
        sqlite3.register_adapter(MetricPrefix, lambda mp: mp.value)
        self.repo_root = repo_root
        self.db_path = repo_root / ESBConfig.db_path
        if not self.db_path.parent.is_dir():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path.touch()
        self.sql = SqlConnection(self.db_path)
        for table in self.tables:
            table.bind_connection(self.sql)

    def create_tables(self):
        for table, create_table_query in self.tables.items():
            self.sql.cur.execute(create_table_query.format(table_name=table.__name__))

    def new_brigadista(self):
        self.ECABrigadista(brigadista_id=str(uuid.uuid4()), creation_date=datetime.now().astimezone()).insert()

    def new_repo(self):
        self.create_tables()
        self.new_brigadista()
