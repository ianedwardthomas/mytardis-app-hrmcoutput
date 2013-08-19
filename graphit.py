import json
from collections import defaultdict
from django.template import Context
import logging
import base64
import os
import tempfile
import re

from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.http import HttpResponse
from django.template import Context
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.core.exceptions import PermissionDenied

from tardis.tardis_portal.shortcuts import return_response_error
from tardis.tardis_portal.shortcuts import return_response_not_found
from tardis.urls import getTardisApps
from tardis.tardis_portal.auth import decorators as authz
from tardis.tardis_portal.models import Dataset, Experiment
from tardis.tardis_portal.shortcuts import get_experiment_referer
from tardis.tardis_portal.shortcuts import render_response_index
from tardis.tardis_portal.models import Schema, DatasetParameterSet
from tardis.tardis_portal.models import ExperimentParameterSet
from tardis.tardis_portal.models import ParameterName, DatasetParameter
from tardis.tardis_portal.models import ExperimentParameter
from tardis.tardis_portal.models import Dataset_File
from tardis.tardis_portal.views import SearchQueryString
from tardis.tardis_portal.views import _add_protocols_and_organizations

from .matplot import MatPlotLib

EXPERIMENT_GRAPH = "http://rmit.edu.au/schemas/expgraph"
DATASET_GRAPH = "http://rmit.edu.au/schemas/dsetgraph"
DATAFILE_GRAPH = "http://rmit.edu.au/schemas/dfilegraph"

logger = logging.getLogger(__name__)


