import logging
import tempfile
import os
import base64

from .common import GraphBackend
from django.template import Context, Template
from django.template.loader import get_template

from django.conf import settings

from django.utils.safestring import mark_safe


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


from django.core.urlresolvers import reverse




# import and configure matplotlib library
try:
    os.environ['HOME'] = settings.MATPLOTLIB_HOME
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as pyplot
    from matplotlib.pyplot import legend
    is_matplotlib_imported = True
    from mpl_toolkits.mplot3d import Axes3D
except ImportError:
    is_matplotlib_imported = False

logger = logging.getLogger(__name__)

MARKER_LIST = ('x', '+', 'o')
COLOR_LIST = ('b', 'g', 'r', 'c', 'm', 'y', 'k')


class MatPlotLib(GraphBackend):

    def graph(self, graph_info, schema, parameter_set, plot_name,  plots):

        import itertools
        markiter = itertools.cycle(MARKER_LIST)
        coloriter = itertools.cycle(COLOR_LIST)

        #fig = matplotlib.pyplot.figure()
        fig = matplotlib.pyplot.gcf()
        #fig.set_size_inches(15.5, 13.5)
        logger.debug("plots=%s" % plots)
        if 'type' in graph_info:
            graph_type = graph_info['type']
        else:
            graph_type = "scatter"
        ax = None
        for i, plot in enumerate(plots):
            logger.debug("plot=%s" % plot)
            vals = []
            for j, coord in enumerate(plot):
                if not j:
                    if plot[0]:
                        label = str(plot[0])
                    else:
                        label = None
                    continue
                logger.debug("coord=%s" % str(coord))
                vals.append(coord[1])

            logger.debug("vals=%s" % vals)

            if not ax:
                if len(vals) == 3:
                    ax = Axes3D(fig)
                    #ax = fig.gca(projection='3d')
                else:
                    ax = fig.add_subplot(111, frame_on=False)

            if vals:
                logger.debug("vals=%s" % vals)
                #xs, ys = vals
                if 'legends' in graph_info:
                    try:
                        l = graph_info['legends'][i]
                    except IndexError, e:
                        logger.warn(e)
                        l = ""
                else:
                    l = ""
                logger.debug("legend=%s" % l)

                point_col = coloriter.next()
                # Create a subplot.
                try:
                    if graph_type == "line":
                        matplotlib.pyplot.plot(*vals, color=point_col,
                            markeredgecolor=point_col, marker=markiter.next(),
                            label=l)
                    else:
                        ax.scatter(*vals, color=point_col,
                            marker=markiter.next(), label=l)

                except ValueError, e:
                    # TODO: handle errors properly
                    logger.error(e)
                    continue
                except NameError, e:
                    # TODO: handle errors properly
                    logger.error(e)
                    continue

        if ax:
            if 'axes' in graph_info:
                pyplot.xlabel(graph_info['axes'][0])
                pyplot.ylabel(graph_info['axes'][1])

            pyplot.grid(True)
            #legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
            legend()
            #pyplot.xlim(xmin=0)

            from os.path import exists, join
            from os import makedirs
            from uuid import uuid4 as uuid

            filename = str(uuid())
            dirname = settings.METADATA_STORE_PATH
            subdir1 = filename[0:2]
            subdir2 = filename[2:4]
            dirname = join(dirname, 'metadata-cache', subdir1, subdir2)
            pfile = join(dirname, filename)
            logger.debug("pfile=%s" % pfile)
            try:
                if not exists(dirname):
                    makedirs(dirname)
                matplotlib.pyplot.savefig("%s.png" % pfile, dpi=100)
            except IOError, e:
                logger.error(e)
                matplotlib.pyplot.close()
                return None
            matplotlib.pyplot.close()
            IMAGE_NAME = "image"
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=schema, name=IMAGE_NAME)
            except ParameterName.DoesNotExist:
                logger.error(
                    "ParameterName is missing %s parameter" % IMAGE_NAME)
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "ParameterName is multiple %s parameters" % IMAGE_NAME)
                return None
            logger.debug("now ready to save")
            try:
                ep = ExperimentParameter.objects.get(
                    parameterset=parameter_set,
                    name=pn)
            except ExperimentParameter.DoesNotExist:
                ep = ExperimentParameter(
                    parameterset=parameter_set,
                    name=pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc experiment schemas returned")
                return None
            ep.string_value = "%s.png" % pfile
            ep.save()

            parset = type(ep.parameterset).__name__
            viewname = ''
            if parset == 'DatafileParameterSet':
                viewname = 'tardis.tardis_portal.views.load_datafile_image'
            elif parset == 'DatasetParameterSet':
                viewname = 'tardis.tardis_portal.views.load_dataset_image'
            elif parset == 'ExperimentParameterSet':
                viewname = 'tardis.tardis_portal.views.load_experiment_image'
            value = "<a href='%s' target='_blank'><img src='%s' /></a>" % \
                 (reverse(viewname=viewname,
                 args=[ep.id]),
                 reverse(viewname=viewname,
                 args=[ep.id]))
            context = {
                'datafile': mark_safe(value)}

            logger.debug("graph_info=%s" % graph_info)
            if 'axes' in graph_info:
                context['xaxislabel'] = graph_info['axes'][0]
                context['yaxislabel'] = graph_info['axes'][1]
            if 'precision' in graph_info:
                context['xaxisprecision'] = graph_info['precision'][0]
                context['yaxisprecision'] = graph_info['precision'][1]
            else:
                context['xaxisprecision'] = 0
                context['yaxisprecision'] = 2

            logger.debug("context=%s" % context)

            template = get_template("hrmc_views/image.html")
            c = Context(context)
            content = template.render(c)
            logger.debug("content=%s" % content)

            from os.path import exists, join
            from os import makedirs
            from uuid import uuid4 as uuid

            filename = str(uuid())
            dirname = settings.METADATA_STORE_PATH
            subdir1 = filename[0:2]
            subdir2 = filename[2:4]
            dirname = join(dirname, 'metadata-cache', subdir1, subdir2)
            pfile = join(dirname, filename)
            logger.debug("pfile=%s" % pfile)

            try:
                if not exists(dirname):
                    makedirs(dirname)

                with open(pfile, 'w') as f:
                    f.write(content)

            except IOError,e:
                logger.error(e)
                return None

            return pfile

            return content

        else:
            logger.debug("one or more files unavailable")
            return None
        return None