from __future__ import absolute_import

import json
from urllib.parse import urlencode
import asyncio

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

    def initialize(self, pool):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.pool = pool
        super().initialize()

    def get_arg(self, value, name, clazz, default):
        if value:
            return clazz(value)
        else:
            if default != '__NONE__':
                return default
            raise MissingArgumentError(name)

    def get_int(self, value, name, default='__NONE__'):
        return self.get_arg(value, name, int, default)

    async def prepare(self):
        self.psql = await self.pool.acquire()
        if "Content-Type" in self.request.headers and \
                self.request.headers["Content-Type"].startswith("application/json"):
            self.json_args = json.loads(self.request.body.decode(), cls=DateTimeAwareJSONDecoder)
        else:
            self.json_args = None
        return super().prepare()

    def on_finish(self):
        asyncio.ensure_future(self.psql.close())
        return super().on_finish()

    async def _execute_query(self, alchemy_query):
        cursor = await self.psql.execute(alchemy_query)
        return cursor

    async def _execute_bulk_queries(self, alchemy_queries):
        results = list()
        async with self.psql.begin():
            for alchemy_query in alchemy_queries:
                query = alchemy_query.compile(dialect=postgresql.dialect())
                cursor = await self.psql.execute(alchemy_query)
                res = await cursor.fetchall()
                results.append(res)
        return results


class SingleRESTAPIHandler(BaseAPIHandler):

    def get_from(self):
        return self.table

    def get_query(self, *args):
        id = self.get_int(args[0], 'id')
        return self.get_from().select().where(self.table.c.id == id)

    async def get_object_dict(self, *args):
        query = self.get_query(*args)
        cursor = await self.psql.execute(query)
        row = await cursor.fetchone()
        return dict(row)

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

    async def put_object_dict(self, id, params):
        update_query = self.table.update().where(self.table.c.id == id).values(
            **params
        )
        await self.psql.execute(update_query)

    async def put(self, *args):
        cursor = await self._execute_query(self.get_query(*args))
        row = await cursor.fetchone()
        if row is None:
            self.set_status(404)
            return
        await self.put_object_dict(row["id"], self.json_args)
        await self.get(*args)

    async def delete(self, *args):
        cursor = await self._execute_query(self.get_query(*args))
        row = await cursor.fetchone()
        if row is None:
            self.set_status(404)
            return
        await self.psql.execute(self.table.delete().where(self.table.c.id == row["id"]))
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

    async def get_object_list(self, query):
        res = await self.psql.execute(query)
        return [dict(row) for row in await res.fetchall()]

    async def get_count(self, query):
        return await self.psql.scalar(select([func.count()]).select_from(query.alias('items')))

    def get_sort_clause(self, sort_field, sort_dir):
        sort_clause = column(sort_field.decode())
        if sort_dir.decode() == 'DESC':
            sort_clause = sort_clause.desc()
        else:
            sort_clause = sort_clause.asc()
        return sort_clause

    def serialize(self, rows):
        return json.dumps(rows, cls=DateTimeAwareJSONEncoder)

    async def get(self, *args):
        page = self.request.arguments.pop('_page', [None])[0]
        per_page = self.request.arguments.pop('_perPage', [None])[0]
        sort_field = self.request.arguments.pop('_sortField', [None])[0]
        sort_dir = self.request.arguments.pop('_sortDir', [None])[0]
        filters = json.loads(self.request.arguments.pop('_filters', [b'{}'])[0].decode())
        arguments = {k: v[0].decode('utf-8') if v else v for k, v in self.request.arguments.items()}

        query = self.get_query(**filters)
        item_count = await self.get_count(query)

        if page:
            query = query.limit(int(per_page)).offset(int(per_page) * (int(page) - 1))
        if sort_field:
            sort_clause = self.get_sort_clause(sort_field, sort_dir)
            query = query.order_by(sort_clause)

        rows = await self.get_object_list(query)

        self.set_header('X-Total-Count', item_count)
        self.write(self.serialize(rows))
        self.set_status(200)

    @gen.coroutine
    def options(self):
        self.set_status(200)

    async def post_object_dict(self, params):
        args = {k: v for k, v in params.items() if hasattr(self.table.c, k)}
        query = self.table.insert(returning=[self.table.c.id]).values(**args)
        return await self.psql.scalar(query)

    @gen.coroutine
    def post(self, *args):
        yield self.post_object_dict(self.json_args)
        self.set_status(201)
