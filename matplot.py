import logging
import tempfile
import os
import base64

from .common import GraphBackend
from django.conf import settings


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


class MatPlotLib(GraphBackend):

    def graph(self, graph_info, schema, parameter_set, plot_name,  plots):

        #fig = matplotlib.pyplot.figure()
        fig = matplotlib.pyplot.gcf()
        #fig.set_size_inches(15.5, 13.5)
        print "plots=%s" % plots
        colors = ['blue', 'red']
        ax = None
        for i, plot in enumerate(plots):
            print "plot=%s" % plot
            vals = []
            for j, coord in enumerate(plot):
                if not j:
                    if plot[0]:
                        label = str(plot[0])
                    else:
                        label = None
                    continue
                print "coord=%s" % str(coord)
                vals.append(coord[1])

            print "vals=%s" % vals

            if not ax:
                if len(vals) == 3:
                    ax = Axes3D(fig)
                    #ax = fig.gca(projection='3d')
                else:
                    ax = fig.add_subplot(111, frame_on=False)

            if vals:
                ax.scatter(*vals, color=colors[i],  marker="x", label=label)

        if ax:
            if 'axes' in graph_info:
                pyplot.xlabel(graph_info['axes'][0])
                pyplot.ylabel(graph_info['axes'][1])

            pyplot.grid(True)
            #legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
            ax.legend()
            #pyplot.xlim(xmin=0)

            pfile = tempfile.mktemp()
            logger.debug("pfile=%s" % pfile)

            matplotlib.pyplot.savefig("%s.png" % pfile, dpi=100)

            with open("%s.png" % pfile) as pf:
                read = pf.read()
                encoded = base64.b64encode(read)
                matplotlib.pyplot.close()

            # TODO: return encode rather than create Parameters as all
            # backends should do the same thing.
            try:
                # FIXME: need to select on parameter set here too
                pn = ParameterName.objects.get(schema=schema, name=plot_name)
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
                    parameterset=parameter_set,
                    name=pn)
            except ExperimentParameter.DoesNotExist:
                ep = ExperimentParameter(
                    parameterset=parameter_set,
                    name=pn)
            except MultipleObjectsReturned:
                logger.error("multiple hrmc experiment schemas returned")
                return None
            ep.string_value = encoded
            ep.save()

            display_image = ep
        else:
            logger.debug("one or more files unavailable")
            return None
        logger.debug("made display_image  %s" % display_image)
        return display_image