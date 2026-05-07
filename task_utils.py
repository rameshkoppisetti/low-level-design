#
# Copyright 2015 Workspan. All Rights Reserved.
#

# Utility functions for tasks.
#
import logging
import os
import types
import datetime
from collections import defaultdict

from . import utils
import settings
import webapp2
import traceback
import string
from google.appengine.api import taskqueue
from google.appengine.ext import deferred

from common.utils import allocate_id
from common.wsutils import increment, get_count
from common.traceutils import trace
from copy import deepcopy
from network.wswtoken.public.wswtoken import WSWTokenAPI
from google.appengine.ext import ndb
import uuid
from . import exceptions
from google.appengine.ext.db import Timeout
from common.tracer_utils import get_tracer

logger = logging.getLogger(_name_)

BULK_OPERATION = 'BULK-OPERATION'

BULK_OPERATION_LOWERCASE = 'Bulk-Operation'

BULK_DELETE_OPERATION = 'BULK-DELETE-OPERATION'

FAILED_ENTITIES_RETRY_QUEUE_TOKEN = 'failed-entity-executor-retry-queue'

COMPANY_NAME = 'WS-X-COMPANY-NAME'

COSELL_APP_TASK = 'X-COSELL-APP-TASK'

SESSION_ID = 'X-Session-Id'

def start_bulk_task():
    os.environ[BULK_OPERATION] = BULK_OPERATION

def start_cosell_app_task():
    os.environ[COSELL_APP_TASK] = 'True'

def is_cosell_app_task():
    if os.environ.get(COSELL_APP_TASK):
        return os.environ.get(COSELL_APP_TASK)
    return None

def set_company_name(company_name=None):
    if company_name:
        os.environ[COMPANY_NAME] = company_name

def set_session_id(session_id=None):
    if session_id:
        os.environ[SESSION_ID] = session_id

def is_bulk_operation():
    return True if os.environ.get(BULK_OPERATION) or os.environ.get(BULK_OPERATION_LOWERCASE) else False


def get_company_name():
    if os.environ.get(COMPANY_NAME):
        return os.environ.get(COMPANY_NAME)
    return None

def get_session_id():
    if os.environ.get(SESSION_ID):
        return os.environ.get(SESSION_ID)
    return None

def start_bulk_delete_task():
    os.environ[BULK_DELETE_OPERATION] = BULK_DELETE_OPERATION

def is_bulk_delete_operation():
    return True if os.environ.get(BULK_DELETE_OPERATION) else False

def get_retry_count():
    try:
        retry_count = webapp2.get_request().headers.get(
            'X-AppEngine-TaskRetryCount')
        logger.info("retry_count: %s", retry_count)
    except AssertionError as ae:
        return None
    if retry_count:
        try:
            retry_count = int(retry_count)
            return retry_count
        except ValueError as ve:
            return None
    return None


def get_task_name():
    try:
        task_name = webapp2.get_request().headers.get(
            'X-Appengine-Taskname')
        logger.info("task_name: %s", task_name)
        return task_name
    except Exception as e:
        logger.info("task_name exception: %s", str(e))

    logger.warn("task_name not found, using None")
    return None


