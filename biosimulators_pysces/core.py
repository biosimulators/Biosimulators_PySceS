""" Methods for executing SED tasks in COMBINE archives and saving their outputs

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-23
:Copyright: 2020, Center for Reproducible Biomedical Modeling
:License: MIT
"""

from .data_model import KISAO_ALGORITHM_MAP
from biosimulators_utils.combine.exec import exec_sedml_docs_in_archive
from biosimulators_utils.config import get_config, Config  # noqa: F401
from biosimulators_utils.log.data_model import CombineArchiveLog, TaskLog, StandardOutputErrorCapturerLevel  # noqa: F401
from biosimulators_utils.viz.data_model import VizFormat  # noqa: F401
from biosimulators_utils.report.data_model import ReportFormat, VariableResults, SedDocumentResults  # noqa: F401
from biosimulators_utils.sedml.data_model import (Task, ModelLanguage, UniformTimeCourseSimulation,  # noqa: F401
                                                  Variable, Symbol)
from biosimulators_utils.utils.core import validate_str_value, parse_value
from biosimulators_utils.sedml import validation
from biosimulators_utils.sedml.exec import exec_sed_doc as base_exec_sed_doc
from biosimulators_utils.simulator.exceptions import AlgorithmDoesNotSupportModelFeatureException
from biosimulators_utils.simulator.utils import get_algorithm_substitution_policy
from biosimulators_utils.utils.core import raise_errors_warnings
from biosimulators_utils.warnings import warn, BioSimulatorsWarning
from kisao.data_model import AlgorithmSubstitutionPolicy, ALGORITHM_SUBSTITUTION_POLICY_LEVELS
from kisao.utils import get_preferred_substitute_algorithm_by_ids
from kisao.warnings import AlgorithmSubstitutedWarning
import lxml.etree
import numpy
import os
import pysces
import tempfile


__all__ = ['exec_sedml_docs_in_combine_archive', 'exec_sed_doc', 'exec_sed_task', 'preprocess_sed_task']


def exec_sedml_docs_in_combine_archive(archive_filename, out_dir, config=None):
    """ Execute the SED tasks defined in a COMBINE/OMEX archive and save the outputs

    Args:
        archive_filename (:obj:`str`): path to COMBINE/OMEX archive
        out_dir (:obj:`str`): path to store the outputs of the archive

            * CSV: directory in which to save outputs to files
              ``{ out_dir }/{ relative-path-to-SED-ML-file-within-archive }/{ report.id }.csv``
            * HDF5: directory in which to save a single HDF5 file (``{ out_dir }/reports.h5``),
              with reports at keys ``{ relative-path-to-SED-ML-file-within-archive }/{ report.id }`` within the HDF5 file

    Returns:
        :obj:`tuple`:

            * :obj:`SedDocumentResults`: results
            * :obj:`CombineArchiveLog`: log
    """
    return exec_sedml_docs_in_archive(exec_sed_doc, archive_filename, out_dir,
                                      apply_xml_model_changes=True,
                                      config=config)


def exec_sed_doc(doc, working_dir, base_out_path, rel_out_path=None,
                 apply_xml_model_changes=False,
                 log=None, indent=0, pretty_print_modified_xml_models=False,
                 log_level=StandardOutputErrorCapturerLevel.c, config=None):
    """ Execute the tasks specified in a SED document and generate the specified outputs

    Args:
        doc (:obj:`SedDocument` or :obj:`str`): SED document or a path to SED-ML file which defines a SED document
        working_dir (:obj:`str`): working directory of the SED document (path relative to which models are located)

        base_out_path (:obj:`str`): path to store the outputs

            * CSV: directory in which to save outputs to files
              ``{base_out_path}/{rel_out_path}/{report.id}.csv``
            * HDF5: directory in which to save a single HDF5 file (``{base_out_path}/reports.h5``),
              with reports at keys ``{rel_out_path}/{report.id}`` within the HDF5 file

        rel_out_path (:obj:`str`, optional): path relative to :obj:`base_out_path` to store the outputs
        apply_xml_model_changes (:obj:`bool`, optional): if :obj:`True`, apply any model changes specified in the SED-ML file before
            calling :obj:`task_executer`.
        log (:obj:`SedDocumentLog`, optional): log of the document
        indent (:obj:`int`, optional): degree to indent status messages
        pretty_print_modified_xml_models (:obj:`bool`, optional): if :obj:`True`, pretty print modified XML models
        log_level (:obj:`StandardOutputErrorCapturerLevel`, optional): level at which to log output
        config (:obj:`Config`, optional): BioSimulators common configuration
        simulator_config (:obj:`SimulatorConfig`, optional): tellurium configuration

    Returns:
        :obj:`tuple`:

            * :obj:`ReportResults`: results of each report
            * :obj:`SedDocumentLog`: log of the document
    """
    return base_exec_sed_doc(exec_sed_task, doc, working_dir, base_out_path,
                             rel_out_path=rel_out_path,
                             apply_xml_model_changes=apply_xml_model_changes,
                             log=log,
                             indent=indent,
                             pretty_print_modified_xml_models=pretty_print_modified_xml_models,
                             log_level=log_level,
                             config=config)