@authz.experiment_access_required
def view_experiment(request, experiment_id,
                    template_name='hrmc_views/view_experiment.html'):

    """View an existing experiment.

    :param request: a HTTP Request instance
    :type request: :class:`django.http.HttpRequest`
    :param experiment_id: the ID of the experiment to be edited
    :type experiment_id: string
    :rtype: :class:`django.http.HttpResponse`

    """
    c = Context({})

    try:
        experiment = Experiment.safe.get(request, experiment_id)
    except PermissionDenied:
        return return_response_error(request)
    except Experiment.DoesNotExist:
        return return_response_not_found(request)

    c['experiment'] = experiment
    c['has_write_permissions'] = \
        authz.has_write_permissions(request, experiment_id)
    c['has_download_permissions'] = \
        authz.has_experiment_download_access(request, experiment_id)
    if request.user.is_authenticated():
        c['is_owner'] = authz.has_experiment_ownership(request, experiment_id)
    c['subtitle'] = experiment.title
    c['nav'] = [{'name': 'Data', 'link': '/experiment/view/'},
                {'name': experiment.title,
                 'link': experiment.get_absolute_url()}]

    if 'status' in request.POST:
        c['status'] = request.POST['status']
    if 'error' in request.POST:
        c['error'] = request.POST['error']
    if 'query' in request.GET:
        c['search_query'] = SearchQueryString(request.GET['query'])
    if 'search' in request.GET:
        c['search'] = request.GET['search']
    if 'load' in request.GET:
        c['load'] = request.GET['load']

    # TODO, FIXME: Each refresh of page triggers recalculation of graphs
    # to allow newly arrived datasets to be integrated into the plots.
    # However, this is a potential DoS vector as new tardis store files are
    # created
    # with each refresh.  This is made worse if experiment is public.
    # Solutions:
    # - only set HRMC_DATA_SCHEMA schema once all data
    #   has arrived, and then only generate the graphs once at that point and
    #   only read after that point.  Waiting on contextual view ability to set
    #   parametersets on existing experiments.
    # - allow creation of new files up until experiment is public, then set
    #   just last version.

    logger.debug("foobar")
    (exp_schema, dset_schema, dfile_schema) = load_graph_schemas()


    functions = {
        'tardis.tardis_portal.filters.getdf': [1,3,5,7], #only works for lists
        'tardis.tardis_portal.filters.x': [2,4,6,8],
        'tardis.tardis_portal.filters.y': [11,14,15,35],
    }

    logger.debug("foogar")

    # Get all experiment graph parameters

    display_images = []


    # TODO: check order of loops so that longests loops are not repeated
    for graph_exp_pset in experiment.getParameterSets().filter(schema=exp_schema):
        try:
            exp_params = ExperimentParameter.objects.filter(
                parameterset=graph_exp_pset)
        except ExperimentParameter.DoesNotExist:
            continue

        name = exp_params.get(name__name="name").get()
        try:
            v_d = str(exp_params.get(name__name="value_dict").get())
            value_dict = json.loads(v_d)
        except ValueError, e:
            logger.error(e)
            continue

        try:
            value_keys = json.loads(str(exp_params.get(name__name="value_keys").get()))
        except ValueError, e:
            logger.error(e)
            continue
        graph_info = json.loads(str(exp_params.get(name__name="graph_info").get()))

        plots = []
        for i, key in enumerate(value_keys):
            logger.debug("key=%s" % key)
            graph_vals = defaultdict(list)


            for dset in Dataset.objects.filter(experiments=experiment):
                logger.debug("dset=%s" % dset)
                dset_pset = dset.getParameterSets() \
                    .filter(schema=dset_schema)
                for graph_dset_pset in dset_pset:
                    logger.debug("graph_dset_pset=%s" % graph_dset_pset)
                    try:
                        dset_params = DatasetParameter.objects.filter(
                            parameterset=graph_dset_pset)
                    except DatasetParameter.DoesNotExist:
                        continue
                    logger.debug("dset_params=%s"  % dset_params)

                    dset_name = dset_params.get(name__name="name").get()
                    dvd = str(dset_params.get(name__name="value_dict").get())
                    logger.debug("dvd=%s" % dvd)
                    dset_value_dict = json.loads(dvd)
                    dset_value_keys = json.loads(str(dset_params.get(name__name="value_keys").get()))
                    dset_graph_info = json.loads(str(dset_params.get(name__name="graph_info").get()))

                    logger.debug("name=%s" % name)
                    logger.debug("dset_name=%s" % dset_name)
                    logger.debug("dset_value_dict=%s" % dset_value_dict)

                    #if dset_name != name:
                    #   continue
                    for k, v in dset_value_dict.items():
                        logger.debug("dset_value_dict[%s] = %s" % (k,v))
                        if str(k) in key:
                            if isinstance(v, basestring):
                                logger.debug(v)
                                if v in functions:
                                    graph_vals[k].extend(
                                        functions[v])
                                else:
                                    graph_vals[k].append(v)
                            elif isinstance(v, (int, long)):
                                graph_vals[k].append(v)
                            else:
                                for l in list(v):
                                    graph_vals[k].append(l)
                        else:
                            logger.warn("%s not in %s" % (k, key))
                            pass
                    logger.debug("graph_vals=%s" % graph_vals)

            #find constants from node via value_keys
            i = 0
            for x in key:
                if '/' not in x:
                    if isinstance(x, basestring):
                        if x in functions:
                            graph_vals[x].extend(functions[x])
                        else:
                            logger.debug("Cannot resolve %s in reference %s" % (x, key))
                        #graph_vals["%s/%s" % (schema, i)].append(functions[x])
                        i += 1
                    elif isinstance(x, (int, long)):
                        graph_vals[x].append(int(x))
                    else:
                        pass
                        # for y in list(x):
                        #     graph_vals["%s/%s" % (schema,i)].append(y)
                        # i += 1

            #find constants from node via value_dict
            for k, v in value_dict.items():
                if k in key:
                    if isinstance(v, basestring):
                        if '/' not in v:
                            if v in functions:
                                graph_vals[k].extend(functions[v])
                            else:
                                logger.debug("cannot resolve %s:%s in reference %s" % (k, v, key))
                        else:
                            graph_vals[k].append(v)
                    elif isinstance(v, (int, long)):
                        graph_vals[k].append(v)
                    else:
                        for l in list(v):
                            graph_vals[k].append(l)

            # reorder based on value_keys
            res = []
            if 'legends' in graph_info:
                res.append(graph_info['legends'][i])
            else:
                res.append([])
            i = 0
            for k in key:
                if isinstance(k, basestring):
                    res.append((k, graph_vals[k]))
                elif isinstance(k, (int, long)):
                    res.append((k, graph_vals[k]))
                else:
                    key = "%s/%s" % (name, i)
                    res.append((key, graph_vals[key]))
                    i += 1

            logger.debug("res=%s" %res)
            plots.append(res)

        logger.debug(("plots=" % plots))
        mtp = MatPlotLib()
        image_to_show = mtp.graph(graph_info, exp_schema, graph_exp_pset, "plot", plots)
        if image_to_show:
            display_images.append(image_to_show)

    # image_to_show = get_exp_images_to_show1(experiment)
    # if image_to_show:
    #     display_images.append(image_to_show)
    # image_to_show = get_exp_images_to_show2(experiment)
    # if image_to_show:
    #     display_images.append(image_to_show)

    c['display_images'] = display_images

    _add_protocols_and_organizations(request, experiment, c)

    import sys
    appnames = []
    appurls = []
    for app in getTardisApps():
        try:
            appnames.append(sys.modules['%s.%s.settings'
                                        % (settings.TARDIS_APP_ROOT, app)].NAME)
            appurls.append('%s.%s.views.index' % (settings.TARDIS_APP_ROOT,
                                                  app))
        except:
            logger.debug(("No tab for %s" % app))
            pass

    c['apps'] = zip(appurls, appnames)

    return HttpResponse(render_response_index(request, template_name, c))


def load_graph_schemas():
    # Get exp graph shema
    exp_schema = Schema.objects.get(
        namespace__exact=EXPERIMENT_GRAPH,
        type=Schema.EXPERIMENT)

    # Get dataset graph schema
    dset_schema = Schema.objects.get(
        namespace__exact=DATASET_GRAPH,
        type=Schema.DATASET)

    # Get datafile graph schema
    dfile_schema = Schema.objects.get(
        namespace__exact=DATAFILE_GRAPH,
        type=Schema.DATAFILE)

    return (exp_schema, dset_schema, dfile_schema)