def get_queue(label, bulk_operation_flag=False, company_name=None, is_cosell_app_task = None):
    '''Get the task queue for label.
       Note: queue name syantax:
        Queue name should match pattern "^[a-zA-Z0-9-]{1,100}$"

       The queue name should follow the following convention:

       service's package name and operation in token name and
       if a new queue is created use <service>-<operation>

       Queues should be added to queue.yaml
    '''
    # This may be tuned further for different labels.
    # To return a non-default queue for label, make sure it is added to
    # queue.yaml.

    bulk_queue_token_map = {'project.post.update': 'project-post-update-bulk',
                            'project.link.reference.fields.update': 'project-link-reference-fields-update-bulk',
                            'table.refresh': 'table-refresh-bulk',
                            'project.auto.link': 'project-auto-link-bulk',
                            'crm.auto.create': 'crm-to-project-auto-create',
                            'crm.post.update': 'crm-post-update-bulk',
                            'reference.table.project.data.sync': 'reference-table-project-data-sync-bulk',
                            'backend.integration.exec': 'backend-integration-exec-bulk',
                            'create.parent.child.link': 'create-parent-child-link-bulk',
                            'mpc.referral.submission': 'mpc-referral-submission-bulk',
                            'ace.api.inbound': 'ace-api-inbound'}

    cosell_app_queues = {
        'backend-subscribe-events-bulk': 'cosell-app-backend-subscribe-events-bulk'
    }

    if is_cosell_app_task and bulk_operation_flag and label in cosell_app_queues:
        cosell_app_queue_name = cosell_app_queues.get(label)
        if cosell_app_queue_name:
            return cosell_app_queue_name 

    if bulk_queue_token_map.get(label) and bulk_operation_flag:
        if company_name and company_name in ["sap", "cisco"] and label not in ["table.refresh", 'backend.integration.exec']: # as we do not have sap-bee-bulk queue in place
            return company_name + "-" + bulk_queue_token_map[label]
        return bulk_queue_token_map[label]
    if label == 'app.marketing_project.index_project':
        return 'projectindexing'
    elif label == 'splits.sync':
        return 'splits-sync'
    if label == 'app.marketing_fund.index_fund':
        return 'fundindexing'
    if label == 'app.marketing_campaign.index_campaign':
        return 'campaignindexing'
    elif label == 'app.marketing_campaign.post_update':
        return 'campaign-post-update'
    elif label == 'app.marketing_campaign.post_update_activity':
        return 'campaign-post-update-activity'
    elif label == 'network.team.post_update':
        return 'campaign-post-update'
    elif label == 'backend.tagging.post_update':
        return 'tagging-post-update'
    elif label == 'backend.toggle.post_update':
        return 'toggle-post-update'
    elif label == 'app.marketing_fund.post_update':
        return 'fund-post-update'
    if label == 'app.applist.post_update':
        return 'list-post-update'
    if label == 'backend.list.clone':
        return 'list-clone'
    elif label == 'backend.email.send':
        return 'backend-email-send'
    elif label == 'network.person.post_update':
        return 'person-company-post-update'
    elif label == 'network.company.post_update':
        return 'person-company-post-update'
    elif label == 'backend.task':
        return 'backend-task'
    elif label == 'backend.note':
        return 'backend-note'
    elif label == 'upgrade':
        return 'upgrade'
    elif label == 'campaign.clone':
        return 'campaign-clone'
    elif label == 'nbo.clone':
        return 'nbo-clone'
    elif label == 'list-autosuggest-refresh':
        return 'list-autosuggest-refresh'
    elif label == 'backend.log.event':
        return 'backend-log-event'
    elif label == 'backend.changeindicator':
        return 'backend-changeindicator'
    elif label == 'fileservice.convert':
        return 'fileservice-convert'
    elif label == 'backend.network.room':
        return 'backend-network-room'
    elif label == 'backend.network.rmsg':
        return 'backend-network-rmsg'
    elif label == 'backend.async.task':
        return 'backend-async-task'
    elif label == 'backend.card.post_update':
        return 'backend-card-post-update'
    elif label == 'backend.card.update_engagement':
        return 'backend-card-update-engagement'
    elif label == 'backend.card.admin_tasks':
        return 'backend-card-admin-tasks'
    elif label == 'backend.integration.exec':
        return 'backend-integration-exec'
    elif label == 'backend.integration.post_update':
        return 'integration-post-update'
    elif label == 'backend.alert.post_update':
        return 'backend-alert-post-update'
    elif label == 'backend.invite.reminders':
        return 'backend-invite-reminders'
    elif label == 'backend.company.index':
        return 'backend-company-index'
    elif label == 'project.post.update':
        return 'project-post-update'
    elif label == 'crm.post.update':
        return 'crm-post-update'
    elif label == 'table.refresh':
        return 'table-refresh'
    elif label == 'report.refresh':
        return 'report-refresh'
    elif label == 'backend-imx':
        return 'backend-imx'
    elif label == 'upgrade-script':
        return 'upgrade-script'
    elif label == 'export-task':
        return 'export-task'
    elif label == 'app.marketing_project.internal.project_crm_parallel_lib':
        return 'crm-to-project-multi-task'
    elif label == 'crm.auto.create':
        return 'crm-to-project-auto-create'
    elif label == DEFAULT_QUEUE_TOKEN:
        return DEFAULT_QUEUE_TOKEN
    elif label == 'network-team':
        return 'team-ops-queue'
    elif label == 'pusher.notification':
        return 'pusher-notification'
    elif label == 'recommendation-task':
        return 'recommendation-task'
    elif label == 'backend-publish-events-bulk':
        return 'backend-publish-events-bulk'
    elif label == 'backend-subscribe-events-bulk':
        return 'backend-subscribe-events-bulk'
    elif label == 'cosell-app-backend-subscribe-events-bulk':
        return 'cosell-app-backend-subscribe-events-bulk'
    elif label == 'go-backend-subscribe-events-bulk':
        return 'go-backend-subscribe-events-bulk'
    elif label == 'go-backend-membership-events':
        return 'go-backend-membership-events'
    elif label == 'bpa-evaluation-events':
        return 'bpa-evaluation-events'
    elif label == 'project-post-update-bulk':
        return 'project-post-update-bulk'
    elif label == 'table-refresh-bulk':
        return 'table-refresh-bulk'
    elif label == 'project-cache-refresh':
        return 'project-cache-refresh'
    elif label == 'bpa.automated.action':
        return 'bpa-automated-action'
    elif label == 'bpa.bulk.action':
        return 'bpa-bulk-action'
    elif label == 'bpa-retry-queue':
        return 'bpa-retry-queue'
    elif label == 'default':
        return 'default'
    elif label == 'failed-entity-executor-retry-queue':
        return 'failed-entity-executor-retry-queue'
    elif label == 'leads.expiration':
        return 'leads-expiration'
    elif label == 'report.email.job':
        return 'report-email-job'
    elif label == 'report.export':
        return 'report-100x-export'
    elif label == 'outbound-integrations':
        return 'outbound-integrations'
    elif label == 'integration.indexing':
        return 'integration-indexing'
    elif label == "reference.table.update":
        if company_name and company_name in ["sap", "cisco"]:
            return company_name + "-" + "reference-table-update-bulk"
        return "reference-table-update-bulk"
    elif label == "project.auto.link":
        return "project-auto-link"
    elif label == "user.input.file.upload.queue":
        return "user-input-file-upload-queue"
    elif label == "marketplace.backend.task":
        return "marketplace-backend-task"
    elif label == "azure.marketplace.backend.task":
        return "azure-marketplace-backend-task"
    elif label == "validate-project-events":
        return "validate-project-events"
    elif label == "membership.backend.task":
        return "membership-backend-task"
    elif label == 'backend.email.send.customer.token':
        return 'backend-email-send-customer-token'
    elif label == 'chart.export':
        return 'report-100x-export'
    elif label == 'cosellwithme.package.install':
        return 'cosellwithme-package-install'
    elif label == "backend.task.high.priority":
        return "backend-task-high-priority"
    elif label == "mpc.referral.submission":
        return "mpc-referral-submission"
    elif label == "project.cswm.auto.installation":
        return "project-cswm-auto-installation"
    elif label == "cswm.auto.installation.request.queue":
        return "cswm-auto-installation-request-queue"
    else:
        logger.warn(
            "task queue for label (%s) not defined. returning 'default'",
            label)
    return 'default'


