from _future_ import absolute_import
from common.task_utils import (
    Task, InParallelTasks, pickleable, TaskStatus,
    TaskCallbackType, DEFAULT_QUEUE_TOKEN,
    retryable_task_wrapper, run_deferred,
    FAILED_ENTITIES_RETRY_QUEUE_TOKEN)
from google.appengine.ext import ndb

from common.exceptions import WorkSpanException
from common.enum.common_enum import JobStatus
import common.model.job_model as job_model
from common.model.ws_model import KeyValue
from protorpc.protojson import MessageJSONEncoder, encode_message, decode_message
import common.ndbutils as ndbutils
import common.job.job_lib as job_lib
from common.enum.common_enum import JobType

import datetime
import logging
import abc
import functools
import json
import common.exceptions as exceptions
import google.appengine.ext.appstats.recording as recording
from google.appengine.ext.db import Timeout
import time
import common.model.modellib as modellib

logger = logging.getLogger(_name_)

DEFAULT_BATCHSIZE = 20
DEFAULT_CACHE_CLEAR = 40
DEFAULT_ALLOWANCE = 570 * 1000
SUBBATCH_SIZE = 5

START_DATETIME = "start_datetime"
SUCCESS_COUNT = "success_count"
FAILURE_COUNT = "failure_count"
TOTAL_COUNT = "total_count"
SUBMITTER_CRED = 'submitter_cred'
MAX_ALLOWED_RETRYABLE_ENTITIES = 990


