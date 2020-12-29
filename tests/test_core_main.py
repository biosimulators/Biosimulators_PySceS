""" Tests of the command-line interface

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-10-29
:Copyright: 2020, Center for Reproducible Biomedical Modeling
:License: MIT
"""

from biosimulators_pysces import __main__
from biosimulators_pysces import core
from biosimulators_utils.combine import data_model as combine_data_model
from biosimulators_utils.combine.io import CombineArchiveWriter
from biosimulators_utils.report import data_model as report_data_model
from biosimulators_utils.report.io import ReportReader
from biosimulators_utils.simulator.exec import exec_sedml_docs_in_archive_with_containerized_simulator
from biosimulators_utils.simulator.specs import gen_algorithms_from_specs
from biosimulators_utils.sedml import data_model as sedml_data_model
from biosimulators_utils.sedml.io import SedmlSimulationWriter
from biosimulators_utils.sedml.utils import append_all_nested_children_to_doc
from unittest import mock
import datetime
import dateutil.tz
import numpy
import numpy.testing
import os
import shutil
import tempfile
import unittest


class CliTestCase(unittest.TestCase):
    DOCKER_IMAGE = 'ghcr.io/biosimulators/biosimulators_pysces/pysces:latest'

    def setUp(self):
        self.dirname = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dirname)

    def test_exec_sed_task_successfully(self):
        task = sedml_data_model.Task(
            model=sedml_data_model.Model(
                source=os.path.join(os.path.dirname(__file__), 'fixtures', 'biomd0000000002.xml'),
                language=sedml_data_model.ModelLanguage.SBML.value,
                changes=[],
            ),
            simulation=sedml_data_model.UniformTimeCourseSimulation(
                algorithm=sedml_data_model.Algorithm(
                    kisao_id='KISAO_0000088',
                    changes=[
                        sedml_data_model.AlgorithmParameterChange(
                            kisao_id='KISAO_0000209',
                            new_value='1e-8',
                        ),
                    ],
                ),
                initial_time=5.,
                output_start_time=10.,
                output_end_time=20.,
                number_of_points=20,
            ),
        )

        variables = [
            sedml_data_model.DataGeneratorVariable(id='time', symbol=sedml_data_model.DataGeneratorVariableSymbol.time),
            sedml_data_model.DataGeneratorVariable(id='AL', target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='AL']"),
            sedml_data_model.DataGeneratorVariable(id='BLL', target='/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id="BLL"]'),
            sedml_data_model.DataGeneratorVariable(id='IL', target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='IL']"),
        ]

        variable_results = core.exec_sed_task(task, variables)

        self.assertTrue(sorted(variable_results.keys()), sorted([var.id for var in variables]))
        self.assertEqual(variable_results[variables[0].id].shape, (task.simulation.number_of_points + 1,))
        numpy.testing.assert_almost_equal(
            variable_results['time'],
            numpy.linspace(task.simulation.output_start_time, task.simulation.output_end_time, task.simulation.number_of_points + 1),
        )

        for results in variable_results.values():
            self.assertFalse(numpy.any(numpy.isnan(results)))

    def test_exec_sed_task_error_handling(self):
        task = sedml_data_model.Task(
            model=sedml_data_model.Model(
                source=os.path.join(os.path.dirname(__file__), 'fixtures', 'biomd0000000002.xml'),
                language=sedml_data_model.ModelLanguage.SBML.value,
                changes=[],
            ),
            simulation=sedml_data_model.UniformTimeCourseSimulation(
                algorithm=sedml_data_model.Algorithm(
                    kisao_id='KISAO_0000001',
                    changes=[
                        sedml_data_model.AlgorithmParameterChange(
                            kisao_id='KISAO_0000209',
                            new_value='2e-8',
                        ),
                    ],
                ),
                initial_time=5.,
                output_start_time=10.,
                output_end_time=20.,
                number_of_points=20,
            ),
        )

        variables = [
            sedml_data_model.DataGeneratorVariable(id='time', symbol=sedml_data_model.DataGeneratorVariableSymbol.time),
            sedml_data_model.DataGeneratorVariable(id='AL', target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='AL']"),
            sedml_data_model.DataGeneratorVariable(id='BLL', target='/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id="BLL"]'),
            sedml_data_model.DataGeneratorVariable(id='IL', target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='IL']"),
        ]

        # Configure task
        task.model.source = os.path.join(self.dirname, 'bad-model.xml')
        with open(task.model.source, 'w') as file:
            file.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
            file.write('<sbml2 xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">')
            file.write('  <model id="model">')
            file.write('  </model>')
            file.write('</sbml2>')
        with self.assertRaisesRegex(ValueError, 'could not be imported'):
            core.exec_sed_task(task, [])
        task.model.source = os.path.join(os.path.dirname(__file__), 'fixtures', 'biomd0000000002.xml')

        task.simulation.algorithm.kisao_id = 'KISAO_0000001'
        with self.assertRaisesRegex(NotImplementedError, 'is not supported'):
            core.exec_sed_task(task, variables)
        task.simulation.algorithm.kisao_id = 'KISAO_0000088'

        task.simulation.algorithm.changes[0].kisao_id = 'KISAO_0000001'
        with self.assertRaisesRegex(NotImplementedError, 'is not supported'):
            core.exec_sed_task(task, variables)
        task.simulation.algorithm.changes[0].kisao_id = 'KISAO_0000209'

        task.simulation.algorithm.changes[0].new_value = 'two e minus 8'
        with self.assertRaisesRegex(ValueError, 'is not a valid'):
            core.exec_sed_task(task, variables)
        task.simulation.algorithm.changes[0].new_value = '2e-8'

        task.simulation.output_end_time = 20.1
        with self.assertRaisesRegex(NotImplementedError, 'must specify an integer number of time points'):
            core.exec_sed_task(task, variables)
        task.simulation.output_end_time = 20.

        variables[0].symbol += '*'
        with self.assertRaisesRegex(NotImplementedError, 'symbols are not supported'):
            core.exec_sed_task(task, variables)
        variables[0].symbol = sedml_data_model.DataGeneratorVariableSymbol.time

        variables[1].target = "/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='kf_0']"
        with self.assertRaisesRegex(ValueError, 'targets could not be recorded'):
            core.exec_sed_task(task, variables)
        variables[1].target = "/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='AL']"

    def test_exec_sedml_docs_in_combine_archive_successfully(self):
        doc, archive_filename = self._build_combine_archive()

        out_dir = os.path.join(self.dirname, 'out')
        core.exec_sedml_docs_in_combine_archive(archive_filename, out_dir,
                                                report_formats=[
                                                    report_data_model.ReportFormat.h5,
                                                    report_data_model.ReportFormat.csv,
                                                ],
                                                bundle_outputs=True,
                                                keep_individual_outputs=True)

        self._assert_combine_archive_outputs(doc, out_dir)

    def _build_combine_archive(self, algorithm=None):
        doc = self._build_sed_doc(algorithm=algorithm)

        archive_dirname = os.path.join(self.dirname, 'archive')
        if not os.path.isdir(archive_dirname):
            os.mkdir(archive_dirname)

        model_filename = os.path.join(archive_dirname, 'model_1.xml')
        shutil.copyfile(
            os.path.join(os.path.dirname(__file__), 'fixtures', 'biomd0000000002.xml'),
            model_filename)

        sim_filename = os.path.join(archive_dirname, 'sim_1.sedml')
        SedmlSimulationWriter().run(doc, sim_filename)

        updated = datetime.datetime(2020, 1, 2, 1, 2, 3, tzinfo=dateutil.tz.tzutc())
        archive = combine_data_model.CombineArchive(
            contents=[
                combine_data_model.CombineArchiveContent(
                    'model_1.xml', combine_data_model.CombineArchiveContentFormat.SBML.value, updated=updated),
                combine_data_model.CombineArchiveContent(
                    'sim_1.sedml', combine_data_model.CombineArchiveContentFormat.SED_ML.value, updated=updated),
            ],
            updated=updated,
        )
        archive_filename = os.path.join(self.dirname,
                                        'archive.omex' if algorithm is None else 'archive-{}.omex'.format(algorithm.kisao_id))
        CombineArchiveWriter().run(archive, archive_dirname, archive_filename)

        return (doc, archive_filename)

    def _build_sed_doc(self, algorithm=None):
        if algorithm is None:
            algorithm = sedml_data_model.Algorithm(
                kisao_id='KISAO_0000088',
                changes=[
                    sedml_data_model.AlgorithmParameterChange(
                        kisao_id='KISAO_0000209',
                        new_value='1e-8',
                    ),
                ],
            )

        doc = sedml_data_model.SedDocument()
        doc.models.append(sedml_data_model.Model(
            id='model_1',
            source='model_1.xml',
            language=sedml_data_model.ModelLanguage.SBML.value,
            changes=[],
        ))
        doc.simulations.append(sedml_data_model.UniformTimeCourseSimulation(
            id='sim_1_time_course',
            algorithm=algorithm,
            initial_time=0.,
            output_start_time=0.1,
            output_end_time=0.2,
            number_of_points=20,
        ))
        doc.tasks.append(sedml_data_model.Task(
            id='task_1',
            model=doc.models[0],
            simulation=doc.simulations[0],
        ))
        doc.data_generators.append(sedml_data_model.DataGenerator(
            id='data_gen_time',
            variables=[
                sedml_data_model.DataGeneratorVariable(
                    id='var_time',
                    symbol=sedml_data_model.DataGeneratorVariableSymbol.time,
                    task=doc.tasks[0],
                    model=doc.models[0],
                ),
            ],
            math='var_time',
        ))
        doc.data_generators.append(sedml_data_model.DataGenerator(
            id='data_gen_AL',
            variables=[
                sedml_data_model.DataGeneratorVariable(
                    id='var_AL',
                    target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='AL']",
                    task=doc.tasks[0],
                    model=doc.models[0],
                ),
            ],
            math='var_AL',
        ))
        doc.data_generators.append(sedml_data_model.DataGenerator(
            id='data_gen_BLL',
            variables=[
                sedml_data_model.DataGeneratorVariable(
                    id='var_BLL',
                    target='/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id="BLL"]',
                    task=doc.tasks[0],
                    model=doc.models[0],
                ),
            ],
            math='var_BLL',
        ))
        doc.data_generators.append(sedml_data_model.DataGenerator(
            id='data_gen_IL',
            variables=[
                sedml_data_model.DataGeneratorVariable(
                    id='var_IL',
                    target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='IL']",
                    task=doc.tasks[0],
                    model=doc.models[0],
                ),
            ],
            math='var_IL',
        ))
        doc.outputs.append(sedml_data_model.Report(
            id='report_1',
            data_sets=[
                sedml_data_model.DataSet(id='data_set_time', label='Time', data_generator=doc.data_generators[0]),
                sedml_data_model.DataSet(id='data_set_AL', label='AL', data_generator=doc.data_generators[1]),
                sedml_data_model.DataSet(id='data_set_BLL', label='BLL', data_generator=doc.data_generators[2]),
                sedml_data_model.DataSet(id='data_set_IL', label='IL', data_generator=doc.data_generators[3]),
            ],
        ))

        append_all_nested_children_to_doc(doc)

        return doc

    def _assert_combine_archive_outputs(self, doc, out_dir):
        self.assertEqual(set(['reports.h5', 'reports.zip', 'sim_1.sedml']).difference(set(os.listdir(out_dir))), set())

        # check HDF report
        report = ReportReader().run(out_dir, 'sim_1.sedml/report_1', format=report_data_model.ReportFormat.h5)

        self.assertEqual(sorted(report.index), sorted([d.label for d in doc.outputs[0].data_sets]))

        sim = doc.tasks[0].simulation
        self.assertEqual(report.shape, (len(doc.outputs[0].data_sets), sim.number_of_points + 1))
        numpy.testing.assert_almost_equal(
            report.loc['Time', :].to_numpy(),
            numpy.linspace(sim.output_start_time, sim.output_end_time, sim.number_of_points + 1),
        )

        self.assertFalse(numpy.any(numpy.isnan(report)))

        # check CSV report
        report = ReportReader().run(out_dir, 'sim_1.sedml/report_1', format=report_data_model.ReportFormat.csv)

        self.assertEqual(sorted(report.index), sorted([d.label for d in doc.outputs[0].data_sets]))

        sim = doc.tasks[0].simulation
        self.assertEqual(report.shape, (len(doc.outputs[0].data_sets), sim.number_of_points + 1))
        numpy.testing.assert_almost_equal(
            report.loc['Time', :].to_numpy(),
            numpy.linspace(sim.output_start_time, sim.output_end_time, sim.number_of_points + 1),
        )

        self.assertFalse(numpy.any(numpy.isnan(report)))

    def test_exec_sedml_docs_in_combine_archive_with_all_algorithms(self):
        for alg in gen_algorithms_from_specs(os.path.join(os.path.dirname(__file__), '..', 'biosimulators.json')).values():
            doc, archive_filename = self._build_combine_archive(algorithm=alg)

            out_dir = os.path.join(self.dirname, alg.kisao_id)
            core.exec_sedml_docs_in_combine_archive(archive_filename, out_dir,
                                                    report_formats=[
                                                        report_data_model.ReportFormat.h5,
                                                        report_data_model.ReportFormat.csv,
                                                    ],
                                                    bundle_outputs=True,
                                                    keep_individual_outputs=True)
            self._assert_combine_archive_outputs(doc, out_dir)

    def test_raw_cli(self):
        with mock.patch('sys.argv', ['', '--help']):
            with self.assertRaises(SystemExit) as context:
                __main__.main()
                self.assertRegex(context.Exception, 'usage: ')

    def test_exec_sedml_docs_in_combine_archive_with_cli(self):
        doc, archive_filename = self._build_combine_archive()
        out_dir = os.path.join(self.dirname, 'out')
        env = self._get_combine_archive_exec_env()

        with mock.patch.dict(os.environ, env):
            with __main__.App(argv=['-i', archive_filename, '-o', out_dir]) as app:
                app.run()

        self._assert_combine_archive_outputs(doc, out_dir)

    def _get_combine_archive_exec_env(self):
        return {
            'REPORT_FORMATS': 'h5,csv'
        }

    def test_exec_sedml_docs_in_combine_archive_with_docker_image(self):
        doc, archive_filename = self._build_combine_archive()
        out_dir = os.path.join(self.dirname, 'out')
        docker_image = self.DOCKER_IMAGE
        env = self._get_combine_archive_exec_env()

        exec_sedml_docs_in_archive_with_containerized_simulator(
            archive_filename, out_dir, docker_image, environment=env, pull_docker_image=False)

        self._assert_combine_archive_outputs(doc, out_dir)

    def test_exec_sedml_docs_in_combine_archive_with_docker_image(self):
        archive_filename = os.path.join(os.path.dirname(__file__), 'fixtures', 'Parmar-BMC-Syst-Biol-2017-iron-distribution.omex')
        out_dir = os.path.join(self.dirname, 'out')
        docker_image = self.DOCKER_IMAGE
        env = {
            'REPORT_FORMATS': 'h5'
        }

        exec_sedml_docs_in_archive_with_containerized_simulator(
            archive_filename, out_dir, docker_image, environment=env, pull_docker_image=False)

        report = ReportReader().run(out_dir, 'Parmar2017_Deficient_Rich_tracer.sedml/simulation_1', format=report_data_model.ReportFormat.h5)

        self.assertEqual(set(report.index), set(['time', 'FeDuo']))

        self.assertEqual(report.shape, (2, 300 + 1))
        numpy.testing.assert_almost_equal(
            report.loc['time', :].to_numpy(),
            numpy.linspace(0., 5100., 300 + 1),
        )

        self.assertFalse(numpy.any(numpy.isnan(report)))
