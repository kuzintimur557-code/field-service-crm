import re
from collections.abc import Mapping


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class HybridRow(Mapping):
    """PostgreSQL row with the two access modes used by sqlite3.Row."""

    def __init__(self, columns, values):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._positions = {
            column: index for index, column in enumerate(self._columns)
        }

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._values[self._positions[key]]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)

    def keys(self):
        return self._columns


def hybrid_row_factory(cursor):
    columns = [
        column.name if hasattr(column, "name") else column[0]
        for column in (cursor.description or ())
    ]

    def make_row(values):
        return HybridRow(columns, values)

    return make_row


def validate_identifier(value):
    identifier = str(value or "")
    if not _IDENTIFIER.fullmatch(identifier):
        raise ValueError("Invalid SQL identifier")
    return identifier


def _translate_placeholders(query, has_parameters):
    if not has_parameters:
        return query

    result = []
    index = 0
    state = "normal"
    while index < len(query):
        char = query[index]
        following = query[index + 1] if index + 1 < len(query) else ""

        if state == "normal":
            if char == "'":
                state = "single"
                result.append(char)
            elif char == '"':
                state = "double"
                result.append(char)
            elif char == "-" and following == "-":
                state = "line_comment"
                result.extend((char, following))
                index += 1
            elif char == "/" and following == "*":
                state = "block_comment"
                result.extend((char, following))
                index += 1
            elif char == "?":
                result.append("%s")
            elif char == "%":
                result.append("%%")
            else:
                result.append(char)
        elif state == "single":
            result.append("%%" if char == "%" else char)
            if char == "'" and following == "'":
                result.append(following)
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "double":
            result.append("%%" if char == "%" else char)
            if char == '"' and following == '"':
                result.append(following)
                index += 1
            elif char == '"':
                state = "normal"
        elif state == "line_comment":
            result.append(char)
            if char == "\n":
                state = "normal"
        else:
            result.append(char)
            if char == "*" and following == "/":
                result.append(following)
                index += 1
                state = "normal"
        index += 1
    return "".join(result)


def translate_sqlite_sql(query, has_parameters=False):
    translated = str(query)
    table_info = re.fullmatch(
        r"\s*PRAGMA\s+table_info\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?\s*",
        translated,
        flags=re.IGNORECASE,
    )
    if table_info:
        table = validate_identifier(table_info.group(1))
        return (
            "SELECT column_name AS name "
            "FROM information_schema.columns "
            "WHERE table_schema=CURRENT_SCHEMA() "
            f"AND table_name='{table}' "
            "ORDER BY ordinal_position"
        )

    sqlite_catalog = """(
        SELECT table_name AS name, 'table' AS type
        FROM information_schema.tables
        WHERE table_schema=CURRENT_SCHEMA()
          AND table_type='BASE TABLE'
        UNION ALL
        SELECT indexname AS name, 'index' AS type
        FROM pg_indexes
        WHERE schemaname=CURRENT_SCHEMA()
    ) AS sqlite_master"""
    translated = re.sub(
        r"\bsqlite_master\b",
        sqlite_catalog,
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bBEGIN\s+IMMEDIATE\b",
        "BEGIN",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\b",
        "BIGSERIAL PRIMARY KEY",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bdate\s*\(\s*'now'\s*\)",
        "TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\s*\(\s*'now'\s*,\s*'([+-]?\d+)\s+days?'\s*\)",
        lambda match: (
            "(CURRENT_TIMESTAMP + INTERVAL "
            f"'{int(match.group(1))} days')"
        ),
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*"
        r"'\+'\s*\|\|\s*\?\s*\|\|\s*'\s*minutes?'\s*\)",
        (
            r"TO_CHAR((\1)::timestamp + ((?)::integer * INTERVAL '1 minute'), "
            r"'YYYY-MM-DD HH24:MI:SS')"
        ),
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)",
        r"(\1)::timestamp",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"GROUP_CONCAT\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)",
        r"STRING_AGG((\1)::text, ',')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"CAST\s*\(\s*REPLACE\s*\(\s*COALESCE\s*\(\s*"
        r"([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*'0'\s*\)\s*,\s*','\s*,\s*"
        r"'\.'\s*\)\s+AS\s+REAL\s*\)",
        (
            r"CAST(NULLIF(REPLACE(COALESCE((\1)::text, '0'), ',', '.'), '') "
            r"AS DOUBLE PRECISION)"
        ),
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\b(SUM|AVG)\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)",
        (
            r"\1(CAST(NULLIF(REPLACE((\2)::text, ',', '.'), '') "
            r"AS DOUBLE PRECISION))"
        ),
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\?\s+IS\s+(NOT\s+)?NULL",
        lambda match: (
            "CAST(? AS TEXT) IS "
            f"{'NOT ' if match.group(1) else ''}NULL"
        ),
        translated,
        flags=re.IGNORECASE,
    )

    ignore_insert = bool(re.search(
        r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b",
        translated,
        flags=re.IGNORECASE,
    ))
    if ignore_insert:
        translated = re.sub(
            r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\b",
            r"\1INSERT INTO",
            translated,
            count=1,
            flags=re.IGNORECASE,
        )
        stripped = translated.rstrip()
        suffix = ";" if stripped.endswith(";") else ""
        translated = stripped.removesuffix(";") + " ON CONFLICT DO NOTHING" + suffix

    return _translate_placeholders(translated, has_parameters)


class PostgresCursorAdapter:
    backend = "postgresql"

    def __init__(self, connection, cursor):
        self._connection = connection
        self._cursor = cursor
        self._insert_executed = False
        self._lastrowid = None

    def execute(self, query, parameters=None):
        translated = translate_sqlite_sql(
            query,
            has_parameters=parameters is not None,
        )
        self._insert_executed = bool(re.match(
            r"^\s*INSERT\b",
            translated,
            flags=re.IGNORECASE,
        ))
        self._lastrowid = None
        if parameters is None:
            self._cursor.execute(translated)
        else:
            self._cursor.execute(translated, parameters)
        return self

    def executemany(self, query, parameters):
        translated = translate_sqlite_sql(query, has_parameters=True)
        self._insert_executed = bool(re.match(
            r"^\s*INSERT\b",
            translated,
            flags=re.IGNORECASE,
        ))
        self._lastrowid = None
        self._cursor.executemany(translated, parameters)
        return self

    @property
    def lastrowid(self):
        if not self._insert_executed:
            return None
        if self._lastrowid is None:
            cursor = self._connection._raw.cursor()
            try:
                cursor.execute("SELECT LASTVAL()")
                row = cursor.fetchone()
                self._lastrowid = row[0] if row else None
            finally:
                cursor.close()
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, size=1):
        return self._cursor.fetchmany(size)

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnectionAdapter:
    backend = "postgresql"

    def __init__(self, connection):
        self._raw = connection

    def cursor(self):
        return PostgresCursorAdapter(self, self._raw.cursor())

    def execute(self, query, parameters=None):
        return self.cursor().execute(query, parameters)

    def executemany(self, query, parameters):
        return self.cursor().executemany(query, parameters)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False

    def __getattr__(self, name):
        return getattr(self._raw, name)


def connect_postgres(database_url):
    import psycopg

    connection = psycopg.connect(
        database_url,
        row_factory=hybrid_row_factory,
    )
    return PostgresConnectionAdapter(connection)
