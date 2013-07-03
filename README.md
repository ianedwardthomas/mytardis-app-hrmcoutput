HRMC ContextualViews
====================

Creates scatter plots of HRMC output data to summarise datasets within
the Bioscience Data Platform MyTardis installation.

Prerequisite
------------

Install MyTardis. For Centos 6x, follow the instruction below. 

NB: This instruction is adapted from https://github.com/mytardis/mytardis-chef/wiki/Chef-Solo-Guide

    sudo -E bash <<EOF
    rpm --httpproxy $http_proxy -Uvh http://rbel.frameos.org/rbel6
    yum -y install ruby ruby-devel ruby-rdoc ruby-shadow gcc gcc-c++ automake autoconf make curl dmidecode
    cd /tmp
    curl -O http://production.cf.rubygems.org/rubygems/rubygems-1.8.10.tgz
    tar zxf rubygems-1.8.10.tgz
    cd rubygems-1.8.10
    ruby setup.rb --no-format-executable
    # Bug in version 11.4.4 of gem. 
    gem install chef --no-ri --no-rdoc --version '11.4.2'
    yum -y install git
    mkdir -p /var/chef-solo
    cd /var/chef-solo
    mkdir mytardis-chef
    git clone https://github.com/mytardis/mytardis-chef.git
    cd mytardis-chef
    if [ $http_proxy != "" ]; then echo http_proxy '"'$http_proxy'"' >> solo/solo.rb;  fi
    EOF

Change the values of "repo" and "branch" in ``/var/chef-solo/mytardis-chef/roles/mytardis-bdp-milestone1.json`` 
and  ``/var/chef-solo/mytardis-chef/roles/mytardis.json``

        "repo": "https://github.com/grischa/mytardis.git",
        "branch": "mytardis-api",
        
Run chef-solo

    chef-solo -c solo/solo.rb -j solo/node.json -ldebug
    

Change directory to Mytardis source code
``cd /opt/mytardis/current``

Checkout mytardis-api branch
``git checkout mytardis-api``

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
