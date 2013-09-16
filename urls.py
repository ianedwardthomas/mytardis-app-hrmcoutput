from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('tardis.apps.hrmc_views.views',
    url(r'(?P<experiment_id>\d+)/$', 'get_graph'),
    url(r'test/$', 'test')
    )