class EntityActionExecutor(Task):
    """
    Given a entity query(query_fn) and an entity action function (action_fn)
    this class provides a convenient way of iterating over all entities and
    performing an action on them without having to deal with deadline
    problems.
    Perform Retry flag would fire a deferred task when an exception is raised
    for a Entity. The number of retries is handled at queue level. The failure
    callbacks would be invoked whenever the retry action function fails.
    If number of retryable entites are above the permissiable limit of
    MAX_ALLOWED_RETRYABLE_ENTITIES then the perform retry flag is turned off.
    """

    def _init_(self, iterable, action_fn, context=None,
                 batchsize=DEFAULT_BATCHSIZE, allowance=DEFAULT_ALLOWANCE,
                 taskname=None, perform_retry=False,
                 max_allowed_retryable_entities=MAX_ALLOWED_RETRYABLE_ENTITIES,
                 **action_opts):
        self.queue_token = action_opts.pop('queue_token', DEFAULT_QUEUE_TOKEN)
        if not self.queue_token:
            self.queue_token = DEFAULT_QUEUE_TOKEN
        self.taskname = taskname
        super(EntityActionExecutor, self)._init_(self._run_action, queue_token=self.queue_token, context=context)
        if not iterable or not action_fn:
            raise exceptions.InternalException(
                "Invalid arguments to %s initializer",
                self._class_._name_)

        # All instance variables must be pickeable.
        # When a subsequent task is spawned for the next task batch,
        # the function _run_action and object instance is pickled.
        logger.info("These are Action Opts: %s", action_opts)
        self._iterable = iterable
        self._action_fn = pickleable(action_fn)
        self._batchsize = batchsize
        self._allowance = allowance
        self._action_opts = action_opts
        self._batchnumber = 0
        self._cursor = None
        self._failed = False
        self._total_count = 0
        self._start_time = None
        self._end_time = None
        self._context = context
        self._perform_retry = perform_retry
        self._retrying_entities = 0
        self._max_allowed_retryable_entities = max_allowed_retryable_entities

    def run(self):
        self._start_time = datetime.datetime.utcnow()
        super(EntityActionExecutor, self).run()
        return self

    def _handle_exception(self, ent, e):
        logger.error(
            "Could not process entity id %s: error %s",
            ent,
            e,
            exc_info=True)

        if self._perform_retry:
            self._retrying_entities += 1
            logger.warning("Retrying Processing Failed entity: %s", ent)
            success_callbacks = self.get_callback_type(
                                    TaskCallbackType.SUCCESS)
            failure_callbacks = self.get_callback_type(
                                    TaskCallbackType.FAILURE)
            pickled = pickleable(retryable_task_wrapper)
            function_args = [ent, success_callbacks, failure_callbacks]
            run_deferred(FAILED_ENTITIES_RETRY_QUEUE_TOKEN, pickled,
                         self._action_fn, *function_args,
                         **self._action_opts)
            if self._retrying_entities >= self._max_allowed_retryable_entities:
                self._perform_retry = False
        else:
            self._failed = True

    def _next_task(self, count, iterator):
        logger.info(
            "For task %s: Scheduling another task to continue processing, already "
            "processed %s entities", self.taskname, count)
        logger.info("For task %s: Processed %s batches so far", self.taskname, self._batchnumber)
        self._cursor = iterator.cursor_after()

        # A function executed in the context of an object instance will have access 
        # to the instance variables. So self._run_action will have access 
        # to the instance variables of the EntityActionExecutor
        task = Task(self._run_action, queue_token=self.queue_token)
        return task

    def _execute_action(self, ent, context=None):
        if self._context is not None:
            self._action_opts['context'] = self._context
        logger.debug("_execute_action: _action_fn: %s, ent: %s, _action_opts: %s", self._action_fn, ent,
                     self._action_opts)
        self._action_fn(ent, **self._action_opts)

    def _finish_ent_processing(self, ent, ent_start_ts, starts):
        endts = datetime.datetime.now()
        logger.info(
            "For task %s: Entity processing took %s (ms)", self.taskname,
            (endts - ent_start_ts).total_seconds() * 1000)
        elapsed_ts = ((endts - starts).total_seconds()) * 1000
        return elapsed_ts

    def _finish(self):
        logger.info("For task %s: Finished processing %s entities.",
                    self.taskname, self._total_count-self._retrying_entities)
        if self._perform_retry and self._retrying_entities:
            logger.info("For task %s: Retrying %s entities",
                        self.taskname, self._retrying_entities)
        self._end_time = datetime.datetime.utcnow()
        elapsed_ts = ((self._end_time - self._start_time).total_seconds()) * 1000
        logger.info("For task %s: Total time taken %s (ms) by entites.", self.taskname, elapsed_ts)
        return elapsed_ts

    def _run_action(self, context=None):
        """
        This method iterates over entities or entity keys returned
        by query from query_fn. It then runs until it exhausts
        the allotted time to run (allowance).
        After exceeding allowance it will schedule itself again
        to resume from where it left off in a new Task.

        This process continues until there are entities to process
        """

        recording.dont_record()
        self._batchnumber += 1

        starts = datetime.datetime.now()
        iterator = self._iterable.iter(self._cursor)

        count = 0
        cache_count = 0
        logger.info("For task %s: Task started at %s and batch number is %s", self.taskname, starts, self._batchnumber)
        for ent in iterator:
            ent_start_ts = datetime.datetime.now()
            if isinstance(ent, (basestring,tuple)):
                logger.info("For task %s: Processing entity %s", self.taskname, ent)
            try:
                self._execute_action(ent, context=context)
            except Exception as e:
                # Log error and continue processing the rest of batch
                self._handle_exception(ent, e)

            elapsed_ts = self._finish_ent_processing(ent, ent_start_ts, starts)
            count += 1
            self._total_count += 1
            cache_count += 1

            if cache_count >= DEFAULT_CACHE_CLEAR or (
                    self._batchsize and cache_count >= self._batchsize):
                context = ndb.get_context()
                context.clear_cache()
                cache_count = 0
                logger.info("For task %s: Clear default cache", self.taskname)

            # Check if we have exhausted the allotted time to run (allowance)
            # If so schedule a continuation
            if elapsed_ts >= self._allowance or (
                    self._batchsize and count >= self._batchsize):
                logger.info("For task %s: Exhausted allotted time or cron limit %s exceeded the batch size %s",
                            self.taskname, count, self._batchsize)
                task = self._next_task(count, iterator)
                return task

        self._finish()

        return TaskStatus.FAILURE if self._failed else TaskStatus.SUCCESS

    def success(self, status_message, **kwargs):
        data = {}
        if self._context is not None:
            data['context'] = self._context
        self.run_relevant_callbacks(TaskCallbackType.SUCCESS, status_message,
                                    **data)

    def failure(self, status_message, **kwargs):
        data = {}
        if self._context is not None:
            data['context'] = self._context
        self.run_relevant_callbacks(TaskCallbackType.FAILURE, status_message,
                                    **data)


