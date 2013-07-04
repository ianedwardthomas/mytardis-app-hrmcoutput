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
    wget http://apt.sw.be/redhat/el6/en/x86_64/rpmforge/RPMS/rpmforge-release-0.5.3-1.el6.rf.x86_64.rpm
    rpm -Uvh rpmforge-release*rpm
    yum -y install ruby-shadow
    yum -y install ruby ruby-devel ruby-rdoc gcc gcc-c++ automake autoconf make curl dmidecode
    
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
    echo 'Done'
    EOF

Change the values of "repo" and "branch" in ``/var/chef-solo/mytardis-chef/roles/mytardis-bdp-milestone1.json`` 
and  ``/var/chef-solo/mytardis-chef/roles/mytardis.json``

        "repo": "https://github.com/grischa/mytardis.git",
        "branch": "synch-views",

Run chef-solo

    cd /var/chef-solo/mytardis-chef
    chef-solo -c solo/solo.rb -j solo/node.json -ldebug   
    
    
Checkout mytardis-api branch and rebuild MyTardis as mytardis user
    
    su - mytardis
    cd /opt/mytardis/current
    git checkout mytardis-api
    bin/buildout -c buildout-prod.cfg install
    bin/django syncdb --noinput --migrate 
    bin/django collectstatic -l --noinput
    exit
    

Installation
------------

Checkout the MyTardis contextual views app as mytardis user:

    su - mytardis
    cd /opt/mytardis/current/tardis/apps/
    git clone https://github.com/ianedwardthomas/mytardis-app-hrmcoutput hrmc_views
    cd hrmc_views
    git checkout hrmc2
    exit

Edit line 239 of /opt/mytardis/current/tardis/tardis_portal/views.py. Replace 
``parameter = DatafileParameter.objects.get(pk=parameter_id)`` by 
``parameter = DatasetParameter.objects.get(pk=parameter_id)``


For centos 6 install the matplotlib library::

    yum install python-matplotlib


In ``/opt/mytardis/current/tardis/settings.py`` add following::

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

Restart MyTardis
    
    stop mytardis
    start mytardis
    
    
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
