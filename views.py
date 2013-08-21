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

    display_images = []
    image_to_show = get_exp_images_to_show1(experiment)
    if image_to_show:
        display_images.append(image_to_show)
    image_to_show = get_exp_images_to_show2(experiment)
    if image_to_show:
        display_images.append(image_to_show)

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
            logger.debug("No tab for %s" % app)
            pass

    c['apps'] = zip(appurls, appnames)

    return HttpResponse(render_response_index(request, template_name, c))


@authz.dataset_access_required
def view_full_dataset(request, dataset_id):
    """Displays a HRMC Dataset as a single scatter plot of x,y values
    from psdXX.dat and gerr.dat files

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

    try:
        sch = Schema.objects.get(namespace__exact=HRMC_DATASET_SCHEMA)
    except Schema.DoesNotExist:
        logger.debug("no hrmc schema")
        return None
    # TODO: check schema contains correct paramters
    except MultipleObjectsReturned:
        logger.error("multiple hrmc schemas returned")
        return None
    try:
        dps = DatasetParameterSet.objects.get(schema=sch, dataset=dataset)
    except DatasetParameterSet.DoesNotExist:
        logger.debug("datset parameterset not found")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple dataset paramter sets returned")
        return None

    display_images = []

    # TODO, FIXME: Each refresh of page triggers recalculation of graphs
    # to allow newly arrived datafiles to be integrated into the plots.
    # However, this is a potential DoS vector as new tardis store files are
    # created
    # with each refresh.  This is made worse if experiment/dataset is public.
    # Solutions:
    # - only set HRMC_DATA_SCHEMA schema once all data
    #   has arrived, and then only generate the graphs once at that point and
    #   only read after that point.  Waiting on contextual view ability to set
    #   parametersets on existing datasets.
    # - allow creation of new files up until experiment is public, then set
    #   just last version.

    # plot psd.dat and PSD_exp.dat versus r
    image_to_show = get_dataset_image_to_show(dataset,
        sch, dps, hrmc_plot_name="plot1",
        filename1="psd.dat", filename2="PSD_exp.dat",
        file_label1="psd", file_label2="PSD_exp",
        x_label="r (Angstroms)",
        y_label="g(r)")
    if image_to_show:
        display_images.append(image_to_show)

    # plot data_grfinal.dat and input_gr.dat versus r
    image_to_show = get_dataset_image_to_show(dataset,
        sch, dps, hrmc_plot_name="plot2",
        filename1="data_grfinal.dat", filename2="input_gr.dat",
        file_label1="data_grfinal", file_label2="input_gr",
        x_label="r (Angstroms)",
        y_label="g(r)")
    if image_to_show:
        display_images.append(image_to_show)

    upload_method = getattr(settings, "UPLOAD_METHOD", "uploadify")

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
        'default_organization':
            getattr(settings, 'DEFAULT_ARCHIVE_ORGANIZATION', 'classic'),
        'default_format':
            getattr(settings, 'DEFAULT_ARCHIVE_FORMATS', ['zip', 'tar'])[0],
        'display_images': display_images,

    })
    return HttpResponse(render_response_index(
        request, 'hrmc_views/view_full_dataset.html', c))


def get_exp_images_to_show1(experiment):
    """
    Graph iteration number versus PSD criterion value ( a scatter
        plot with M points per iteration number)


    """
    # check we are setup correctly.
    try:
        Schema.objects.get(
            namespace__exact=HRMC_DATASET_SCHEMA,
            type=Schema.DATASET)
    except Schema.DoesNotExist:
        logger.debug("no hrmc dataset schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc dataset schemas returned")
        return None

    try:
        hrmc_experiment_schema = Schema.objects.get(
            namespace__exact=HRMC_EXPERIMENT_SCHEMA,
            type=Schema.EXPERIMENT)
    except Schema.DoesNotExist:
        logger.debug("no hrmc experiment schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc experiment schemas returned")
        return None

    try:
        hrmc_output_dataset_schema = Schema.objects.get(
            namespace__exact=HRMC_OUTPUT_DATASET_SCHEMA,
            type=Schema.DATASET)
    except Schema.DoesNotExist:
        logger.debug("no hrmc dataset schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc dataset schemas returned")
        return None

    try:
        eps = ExperimentParameterSet.objects.get(
            schema=hrmc_experiment_schema, experiment=experiment)
    except ExperimentParameterSet.DoesNotExist:
        logger.debug("exp parameterset not found")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple experiment paramter sets returned")
        # NB: If admin tool added additional param set,
        # we know that all data will be the same for this schema
        # so can safely delete any extras we find.
        pslist = [x.id for x in ExperimentParameterSet.objects.filter(
            schema=hrmc_experiment_schema,
            experiment=experiment)]
        logger.debug("pslist=%s" % pslist)
        ExperimentParameterSet.objects.filter(id__in=pslist[1:]).delete()
        eps = ExperimentParameterSet.objects.get(id=pslist[0])

    try:
        pn = ParameterName.objects.get(
            schema=hrmc_experiment_schema, name="plot1")
    except ParameterName.DoesNotExist:
        logger.error("schema is missing plot parameter")
        return None
    except MultipleObjectsReturned:
        logger.error("schema is multiple plot parameters")
        return None
    logger.debug("pn=%s" % pn)

    CRITERION_FILE = "criterion.txt"
    DS_NAME_SEP = "_"
    ys = []
    xs = []
    for df in experiment.get_datafiles().filter(filename=CRITERION_FILE):
        logger.debug("df=%s" % df)
        try:
            DatasetParameterSet.objects.get(
                schema=hrmc_output_dataset_schema, dataset=df.dataset)
        except DatasetParameterSet.DoesNotExist:
            logger.debug("criterion file found in non hrmc dataset")
            continue
        except MultipleObjectsReturned:
            logger.error("multiple dataset paramter sets returned")
        ds_desc = df.dataset.description
        logger.debug("ds_desc=%s" % ds_desc)
        ds_desc = ds_desc.split(DS_NAME_SEP)
        if len(ds_desc) == 3:
            try:
                x = int(ds_desc[0])
            except IndexError, e:
                logger.error("problem parsing %s:%s" % (ds_desc, e))
                continue
            except ValueError, e:
                logger.error("problem parsing %s:%s" % (ds_desc, e))
                continue
        else:
            logger.error("found criterion file in input data")
            continue
        logger.debug("x=%s" % x)
        try:
            fp = df.get_file()
        except ValueError:
            logger.warn("file has not been verified")
            continue
            # can fail if datafile has been upload but has not been verified

        try:
            criterion = float(fp.read())
        except IOError, e:
            logger.error(e)
            continue
        except Exception, e:
            logger.error(e)
            continue
        logger.debug("criterion=%s" % criterion)
        ys.append(criterion)
        xs.append(x)

    if len(ys) and len(xs):
        fig = matplotlib.pyplot.gcf()
        fig.set_size_inches(15.5, 13.5)
        ax = fig.add_subplot(111, frame_on=False)
        logger.debug("ready to save")
        try:
            ep = ExperimentParameter.objects.get(
                parameterset=eps,
                name=pn)
        except ExperimentParameter.DoesNotExist:
            ep = ExperimentParameter(
                parameterset=eps,
                name=pn)
        except MultipleObjectsReturned:
            logger.error("multiple hrmc experiment schemas returned")
            return None

        # Create a subplot.
        try:
            ax.scatter(xs, ys, color="blue",  marker="x", label="criterion")
        except ValueError, e:
            logger.error(e)
            return None
        pfile = tempfile.mktemp()
        logger.debug("pfile=%s" % pfile)

        pyplot.xlabel("iteration")
        pyplot.ylabel("criterion")
        pyplot.grid(True)
        #legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
        legend()
        pyplot.xlim(xmin=0)

        matplotlib.pyplot.savefig("%s.png" % pfile, dpi=100)

        with open("%s.png" % pfile) as pf:
            read = pf.read()
            encoded = base64.b64encode(read)
            matplotlib.pyplot.close()

        ep.string_value = encoded
        ep.save()

        return ep
    else:
        return None


def get_exp_images_to_show2(experiment):
    """
    For the final iteration of a run, graph step number versus ERRgr*wf
    from the data_errors.dat for each calculation (scatter of N values
        per step number)
    """

    import itertools
    markiter = itertools.cycle(MARKER_LIST)
    coloriter = itertools.cycle(COLOR_LIST)

    try:
        Schema.objects.get(
            namespace__exact=HRMC_DATASET_SCHEMA,
            type=Schema.DATASET)
    except Schema.DoesNotExist:
        logger.debug("no hrmc dataset schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc dataset schemas returned")
        return None

    try:
        hrmc_experiment_schema = Schema.objects.get(
            namespace__exact=HRMC_EXPERIMENT_SCHEMA,
            type=Schema.EXPERIMENT)
    except Schema.DoesNotExist:
        logger.debug("no hrmc experiment schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc experiment schemas returned")
        return None

    try:
        hrmc_output_dataset_schema = Schema.objects.get(
            namespace__exact=HRMC_OUTPUT_DATASET_SCHEMA,
            type=Schema.DATASET)
    except Schema.DoesNotExist:
        logger.debug("no hrmc dataset schema")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple hrmc dataset schemas returned")
        return None

    try:
        eps = ExperimentParameterSet.objects.get(
            schema=hrmc_experiment_schema, experiment=experiment)
    except ExperimentParameterSet.DoesNotExist:
        logger.debug("exp parameterset not found")
        return None
    except MultipleObjectsReturned:
        logger.error("multiple experiment paramter sets returned")
        # NB: If admin tool added additional param set,
        # we know that all data will be the same for this schema
        # so can safely delete any extras we find.
        pslist = [x.id for x in ExperimentParameterSet.objects.filter(
            schema=hrmc_experiment_schema,
            experiment=experiment)]
        logger.debug("pslist=%s" % pslist)
        ExperimentParameterSet.objects.filter(id__in=pslist[1:]).delete()
        eps = ExperimentParameterSet.objects.get(id=pslist[0])

    ys = []
    xs = []

    fig = matplotlib.pyplot.gcf()
    fig.set_size_inches(15.5, 13.5)
    matplotlib.axes.set_default_color_cycle(['r', 'g', 'b', 'c'])
    ax = fig.add_subplot(111, frame_on=False)
    re_dbl_fort = re.compile(r'(\d*\.\d+)[dD]([-+]?\d+)')

    for df in experiment.get_datafiles() \
        .filter(filename=DATA_ERRORS_FILE) \
        .filter(dataset__description__startswith="final"):
        logger.debug("df=%s" % df)
        try:
            DatasetParameterSet.objects.get(
                schema=hrmc_output_dataset_schema,
                dataset=df.dataset)
        except DatasetParameterSet.DoesNotExist:
            logger.debug("criterion file found in non hrmc dataset")
            continue
        except MultipleObjectsReturned:
            logger.error("multiple dataset paramter sets returned")
        ds_desc = df.dataset.description
        logger.debug("ds_desc=%s" % ds_desc)
        ds_desc = ds_desc.split(DS_NAME_SEP)
        try:
            fp = df.get_file()
        except ValueError:
            # if file has not been verified
            continue
        xs = []
        ys = []
        for i, line in enumerate(fp):
            if i == 0:
                continue
            columns = line.split()
            try:
                hrmc_step = int(columns[STEP_COLUMN_NUM])
            except ValueError:
                logger.warn("could not parse hrmc_step value on line %s" % i)
                continue
            # handle  format double precision float format
            val = columns[ERRGR_COLUMN_NUM]
            val = re_dbl_fort.sub(r'\1E\2', val)
            logger.debug("val=%s" % val)
            try:
                hrmc_errgr = float(val)
            except ValueError:
                logger.warn("could not parse hrmc_errgr value on line %s" % i)
                continue
            xs.append(hrmc_step)
            ys.append(hrmc_errgr)

        if len(ys) and len(xs):
            ax.scatter(xs, ys, color=coloriter.next(),
                label=str(df.dataset.description),  marker=markiter.next())

        logger.debug("xs=%s" % xs)
        logger.debug("ys=%s" % ys)

    pfile = tempfile.mktemp()
    logger.debug("pfile=%s" % pfile)

    pyplot.xlabel(STEP_LABEL)
    pyplot.ylabel(ERRGR_LABEL)
    logger.debug("label")
    pyplot.grid(True)
    #legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    legend()
    #pyplot.xlim(xmin=0)

    logger.debug("set legend")
    try:
        matplotlib.pyplot.savefig("%s.png" % pfile, dpi=100)
    except Exception, e:
        logger.error(e)
        raise

    logger.debug("saved")
    with open("%s.png" % pfile) as pf:
        read = pf.read()
        encoded = base64.b64encode(read)
        matplotlib.pyplot.close()
    try:
        pn = ParameterName.objects.get(
            schema=hrmc_experiment_schema, name="plot2")
    except ParameterName.DoesNotExist:
        logger.error("schema is missing plot parameter")
        return None
    except MultipleObjectsReturned:
        logger.error("schema is multiple plot parameters")
        return None

    logger.debug("ready to save")
    logger.debug("pn=%s" % pn)

    try:
        ep = ExperimentParameter.objects.get(
            parameterset=eps,
            name=pn)
    except ExperimentParameter.DoesNotExist:
        ep = ExperimentParameter(
            parameterset=eps,
            name=pn)
    except MultipleObjectsReturned:
        logger.error("multiple hrmc experiment schemas returned")
        return None
    ep.string_value = encoded
    ep.save()

    return ep


def get_dataset_image_to_show(dataset, sch, ps, hrmc_plot_name,
    filename1, filename2, file_label1, file_label2, x_label, y_label):
    logger.debug("found ps=%s" % ps)
    for param in DatasetParameter.objects.filter(parameterset=ps):
        logger.debug("param=%s" % param)
        logger.debug("param.name=%s" % param.name)

        if hrmc_plot_name in param.name.name:
            logger.debug("found existing image")
            return param

    logger.debug("building plots")
    display_image = None
    file2 = None
    file1 = None
    for df in Dataset_File.objects.filter(dataset=dataset):
        logger.debug("testing %s" % df.filename)
        if filename1 in df.filename:
            file1 = df
        if filename2 in df.filename:
            file2 = df
    if file1 and file2 and is_matplotlib_imported:
        logger.debug("found both")
        fp = file1.get_absolute_filepath()
        file1_buff = []
        with open(fp) as f:
            for d in f.read():
                file1_buff.append(d)

        fp = file2.get_absolute_filepath()
        file2_buff = []
        with open(fp) as f:
            for d in f.read():
                file2_buff.append(d)

        xs = []
        ys = []
        for l in ''.join(file2_buff).split("\n"):
            #logger.debug("l=%s" % l)
            if l:
                x, y = l.split()
                xs.append(float(x))
                ys.append(float(y))
        matplotlib.pyplot.plot(xs, ys, color="blue",
            markeredgecolor='blue', marker="D", label=file_label1)

        xs = []
        ys = []
        for l in ''.join(file1_buff).split("\n"):
            #logger.debug("l=%s" % l)
            if l:
                x, y = l.split()
                xs.append(float(x))
                ys.append(float(y))
        matplotlib.pyplot.plot(xs, ys, color="red",
            markeredgecolor='red', marker="o", label=file_label2)

        import tempfile
        pfile = tempfile.mktemp()
        logger.debug("pfile=%s" % pfile)

        pyplot.xlabel(x_label)
        pyplot.ylabel(y_label)
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
            pn = ParameterName.objects.get(schema=sch, name=hrmc_plot_name)
        except ParameterName.DoesNotExist:
            logger.error(
                "ParameterName is missing %s parameter" % hrmc_plot_name)
            return None
        except MultipleObjectsReturned:
            logger.error(
                "ParameterName is multiple %s parameters" % hrmc_plot_name)
            return None

        logger.debug("ready to save")

        try:
            dfp = DatasetParameter.objects.get(
                parameterset=ps,
                name=pn)
        except DatasetParameter.DoesNotExist:
            dfp = DatasetParameter(
                parameterset=ps,
                name=pn)
        except MultipleObjectsReturned:
            logger.error("multiple hrmc experiment schemas returned")
            return None
        dfp.string_value = encoded
        dfp.save()

        display_image = dfp
    else:
        logger.debug("one or more files unavailable")
        return None
    logger.debug("made display_image  %s" % display_image)
    return display_image
