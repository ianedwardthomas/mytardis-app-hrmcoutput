# Copyright (C) 2013, RMIT University

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.


import logging
import base64
from collections import defaultdict
import os
from pprint import pformat
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
from tardis.tardis_portal.models import ( ParameterName,
    DatasetParameter, DatafileParameter)

from tardis.tardis_portal.models import ExperimentParameter
from tardis.tardis_portal.models import Dataset_File
from tardis.tardis_portal.views import SearchQueryString
from tardis.tardis_portal.views import _add_protocols_and_organizations

from django.template import Context, Template
from django.template.loader import get_template


from . import graphit
from .matplot import MatPlotLib
from .flot import Flot
#from .d3 import D3

# import and configure matplotlib library
try:
    os.environ['HOME'] = settings.MATPLOTLIB_HOME
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as pyplot
    from matplotlib.pyplot import legend
    is_matplotlib_imported = True
except ImportError:
    is_matplotlib_imported = False

logger = logging.getLogger(__name__)

HRMC_DATASET_SCHEMA = "http://rmit.edu.au/schemas/hrmcdataset"
HRMC_OUTPUT_DATASET_SCHEMA = "http://rmit.edu.au/schemas/hrmcdataset/output"
HRMC_EXPERIMENT_SCHEMA = "http://rmit.edu.au/schemas/hrmcexp"
DATA_ERRORS_FILE = "data_errors.dat"
DS_NAME_SEP = "_"
STEP_COLUMN_NUM = 0
ERRGR_COLUMN_NUM = 28
MARKER_LIST = ('x', '+', 'o')
COLOR_LIST = ('b','g','r','c','m','y','k')
STEP_LABEL = "Step"
ERRGR_LABEL = "ERRGr*wf"


EXPERIMENT_GRAPH = "http://rmit.edu.au/schemas/expgraph"
DATASET_GRAPH = "http://rmit.edu.au/schemas/dsetgraph"
DATAFILE_GRAPH = "http://rmit.edu.au/schemas/dfilegraph"
CHECKSUM_NAME = "checksum"
PLOT_NAME = "plot"


