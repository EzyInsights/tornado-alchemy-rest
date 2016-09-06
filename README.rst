Tornado + Alchemy REST Client
=============================

This simple module creates CRUD endpoints for SQLAlchemy table. Its
purpose to allow quickly create RESTful APIs, for example for admin
panel. List endpoints support pagination and filtering. Was written for
Angular’s ng-admin, so this module supports ng-admin querying out of the
box

Installation
------------

::

        pip install tornado-alchemy-rest

Usage example
-------------

.. code:: python

        import tornado.web
        from tornado.web import URLSpec
        from .models import ItemTable
        from tornado_alchemy_rest import SingleRESTAPIHandler, ListRESTAPIHandler
      
        class SingleItemHandler(SingleRESTAPIHandler):
            table = ItemTable
        
            def delete(self, *args, **kwargs):
                raise HTTPError(405)
        
        
        class ItemHandler(ListRESTAPIHandler):
            table = ItemTable

        app = tornado.web.Application([
            URLSpec(prefix(r'items'), ItemHandler, dict(psql=psql_pool), 'items'),
            URLSpec(prefix(r'items/(\d+)'), SingleItemHandler, dict(psql=psql_pool), 'single_item'),
        ])

More complex example, where you can override object creation methods:

.. code:: python

    class SingleItemHandler(SingleRESTAPIHandler):
        table = TableItem

        @gen.coroutine
        def get_object_dict(self, *args):
            obj = yield super().get_object_dict(*args)
            
            cursor = yield self._execute_query(User.select().where(User.c.id == obj['user_id']))
            obj['user'] = cursor.fetchone()
            return obj

        @gen.coroutine
        def put_object_dict(self, id, params):
            assert params['value'] > 5
            yield super().put_object_dict(id, params)

    class ItemHandler(ListRESTAPIHandler):
        table = TableItem

        @gen.coroutine
        def get_object_list(self, query):
            objects = yield super().get_object_list(query)
            for obj in objects:
                cursor = yield self._execute_query(User.select().where(User.c.id == obj['user_id']))
                obj['user'] = cursor.fetchone()
            raise gen.Return(objects)

        @gen.coroutine
        def post_object_dict(self, params):
            assert params['value'] > 5
            yield super().post_object_dict(params)

Querying
--------

To get second page with ordering by id DESC you need to do that query:

::

    GET /item?_page=2&_perPage=30&_sortField=id&_sortDir=DESC

To get all items, where ``name`` contains “test” and ``type`` is 5 and
``value`` is 7 or 6, you will need that query:

::

    GET /item?_filters={"name__contains":"test", "type":5, "value__any":[7,6]}

Query params
~~~~~~~~~~~~

-  \_page – page name
-  \_perPage – rows per page
-  \_sortField – field to order by
-  \_sortDir – direction to sort by
-  \_filters – filter items with given params. Currently supported
   filters are: “” (equality), startswith, contains, icontains, any, ne

Join support
~~~~~~~~~~~~

That will return data from both tables at some time:

.. code:: python

    class SingleItemHandler(SingleRESTAPIHandler):
        table = TableItem

        def get_from(self):
            return self.table.join(TableUser, isouter=True)

Requirements
------------

tornado, sqlalchemy
