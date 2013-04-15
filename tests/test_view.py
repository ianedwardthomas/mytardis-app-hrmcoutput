
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

import os
from django.test import TestCase
from django.contrib.auth.models import User
from django.test.client import Client
from django.conf import settings
import logging


from tardis.tardis_portal.models import UserProfile, ExperimentACL, \
    Experiment, Dataset, Dataset_File, ParameterName, Schema, \
    DatasetParameter, DatasetParameterSet
from tardis.tardis_portal.models import License

from tardis.tardis_portal.filters import hrmc

logger = logging.getLogger(__name__)


def _create_test_user():
    user_ = User(username='tom',
                first_name='Thomas',
                last_name='Atkins',
                email='tommy@atkins.net')
    user_.save()
    UserProfile(user=user_).save()
    return user_


def _create_license():
    license_ = License(name='Creative Commons Attribution-NoDerivs 2.5 Australia',
                       url='http://creativecommons.org/licenses/by-nd/2.5/au/',
                       internal_description='CC BY 2.5 AU',
                       allows_distribution=True)
    license_.save()
    return license_


def _create_test_experiment(user, license_):
    experiment = Experiment(title='Norwegian Blue',
                            description='Parrot + 40kV',
                            created_by=user)
    experiment.public_access = Experiment.PUBLIC_ACCESS_FULL
    experiment.license = license_
    experiment.save()
    experiment.author_experiment_set.create(order=0,
                                            author="John Cleese",
                                            url="http://nla.gov.au/nla.party-1")
    experiment.author_experiment_set.create(order=1,
                                            author="Michael Palin",
                                            url="http://nla.gov.au/nla.party-2")
    acl = ExperimentACL(experiment=experiment,
                    pluginId='django_user',
                    entityId=str(user.id),
                    isOwner=True,
                    canRead=True,
                    canWrite=True,
                    canDelete=True,
                    aclOwnershipType=ExperimentACL.OWNER_OWNED)
    acl.save()
    return experiment


def get_size_and_sha512sum(testfile):
    import hashlib
    with open(testfile, 'rb') as f:
        contents = f.read()
        return (len(contents), hashlib.sha512(contents).hexdigest())


def _create_test_dataset(ds, exp_id, fnames):
    for fname, contents in fnames.items():
        dest = os.path.abspath(os.path.join(settings.FILE_STORE_PATH, '%s/%s/'
                                  % (exp_id,
                                  ds.id)))
        if not os.path.exists(dest):
            os.makedirs(dest)
        testfile = os.path.abspath(os.path.join(dest, fname))
        with open(testfile, "w+b") as f:
            f.write(contents)

        size, sha512sum = get_size_and_sha512sum(testfile)
        dataset_file = Dataset_File(dataset=ds,
                                          filename=fname,
                                          protocol='',
                                          size=size,
                                          sha512sum=sha512sum,
                                          url='%d/%d/%s'
                                              % (exp_id,
                                                 ds.id,
                                                 fname))
        dataset_file.verify()
        dataset_file.save()
    return ds


def get_param_sets(ds):

    return DatasetParameterSet.objects.filter(
        schema__namespace="http://rmit.edu.au/schemas/hrmcdataset",
        dataset=ds)


class HRMCOutputTest(TestCase):

    HRMCSCHEMA = "http://rmit.edu.au/schemas/hrmcdataset"

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_hrmc_filter(self):
        """
           Make an experiment, lood up grexp file and check
           dataset schema missing, then loadup grfinal and check dataset schema
           created
        """
        user = _create_test_user()
        license = _create_license()
        exp = _create_test_experiment(user, license)
        ds = Dataset(description='happy snaps of plumage')
        ds.save()
        _create_test_dataset(ds, exp.id,
            {"output.dat": 'hello', "grexp.dat": '2 5\n6 15\n'})
        ds.experiments.add(exp)
        ds.save()

        sch = Schema(namespace=self.HRMCSCHEMA,
            name="hrmc_views", type=Schema.DATASET)
        sch.save()

        param = ParameterName(schema=sch, name="plot",
            full_name="scatterplot", units="image",
            data_type=ParameterName.FILENAME
            )
        param.save()

        param_sets = get_param_sets(ds)
        self.assertEquals(list(param_sets), [])

        _create_test_dataset(ds, exp.id, {'grfinal21.dat': "1 3\n5 14\n"})

        df2 = Dataset_File(dataset=ds, url='path/grfinal21.dat')
        df2.save()

        h = hrmc.HRMCOutput('HRMC', self.HRMCSCHEMA)
        h(sender=Dataset_File, instance=df2)

        param_sets = get_param_sets(ds)
        self.assertEquals([x.schema.namespace for x in param_sets],
            [self.HRMCSCHEMA])

    def test_contextual_view(self):
        """
            Given schema on dataset, check that  image file created
        """
        user = _create_test_user()
        license = _create_license()
        exp = _create_test_experiment(user, license)
        ds = Dataset(description='happy snaps of plumage')
        ds.save()
        ds = _create_test_dataset(ds, exp.id, {
            "output.dat": 'test data\n',
            "grexp.dat": '1 2\n2 3\n3 7\n',
            "grfinal21.dat": '1 2\n 2 4\n4 9\n'})

        sch = Schema(namespace=self.HRMCSCHEMA,
            name="hrmc_views", type=Schema.DATASET)
        sch.save()

        param = ParameterName(schema=sch, name="plot",
            full_name="scatterplot", units="image",
            data_type=ParameterName.FILENAME
            )
        param.save()

        dps = DatasetParameterSet(schema=sch, dataset=ds)
        dps.save()

        ds.experiments.add(exp)
        ds.save()

        client = Client()
        response = client.get('/dataset/%s' % ds.id)
        self.assertEqual(response.status_code, 200)

        param_sets = get_param_sets(ds)
        self.assertTrue(param_sets)

        dp = DatasetParameter.objects.get(parameterset=param_sets[0],
            name=param)

        self.assertTrue(dp)
        self.assertNotEquals(dp.string_value, "")  # ie, it has a filename
