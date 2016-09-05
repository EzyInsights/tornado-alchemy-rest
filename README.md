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