def _task_wrapper(task, tracer, bulk_operation_flag, bulk_delete_operation_flag=False, env_company_name=None, is_cosell_app_task=False, session_id=None, *args, **kwds):
    logger.info(
        "calling = %s for task = %s with tracer = %s args = %s and kwds = %s",
        '_task_wrapper', task, tracer, args, kwds)
    if bulk_operation_flag:
        start_bulk_task()
    if bulk_delete_operation_flag:
        start_bulk_delete_task()
    if env_company_name:
        set_company_name(env_company_name)
    if is_cosell_app_task:
        start_cosell_app_task()
    if session_id:
        set_session_id(session_id)
    
    # Remove marketplace app task flag from kwargs for Python 2/3 compatibility only
    # This handles the case where a task created in Python 3 is processed in a Python 2 queue
    # No marketplace functionality is handled here - this just prevents kwargs errors
    kwds.pop('is_marketplace_app_task', False)
    return task(*args, **kwds)


def retryable_task_wrapper(func, *args, **kwds):
    logger.info("Calling function: %s, with args: %s and kwargs: %s",
                func, args, kwds)
    entity_id = args[0]
    success_callbacks = args[1]
    failure_callbacks = args[2]

    def _invoke_callbacks(callbacks, status_message):
        for callback in callbacks:
            run_deferred(
                FAILED_ENTITIES_RETRY_QUEUE_TOKEN,
                callback, status_message, **kwds)
    try:
        func(entity_id, **kwds)
        _invoke_callbacks(success_callbacks, "Task succeeded")
    except (exceptions.ValidationException, exceptions.NotFoundException) as e:
        logger.error("Entity Retry Action for entity: %s Failed with: %s",
                     entity_id, e)
        _invoke_callbacks(failure_callbacks, "Task returned failure status")
    except Exception as e:
        logger.error("Could not process entity: %s, Action Function Failed with: %s",
                     entity_id, e)
        _invoke_callbacks(failure_callbacks, "Task returned failure status")
        raise


def run_deferred_with_timed_task_name_delayed(task_name_prefix, task_type, func, queue_token, countdown=60, *args, **kwargs):
    """
    Objective is to make sure table view refreshes are not duplicated.
    Steps:
    creating a taskname with current time min granularity, and alternate task name with min+1 in case first task
    created has been already executed.
    Then adding task to queue.
    countdown makes sure task is attempted to ran x seconds later after its added to queue.
    """
    now = datetime.datetime.utcnow()

    minutes = int(countdown/60)
    now_plus_countdown = now + datetime.timedelta(minutes=minutes)

    function_name = str(func._name_)

    task_prefix = "{}-{}-{}".format(task_name_prefix, str(task_type), string.replace(queue_token, '.', ''))
    task_name = "{}-{}".format(task_prefix, now.strftime('%Y%m%d%H%M'))
    alt_task_name = "{}-{}".format(task_prefix, now_plus_countdown.strftime('%Y%m%d%H%M'))

    kwargs['alt_task_name'] = alt_task_name
    kwargs['countdown'] = countdown

    run_deferred_by_taskname(task_name, queue_token, func, *args, **kwargs)

