HRMC ContextualViews
====================

Creates scatter plots of HRMC output data to summarise datasets within
the Bioscience Data Platform MyTardis installation.

Installation
------------

Currently requires mytardis API branch of the MyTardis system:
``git clone https://github.com/grischa/mytardis/tree/mytardis-api``

which can be installed using the mytardis-chef cookbook.

Then checkout the MyTardis app:
``git clone https://github.com/ianedwardthomas/mytardis-app-hrmcoutput hrmc_views``
to be installed under the ``tardis/apps`` directory

and use the hrmc2 branch

cp ``hrmc_views/mytardis/views.py`` to replace tardis_portal/views.py (temporary fix)

cp ``hrmc_views/mytardis/view_experiment.py`` to replace ``tardis_portal/templates/tardis_portal/view_experiment.html`` (temporary fix)


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
    EXPERIMENT_VIEWS = [("http://rmit.edu.au/schemas/hrmcexp",
            "tardis.apps.hrmc_views.views.view_experiment")]

    # Add Middleware
    tmp = list(MIDDLEWARE_CLASSES)
    tmp.append('tardis.tardis_portal.filters.FilterInitMiddleware')
    MIDDLEWARE_CLASSES = tuple(tmp)

Once installed, use admin tool to create following schema::

    Schema(namespace="http://rmit.edu.au/schemas/hrmcdataset",
        name="hrmc_dataset_views"
        type="Dataset schema"
        Hidden=True)


    ParameterName(name="plot1",
        fullname = "scatterplot1",
        units="image", datatype=FILENAME)

    ParameterName(name="plot2",
        fullname = "scatterplots",
        units="image", datatype=FILENAME)

    Schema(namespace="http://rmit.edu.au/schemas/hrmcexp",
        name="hrmc_dataset_views"
        type="Dataset schema"
        Hidden=True)

    ParameterName(name="plot1",
        fullname = "scatterplot1",
        units="image", datatype=FILENAME)

    ParameterName(name="plot2",
        fullname = "scatterplots",
        units="image", datatype=FILENAME)

    Schema(namespace="http://rmit.edu.au/schemas/hrmcdataset/output",
        name="HRMC V2.0 output"
        type="Dataset schema"
        Hidden=True)


    Schema(namespace="http://rmit.edu.au/schemas/hrmcdataset/input",
        name="HRMC V2.0 input"
        type="Dataset schema"
        Hidden=True)
