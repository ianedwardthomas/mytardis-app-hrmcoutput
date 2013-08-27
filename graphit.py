import json
from collections import defaultdict
from django.template import Context
import logging
import base64
import os
import tempfile
import re

from django.http import HttpResponse
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.core.exceptions import MultipleObjectsReturned


from tardis.tardis_portal.shortcuts import return_response_error
from tardis.tardis_portal.shortcuts import return_response_not_found
from tardis.urls import getTardisApps
from tardis.tardis_portal.auth import decorators as authz
from tardis.tardis_portal.models import Dataset, Experiment
from tardis.tardis_portal.shortcuts import get_experiment_referer
from tardis.tardis_portal.shortcuts import render_response_index
from tardis.tardis_portal.models import Schema, DatasetParameterSet
from tardis.tardis_portal.models import ExperimentParameterSet
from tardis.tardis_portal.models import (ParameterName, DatasetParameter,
    DatafileParameter)
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
    logger.debug("request=%s" % request)
    logger.debug("requset.user=%s" % request.user)

    try:
        experiment = Experiment.safe.get(request.user, experiment_id)
    except PermissionDenied:
        return return_response_error(request)
    except Experiment.DoesNotExist:
        return return_response_not_found(request)

    logger.debug("foobar1")
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

    logger.debug("foobar2")
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

    (exp_schema, dset_schema, dfile_schema) = load_graph_schemas()

    # TODO: should be read from domain-specific filter plugins
    functions = {
        'tardis.tardis_portal.filters.getdf': [1, 3, 5 , 7],  #only works for lists
        'tardis.tardis_portal.filters.x': [2, 4 , 6, 8],
        'tardis.tardis_portal.filters.y': [11, 14, 15, 35],
    }

    # Get all experiment graph parameters


    """
    # TODO: reorder so that datasets are only once, because assume
    # most expsensive read (followed by experiment)


    display_images = []

    # TODO: check order of loops so that longests loops are not repeated
    plots = []

    graph_vals = defaultdict(list)


    # get datasets
    for dset in Dataset.objects.filter(experiments=experiment):
        logger.debug("dset=%s" % dset)
        dset_psets = dset.getParameterSets() \
            .filter(schema=dset_schema)

        # get dataset parametersets
        for dset_pset in dset_psets:
            logger.debug("dset_pset=%s" % dset_pset)
            # get dataset params
            try:
                dset_params = DatasetParameter.objects.filter(
                    parameterset=dset_pset)
            except DatasetParameter.DoesNotExist:
                continue

            # for each graph experiment pset

            for exp_pset in experiment.getParameterSets().filter(schema=exp_schema):
                logger.debug("exp_pset=%s" % exp_pset)
                # get all experiment parameters
                try:
                    exp_params = ExperimentParameter.objects.filter(
                        parameterset=exp_pset)
                except ExperimentParameter.DoesNotExist:
                    continue

                try:
                    (exp_name, value_keys, value_dict, graph_info) = \
                        _get_graph_data(exp_params)
                except ValueError, e:
                    logger.error(e)
                    continue

                graph_vals = graphs[exp_pset]
                for m, key in enumerate(value_keys):
                    logger.debug("key=%s" % key)

                    logger.debug("exp_name=%s" % exp_name)

                    logger.debug("graph_vals=%s" % graph_vals)
                    try:
                        graph_vals = _match_key_vals(graph_vals, dset_params, key, functions)
                    except ValueError, e:
                        logger.error(e)
                        continue
                    logger.debug("graph_vals=%s" % graph_vals)

                    try:
                        graph_vals.update(_match_constants(key, functions))
                    except ValueError, e:
                        logger.error(e)
                        continue

                    logger.debug("graph_vals=%s" % graph_vals)


                    try:
                        plot = reorder_keys(graph_vals, graph_info, key, exp_name)
                    except ValueError, e:
                        logger.error(e)
                        continue
                    logger.debug("plot=%s" % plot)

                    plots.append(plot)
                graphs[exp_psets] = graph_vals


    logger.debug(("plots=%s" % plots))
    mtp = MatPlotLib()
    image_to_show = mtp.graph(graph_info, exp_schema, graph_exp_pset, "plot", plots)
    if image_to_show:
        display_images.append(image_to_show)


    """

    display_images = []

    # TODO: check order of loops so that longests loops are not repeated
    for graph_exp_pset in experiment.getParameterSets().filter(schema=exp_schema):
        logger.debug("graph_exp_pset=%s" % graph_exp_pset)
        try:
            exp_params = ExperimentParameter.objects.filter(
                parameterset=graph_exp_pset)
        except ExperimentParameter.DoesNotExist:
            continue

        try:
            (exp_name, value_keys, value_dict, graph_info) = \
                _get_graph_data(exp_params)
        except ValueError, e:
            logger.error(e)
            continue

        plots = []
        for m, key in enumerate(value_keys):
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

                    logger.debug("exp_name=%s" % exp_name)

                    logger.debug("graph_vals=%s" % graph_vals)
                    try:
                        graph_vals = _match_key_vals(graph_vals, dset_params, key, exp_name, functions)
                    except ValueError, e:
                        logger.error(e)
                        continue
                    logger.debug("graph_vals=%s" % graph_vals)

                logger.debug("graph_vals=%s" % graph_vals)

            try:
                graph_vals.update(_match_constants(key, value_dict,  functions))
            except ValueError, e:
                logger.error(e)
                continue

            logger.debug("graph_vals=%s" % graph_vals)

            try:
                plot = reorder_keys(graph_vals, graph_info, key, exp_name)
            except ValueError, e:
                logger.error(e)
                continue
            logger.debug("plot=%s" % plot)

            plots.append(plot)

        logger.debug(("plots=%s" % plots))
        mtp = MatPlotLib()
        plot_name = "plot"
        pfile = mtp.graph(graph_info, exp_schema, graph_exp_pset, plot_name, plots)

        if pfile:
            # TODO: return encode rather than create Parameters as all
            # backends should do the same thing.
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=exp_schema, name=plot_name)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % plot_name)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % plot_name)
                return None

            logger.debug("ready to save")

            try:
                ep = ExperimentParameter.objects.get(
                    parameterset=graph_exp_pset,
                    name=pn)
            except ExperimentParameter.DoesNotExist:
                ep = ExperimentParameter(
                    parameterset=graph_exp_pset,
                    name=pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc experiment schemas returned")
                return None
            ep.string_value = "%s.png" % pfile
            ep.save()

            display_images.append(ep)

    # TODO: Need some sort of caching so that graphs are only recreated if data
    # has actually changed.  Also want creation to be async process to the
    # display of the page.
    # FIXME: currently, reloading the page creates a brand new graph file,
    # which could be DoS attack vector.

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


def _get_graph_data(params):

    # TODO: as this data comes from user editable parameter set in UI,
    # this data must be validated before accepted.  json loads, is
    # probably in sufficient, and need to check right formats for values etc.

    name = params.get(name__name="name").get()
    logger.debug("name=%s" % name)

    v_d = str(params.get(name__name="value_dict").get())
    value_dict = json.loads(v_d)
    logger.debug("value_dict=%s" % value_dict)

    logger.debug("value_dict=%s" % value_dict)
    value_keys = json.loads(str(params.get(name__name="value_keys").get()))
    logger.debug("value_keys=%s" % value_keys)

    graph_info = json.loads(str(params.get(name__name="graph_info").get()))
    logger.debug("graph_info=%s" % graph_info)

    return (name, value_keys, value_dict, graph_info)


def _match_key_vals(graph_vals, params, key, parent_name,  functions):

    logger.debug("params=%s" % params)
    logger.debug("key=%s" % key)

    (name, value_keys, value_dict, graph_info) = \
        _get_graph_data(params)

    logger.debug("dset_name=%s" % name)
    logger.debug("value_dict=%s" % value_dict)

    for k, v in value_dict.items():
        logger.debug("value_dict[%s] = %s" % (k, v))
        if str(k) in key:

            id = str(k).split('/')[0]
            logger.debug("id=%s" % id)
            if id != name:
                logger.debug("non match %s to %s" % (id, name))
                continue

            if isinstance(v, basestring):
                logger.debug(v)
                if v in functions:
                    graph_vals[k].extend(
                        functions[v])
                else:
                    graph_vals[k].append(v)
            elif isinstance(v, (int, long)):
                graph_vals[k].append(v)
            elif isinstance(v, float):
                graph_vals[k].append(float(v))
            else:
                for l in list(v):
                    graph_vals[k].append(l)
        else:
            logger.warn("%s not in %s" % (k, key))
            pass

    return graph_vals


def _match_constants(key, value_dict, functions):

    i = 0
    graph_vals = defaultdict(list)

    #find constants from node via value_keys

    logger.debug("key=%s" % key)
    for x in key:
        logger.debug("x=%s" % x)
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
            elif isinstance(x, float):
                graph_vals[x].append(float(x))
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
            elif isinstance(v, float):
                graph_vals[k].append(float(v))
            else:
                for l in list(v):
                    graph_vals[k].append(l)
    logger.debug("graph_vals=%s" % graph_vals)

    return graph_vals


def reorder_keys(graph_vals, graph_info,  key, name):
    # reorder based on value_keys
    # FIXME: need to validate this code.
    plot = []
    if 'legends' in graph_info:
        plot.append(graph_info['legends'])
    else:
        plot.append([])
    i = 0
    for k in key:
        if isinstance(k, basestring):
            plot.append((k, graph_vals[k]))
        elif isinstance(k, (int, long)):
            plot.append((k, graph_vals[k]))
        elif isinstance(k, float):
            plot.append((k, graph_vals[k]))
        else:
            key = "%s/%s" % (name, i)
            plot.append((key, graph_vals[key]))
            i += 1
    return plot


def load_graph_schemas():
    # TODO: if schemas missing, then create them.
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



@authz.dataset_access_required
def view_dataset(request, dataset_id):
    """Displays a Dataset and associated information.

    Shows a dataset its metadata and a list of associated files with
    the option to show metadata of each file and ways to download those files.
    With write permission this page also allows uploading and metadata
    editing.
    Optionally, if set up in settings.py, datasets of a certain type can
    override the default view.
    Settings example:
    DATASET_VIEWS = [("http://dataset.example/schema",
                      "tardis.apps.custom_views_app.views.my_view_dataset"),]
    """
    dataset = Dataset.objects.get(id=dataset_id)

    def get_datafiles_page():
        # pagination was removed by someone in the interface but not here.
        # need to fix.
        pgresults = 100

        paginator = Paginator(dataset.dataset_file_set.all(), pgresults)

        try:
            page = int(request.GET.get('page', '1'))
        except ValueError:
            page = 1

        # If page request (9999) is out of range, deliver last page of results.

        try:
            return paginator.page(page)
        except (EmptyPage, InvalidPage):
            return paginator.page(paginator.num_pages)

    upload_method = getattr(settings, "UPLOAD_METHOD", "uploadify")

    # TODO: should be read from domain-specific filter plugins
    functions = {
        'tardis.tardis_portal.filters.getdf': [1, 3, 5 , 7],  #only works for lists
        'tardis.tardis_portal.filters.x': [2, 4 , 6, 8],
        'tardis.tardis_portal.filters.y': [11, 14, 15, 35],
    }

    (exp_schema, dset_schema, dfile_schema) = load_graph_schemas()

    display_images = []

    # TODO: check order of loops so that longests loops are not repeated
    for graph_dset_pset in dataset.getParameterSets().filter(schema=dset_schema):
        logger.debug("graph_dset_pset=%s" % graph_dset_pset)
        try:
            dset_params = DatasetParameter.objects.filter(
                parameterset=graph_dset_pset)
        except DatasetParameter.DoesNotExist:
            continue

        try:
            (dset_name, value_keys, value_dict, graph_info) = \
                _get_graph_data(dset_params)
        except ValueError, e:
            logger.error(e)
            continue

        plots = []
        for m, key in enumerate(value_keys):
            logger.debug("key=%s" % key)
            graph_vals = defaultdict(list)

            for dfile in Dataset_File.objects.filter(dataset=dataset):
                logger.debug("dfile=%s" % dfile)
                dset_pset = dfile.getParameterSets() \
                    .filter(schema=dfile_schema)

                for graph_dfile_pset in dset_pset:
                    logger.debug("graph_dfile_pset=%s" % graph_dfile_pset)
                    try:
                        dfile_params = DatafileParameter.objects.filter(
                            parameterset=graph_dfile_pset)
                    except DatafileParameter.DoesNotExist:
                        continue

                    logger.debug("dset_name=%s" % dset_name)

                    logger.debug("1graph_vals=%s" % graph_vals)
                    try:
                        graph_vals = _match_key_vals(graph_vals, dfile_params, key, dset_name, functions)
                    except ValueError, e:
                        logger.error(e)
                        continue
                    logger.debug("2graph_vals=%s" % graph_vals)

                logger.debug("3graph_vals=%s" % graph_vals)

            try:
                graph_vals.update(_match_constants(key, value_dict, functions))
            except ValueError, e:
                logger.error(e)
                continue

            logger.debug("4graph_vals=%s" % graph_vals)

            try:
                plot = reorder_keys(graph_vals, graph_info, key, dset_name)
            except ValueError, e:
                logger.error(e)
                continue
            logger.debug("plot=%s" % plot)

            plots.append(plot)

        logger.debug(("plots=%s" % plots))
        mtp = MatPlotLib()
        plot_name = "plot"
        pfile = mtp.graph(graph_info, dset_schema, graph_dset_pset, plot_name, plots)

        if pfile:
            # TODO: return encode rather than create Parameters as all
            # backends should do the same thing.
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=dset_schema, name=plot_name)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % plot_name)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % plot_name)
                return None

            logger.debug("ready to save")

            try:
                ep = DatasetParameter.objects.get(
                    parameterset=graph_dset_pset,
                    name=pn)
            except DatasetParameter.DoesNotExist:
                ep = DatasetParameter(
                    parameterset=graph_dset_pset,
                    name=pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc dset schemas returned")
                return None
            ep.string_value = "%s.png" % pfile
            ep.save()

            display_images.append(ep)

    # TODO: Need some sort of caching so that graphs are only recreated if data
    # has actually changed.  Also want creation to be async process to the
    # display of the page.
    # FIXME: currently, reloading the page creates a brand new graph file,
    # which could be DoS attack vector.

    c = Context({
        'dataset': dataset,
        'datafiles': get_datafiles_page(),
        'parametersets': dataset.getParameterSets()
                                .exclude(schema__hidden=True),
        'has_download_permissions':
            authz.has_dataset_download_access(request, dataset_id),
        'has_write_permissions':
            authz.has_dataset_write(request, dataset_id),
        'from_experiment':
            get_experiment_referer(request, dataset_id),
        'other_experiments':
            authz.get_accessible_experiments_for_dataset(request, dataset_id),
        'upload_method': upload_method,
        'display_images': display_images
    })
    _add_protocols_and_organizations(request, None, c)
    return HttpResponse(render_response_index(
        request, 'hrmc_views/view_full_dataset.html', c))