def run_deferred_with_timed_task_name_delayed_10min(task_name_prefix, task_type, func, queue_token, countdown=60, *args, **kwargs):
    """
    Objective is to make sure table view refreshes are not duplicated.
    Steps:
    creating a taskname with current time 10 min granularity, and alternate task name with min+1 in case first task
    created has been already executed.
    Then adding task to queue.
    countdown makes sure task is attempted to ran x seconds later after its added to queue.
    """
    now = datetime.datetime.utcnow()

    suffix = now.strftime('%Y%m%d%H%M')[:-1]

    function_name = str(func._name_)

    task_prefix = "{}-{}-{}".format(task_name_prefix, str(task_type), string.replace(queue_token, '.', ''))
    task_name = "{}-{}".format(task_prefix, suffix)
    kwargs['countdown'] = countdown

    run_deferred_by_taskname(task_name, queue_token, func, *args, **kwargs)

def run_deferred_by_taskname(task_name, queue_token, func, *args, **kwds):
    """
    This is wrapper function to schedule a named task to task queue.
    :param task_name: name of the task to be queued
    :param queue_token: task queue name
    :param func: function to be executed when task is executed
    :param args: function args
    :param kwds: Alternative taskname to be defined as kwds['alt_task_name'] for scheduling in case of tombstone/exist error.
    :return: none
    """
    #name of the task to run
    kwds['_name'] = task_name
    alt_task_name= kwds.pop('alt_task_name', None)
    countdown = kwds.pop('countdown', 0)
    initial_countdown = kwds.pop('initial_countdown', 0)
    try:
        kwds['_countdown'] = initial_countdown
        run_deferred(queue_token, func, *args, **kwds)
    except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
        if alt_task_name is not None:
            logger.info('Requeing task (already exists/executed) with alternate name: {}'.format(alt_task_name))
            kwds['_name'] = alt_task_name
            kwds['_countdown'] = countdown
            try:
                run_deferred(queue_token, func, *args, **kwds)
            except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
                logging.info('Skipping task (already exists/executed, second try): {}'.format(alt_task_name))
        else:
            logger.info('Skipping task (already executed): {}'.format(kwds['_name']))

def run_deferred(queue_token, func, *args, **kwds):
    ''' The queue_token can be defined in the method get_queue()
    '''

    # TODO: (Geetanjali) Clean up where we are passing queue_name
    #  based on bulk_operation flag
    _enable_deferred = settings.config.get('ENABLE_DEFERRED', True)

    in_transaction = ndb.in_transaction()
    if not in_transaction:
        if not kwds.has_key('_name') or kwds.get('_name') is None:
            kwds['name'] = (str(func.__name_)+""+str(uuid.uuid4().hex)).replace('.','').replace('<', '').replace('>', '').replace(' ', '_')
            logger.debug("Task Name: %s", kwds['_name'])

    if _enable_deferred:
        bulk_operation_flag = is_bulk_operation()
        env_company_name = get_company_name()
        is_cosell_app_flow = is_cosell_app_task()
        session_id = get_session_id()
        _queue = get_queue(queue_token, bulk_operation_flag, company_name=env_company_name, is_cosell_app_task=is_cosell_app_flow)
        ''' this queue change is to blackhole project-post-update tasks 
            when delete_bulk_project upgrade is executing'''
        bulk_delete_operation_flag = is_bulk_delete_operation()
        if queue_token == 'project.post.update' and bulk_delete_operation_flag:
            _queue = 'project-delete-bulk'
        
        logger.debug(
            "adding deferred task = '%s' to queue = '%s' args = %s kwds = %s",
            func._name_, _queue, args, kwds)
        tracer = get_tracer()
        logger.info(
        "calling = %s for task = %s with tracer = %s args = %s and kwds = %s",
        'run_deferred', func._name_, tracer, args, kwds)
        trace(action="enqueue", category="task", queue=_queue,
           name=kwds.get("_name",""))

        if args or kwds:
            deferred.defer(_task_wrapper, pickleable(func), tracer, bulk_operation_flag, bulk_delete_operation_flag, env_company_name, is_cosell_app_flow, session_id, *args, _queue=_queue, **kwds)
        else:
            deferred.defer(_task_wrapper, pickleable(func), tracer, bulk_operation_flag, bulk_delete_operation_flag, env_company_name, is_cosell_app_flow, session_id, _queue=_queue)
    else:
        logger.info("executing function %s without deferring", func._name_)
        # deferred.defer treats keyword arguments starting with '_' as special
        # and passes them to the task api.
        # https://cloud.google.com/appengine/docs/python/taskqueue/tasks
        # If we are not deferring, filter out these arguments.
        if args or kwds:
            filtered_kwds = {}
            for (k, v) in kwds.iteritems():
                if not k.startswith('_'):
                    filtered_kwds[k] = v
            func(*args, **filtered_kwds)
        else:
            func()


