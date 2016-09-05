from __future__ import absolute_import

import json
from urllib.parse import urlencode

import tornado.web
from tornado.web import MissingArgumentError
from tornado.httpclient import AsyncHTTPClient
from tornado import gen

from sqlalchemy import column, bindparam, and_, func, select
from sqlalchemy.dialects import postgresql

from .encoders import DateTimeAwareJSONEncoder, DateTimeAwareJSONDecoder


class BaseAPIHandler(tornado.web.RequestHandler):

    def data_received(self, chunk):
        pass

    def initialize(self, psql):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.psql = psql

    def get_arg(self, value, name, clazz, default):
        if value:
            return clazz(value)
        else:
            if default != '__NONE__':
                return default
            raise MissingArgumentError(name)

    def get_int(self, value, name, default='__NONE__'):
        return self.get_arg(value, name, int, default)

    def prepare(self):
        if "Content-Type" in self.request.headers and \
                self.request.headers["Content-Type"].startswith("application/json"):
            self.json_args = json.loads(self.request.body.decode(), cls=DateTimeAwareJSONDecoder)
        else:
            self.json_args = None

    @gen.coroutine
    def _execute_query(self, alchemy_query):
        query = alchemy_query.compile(dialect=postgresql.dialect())
        cursor = yield self.psql.execute(str(query), query.params)
        return cursor


class SingleRESTAPIHandler(BaseAPIHandler):

    def get_from(self):
        return self.table

    def get_query(self, *args):
        id = self.get_int(args[0], 'id')
        return self.get_from().select().where(self.table.c.id == id)

    @gen.coroutine
    def get_object_dict(self, *args):
        query = self.get_query(*args).compile(dialect=postgresql.dialect())
        cursor = yield self.psql.execute(str(query), query.params)
        row = cursor.fetchone()
        raise gen.Return(row)

    @gen.coroutine
    def get(self, *args):
        row = yield self.get_object_dict(*args)
        if row is None:
            self.set_status(404)
            return
        self.write(json.dumps(row, cls=DateTimeAwareJSONEncoder))
        self.set_status(200)

    @gen.coroutine
    def options(self, *args):
        self.set_status(200)

    @gen.coroutine
    def put_object_dict(self, id, params):
        update_query = self.table.update().where(self.table.c.id == id).values(
            **params
        ).compile(dialect=postgresql.dialect())
        yield self.psql.execute(str(update_query), update_query.params)

    @gen.coroutine
    def put(self, *args):
        cursor = yield self._execute_query(self.get_query(*args))
        row = cursor.fetchone()
        if row is None:
            self.set_status(404)
            return
        yield self.put_object_dict(row["id"], self.json_args)
        yield self.get(*args)

    @gen.coroutine
    def delete(self, *args):
        cursor = yield self._execute_query(self.get_query(*args))
        row = cursor.fetchone()
        if row is None:
            self.set_status(404)
            return
        delete_query = self.table.delete().where(self.table.c.id == row["id"]).compile(dialect=postgresql.dialect())
        yield self.psql.execute(str(delete_query), delete_query.params)
        self.set_status(204)


class ProxyAPIHandler(BaseAPIHandler):
    @gen.coroutine
    def get(self):
        client = AsyncHTTPClient()
        res = yield client.fetch(self.url + '?' + urlencode({k: v[0] for k, v in self.request.arguments.items()}))
        self.write(res.body)


class ListRESTAPIHandler(BaseAPIHandler):

    def get_from(self):
        return self.table

    def get_query(self, **filters):
        query = self.get_from().select()
        for k, v in filters.items():
            field, _, filter_ = k.partition('__')
            if not filter_:
                query = query.where(column(field) == v)
            elif filter_ == 'startswith':
                query = query.where(getattr(self.table.c, field).startswith(v))
            elif filter_ == 'contains':
                query = query.where(getattr(self.table.c, field).contains(v))
            elif filter_ == 'icontains':
                query = query.where(getattr(self.table.c, field).ilike('%' + v + '%'))
            elif filter_ == 'any':
                query = query.where(getattr(self.table.c, field).any(v))
            elif filter_ == 'ne':
                query = query.where(getattr(self.table.c, field) != v)
        return query

    @gen.coroutine
    def get_object_list(self, query):
        cursor = yield self._execute_query(query)
        raise gen.Return(cursor.fetchall())

    @gen.coroutine
    def get_count(self, query):
        count_cursor = yield self._execute_query(select([func.count()]).select_from(query.alias('items')))
        raise gen.Return(count_cursor.fetchone()["count_1"])

    def get_sort_clause(self, sort_field, sort_dir):
        sort_clause = column(sort_field.decode())
        if sort_dir.decode() == 'DESC':
            sort_clause = sort_clause.desc()
        else:
            sort_clause = sort_clause.asc()
        return sort_clause

    def serialize(self, rows):
        return json.dumps(rows, cls=DateTimeAwareJSONEncoder)

    @gen.coroutine
    def get(self, *args):
        page = self.request.arguments.pop('_page', [None])[0]
        per_page = self.request.arguments.pop('_perPage', [None])[0]
        sort_field = self.request.arguments.pop('_sortField', [None])[0]
        sort_dir = self.request.arguments.pop('_sortDir', [None])[0]
        filters = json.loads(self.request.arguments.pop('_filters', [b'{}'])[0].decode())
        arguments = {k: v[0].decode('utf-8') if v else v for k, v in self.request.arguments.items()}

        query = self.get_query(**filters)
        item_count = yield self.get_count(query)

        if page:
            query = query.limit(int(per_page)).offset(int(per_page) * (int(page) - 1))
        if sort_field:
            sort_clause = self.get_sort_clause(sort_field, sort_dir)
            query = query.order_by(sort_clause)

        rows = yield self.get_object_list(query)

        self.set_header('X-Total-Count', item_count)
        self.write(self.serialize(rows))
        self.set_status(200)

    @gen.coroutine
    def options(self):
        self.set_status(200)

    @gen.coroutine
    def post_object_dict(self, params):
        args = {k: v for k, v in params.items() if hasattr(self.table.c, k)}
        query = self.table.insert(returning=[self.table.c.id]).values(**args)
        cursor = yield self._execute_query(query)
        raise gen.Return(cursor.fetchone()['id'])

    @gen.coroutine
    def post(self, *args):
        yield self.post_object_dict(self.json_args)
        self.set_status(201)
