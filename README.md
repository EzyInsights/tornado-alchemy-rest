##Tornado + Alchemy REST Client

This simple module creates CRUD endpoints for some SQLAlchemy model.

####Usage example

```python
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
```

More complex example, where you can override object creation methods:

```python
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

```


