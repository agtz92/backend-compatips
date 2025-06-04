from django.contrib import admin
from django.urls import path
from strawberry.django.views import GraphQLView
from django.views.decorators.csrf import csrf_exempt
from api.schema import schema
from api.views import health_check


urlpatterns = [
    path('', health_check),
    path('admin/', admin.site.urls),
    path("graphql/", csrf_exempt(GraphQLView.as_view(schema=schema))),
]
