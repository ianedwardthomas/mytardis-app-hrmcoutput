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
        "branch": "master",

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

Create administrator account as mytardis user

    su - mytardis
    cd /opt/mytardis/current
    bin/django createsuperuser
    exit


Checkout the MyTardis contextual views app as mytardis user:

    su - mytardis
    cd /opt/mytardis/current/tardis/apps/
    git clone https://github.com/ianedwardthomas/mytardis-app-hrmcoutput hrmc_views
    cd hrmc_views
    git checkout hrmc2
    exit



For centos 6 install the matplotlib library::

    yum install python-matplotlib


In ``/opt/mytardis/current/tardis/settings.py`` add following::

    MATPLOTLIB_HOME = path.abspath(path.join(path.dirname(__file__),
        '../')).replace('\\', '/')

    INSTALLED_APPS += ("tardis.apps.hrmc_views",)
    EXPERIMENT_VIEWS = [("http://rmit.edu.au/schemas/expgraph",
            "tardis.apps.hrmc_views.graphit.view_experiment")]
    DATASET_VIEWS = [("http://rmit.edu.au/schemas/dsetgraph",
            "tardis.apps.hrmc_views.graphit.view_dataset")]

Execute the following commands

    sudo -s mytardis
    cd /opt/mytardis/current
    cp /opt/mytardis/current/tardis/apps/hrmc_views/mytardis/view_dataset.html /opt/mytardis/current/tardis/tardis_portal/templates/tardis_portal/view_dataset.html

    cp /opt/mytardis/current/tardis/apps/hrmc_views/mytardis/view_experiment.html /opt/mytardis/current/tardis/tardis_portal/templates/tardis_portal/view_experiment.html
    bin/django loaddata tardis_portal /opt/mytardis/current/tardis/apps/hrmc_views/initial.json
    bin/django collectstatic -l --noinput

Restart MyTardis

    stop mytardis
    start mytardis