@utils.decorator
def deferred_task(func, args, kwds, **options):
    """ deferred_task will be used as a decorator for a function
      Decorator processes 'retries' option

      Inspired by ndb.transactional
      This supports two forms:

      (1) Vanilla: (retries default to 0)
          @deferred_task
          def callback(args, kwds):
        ...

      (2) With options:
          @deferred_task(retries=1)
          def callback(args, kwds):

    NOTE: Do not have keyword arguments starting with '_' for func.
    See run_deferred above for why.
        ...
    """
    options.setdefault('retries', 0)
    options.setdefault('name', func._name_)
    _num_retries = options['retries']
    logger.info(
        "starting execution of function %s  retries=%s",
        func._name_,
        _num_retries)
    _start_time=datetime.datetime.utcnow()
    trace(action="start", category="task", time=_start_time.isoformat(),
       name=options['name'])
    try:
        if args or kwds:
            return func(*args, **kwds)
        else:
            return func()
    except exceptions.UnrecoverableErrorException as e:
        message = "Unrecoverable error in deferred task (%s, args=%s, kwds=%s, options=%s), avoiding retries. Error message: %s" % (
            options['name'], args, kwds, options, e.get_error_message())
        logger.error(message)
        raise deferred.PermanentTaskFailure(message)
    except BaseException:
        logger.error(
            "exception in deferred task: %s",
            options['name'],
            exc_info=True)
        retry_count = get_retry_count()
        logger.debug("got retry_count: %s", retry_count)
        if retry_count is None or retry_count >= _num_retries:
            raise deferred.PermanentTaskFailure(
                "%s failed after %s retries" %
                (options['name'], retry_count))
        else:
            logger.info("retrying deferred task: %s", options['name'])
            raise
    finally:
        _end_time=datetime.datetime.utcnow()
        delta = (_end_time - _start_time).total_seconds()
        trace(action="end", category="task", time=_end_time.isoformat(),
           name=options['name'], elapsed_time=delta)


@utils.decorator
def postponed_callback(func, args, kwds):
    """ postponed_exec will be used as a decorator for a function
    that returns a token, corresponding to a callback whose
    execution is completed at a later time.

    The purpose of the decorator is to allow the immediate (versus postponed)
    execution of the callback in unit tests.
    """

    _enable_postponed_callbacks = \
        settings.config.get('ENABLE_POSTPONED_CALLBACKS', True)

    logger.info(
        "starting execution of callback %s, _enable_postponed_callbacks: %s",
        func._name_, _enable_postponed_callbacks)

    if not _enable_postponed_callbacks and (args or kwds):
        token = func(*args, **kwds)
        logger.debug("postponed_callback: token: %s", token)
        return WSWTokenAPI.process(token)

    elif not _enable_postponed_callbacks:
        token = func(*args, **kwds)
        logger.debug("postponed_callback: token: %s", token)
        return WSWTokenAPI.process(token)

    elif args or kwds:
        return func(*args, **kwds)

    else:
        return func


DEFAULT_QUEUE_TOKEN = 'default-task'


class TaskCallbackType(object):
    SUCCESS = 'success'
    FAILURE = 'failure'
    FINALLY = 'finally'

    @classmethod
    def list(cls):
        return [cls.SUCCESS, cls.FAILURE, cls.FINALLY]


class TaskStatus(object):
    SUCCESS = 'success'
    FAILURE = 'failure'
    RUNAGAIN = 'runagain'


class CallbackMixin(object):

    def _init_(self, queue_token, context=None):
        self.queue_token=queue_token
        self.callbacks = defaultdict(set)
        self._context = context

    def _add_callback(self, callback_type, callback):
        self.callbacks[callback_type].add(pickleable(callback))

    def on_success(self, callback):
        self._add_callback(TaskCallbackType.SUCCESS, callback)
        return self

    def on_failure(self, callback):
        self._add_callback(TaskCallbackType.FAILURE, callback)
        return self

    def get_callback_type(self, callback_type):
        return self.callbacks.get(callback_type, set())

    def always_run(self, callback):
        self._add_callback(TaskCallbackType.FINALLY, callback)

    def run_relevant_callbacks(self, callback_type, status_message, **kwargs):
        callbacks = []
        if self.callbacks[callback_type]:
            callbacks.extend(self.callbacks[callback_type])
        if self.callbacks[TaskCallbackType.FINALLY]:
            callbacks.extend(self.callbacks[TaskCallbackType.FINALLY])

        for c in callbacks:
            run_deferred(self.queue_token, c, status_message, **kwargs)

    def success(self, status_message, **kwargs):
        if self._context is not None:
            self.run_relevant_callbacks(TaskCallbackType.SUCCESS, status_message, context=self._context, **kwargs)
        else:
            self.run_relevant_callbacks(TaskCallbackType.SUCCESS, status_message, **kwargs)

    def failure(self, status_message, **kwargs):
        if self._context is not None:
            self.run_relevant_callbacks(TaskCallbackType.FAILURE, status_message, context=self._context, **kwargs)
        else:
            self.run_relevant_callbacks(TaskCallbackType.FAILURE, status_message, **kwargs)

    def transfer_callbacks_to(self, dest_task):
        """
        Transfers callabcks from self to task contained in dest_task
        This is used when a Task returns another task at the end of
        its execution. In such cases we used to previously nest
        callbacks until the inner most callback is done. This meant
        that the more the depth of nesting of tasks the more stack space
        is required to serialize(pickle) the deferred task that runs the
        "Task". Instead this method now merges tasks from outer Task into
        the new inner task so that when the inner most task is done it
        can run all the callbacks from its outer Tasks

        Here is a flow of how things were before:
        Task T1 with callback C1 returns Task T2 with callback C2 which when
        done returns Task T3 with callback C3 and so on .... Task Tn, Callback Cn
        The layering of callbacks was as follows
            Task T1 has callback C1
            Task T2 has callback C2 -> C1
            ...

            Task Tn has callback Cn -> Cn-1 -> .... C1
        Where -> indicates Cn contains a call (pickled curried function) to Cn-1 and so on
        Instead with this method we can achieve the following
            Task T1 has callback C1
            Task T2 has callback C2, C1
            ...
            Task Tn has callback Cn, Cn-1, ..., C1

        Instead of nesting now we have a list of callbacks that are invoked when the inner
        most task is done. This avoids recursion when pickling callbacks and yet retains
        the expected behavior.
        """

        if self._context is not None:
            dest_task._context = self._context

        for type in TaskCallbackType.list():
            cbs = set()
            func = None
            if self.callbacks[type]:
                cbs = self.callbacks[type]
            if type == TaskCallbackType.SUCCESS:
                func = dest_task.on_success
            elif type == TaskCallbackType.FAILURE:
                func = dest_task.on_failure
            elif type == TaskCallbackType.FINALLY:
                func = dest_task.always_run
            for c in cbs:
                func(c)