class EntityJobExecutor(EntityActionExecutor):
    """
        This class executes an action over entities,
        and while doing so records the state of the job and subtasks,
        including successes and failures

        If function action_fn throws an exception of type BaseJobTaskException,
        the task_errors property of the exception will be stored
        as error parameters in the JobTask.  This allows the action_fn to communicate
        error parameters to the EntityJobExecutor and to have these error parameters
        stored with the JobTask.

        action_opts, i.e., job parameters are saved in the job's 'params' attribute

        By default, the job id is stored in the executor's _context as the WS_JOB_ID parameter, 
        which is passed to success and failure callbacks. So the success and failure callbacks
        must take 'context' as a parameter
    """

    def _init_(self, iterable, action_fn, parent_id, job_type, user_cred, job_member_ids=None,
                 context=None, batchsize=DEFAULT_BATCHSIZE, allowance=DEFAULT_ALLOWANCE,
                 **action_opts):
        """

            Args:
                job_member_ids (list) list of job members that will be added to the job as participants.
                    The submitter denoted by the user_cred will be added as a job member with a lead role.

        """
        logger.info("Creating EntityJobExecutor (%s)", locals())
        action_opts['user_cred'] = user_cred
        super(EntityJobExecutor, self)._init_(iterable, action_fn, context,
                                                batchsize, allowance, **action_opts)
        self._job_id = None
        self._success_count = 0
        self._failure_count = 0
        self._parent_id = parent_id
        self._job_type = job_type
        self._user_cred = user_cred
        self._job_member_ids = job_member_ids if job_member_ids is not None else []
        self.elapsed_ts = 0

    def run(self):
        self._start_time = datetime.datetime.utcnow()

        # initialize exec_stats
        exec_stats = list()
        self._update_exec_stats(exec_stats)
        logger.info("Inside run of EntityJobExecutor. action_opts = (%s)", self._action_opts)
        job_ent = job_lib.create_job(self._user_cred, self._parent_id, self._user_cred.user_id,
                                     self._job_type, self._job_member_ids, exec_stats, self._start_time,
                                     self._action_opts)

        self._job_id = job_ent.job_id
        
        # add job id to context
        self._context = self._context if self._context else dict()
        self._context[job_lib.WS_JOB_ID] = self._job_id

        logger.info("running job %s", self._job_id)
        super(EntityJobExecutor, self).run()
        return self._job_id

    def _execute_action(self, ent, context=None):
        super(EntityJobExecutor, self)._execute_action(ent)
        self._success_count += 1
        # TODO: considering publishing an event to record success in JobTask
        inputs = list()
        kv = KeyValue(name='input', value=str(ent))
        inputs.append(kv)

        saved = False
        while(not saved):
            try:
                job_model.JobTask.create_and_save(
                    self._user_cred,
                    self._job_id,
                    self._parent_id,
                    JobStatus.SUCCESS,
                    inputs
                )
                saved = True
            except Timeout as te:
                time.sleep(10)


        # update job execution status
        if self._success_count % SUBBATCH_SIZE == 0:
            exec_stats = list()
            self._update_exec_stats(exec_stats)

            saved = False
            while(not saved):
                try:
                    job_lib.update_job(
                        self._user_cred,
                        self._job_id,
                        exec_stats=exec_stats
                    )
                    saved = True
                except Timeout as te:
                    time.sleep(10)


    def _finish_ent_processing(self, ent, ent_start_ts, starts):

        """ Steps for job task completion
        """
        elapsed_ts = super(EntityJobExecutor, self)._finish_ent_processing(ent, ent_start_ts, starts)
        return elapsed_ts

    def _update_exec_stats(self, exec_stats):
        KeyValue.uppend(exec_stats, 'success_count', self._success_count)
        KeyValue.uppend(exec_stats, 'failure_count', self._failure_count)
        KeyValue.uppend(exec_stats, 'total_count', self._total_count)

    def _finish(self):
        """
            Steps for job completion.
        """
        elapsed_ts = super(EntityJobExecutor, self)._finish()

        # Record successful job completion
        status = JobStatus.SUCCESS if self._failure_count == 0 else JobStatus.FAILURE
        exec_stats = list()
        KeyValue.uppend(exec_stats, 'elapsed_ts', elapsed_ts)
        self._update_exec_stats(exec_stats)

        saved = False
        while(not saved):
            try:
                job_lib.update_job(self._user_cred, self._job_id, exec_stats=exec_stats, status=status,
                                end_datetime=self._end_time)
                saved = True
            except Timeout as te:
                time.sleep(10)

        return elapsed_ts

    def _handle_exception(self, ent, e):
        super(EntityJobExecutor, self)._handle_exception(ent, e)
        self._failure_count += 1

        # TODO: consider publishing event
        # to record the failures of the job task with both the task the job
        if isinstance(e, exceptions.BaseJobTaskException):
            errors = e.task_errors
            logger.error("errors: %s" % errors)
        else:
            task_error = job_model.JobTaskError()
            if isinstance(e, exceptions.ValidationException):
                msg_str = e.json_string()
                msg_json = json.loads(msg_str)
                msg_value = msg_json.get('msg')
            else:
                msg_value = str(e)
            kv = KeyValue(name='msg', value=msg_value)
            task_error.properties.append(kv)
            errors = list()
            errors.append(task_error)
        context = list()
        KeyValue.uppend(context, 'input', str(ent))
        job_model.JobTask.create_and_save(self._user_cred, self._job_id,
                                          self._parent_id, JobStatus.FAILURE,
                                          context, errors)

        # update job execution status
        exec_stats = list()
        self._update_exec_stats(exec_stats)

        saved = False
        while(not saved):
            try:
                job_lib.update_job(self._user_cred, self._job_id, exec_stats=exec_stats, task_errors=errors)
                saved = True
            except Timeout as te:
                time.sleep(10)

    def _next_task(self, count, iterator):
        task = super(EntityJobExecutor, self)._next_task(count, iterator)

        # Update job task counts
        job_ent = job_model.Job.read_entity(self._job_id)
        exec_stats = job_ent.exec_stats
        self._update_exec_stats(exec_stats)
        job_ent.save(self._user_cred)

        return task

    def get_job_id(self):
        return self._job_id


