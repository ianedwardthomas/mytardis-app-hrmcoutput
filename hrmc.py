
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

"""
hrmc.py

.. moduleauthor::  Ian Thomas <ianedwardthomas@gmail.com>

"""
import logging

from django.core.exceptions import MultipleObjectsReturned

from tardis.tardis_portal.models import Schema
from tardis.tardis_portal.models import Dataset_File, DatasetParameterSet

logger = logging.getLogger(__name__)


class HRMCOutput(object):
    """This
    :param name: the short name of the schema.
    :type name: string
    :param schema: the name of the schema to load the EXIF data into.
    :type schema: string
    :param tagsToFind: unused
    :type tagsToFind: list of strings
    :param tagsToExclude: unused
    :type tagsToExclude: list of strings
    """
    def __init__(self, name, schema,
                 tagsToFind=[], tagsToExclude=[]):
        self.name = name
        self.schema = schema
        logger.debug("hrmc __init__")

    def __call__(self, sender, **kwargs):
        """post save callback entry point.

        :param sender: The model class.
        :param instance: The actual instance being saved.
        :param created: A boolean; True if a new record was created.
        :type created: bool
        """
        logger.debug("hrmc __call__")

        datafile_instance = kwargs.get('instance')
        dataset_instance = datafile_instance.dataset
        try:
            sch = Schema.objects.get(
                namespace=self.schema)
        except Schema.DoesNotExist:
            logger.debug("no hrmc schema")
            return None
        except MultipleObjectsReturned:
            logger.error("multiple hrmc schemas returned")
            return None
        logger.debug("sch=%s" % sch)

        try:
            ps = DatasetParameterSet.objects.get(schema=sch,
                dataset=dataset_instance)
        except DatasetParameterSet.DoesNotExist:
            pass
        except MultipleObjectsReturned:
            logger.warn(
                "Multiple dataset paramter sets for %s returned"
                % self.name)
            # NB: If multiple filters run in dataset could get race condition
            # which causes multiple DatasetParameterSets to be created.
            # However, we know that all data will be the same for this schema
            # so can safely delete any extras we find.
            pslist = [x.id for x in DatasetParameterSet.objects.filter(schema=sch,
                dataset=dataset_instance)]
            logger.debug("pslist=%s" % pslist)
            DatasetParameterSet.objects.filter(id__in=pslist[1:]).delete()
            return None
        else:
            logger.debug("parameterset already exists")
            return None

        logger.debug("dataset_instance=%s" % dataset_instance)
        filepath = datafile_instance.get_absolute_filepath()
        logger.debug("filepath=%s" % filepath)

        grexp_file = None
        grfinal_file = None
        for df in Dataset_File.objects.filter(dataset=dataset_instance):
            logger.debug("df=%s" % df.filename)
            if "grexp.dat" in df.filename:
                grexp_file = df
            if df.filename.startswith("grfinal"):
                grfinal_file = df

        if grexp_file and grfinal_file:
            logger.debug("found all files")
            try:
                ps = DatasetParameterSet.objects.get(schema=sch,
                    dataset=dataset_instance)
            except DatasetParameterSet.DoesNotExist:
                ps = DatasetParameterSet(schema=sch,
                                          dataset=dataset_instance)
                ps.save()
                logger.debug("created new dataset")
                return None
            except MultipleObjectsReturned:
                logger.error(
                    "Multiple dataset paramter sets for %s returned"
                    % self.name)
                return None
            else:
                logger.debug("parameterset already exists")
            return None
        else:
            logger.debug("one or more files missing")




def make_filter(name='', schema='', tagsToFind=[], tagsToExclude=[]):
    logger.debug("make_filter HRMC")
    if not name:
        raise ValueError("HRMCOutput "
                         "requires a name to be specified")
    if not schema:
        raise ValueError("HRMCOutput "
                         "requires a schema to be specified")
    return HRMCOutput(name, schema, tagsToFind, tagsToExclude)
make_filter.__doc__ = HRMCOutput.__doc__