class BaseTask(CallbackMixin):
    """
    Base Task that supports the notion of addition of subtasks
    The base task is not complete until all its subtasks are complete
    If there are no sub tasks then the base task is complete when its
    "run" function is done.
    The "run" function itself is to be implemented in subclasses
    """

    def _init_(self, **options):
        self.options = options
        self.queue_token = options.pop('queue_token', DEFAULT_QUEUE_TOKEN)
        context = options.pop('context', None)
        super(BaseTask, self)._init_(self.queue_token, context)

    def run(self):
        raise NotImplementedError

    def add_subtask(self, task):
        task.on_success(
            self._subtask_completed).on_failure(
            self._subtask_failed).run()

    def _subtask_completed(self, status_message, **kwargs):
        self.success(status_message, **kwargs)

    def _subtask_failed(self, status_message, **kwargs):
        self.failure(status_message, **kwargs)


class Task(BaseTask):
    """
    Single Task that supports registering callbacks for completion(success/failure)
    Example usage:
        t = Task(<task func>, 1, "run this").on_success(<success_callback>)
            .on_failure(<failure_callback>).run()

    results in
        <task_func>(1, "run this")
        when task_func is done based on its execution status either
        success_callback or failure callback is called.
        task_func can raise an exception to trigger failure
        task_func is expected to return TaskStatus enum value to
        indiciate FAILURE/SUCCESS

        The task itself is run on the upgrade queue but that can
        easily be changed in future to run on any queue using the
        _queue argument to deferred.defer
    """

    def _init_(self, func, *args, **kwargs):
        self.call_func = pickleable(func)
        self.args = args
        self.kwargs = kwargs
        super(Task, self)._init_(**kwargs)
        self.kwargs.pop('queue_token', None)

    @deferred_task(retries=0)
    def _run_internal(self):
        status = TaskStatus.SUCCESS
        try:
            kwargs = self.kwargs.copy()
            if self._context is not None:
                kwargs['context'] = self._context
            status = self.call_func(*self.args, **kwargs)
        except Exception as e:
            logger.error("Task failed due to exception %s", e, exc_info=True)
            self.failure(str(e))
            return

        if status is TaskStatus.FAILURE:
            self.failure("Task returned failure status")
        elif status is TaskStatus.RUNAGAIN:
            self.add_subtask(self)
        elif isinstance(status, BaseTask):
            self.add_subtask_internal(status)
        else:
            self.success("Task succeeded")

        return

    def add_subtask_internal(self, task):
        stop = False
        while (not stop):
            try:
                self.transfer_callbacks_to(task)
                task.run()
                stop = True
            except Timeout as te:
                logger.error("Datatore Timedout, trying again")
            except Exception as e:
                logger.error("Continuation task failed: %s", e, exc_info=True)
                stop = True
                self.failure(str(e))

    def run(self):
        logger.info("Inside run of Task. _run_internal = (%s)", self._run_internal)
        pickled = pickleable(self._run_internal)
        logger.info("Inside run of Task. pickled = (%s)", pickled)
        run_deferred(self.queue_token, pickled)