class EntityAction(object):
    """Execute the given action on all entities returned by the query.
    Uses the EntityActionExecutor.
    This needs to be pickleable.
    Usage. EntityAction().executor().run()
    """

    @abc.abstractmethod
    def action(self, entity, context=None):
        raise NotImplementedError

    @abc.abstractmethod
    def query(self):
        raise NotImplementedError

    def query_options(self):
        return None

    def executor(self, batchsize=DEFAULT_BATCHSIZE,
                 allowance=DEFAULT_ALLOWANCE,
                 taskname=None,
                 context=None, **opts):
        """Returns an executor to execute this action. To execute the action,
        call run() on the executor.
        """
        queue_token = opts.pop('queue_token', DEFAULT_QUEUE_TOKEN)

        iterable = EntityIterable(self.query, self.query_options())
        return EntityActionExecutor(iterable, self.action,
                                    batchsize=batchsize, allowance=allowance,
                                    taskname=taskname, queue_token=queue_token,
                                    context=context)


class Action(object):
    """Execute the given action on all objects provided in the constructor.
    Uses the EntityActionExecutor with an InMemoryIterator or
    NDBObjectIterator.
    This needs to be pickleable.
    Usage: Action(objs).executor().run()
    """
    def _init_(self, objects):
        """
        Create an action
        :param objects: List of objects to run the action on.
        """
        iterable = None
        INMEMORY_ITERATOR_LIMIT = 1000
        if len(objects) < INMEMORY_ITERATOR_LIMIT:
            logger.info("Using in memory iterator")
            iterable = InMemoryIterator(objects)
        else:
            logger.info("Using in NDB object iterator")
            iterable = NDBObjectIterator(objects)
        self._iterable = iterable

    @abc.abstractmethod
    def action(self, obj, context=None):
        """
        Run this function on every object in the list of objects.
        """
        raise NotImplementedError

    def success_callback(self, msg, context=None):
        """
        Override this method for a success callback. Default implementation
        does nothing.
        :param msg: logger message for success callback
        :param context: Context that was passed in to the executor() method if
        any.
        :return: Nothing.
        """
        pass

    def failure_callback(self, msg, context=None):
        """
        Override this method for a failure callback. Default implementation
        does nothing.
        :param msg: logger message for failure callback
        :param context: Context that was passed in to the executor() method if
        any.
        :return: Nothing.
        """
        pass

    def executor(self, batchsize=None, taskname=None,
                 allowance=DEFAULT_ALLOWANCE,
                 context=None, **opts):
        """Returns an executor to execute this action. To execute the action,
        call run() on the executor.
        """
        queue_token = opts.pop('queue_token', DEFAULT_QUEUE_TOKEN)
        executor = EntityActionExecutor(self._iterable, self.action,
                                        allowance=allowance,
                                        taskname=taskname,
                                        batchsize=batchsize,
                                        queue_token=queue_token,
                                        context=context)
        executor.on_success(pickleable(self.success_callback)).on_failure(
            pickleable(self.failure_callback))
        return executor


