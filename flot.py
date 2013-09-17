from .common import GraphBackend
from django.template import Context, Template
from django.template.loader import get_template

import logging

from django.conf import settings
logger = logging.getLogger(__name__)


class Flot(GraphBackend):
    def graph(self, graph_info, schema, parameter_set, plot_name,  plots):


        logger.debug("flot")
        data = []
        for i, plot in enumerate(plots):
            logger.debug("plot=%s" % plot)
            vals = []
            for j, coord in enumerate(plot):
                logger.debug("j=%s coord=%s"  % (j,coord))
                if not j:
                    if plot[0]:
                        label = str(plot[0])
                    else:
                        label = None
                    continue
                vals.append(coord[1])

            if 'legends' in graph_info:
                try:
                    l = graph_info['legends'][i]
                except IndexError, e:
                    logger.warn(e)
                    l = ""
            else:
                l = ""
            logger.debug("legend=%s" % l)

            if vals:
                res = []
                res.append(str(l))
                res.append([list(a) for a in zip(*vals)])
                data.append(res)
        logger.debug("data=%s" % data)


        context = {
        'id': parameter_set.id,
        'plots': data}

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

        #template = Template(tcontent)
        template = get_template("hrmc_views/flot.html")
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

