from abc import ABC, abstractmethod
import re


# =========================
# QUERY (IR)
# =========================

class Query:
    def __init__(self, select, table, filters):
        self.select = select
        self.table = table
        self.filters = filters  # (field, op, value)


class Filter:
    pass

class Condition(Filter):
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value

class And(Filter):
    def __init__(self, left, right):
        self.left = left
        self.right = right

class Or(Filter):
    def __init__(self, left, right):
        self.left = left
        self.right = right
        

# =========================
# PARSER (VERY BASIC)
# =========================

class QueryParser:

    def parse(self, sql: str) -> Query:
        # Example:
        # SELECT name FROM users WHERE age > 25

        sql = sql.strip().lower()

        select_match = re.search(r"select (.*?) from", sql)
        print(select_match)
        table_match = re.search(r"from (\w+)", sql)
        print(table_match)
        where_match = re.search(r"where (.*)", sql)
        print(where_match)

        select_fields = select_match.group(1).split(",")
        table = table_match.group(1)

        filters = None
        if where_match:
            condition = where_match.group(1)
            # simple: age > 25
            parts = self.parse_where(condition)

        return Query(select_fields, table, filters)


    def parse_where(self, condition):
        tokens = condition.split()

        # simple AND support
        if "and" in tokens:
            idx = tokens.index("and")
            left = Condition(tokens[0], tokens[1], tokens[2])
            right = Condition(tokens[idx+1], tokens[idx+2], tokens[idx+3])
            return And(left, right)

        return Condition(tokens[0], tokens[1], tokens[2])


# =========================
# DATASOURCE INTERFACE
# =========================

class DataSource(ABC):

    @abstractmethod
    def execute(self, query: Query):
        pass


# =========================
# SQL DATASOURCE
# =========================

class SQLDataSource(DataSource):

    def execute(self, query: Query):
        sql = self._translate(query)
        print(f"[SQL EXECUTE]: {sql}")
        return ["sql_result"]

    def _translate(self, query: Query):
        base = f"SELECT {', '.join(query.select)} FROM {query.table}"

        if query.filters:
            field, op, val = query.filters
            base += f" WHERE {field} {op} {val}"

        return base


# =========================
# MONGO DATASOURCE
# =========================

class MongoDataSource(DataSource):

    def execute(self, query: Query):
        mongo_query = self._translate(query)
        print(f"[MONGO EXECUTE]: {mongo_query}")
        return ["mongo_result"]

    def _translate(self, query: Query):
        mongo = {}

        if query.filters:
            self.translate_filter(query.filters)
                

        return {
            "collection": query.table,
            "filter": mongo,
            "projection": query.select
        }
    
    def translate_filter(self, filter):

        if isinstance(filter, Condition):
            field, op, val = filter.field, filter.op, filter.value

            if op == ">":
                return {field: {"$gt": int(val)}}
            elif op == "<":
                return {field: {"$lt": int(val)}}
            elif op == "=":
                return {field: val}

        if isinstance(filter, And):
            return {
                "$and": [
                    self.translate_filter(filter.left),
                    self.translate_filter(filter.right)
                ]
            }

        if isinstance(filter, Or):
            return {
                "$or": [
                    self.translate_filter(filter.left),
                    self.translate_filter(filter.right)
                ]
            }

OP_MAP = {
    ">": "$gt",
    "<": "$lt",
    "=": "$eq"
}

# =========================
# FACTORY
# =========================

class DataSourceFactory:

    @staticmethod
    def get_source(source_type: str) -> DataSource:
        if source_type == "sql":
            return SQLDataSource()
        elif source_type == "mongo":
            return MongoDataSource()
        else:
            raise ValueError("Unsupported source")


# =========================
# EXECUTOR (FACADE)
# =========================

class QueryExecutor:

    def __init__(self):
        self.parser = QueryParser()

    def execute(self, sql: str, source_type: str):
        # Step 1: Parse SQL → IR
        query = self.parser.parse(sql)

        # Step 2: Get datasource
        source = DataSourceFactory.get_source(source_type)

        # Step 3: Execute
        return source.execute(query)


# =========================
# DEMO
# =========================

def main():
    executor = QueryExecutor()

    sql = "SELECT name FROM users WHERE age > 25"

    print("\n--- SQL DB ---")
    res1 = executor.execute(sql, "sql")
    print(res1)

    print("\n--- Mongo DB ---")
    res2 = executor.execute(sql, "mongo")
    print(res2)


if __name__ == "__main__":
    main()