def get_exp_graph(request, experiment_id):
    display_html = []

    # TODO: should be read from domain-specific filter plugins
    functions = {
        'tardis.tardis_portal.filters.getdf': [1, 3, 5 , 7], #only works for lists
        'tardis.tardis_portal.filters.x': [2, 4 , 6, 8],
        'tardis.tardis_portal.filters.y': [11, 14, 15, 35],
    }

    c = Context({})
    try:
        experiment = Experiment.safe.get(request.user, experiment_id)
    except PermissionDenied:
        return return_response_error(request)
    except Experiment.DoesNotExist:
        return return_response_not_found(request)

    (exp_schema, dset_schema, dfile_schema) = graphit.load_graph_schemas()

    # precompute and reuse
    dsets = list(Dataset.objects.filter(experiments=experiment))
    #logger.debug("dsets=%s" % dsets)
    #logger.debug("foo1")
    dset_pset_info = {}
    for dset in dsets:
        #logger.debug("dset=%s" % dset)
        #logger.debug("dset.id=%s" % dset.id)
        dset_pset = dset.getParameterSets() \
                    .filter(schema=dset_schema)
        #logger.debug("dset_pset=%s" % dset_pset)

        #if len(dset_pset):
        dset_pset_info[dset.id] = [x.id for x in dset_pset]
    #logger.debug("foo2")
    logger.debug("dset_pset_info=%s" % dset_pset_info)

    dset_p_info = {}
    for d in dset_pset_info.values():
        #logger.debug("d=%s" % d)
        for p in d:
            #logger.debug("p=%s" % p)
            try:
                dset_params = DatasetParameter.objects.filter(
                                parameterset__id=p)
            except DatasetParameter.DoesNotExist:
                pass

            #logger.debug("dset_params=%s" % dset_params)
            #logger.debug("p.id=%s" % p.id)
            dset_p_info[p] = dset_params

    logger.debug("dset_p_info=%s" % dset_p_info)
    logger.debug("dsets=%s" % len(dsets))
    errors = {}
    # TODO: check order of loops so that longests loops are not repeated
    for graph_exp_pset in experiment.getParameterSets().filter(schema=exp_schema):
        errors = ''
        logger.debug("graph_exp_pset=%s" % graph_exp_pset)
        try:
            exp_params = ExperimentParameter.objects.filter(
                parameterset=graph_exp_pset)
        except ExperimentParameter.DoesNotExist:
            continue

        try:
            (exp_name, value_keys, value_dict, graph_info, checksum) = \
                graphit._get_graph_data(exp_params)
        except ValueError, e:
            logger.error(e)
            display_html.append(render_error(e))
            continue
        except ExperimentParameter.DoesNotExist, e:
            logger.error(e)
            display_html.append(render_error(e))
            continue

        logger.debug("dsets=%s" % len(dsets))
        logger.debug("checksum=%s" % checksum)
        if len(dsets) == checksum:
            logger.debug("already computed")
            try:
                checksum_pn = ParameterName.objects.get(schema=exp_schema, name=CHECKSUM_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                continue
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
                continue

            try:
                ep = ExperimentParameter.objects.get(
                    parameterset=graph_exp_pset,
                    name=checksum_pn)
            except ExperimentParameter.DoesNotExist:
                # if cannot load parameter, then recalculate anyway
                pass
            except MultipleObjectsReturned:
                logger.error("multiple hrmc experiment schemas returned")
                continue
            else:
                try:
                    pn = ParameterName.objects.get(schema=exp_schema, name=PLOT_NAME)
                except ParameterName.DoesNotExist:
                    logger.error(
                        "ParameterName is missing %s parameter" % PLOT_NAME)
                    continue
                except MultipleObjectsReturned:
                    logger.error(
                        "ParameterName is multiple %s parameters" % PLOT_NAME)
                    continue

                try:
                    ep = ExperimentParameter.objects.get(
                        parameterset=graph_exp_pset,
                        name=pn)
                except ExperimentParameter.DoesNotExist:
                    # if cannot load param, then continue anyway
                    pass
                except MultipleObjectsReturned:
                    logger.error("multiple hrmc experiment schemas returned")
                    continue
                else:
                    res = ''
                    with open(ep.string_value, 'r') as f:
                        res += f.read()
                    display_html.append(res)
                    continue
        else:
            logger.debug("new plot generated")
            # TODO: clean up old cached version of the file

        plots = []
        logger.debug("dset_p_info=%s" % dset_p_info)

        graph_val_dict = defaultdict(dict)

        for dset in dsets:
            logger.debug("dset=%s" % dset)

            for m, key in enumerate(value_keys):
                logger.debug("key=%s" % key)
                graph_vals = graph_val_dict[m]
                #graph_vals = defaultdict(list)

                #for dset in Dataset.objects.filter(experiments=experiment):
                #logger.debug("dset=%s" % dset)
                #dset_pset = dset.getParameterSets() \
                #    .filter(schema=dset_schema)

                #logger.debug("dset_pset_info=%s" % dset_pset_info)
                for graph_dset_pset in dset_pset_info[dset.id]:
                    #for graph_dset_pset in dset_pset:
                        logger.debug("graph_dset_pset=%s" % graph_dset_pset)
                        # try:
                        #     dset_params = DatasetParameter.objects.filter(
                        #         parameterset=graph_dset_pset)
                        # except DatasetParameter.DoesNotExist:
                        #     continue

                        dset_params = []

                        dset_params = dset_p_info[graph_dset_pset]

                        # for d in graph_dset_pset:
                        #     logger.debug("d=%s" % d)
                        #     logger.debug("d.id=%s" % d.id)
                        #     dset_params.append(dset_p_info[d.id])

                        #logger.debug("dset_params=%s" % dset_params)
                        #logger.debug("exp_name=%s" % exp_name)

                        #logger.debug("graph_vals=%s" % graph_vals)
                        try:
                            graph_vals = graphit._match_key_vals(graph_vals, dset_params, value_keys[m], exp_name, functions)
                        except ValueError, e:
                            errors = str(e)
                            logger.error(e)
                            continue
                        #logger.debug("graph_vals=%s" % graph_vals)

                    #logger.debug("graph_vals=%s" % graph_vals)

                try:
                    graph_vals.update(graphit._match_constants(value_keys[m], value_dict,  functions))
                except ValueError, e:
                    logger.error(e)
                    errors = str(e)
                    continue

            graph_val_dict[m] = graph_vals

        logger.debug("graph_val_dict=%s" % graph_val_dict)
        plots = []
        for k in graph_val_dict:
            try:
                plot = graphit.reorder_keys(graph_val_dict[k], graph_info, value_keys[k], exp_name)
            except ValueError, e:
                logger.error(e)
                errors = str(e)
                continue
            logger.debug("plot=%s" % plot)
            plots.append(plot)

        logger.debug(("plots=%s" % plots))

        def detected3d(plots):
            threed = False
            for plot in plots:
                logger.debug("plot=%s" % plot)
                if len(plot) > 3:
                    threed = True
                    break
            return threed

        if detected3d(plots):
            logger.debug("3d")
            #g = D3()
            g = MatPlotLib()
        else:
            g = Flot()

        # pfile = None
        # try:
        # except Exception, e:
        #     logger.error(e)
        #     errors = "Cannot render graph"
        # else:
        #     if not pfile:
        #         errors = "Cannot render graph

        pfile = g.graph(graph_info, exp_schema, graph_exp_pset, PLOT_NAME, plots)


        logger.debug("pfile=%s" % pfile)
        if pfile:
            # TODO: return encode rather than create Parameters as all
            # backends should do the same thing.
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=exp_schema, name=PLOT_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
                return None

            logger.debug("ready to save")

            try:
                checksum_pn = ParameterName.objects.get(schema=exp_schema, name=CHECKSUM_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
                return None

            try:
                ep = ExperimentParameter.objects.get(
                    parameterset=graph_exp_pset,
                    name=checksum_pn)
            except ExperimentParameter.DoesNotExist:
                ep = ExperimentParameter(
                    parameterset=graph_exp_pset,
                    name=checksum_pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc experiment schemas returned")
                return None
            ep.numerical_value = len(dsets)
            #ep.numerical_value = 0

            ep.save()

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
            ep.string_value = pfile
            ep.save()

            if errors:
                display_html.append(render_error(errors))
            else:
                res = ''
                with open(pfile, 'r') as f:
                    res += f.read()
                display_html.append(res)

    c['display_html'] = display_html
    return HttpResponse(render_response_index(request, "hrmc_views/graph_view.html", c))


def render_error(msg):
    context = {'error': msg}
    template = get_template("hrmc_views/error.html")
    c = Context(context)
    content = template.render(c)
    logger.debug("content=%s" % content)
    return content



def get_dset_graph(request, dset_id):
    display_html = []

    # TODO: should be read from domain-specific filter plugins
    functions = {
        'tardis.tardis_portal.filters.getdf': [1, 3, 5 , 7], #only works for lists
        'tardis.tardis_portal.filters.x': [2, 4 , 6, 8],
        'tardis.tardis_portal.filters.y': [11, 14, 15, 35],
    }

    c = Context({})
    try:
        dataset = Dataset.objects.get(id=dset_id)
    except PermissionDenied:
        return return_response_error(request)
    except Dataset.DoesNotExist:
        return return_response_not_found(request)

    (exp_schema, dset_schema, dfile_schema) = graphit.load_graph_schemas()

    dfiles = list(Dataset_File.objects.filter(dataset=dataset))
    logger.debug("len(dfiles)=%s" % len(dfiles))

    errors = ""
    # TODO: check order of loops so that longests loops are not repeated
    for graph_dset_pset in dataset.getParameterSets().filter(schema=dset_schema):
        logger.debug("graph_dset_pset=%s" % graph_dset_pset)
        try:
            dset_params = DatasetParameter.objects.filter(
                parameterset=graph_dset_pset)
        except DatasetParameter.DoesNotExist:
            continue

        try:
            (dset_name, value_keys, value_dict, graph_info, checksum) = \
                graphit._get_graph_data(dset_params)
        except ValueError, e:
            logger.error(e)
            continue

        if not value_keys:
            continue

        if len(dfiles) == checksum:
            logger.debug("already computed")
            try:
                checksum_pn = ParameterName.objects.get(schema=dset_schema, name=CHECKSUM_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                continue
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
                continue

            try:
                ep = DatasetParameter.objects.get(
                    parameterset=graph_dset_pset,
                    name=checksum_pn)
            except DatasetParameter.DoesNotExist:
                logger.warn("cannot load dataset paramter for checksum")
                # if cannot load parameter, then recalculate anyway
                pass
            except MultipleObjectsReturned:
                logger.error("multiple hrmc dset schemas returned")
                continue
            else:
                try:
                    pn = ParameterName.objects.get(schema=dset_schema, name=PLOT_NAME)
                except ParameterName.DoesNotExist:
                    logger.error(
                        "ParameterName is missing %s parameter" % PLOT_NAME)
                    continue
                except MultipleObjectsReturned:
                    logger.error(
                        "ParameterName is multiple %s parameters" % PLOT_NAME)
                    continue
                logger.debug("pn=%s" % pn)
                logger.debug("dset_name=%s" % dset_name)
                logger.debug("graph_dset_pset=%s" % graph_dset_pset)
                try:
                    dp = DatasetParameter.objects.get(
                        parameterset=graph_dset_pset,
                        name=pn)
                except DatasetParameter.DoesNotExist:
                    # if cannot load param, then continue anyway
                    logger.warn("cannot load dataset parameter")
                    pass
                except MultipleObjectsReturned:
                    logger.error("multiple hrmc dset schemas returned")
                    continue
                else:
                    res = ''
                    with open(dp.string_value, 'r') as f:
                        res += f.read()
                    display_html.append(res)
                    continue
        else:
            logger.debug("new plot generated")
            # TODO: clean up old cached version of the file

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
                    except DatafileParameter.DoesNotExist, e:
                        logger.error(e)
                        errors = str(e)
                        continue

                    logger.debug("dset_name=%s" % dset_name)

                    logger.debug("1graph_vals=%s" % graph_vals)
                    try:
                        graph_vals = graphit._match_key_vals(graph_vals, dfile_params, key, dset_name, functions)
                    except ValueError, e:
                        logger.error(e)
                        errors = str(e)
                        continue
                    logger.debug("2graph_vals=%s" % graph_vals)

                logger.debug("3graph_vals=%s" % graph_vals)

            try:
                graph_vals.update(graphit._match_constants(key, value_dict, functions))
            except ValueError, e:
                logger.error(e)
                errors = str(e)
                continue

            logger.debug("4graph_vals=%s" % graph_vals)

            try:
                plot = graphit.reorder_keys(graph_vals, graph_info, key, dset_name)
            except ValueError, e:
                logger.error(e)
                continue
            logger.debug("plot=%s" % plot)

            plots.append(plot)

        g = Flot()
        pfile = None
        try:
            pfile = g.graph(graph_info, dset_schema, graph_dset_pset, PLOT_NAME, plots)
        except Exception, e:
            logger.error(e)
            errors = "Cannot render graph"
        else:
            if not pfile:
                errors = "Cannot render graph"

        # logger.debug(("plots=%s" % plots))
        # mtp = MatPlotLib()
        # pfile = mtp.graph(graph_info, dset_schema, graph_dset_pset, PLOT_NAME, plots)

        if pfile:

            try:
                checksum_pn = ParameterName.objects.get(schema=dset_schema, name=CHECKSUM_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
                return None

            try:
                dp = DatasetParameter.objects.get(
                    parameterset=graph_dset_pset,
                    name=checksum_pn)
            except DatasetParameter.DoesNotExist:
                dp = DatasetParameter(
                    parameterset=graph_dset_pset,
                    name=checksum_pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc dataset schemas returned")
                return None
            dp.numerical_value = len(dfiles)
            #dp.numerical_value = 0

            dp.save()


            # TODO: return encode rather than create Parameters as all
            # backends should do the same thing.
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=dset_schema, name=PLOT_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % PLOT_NAME)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % PLOT_NAME)
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
            ep.string_value = pfile
            ep.save()

            if errors:
                display_html.append(render_error(errors))
            else:
                res = ''
                with open(pfile, 'r') as f:
                    res += f.read()
                display_html.append(res)

    c['display_html'] = display_html
    return HttpResponse(render_response_index(request, "hrmc_views/graph_view.html", c))


def test(request):
    c = Context({})
    return HttpResponse(render_response_index(request, "hrmc_views/test.html", c))