class BulkAction(object):
    """
    Execute the given action on all entities supplied using an iterable.
    Uses the EntityActionExecutor.
    Usage. BulkAction().executor().run()
    """

    def _init_(self, iterable, request, request_format, user_cred):
        """

        :param iterable: This is a list of entities that can be represented
                            using an InMemoryIterator, CursorizedIterator, etc.
        :param request: Incoming request in encoded form.
        :param request_format: Request format to decode encoded request. For
        eg. team_messages.InviteMultiReq
        :param user_cred: User Credentials
        """
        self._iterable = iterable
        self._request = request
        self._request_format = request_format
        self._user_cred = user_cred

    @abc.abstractmethod
    def action_fn(self, request, object_id, context):
        """
        :param request: Incoming request in decoded format
        :param object_id: Object id for which action needs to be performed
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while
                        iterating over object ids to perform action.
        :return: Nothing
        """
        raise NotImplementedError

    @abc.abstractmethod
    def success_callback(self, msg, context):
        """
        :param msg: logger message for success callback
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while
                        iterating over object ids to perform action.
        :return: Nothing. It should log the success msg and send pusher
                    notification.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def failure_callback(self, msg, context):
        """
        :param msg: logger message for failure callback
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while
                        iterating over object ids to perform action.
        :return: Nothing. It should log the failure msg and send pusher
                        notification.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def success_payload_helper_fn(self, payload, request, object_id, context):
        """
        populate the payload with success pusher message
        :param payload: a list that contains all the pusher messages
        :param request: Incoming request in decoded format
        :param object_id: Object id for which action needs to be performed
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while
                        iterating over object ids to perform action.
        :return: Nothing
        """
        raise NotImplementedError

    @abc.abstractmethod
    def failure_payload_helper_fn(self, payload, request, object_id, error_msg, context):
        """
        populate the payload with failure pusher message
        :param payload: a list that contains all the pusher messages
        :param request: Incoming request in decoded format
        :param object_id: Object id for which action needs to be performed"
        :param error_msg: Error message that can be shown in the pusher notification
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while iterating over
                        object ids to perform action.
        :return: Nothing
        """
        raise NotImplementedError

    def _run_action(self, request, object_id, context):
        """
        :param request: Incoming request in encoded format
        :param object_id: Object id for which action needs to be performed
        :param context: a dictionary that can be used to store variables like
                        user cred and push notification payload while iterating over
                        object ids to perform action.
        :return: Nothing
        """
        payload = context.get("payload", [])
        try:
            request = decode_message(self._request_format, request)
            self.action_fn(request, object_id, context)
            self.success_payload_helper_fn(payload, request, object_id, context)
        except Exception as e:
            logger.info("Failed to perform action on object (%s)", object_id, exc_info=True)
            if isinstance(e, WorkSpanException):
                error_msg = json.loads(e.json_string())["msg"]
            else:
                error_msg = str(e)
            self.failure_payload_helper_fn(payload, request, object_id,
                                           error_msg, context)
        finally:
            context["payload"] = payload

    def executor(self):
        """
        Returns an executor to execute this action. To execute the action,
        call run() on the executor.  It will also send pusher notifications,
        the methods for which need to be defined in the sub-class.
        """
        action_fn = functools.update_wrapper(
            functools.partial(
                pickleable(self._run_action),
                self._request
            ),
            self._run_action
        )
        executor = EntityActionExecutor(self._iterable, action_fn,
                                        context={"user_cred": self._user_cred})
        executor.on_success(pickleable(self.success_callback)).on_failure(
            pickleable(self.failure_callback))
        return executor


class CursorizedIterator(object):

    @abc.abstractmethod
    def cursor_after(self):
        raise NotImplementedError

    def _iter_(self):
        return self

    @abc.abstractmethod
    def next(self):
        raise NotImplementedError