class InOrderTasks(BaseTask):

    """
    Class that supports running Tasks in order that they are registered
    Example usage:
        t = Task(<task func>, 1, "run this").on_success(<success_callback>)
            .on_failure(<failure_callback>)
        t1 = Task(<task func1>, 2, "run that").on_success(<callback>)
            .on_failure(<callback>)

        InOrderTasks([t, t1]).on_success(<cb>).on_failure(<cb>)

    results in
        task t and t1 run in order i.e. one after another sequentially.
        After both tasks are complete then based on overall status of t and t1
        either success or failure callback is called.

    Options:
        abort_on_failure (boolean) If set to True and a task fails, all
            subsequent tasks will not be executed.

            If set to False (default), failure in one task will
            not abort execution i.e. other tasks will continue to run after
            failed task.
    """

    def _init_(self, *tasks, **options):
        self.atleast_one_failed = False
        self.tasks = list(tasks)
        self.abort_on_failure = options.get('abort_on_failure', False)
        logger.debug(locals())
        super(InOrderTasks, self)._init_(**options)

    def run(self):
        logger.info("Running next task")
        task = self.tasks.pop(0)
        self.add_subtask(task)

    def _subtask_completed(self, status_message, **kwargs):
        if self.tasks:
            self.run()
        else:
            if self.atleast_one_failed:
                self.failure("Some tasks failed", **kwargs)
            else:
                self.success(status_message, **kwargs)

    def _subtask_failed(self, status_message, **kwargs):
        self.atleast_one_failed = True
        if (not self.atleast_one_failed or (self.atleast_one_failed and not self.abort_on_failure)) and self.tasks:
            self.run()
        else:
            self.failure(status_message, **kwargs)


class InParallelTasks(BaseTask):

    """
    Class that supports running Tasks in parallel
    Example usage:
        t = Task(<task func>, 1, "run this").on_success(<success_callback>)
            .on_failure(<failure_callback>)
        t1 = Task(<task func1>, 2, "run that").on_success(<callback>)
            .on_failure(<callback>)

        InParallelTasks(t, t1).on_success(<cb>).on_failure(<cb>)

    results in
        task t and t1 run in parallel.
        After both tasks are complete then based on overall status of t and t1
        either success or failure callback is called. Failure in one task will
        not abort execution i.e. other tasks will continue to run after failed task.

        Uses sharedcounter to track how many tasks are complete in all.
    """

    def _init_(self, *tasks, **options):
        self.tasks = list(tasks)
        super(InParallelTasks, self)._init_(**options)
        self.counter_id = allocate_id()
        self.failed_counter_id = allocate_id()

    def run(self):
        from common.entity_task_utils import EntityActionExecutor, InMemoryIterator
        self.completed = 0
        # TODO(vshenoi): Cleanup counter
        # Use EntityActionExecutor to avoid timeouts in this.
        iterable = InMemoryIterator(self.tasks)
        executor = EntityActionExecutor(iterable, self.add_subtask, queue_token=self.queue_token)
        executor.run()

    def _subtask_completed(self, status_message, **kwargs):
        increment(self.counter_id)

        if len(self.tasks) == get_count(self.counter_id):
            # if both the parent and the child task have a context,
            # remove child context to avoid param name conflict during callback call
            if self._context and 'context' in kwargs:
                kwargs.pop('context')

            if get_count(self.failed_counter_id) != 0:
                self.failure("Some tasks failed")
            else:
                self.success(status_message, **kwargs)

    def _subtask_failed(self, status_message, **kwargs):
        increment(self.counter_id)
        increment(self.failed_counter_id)

        if len(self.tasks) == get_count(self.counter_id):
            # if both the parent and the child task have a context,
            # remove child context to avoid param name conflict during callback call
            if self._context and 'context' in kwargs:
                kwargs.pop('context')

            self.failure(status_message, **kwargs)


