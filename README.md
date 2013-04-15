HRMC ContextualViews
====================

Creates scatter plots of HRMC output data to summarise datasets within
the Bioscience Data Platform MyTardis installation.

Installation
------------

Currently requires contextual view branch of the MyTardis system:
``git clone https://github.com/grischa/mytardis/tree/synch-views mytardis``

Then checkout the MyTardis app:
``git clone https://github.com/ianedwardthomas/mytardis-app-hrmcoutput hrmc_views``
to be installed under the ``tardis/apps`` directory

See this repository for more information.

install ``hrmc.py`` filter  into mytardis::

    mv hrmc_views/hrmc.py ../../tardis/tardis_portal/filters

For centos 6 install the matplotlib library::

    sudo yum install python-matplotlib

In ``tardis/settings.py`` add following::

    # Post Save Filters
    POST_SAVE_FILTERS = [
        ("tardis.tardis_portal.filters.hrmc.make_filter",
            ["HRMC", "http://rmit.edu.au/schemas/hrmcdataset"]),
    ]

    MATPLOTLIB_HOME = path.abspath(path.join(path.dirname(__file__),
        '../')).replace('\\', '/')

    INSTALLED_APPS += ("tardis.apps.hrmc_views",)
    DATASET_VIEWS = [("http://rmit.edu.au/schemas/hrmcdataset",
        "tardis.apps.hrmc_views.views.view_full_dataset")]

    # Add Middleware
    tmp = list(MIDDLEWARE_CLASSES)
    tmp.append('tardis.tardis_portal.filters.FilterInitMiddleware')
    MIDDLEWARE_CLASSES = tuple(tmp)

Once installed, use admin tool to create following schema::

    Schema(namespace="http://rmit.edu.au/schemas/hrmcdataset",
        name="hrmc_views"
        type="Dataset schema"
        Hidden=True)

    ParameterName(name="plot",
        fullname = "scatterplot",
        units="image", datatype=FILENAME)