class EntityIterable(object):

    def _init_(self, query_fn, query_options):
        self._query_fn = pickleable(query_fn)
        self._query_options = query_options

    def iter(self, cursor=None):
        new_options = ndb.QueryOptions(
            produce_cursors=True, start_cursor=cursor)
        if self._query_options:
            query_options = self._query_options.merge(new_options)
        else:
            query_options = new_options
        query = self._query_fn()
        query_iter = query.iter(options=query_options)
        return query_iter

    def _iter_(self):
        # Default iter function returns an iterator that iterates starting
        # from the beginning.
        return self.iter()

class EntityBatchIterator(CursorizedIterator):
    def _init_(self, query_fn, query_options, batch_size = 10):
        self._query_fn = pickleable(query_fn)
        self._query_options = query_options
        self._batch_size = batch_size
    
    def iter(self, cursor=None):
        self._cursor = cursor
        self._end_of_iter = False
        return self
    
    def cursor_after(self):
        return self._cursor

    def next(self):
        if self._end_of_iter:
            raise StopIteration
        results = ndbutils.paginate(self._query_fn(), options = self._query_options, page_token=self._cursor, limit = self._batch_size)
        self._cursor = results.next_page_token
        if results.end_of_list:
            self._end_of_iter = True
        return results.items

class InMemoryIterator(CursorizedIterator):

    def _init_(self, data):
        self._data = data
        self._cursor = 0

    def iter(self, cursor=0):
        self._cursor = cursor
        if self._cursor is None:
            self._cursor = 0
        return self

    def cursor_after(self):
        return self._cursor

    def next(self):
        if self._cursor >= len(self._data):
            raise StopIteration
        data = self._data[self._cursor]
        self._cursor = self._cursor + 1
        return data


class NDBObjectCursor(object):
    def _init_(self, ndb_obj_keys=None, ndb_obj_data=None):
        self._ndb_obj_keys = ndb_obj_keys
        self._ndb_obj_data = ndb_obj_data
        self._obj_key_index = 0
        self._data_index = 0

    def next(self):
        if not self._ndb_obj_keys:
            raise StopIteration

        # Initialise ndb object data
        if not self._ndb_obj_data:
            if self._obj_key_index == len(self._ndb_obj_keys):
                # All elements are processed.
                raise StopIteration
            next_ndb_obj_key = self._ndb_obj_keys[self._obj_key_index]
            self._obj_key_index += 1
            next_ndb_obj = next_ndb_obj_key.get()
            if next_ndb_obj:
                self._ndb_obj_data = next_ndb_obj.cache_keys

        if (not self._ndb_obj_data) \
                or (self._data_index == len(self._ndb_obj_data)):
            # Data of this obj is processed, go to next obj
            self._data_index = 0
            self._ndb_obj_data = None
            return self.next()
        next_data_item = self._ndb_obj_data[self._data_index]
        self._data_index += 1
        return next_data_item


class NDBObjectIterator(CursorizedIterator):
    """
    Uses ndb objects for iterating over documents.
    For large data, chunk them into smaller ndb objects
    and use them for iteration.
    """

    class NDBCacheObject(ndb.Model,modellib.TTLMixin):
        cache_keys = ndb.PickleProperty()

    def _init_(self, data, chunk_size=1000):
        self._MAX_CHUNK_SIZE = chunk_size
        self._ndb_object_keys = []
        if not isinstance(data, list):
            raise ValueError("Data is not a list")
        self._cache_chunk_util(data)

    def _cache_chunk_util(self, data):
        def _chunk_data(l, n):
            for i in range(0, len(l), n):
                yield l[i:i+n]
        ndb_key_futs = []
        for data_chunk in _chunk_data(data, self._MAX_CHUNK_SIZE):
            cached_obj = self.NDBCacheObject()
            cached_obj.cache_keys = data_chunk
            cached_obj.set_ttl()
            cached_obj_key_fut = cached_obj.put_async()
            ndb_key_futs.append(cached_obj_key_fut)
        ndb.Future.wait_all(ndb_key_futs)
        logger.info('data length is %s' % len(data))
        logger.info('chunk size is %s' % self._MAX_CHUNK_SIZE)
        logger.info('total number of chunks is %s' % len(ndb_key_futs))
        self._ndb_object_keys = [fut.get_result() for fut in ndb_key_futs]
        self._cursor = NDBObjectCursor(self._ndb_object_keys)

    def iter(self, cursor=None):
        # Initialize ndb obj cursor here
        self._cursor = cursor
        if not self._cursor:
            self._cursor = NDBObjectCursor(ndb_obj_keys=self._ndb_object_keys)
        return self

    def cursor_after(self):
        return self._cursor

    def next(self):
        return self._cursor.next()

    def delete(self):
        if self._ndb_object_keys is not None:
            delete_futs = []
            for key in self._ndb_object_keys:
                delete_futs.append(key.delete_async())
            ndb.Future.wait_all(delete_futs)

