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
import os
import re

from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.http import HttpResponse
from django.template import Context
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned

from tardis.tardis_portal.auth import decorators as authz
from tardis.tardis_portal.models import Dataset
from tardis.tardis_portal.shortcuts import get_experiment_referer
from tardis.tardis_portal.shortcuts import render_response_index
from tardis.tardis_portal.models import Schema, DatasetParameterSet
from tardis.tardis_portal.models import ParameterName, DatasetParameter
from tardis.tardis_portal.models import Dataset_File

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

# TODO: contextual view should pass info about DATASET view to its view
HRMC_DATASET_SCHEMA = "http://rmit.edu.au/schemas/hrmcdataset"

@authz.dataset_access_required
def view_full_dataset(request, dataset_id):
    """Displays a HRMC Dataset as a single scatter plot of x,y values
    from grfinalXX.dat and gerr.dat files

    Requires BDPMytardis with single

    Settings for this view:
    INSTALLED_APPS += ("tardis.apps.hrmc_views",)
    DATASET_VIEWS = [("http://rmit.edu.au/schemas/hrmcdataset",
                      "tardis.apps.hrmc_views.views.view_full_dataset"),]

    """
    logger.debug("got to hrmc views")
    dataset = Dataset.objects.get(id=dataset_id)

    # FIXME: as single image, can remove this
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

    display_images = []
    image_to_show = get_image_to_show(dataset)
    if image_to_show:
        display_images.append(image_to_show)

    c = Context({
        'dataset': dataset,
        'datafiles': get_datafiles_page(),
        'parametersets': dataset.getParameterSets()
                                .exclude(schema__hidden=True),
        'has_download_permissions':
            authz.has_dataset_download_access(request, dataset_id),
        'has_write_permissions':
            authz.has_dataset_write(request, dataset_id),
        'from_experiment': \
            get_experiment_referer(request, dataset_id),
        'other_experiments': \
            authz.get_accessible_experiments_for_dataset(request, dataset_id),
        'display_images': display_images,
    })
    return HttpResponse(render_response_index(
        request, 'hrmc_views/view_full_dataset.html', c))


def get_image_to_show(dataset):

    try:
        sch = Schema.objects.get(namespace__exact=HRMC_DATASET_SCHEMA)
    except Schema.DoesNotExist:
        logger.debug("no hrmc schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc schemas returned")
        return None
    #FIXME: possible that more than once dataset can appear, so pick only one.
    try:
        ps = DatasetParameterSet.objects.get(schema=sch, dataset=dataset)
    except DatasetParameterSet.DoesNotExist:
        logger.debug("datset parameterset not found")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple dataset paramter sets returned")
        # NB: If admin tool added additional param set,
        # we know that all data will be the same for this schema
        # so can safely delete any extras we find.
        pslist = [x.id for x in DatasetParameterSet.objects.filter(schema=sch,
            dataset=dataset)]
        logger.debug("pslist=%s" % pslist)
        DatasetParameterSet.objects.filter(id__in=pslist[1:]).delete()
        ps = DatasetParameterSet.objects.get(id=pslist[0])


    logger.debug("found ps=%s" % ps)
    for param in DatasetParameter.objects.filter(parameterset=ps):
        logger.debug("param=%s" % param)
        logger.debug("param.name=%s" % param.name)

        if "plot" in param.name.name:
            logger.debug("found existing image")
            return param

    logger.debug("building plots")
    display_image = None
    grfinal_file = None
    grexp_file = None
    for df in Dataset_File.objects.filter(dataset=dataset):
        logger.debug("testing %s" % df.filename)
        if "grexp.dat" in df.filename:
            grexp_file = df
        if df.filename.startswith("grfinal"):
            grfinal_file = df
    if grexp_file and grfinal_file and is_matplotlib_imported:
        logger.debug("found both")
        fp = grexp_file.get_absolute_filepath()
        grexp_buff = []
        with open(fp) as f:
            for d in f.read():
                grexp_buff.append(d)

        fp = grfinal_file.get_absolute_filepath()
        grfinal_buff = []
        with open(fp) as f:
            for d in f.read():
                grfinal_buff.append(d)

        mat = re.compile("grfinal(\d+)\.dat").match(grfinal_file.filename)
        if mat:
            grlabel = "Calculation %s" % mat.group(1)
        else:
            grlabel = grfinal_file.filename

        xs = []
        ys = []
        for l in ''.join(grfinal_buff).split("\n"):
            #logger.debug("l=%s" % l)
            if l:
                x, y = l.split()
                xs.append(float(x))
                ys.append(float(y))
        matplotlib.pyplot.plot(xs, ys, color="blue", markeredgecolor = 'blue', marker="D", label=str(grlabel))

        xs = []
        ys = []
        for l in ''.join(grexp_buff).split("\n"):
            #logger.debug("l=%s" % l)
            if l:
                x, y = l.split()
                xs.append(float(x))
                ys.append(float(y))
        matplotlib.pyplot.plot(xs, ys, color="red", markeredgecolor = 'red', marker="o", label="Experiment")

        import tempfile
        pfile = tempfile.mktemp()
        logger.debug("pfile=%s" % pfile)

        pyplot.xlabel("r (Angstroms)")
        pyplot.ylabel("g(r)")
        pyplot.grid(True)
        #legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
        legend()
        pyplot.xlim(xmin=0)

        fig = matplotlib.pyplot.gcf()
        fig.set_size_inches(15.5, 13.5)
        matplotlib.pyplot.savefig("%s.png" % pfile, dpi=100)

        with open("%s.png" % pfile) as pf:
            read = pf.read()
            encoded = base64.b64encode(read)
            matplotlib.pyplot.close()
        try:
            pn = ParameterName.objects.get(schema=sch, name="plot")
        except DatasetParameterSet.DoesNotExist:
            logger.error("schema is missing plot parameter")
            return None
        except MultipleObjectsReturned:
            logger.error("schema is multiple plot parameters")
            return None

        logger.debug("ready to save")

        dfp = DatasetParameter(parameterset=ps,
                                        name=pn)
        dfp.string_value = encoded
        dfp.save()
        display_image = dfp
    else:
        logger.debug("one or more files unavailable")
        return None
    logger.debug("made display_image  %s" % display_image)
    return display_image