class DependentTaskScheduler(BaseTask):
    """
    Class that orders execution of Tasks on the basis of its dependencies on other tasks. 
    Args: 
        dependency_graph - Depedency graph in the form of adjacency list with task_name
                            denoting Tasks.
        task_map - map of task_name to task.
    For example
    for this dependency_graph -
        {
            't0': ['t5','t4'],
            't1': ['t3','t4'],   (here t1 depends on t3 and t4)
            't2': ['t5'],
            't3': ['t2'],
            't4': [],
            't5': []
        }
    The execution would be 
        [t5, t4],
        [t2, t0],
        [t3],
        [t1]
    here each line is executed in Parallel and all the lines in Sequence
    """

    def _init_(self, dependency_graph, task_map=None, **options):
        # type: (dict, dict, Any) -> None
        self._dependency_graph = deepcopy(dependency_graph)
        self._task_map = task_map
        self._reverse_graph = {}
        self._batches = []
        self._task_batches = []
        super(DependentTaskScheduler, self)._init_(**options)

    def _reverse_dependency_graph(self):
        """
        Reverses the directed dependency graph represented as Adjacency List
        and stores it in _reverse_graph for a quick lookup during batching
        """
        self._reverse_graph = {}
        for task, dependencies in self._dependency_graph.items():
            for dependency in dependencies:
                self._reverse_graph.setdefault(dependency, []).append(task)
        
            edge_vertices = set(self._dependency_graph.keys()) - \
                                     set(self._reverse_graph.keys())
            for edge_vertice in edge_vertices:
                self._reverse_graph[edge_vertice] = []

    def cycle_check(self):
        """
        Checks if there is any cyclic dependency. 
        Throws ValidationException if cycle is present
        else Returns None 
        """
        visited = {}
        dfs_visited = {}
        for node, _ in self._dependency_graph.items():
            if not visited.get(node):
                self._cycle_check_helper(visited, dfs_visited, node)

    def _cycle_check_helper(self, visited, dfs_visited, node):
        """
        Raises Validation exception if there is any cyclic dependency.
        """
        visited[node] = True
        dfs_visited[node] = True

        for neighbour in self._dependency_graph[node]:
            if not visited.get(neighbour):
                self._cycle_check_helper(visited, dfs_visited, neighbour)
            elif dfs_visited.get(neighbour):
                raise exceptions.ValidationException("TASK-9", node1=node, node2=neighbour)

        dfs_visited[node] = False

    def _batch_tasks(self):
        """
        Batches tasks to be executed in parralel and inorder. 
        Mutates batches to a list of list. 
        NOTE: also makes _dependency_graph empty
        """
        while self._dependency_graph:
            current_batch = []
            for task, dependencies in self._dependency_graph.items():
                if not dependencies:
                    current_batch.append(task)

            for task in current_batch:
                self._dependency_graph.pop(task)
                self._remove_from_dependencies(task)
            
            self._batches.append(current_batch)

    def _remove_from_dependencies(self, task):
        """
        Removes a task from all the dependencies (i.e - from all dependency lists)
        Mutates _dependency_graph. Uses _reverse_graph for a quick lookup
        """
        waiting_tasks = self._reverse_graph.get(task, []) 
    
        for wait_task in waiting_tasks:
            dependency_list = self._dependency_graph.get(wait_task, []) 
            if task in dependency_list:
                dependency_list.remove(task)

    def _batch_parallel_tasks(self):
        """
        Batches all parrallel tasks using _batches. Mutates _task_batches
        """
        for batch in self._batches:
            parralel_tasks = []
            
            for task_name in batch:
                task = self._task_map.get(task_name)
                if task:
                    parralel_tasks.append(task)

            if parralel_tasks:
                curr_task_batch = InParallelTasks(*tuple(parralel_tasks))
                self._task_batches.append(curr_task_batch)


    def _transfer_callbacks(self, all_tasks):
        """
        Transfers callbacks to InOrderTasks
        """
        for callback_type, callbacks in self.callbacks.items():
            if callback_type == TaskCallbackType.SUCCESS:
                for callback in callbacks:
                    all_tasks.on_success(callback)
            elif callback_type == TaskCallbackType.FAILURE:
                for callback in callbacks:
                    all_tasks.on_failure(callback)
            elif callback_type == TaskCallbackType.FINALLY:
                for callback in callbacks:
                    all_tasks.always_run(callback)

    def run(self):
        """
        Run the Tasks on basis of dependencies on other tasks.
        """
        self.cycle_check()
        self._reverse_dependency_graph()
        self._batch_tasks()
        self._batch_parallel_tasks()
        all_tasks = InOrderTasks(*tuple(self._task_batches), abort_on_failure = True)
        self._transfer_callbacks(all_tasks)
        all_tasks.run()

    def return_batches(self):
        """
        Returns the batches of tasks to be executed in parallel
        """
        self.cycle_check()
        self._reverse_dependency_graph()
        self._batch_tasks()
        # once batches are formed, they will be in order like this
        # parallel batch p1 -> parallel batch p2 -> parallel batch p3 -> ...
        # each parallel batch will have tasks that can be executed in any order
        task_batches = []
        for batch in self._batches:
            for task in batch:
                task_batches.append(task)
        logger.info("Task batches: %s", task_batches)
        return task_batches

def pickleable(callable):
    """
    This method converts a given callback type to something that
    can be pickled for deferred execution. Mainly handles
    transformation of instance methods into _PickleableMethod instances
    """
    if isinstance(callable, types.MethodType):
        return PickleableMethod(callable.im_self, callable.im_func.__name_)
    elif isinstance(callable, types.BuiltinMethodType):
        if not callable._self_:
            return callable
        else:
            return PickleableMethod(callable.__self_, callable._name_)
    elif isinstance(callable, types.ObjectType) and hasattr(callable, "_call_"):
        return callable
    elif isinstance(callable, (types.FunctionType, types.BuiltinFunctionType,
                               types.ClassType, types.UnboundMethodType)):
        return callable
    else:
        raise ValueError("Can't defer %s. Must be callable" % callable)


class _PickleableMethod(object):

    def _init_(self, *curried):
        self.curried = curried

    def _call_(self, *a, **kw):
        return getattr(*self.curried)(*a, **kw)

    @property
    def _name_(self):
        return "%s.%s" % self.curried

    def _str_(self):
        return str(self.curried)