def exec_sed_task(task, variables, preprocessed_task=None, log=None, config=None):
    ''' Execute a task and save its results

    Args:
        task (:obj:`Task`): task
        variables (:obj:`list` of :obj:`Variable`): variables that should be recorded
        preprocessed_task (:obj:`object`, optional): preprocessed information about the task, including possible
            model changes and variables. This can be used to avoid repeatedly executing the same initialization
            for repeated calls to this method.
        log (:obj:`TaskLog`, optional): log for the task
        config (:obj:`Config`, optional): BioSimulators common configuration

    Returns:
        :obj:`tuple`:

            :obj:`VariableResults`: results of variables
            :obj:`TaskLog`: log
    '''
    config = config or get_config()

    if config.LOG and not log:
        log = TaskLog()

    if preprocessed_task is None:
        preprocessed_task = preprocess_sed_task(task, variables, config=config)

    model = task.model
    sim = task.simulation

    if config.VALIDATE_SEDML:
        raise_errors_warnings(validation.validate_task(task),
                              error_summary='Task `{}` is invalid.'.format(task.id))
        raise_errors_warnings(validation.validate_model_language(task.model.language, ModelLanguage.SBML),
                              error_summary='Language for model `{}` is not supported.'.format(model.id))
        raise_errors_warnings(validation.validate_model_change_types(task.model.changes, ()),
                              error_summary='Changes for model `{}` are not supported.'.format(model.id))
        raise_errors_warnings(*validation.validate_model_changes(task.model),
                              error_summary='Changes for model `{}` are invalid.'.format(model.id))
        raise_errors_warnings(validation.validate_simulation_type(task.simulation, (UniformTimeCourseSimulation, )),
                              error_summary='{} `{}` is not supported.'.format(sim.__class__.__name__, sim.id))
        raise_errors_warnings(*validation.validate_simulation(task.simulation),
                              error_summary='Simulation `{}` is invalid.'.format(sim.id))
        raise_errors_warnings(*validation.validate_data_generator_variables(variables),
                              error_summary='Data generator variables for task `{}` are invalid.'.format(task.id))

    model_etree = lxml.etree.parse(task.model.source)
    target_x_paths_to_sbml_ids = validation.validate_target_xpaths(variables, model_etree, attr='id')

    # Get the current working directory because PySCeS opaquely changes it
    cwd = os.getcwd()

    # Read the model
    interfaces = pysces.PyscesInterfaces.Core2interfaces()
    fid, model_filename = tempfile.mkstemp(suffix='.psc')
    os.close(fid)
    try:
        interfaces.convertSBML2PSC(sbmlfile=task.model.source, pscfile=model_filename)
    except Exception as exception:
        os.remove(model_filename)
        raise ValueError('Model at {} could not be imported:\n  {}'.format(
            task.model.source, str(exception).replace('\n', '\n  ')))
    model = pysces.model(model_filename)
    os.remove(model_filename)

    # Load the algorithm specified by `simulation.algorithm.kisao_id`
    sim = task.simulation
    algorithm_substitution_policy = get_algorithm_substitution_policy(config=config)
    exec_kisao_id = get_preferred_substitute_algorithm_by_ids(
        sim.algorithm.kisao_id, KISAO_ALGORITHM_MAP.keys(),
        substitution_policy=algorithm_substitution_policy)
    integrator = KISAO_ALGORITHM_MAP[exec_kisao_id]
    model.mode_integrator = integrator['id']

    # Apply the algorithm parameter changes specified by `task.simulation.algorithm.changes`
    if exec_kisao_id == sim.algorithm.kisao_id:
        for change in sim.algorithm.changes:
            setting = integrator['settings'].get(change.kisao_id, None)
            if setting is None:
                if (
                    ALGORITHM_SUBSTITUTION_POLICY_LEVELS[algorithm_substitution_policy]
                    <= ALGORITHM_SUBSTITUTION_POLICY_LEVELS[AlgorithmSubstitutionPolicy.NONE]
                ):
                    msg = "".join([
                        "Algorithm parameter with KiSAO id '{}' is not supported. ".format(change.kisao_id),
                        "Parameter must have one of the following KiSAO ids:\n  - {}".format('\n  - '.join(
                            '{}: {} ({})'.format(kisao_id, setting['id'], setting['name'])
                            for kisao_id, setting in integrator['settings'].items())),
                    ])
                    raise NotImplementedError(msg)
                else:
                    msg = "".join([
                        "Algorithm parameter with KiSAO id '{}' was ignored because it is not supported. ".format(change.kisao_id),
                        "Parameter must have one of the following KiSAO ids:\n  - {}".format('\n  - '.join(
                            '{}: {} ({})'.format(kisao_id, setting['id'], setting['name'])
                            for kisao_id, setting in integrator['settings'].items())),
                    ])
                    warn(msg, BioSimulatorsWarning)
                    continue

            value = change.new_value
            if not validate_str_value(value, setting['type']):
                if (
                    ALGORITHM_SUBSTITUTION_POLICY_LEVELS[algorithm_substitution_policy]
                    <= ALGORITHM_SUBSTITUTION_POLICY_LEVELS[AlgorithmSubstitutionPolicy.NONE]
                ):
                    msg = "'{}' is not a valid {} value for parameter {}".format(
                        value, setting['type'].name, change.kisao_id)
                    raise ValueError(msg)
                else:
                    msg = "'{}' was ignored because it is not a valid {} value for parameter {}".format(
                        value, setting['type'].name, change.kisao_id)
                    warn(msg, BioSimulatorsWarning)
                    continue

            parsed_value = parse_value(value, setting['type'])
            model.__settings__[setting['id']] = parsed_value

    # override algorithm choice if there are events
    if integrator['id'] == 'LSODA' and model.__events__:
        model.mode_integrator = 'CVODE'
        substitution_policy = get_algorithm_substitution_policy(config=config)
        if (
            ALGORITHM_SUBSTITUTION_POLICY_LEVELS[substitution_policy]
            >= ALGORITHM_SUBSTITUTION_POLICY_LEVELS[AlgorithmSubstitutionPolicy.SIMILAR_VARIABLES]
        ):
            warn('CVODE (KISAO_0000019) will be used rather than LSODA (KISAO_0000088) because the model has events',
                 AlgorithmSubstitutedWarning)
        else:
            raise AlgorithmDoesNotSupportModelFeatureException('LSODA cannot execute the simulation because the model has events')

    if model.mode_integrator == 'CVODE':
        model.__settings__['cvode_return_event_timepoints'] = False

    # setup time course
    model.sim_start = sim.initial_time
    model.sim_end = sim.output_end_time
    model.sim_points = (
        sim.number_of_points
        * (sim.output_end_time - sim.initial_time)
        / (sim.output_end_time - sim.output_start_time)
        + 1
    )
    if model.sim_points != int(model.sim_points):
        raise NotImplementedError('Time course must specify an integer number of time points')

    # execute simulation
    model.Simulate()

    # extract results
    variable_results = VariableResults()
    unpredicted_symbols = []
    unpredicted_targets = []
    results, labels = model.data_sim.getAllSimData(lbls=True)
    labels = {label: i_label for i_label, label in enumerate(labels)}

    for variable in variables:
        if variable.symbol:
            if variable.symbol == Symbol.time:
                i_result = labels['Time']
                variable_results[variable.id] = results[:, i_result][-(sim.number_of_points + 1):]
            else:
                unpredicted_symbols.append(variable.symbol)

        else:
            sbml_id = target_x_paths_to_sbml_ids[variable.target]
            i_result = labels.get(sbml_id, None)
            if i_result is not None:
                variable_results[variable.id] = results[:, i_result][-(sim.number_of_points + 1):]
            elif sbml_id in model.fixed_species:
                variable_results[variable.id] = numpy.full((sim.number_of_points + 1,), getattr(model, sbml_id))
            else:
                unpredicted_targets.append(variable.target)

    if unpredicted_symbols:
        raise NotImplementedError("".join([
            "The following variable symbols are not supported:\n  - {}\n\n".format(
                '\n  - '.join(sorted(unpredicted_symbols)),
            ),
            "Symbols must be one of the following:\n  - {}".format(Symbol.time),
        ]))

    if unpredicted_targets:
        raise ValueError(''.join([
            'The following variable targets could not be recorded:\n  - {}\n\n'.format(
                '\n  - '.join(sorted(unpredicted_targets)),
            ),
            'Targets must have one of the following ids:\n  - {}'.format(
                '\n  - '.join(sorted(set(labels.keys()).difference(set(['Time'])))),
            ),
        ]))

    # restore working directory
    os.chdir(cwd)

    # log action
    if config.LOG:
        log.algorithm = 'KISAO_0000019' if model.mode_integrator == 'CVODE' else 'KISAO_0000088'

        arguments = {}
        for key, val in model.__settings__.items():
            if model.mode_integrator == 'CVODE':
                if key.startswith('cvode_'):
                    arguments[key] = val
            else:
                if key.startswith('lsoda_'):
                    arguments[key] = val

        log.simulator_details = {
            'method': model.Simulate.__module__ + '.' + model.Simulate.__name__,
            'arguments': arguments,
        }

    # return results and log
    return variable_results, log


def preprocess_sed_task(task, variables, config=None):
    """ Preprocess a SED task, including its possible model changes and variables. This is useful for avoiding
    repeatedly initializing tasks on repeated calls of :obj:`exec_sed_task`.

    Args:
        task (:obj:`Task`): task
        variables (:obj:`list` of :obj:`Variable`): variables that should be recorded
        preprocessed_task (:obj:`PreprocessedTask`, optional): preprocessed information about the task, including possible
            model changes and variables. This can be used to avoid repeatedly executing the same initialization for repeated
            calls to this method.
        config (:obj:`Config`, optional): BioSimulators common configuration

    Returns:
        :obj:`object`: preprocessed information about the task
    """
    pass
