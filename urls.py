from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('tardis.apps.hrmc_views.views',
    url(r'expgraph/(?P<experiment_id>\d+)/$', 'get_exp_graph'),
    url(r'dsetgraph/(?P<dset_id>\d+)/$', 'get_dset_graph'),
    url(r'test/$', 'test')
    )