class  ParallelEntityJobExecutor(InParallelTasks):
    '''
    This is a Parallel Entity Job Executor.
    It takes in action function and a iterable generator that would generate batches of iterator,
    which would be processed by an Executor
    '''

    def _init_(self, user_cred, action_fn, iterable_gen, batchsize, context=None, task_name=JobType.PARALLEL_JOB, parent_id=None, sub_task_on_success=None,  sub_task_on_failure=None, **opts):
        """
        args:
            user_cred: UserCredentials(user_id, company_id)
            action_fn: Action Function that would be applied on each iterated item.
            iterable_gen: A generator that would generate iterables and takes in parameter batchsize
            batchsize: Batchsize of each child job that would be created and run in parallel. no. of parallel tasks = (total number of items/batchsize)
            task_name: Name/Type of the task
            parent_id: Parent ID of the job.
            sub_task_on_success: on_success function that would be called for each job that has finished successfully.
            sub_task_on_fail: on_fail function that would be called for each job that has failed
            opts:

            returns:
                None
        """
        self._user_cred = user_cred
        self._batchsize = batchsize
        self._task_name = task_name
        self._parent_id = parent_id
        self._context = context

        self.tasks = []
        iterator_generator = iterable_gen(self._batchsize)

        for itr in iterator_generator:
            task_executor = EntityJobExecutor(
                                itr,
                                action_fn,
                                self._parent_id,
                                self._task_name,
                                user_cred,
                                context=self._context,
                                **opts
                            )

            if sub_task_on_success:
                task_executor.on_success(sub_task_on_success)

            if sub_task_on_failure:
                task_executor.on_failure(sub_task_on_failure)

            self.tasks.append(task_executor)
        
        super(ParallelEntityJobExecutor, self)._init_(*self.tasks, **opts)


class SqlQueryCursor(object):
    def _init_(self, query_fn, offset=0, pagesize=1000, qry_fn_opts=None):
        self._query_fn = pickleable(query_fn)
        self._offset = offset
        self._limit = pagesize
        self._pagination_done = False
        self._data = []
        self._data_idx = 0
        self._qry_fn_opts = qry_fn_opts

    def next(self):
        if self._data_idx >= len(self._data):
            if self._pagination_done:
                raise StopIteration
            
            #query fn should return a list
            self._data = list(self._query_fn(self._offset, self._limit, self._qry_fn_opts))
            if len(self._data) == 0:
                raise StopIteration
            
            self._pagination_done = len(self._data) != self._limit
            self._data_idx = 0
            self._offset = self._offset + self._limit

        data = self._data[self._data_idx]
        self._data_idx = self._data_idx + 1
        return data

class SqlQueryIterator(CursorizedIterator):
    """
    An offset and limit based Sql Iterator.
    It takes a query function to fetch paginated data and 
    iterate over it till the end.
    Query function takes offset and limit as parameters.
    """
    def _init_(self, query_fn, offset=0, pagesize=1000, qry_fn_opts=None):
        self._query_fn = pickleable(query_fn)
        self._offset = offset
        self._pagesize = pagesize
        self._cursor = SqlQueryCursor(
            self._query_fn,
            offset=self._offset,
            pagesize=self._pagesize,
            qry_fn_opts=qry_fn_opts)
    def iter(self, cursor=None):
        if cursor:
            if not isinstance(cursor, SqlQueryCursor):
                raise ValueError("Cursor is not a SqlQueryCursor")
            self._cursor = cursor
        return self

    def cursor_after(self):
        return self._cursor

    def next(self):
        return self._cursor.next()