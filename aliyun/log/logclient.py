#!/usr/bin/env python
# encoding: utf-8

# Copyright (C) Alibaba Cloud Computing
# All rights reserved.


try:
    import logservice_lz4
except ImportError:
    pass

import requests
from datetime import datetime

from .consumer_group_request import *
from .acl_response import *
from .consumer_group_response import *
from .cursor_response import GetCursorResponse
from .cursor_time_response import GetCursorTimeResponse
from .gethistogramsresponse import GetHistogramsResponse
from .getlogsresponse import GetLogsResponse
from .index_config_response import *
from .listlogstoresresponse import ListLogstoresResponse
from .listtopicsresponse import ListTopicsResponse
from .log_logs_pb2 import LogGroup
from .logclient_operator import copy_project
from .logexception import LogException
from .logstore_config_response import *
from .logtail_config_response import *
from .machinegroup_response import *
from .project_response import *
from .pulllog_response import PullLogResponse
from .putlogsresponse import PutLogsResponse
from .shard_response import *
from .shipper_response import *
from .util import Util
from .util import base64_encodestring as e64, base64_decodestring as d64
from .version import API_VERSION, USER_AGENT
import json
import six
import zlib

CONNECTION_TIME_OUT = 20

"""
LogClient class is the main class in the SDK. It can be used to communicate with 
log service server to put/get data.

:Author: Aliyun
"""


class LogClient(object):
    """ Construct the LogClient with endpoint, accessKeyId, accessKey.
    
    :type endpoint: string
    :param endpoint: log service host name, for example, http://ch-hangzhou.sls.aliyuncs.com
    
    :type accessKeyId: string
    :param accessKeyId: aliyun accessKeyId
    
    :type accessKey: string
    :param accessKey: aliyun accessKey
    """

    __version__ = API_VERSION
    Version = __version__

    def __init__(self, endpoint, accessKeyId, accessKey, securityToken=None, source=None):
        self._isRowIp = Util.is_row_ip(endpoint)
        self._port = 80
        self._setendpoint(endpoint)
        self._accessKeyId = accessKeyId
        self._accessKey = accessKey
        self._timeout = CONNECTION_TIME_OUT
        if source is None:
            self._source = Util.get_host_ip(self._logHost)
        else:
            self._source = source
        self._securityToken = securityToken

        self._user_agent = USER_AGENT

    def set_user_agent(self, user_agent):
        """
        set user agent

        :type user_agent: string
        :param user_agent: user agent

        :return: None

        """
        self._user_agent = user_agent

    def _setendpoint(self, endpoint):
        pos = endpoint.find('://')
        if pos != -1:
            endpoint = endpoint[pos + 3:]  # strip http://
        pos = endpoint.find('/')
        if pos != -1:
            endpoint = endpoint[:pos]
        pos = endpoint.find(':')
        if pos != -1:
            self._port = int(endpoint[pos + 1:])
            endpoint = endpoint[:pos]
        self._logHost = endpoint
        self._endpoint = endpoint + ':' + str(self._port)

    @staticmethod
    def _getGMT():
        return datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

    @staticmethod
    def _loadJson(resp_status, resp_header, resp_body, requestId):
        if not resp_body:
            return None
        try:
            if six.PY3 and isinstance(resp_body, six.binary_type):
                return json.loads(resp_body.decode('utf8'))
            return json.loads(resp_body)
        except Exception as ex:
            raise LogException('BadResponse',
                               'Bad json format:\n%s' % resp_body + '\n' + str(ex),
                               requestId, resp_status, resp_header, resp_body)

    def _getHttpResponse(self, method, url, params, body, headers):  # ensure method, url, body is str
        try:
            headers['User-Agent'] = self._user_agent
            r = None
            if method.lower() == 'get':
                r = requests.get(url, params=params, data=body, headers=headers, timeout=self._timeout)
            elif method.lower() == 'post':
                r = requests.post(url, params=params, data=body, headers=headers, timeout=self._timeout)
            elif method.lower() == 'put':
                r = requests.put(url, params=params, data=body, headers=headers, timeout=self._timeout)
            elif method.lower() == 'delete':
                r = requests.delete(url, params=params, data=body, headers=headers, timeout=self._timeout)
            return r.status_code, r.content, r.headers
        except Exception as ex:
            raise LogException('LogRequestError', str(ex))

    def _sendRequest(self, method, url, params, body, headers, respons_body_type='json'):
        (resp_status, resp_body, resp_header) = self._getHttpResponse(method, url, params, body, headers)
        header = {}
        for key, value in resp_header.items():
            header[key] = value

        requestId = Util.h_v_td(header, 'x-log-requestid', '')

        if resp_status == 200:
            if respons_body_type == 'json':
                exJson = self._loadJson(resp_status, resp_header, resp_body, requestId)
                exJson = Util.convert_unicode_to_str(exJson)
                return exJson, header
            else:
                return resp_body, header

        exJson = self._loadJson(resp_status, resp_header, resp_body, requestId)
        exJson = Util.convert_unicode_to_str(exJson)

        if 'errorCode' in exJson and 'errorMessage' in exJson:
            raise LogException(exJson['errorCode'], exJson['errorMessage'], requestId,
                               resp_status, resp_header, resp_body)
        else:
            exJson = '. Return json is ' + str(exJson) if exJson else '.'
            raise LogException('LogRequestError',
                               'Request is failed. Http code is ' + str(resp_status) + exJson, requestId,
                               resp_status, resp_header, resp_body)

    def _send(self, method, project, body, resource, params, headers, respons_body_type='json'):
        if body:
            headers['Content-Length'] = str(len(body))
            headers['Content-MD5'] = Util.cal_md5(body)
        else:
            headers['Content-Length'] = '0'
            headers["x-log-bodyrawsize"] = '0'

        headers['x-log-apiversion'] = API_VERSION
        headers['x-log-signaturemethod'] = 'hmac-sha1'
        if self._isRowIp or not project:
            url = "http://" + self._endpoint
        else:
            url = "http://" + project + "." + self._endpoint

        if project:
            headers['Host'] = project + "." + self._logHost
        else:
            headers['Host'] = self._logHost

        headers['Date'] = self._getGMT()

        if self._securityToken:
            headers["x-acs-security-token"] = self._securityToken

        signature = Util.get_request_authorization(method, resource,
                                                   self._accessKey, params, headers)

        headers['Authorization'] = "LOG " + self._accessKeyId + ':' + signature
        url = url + resource

        return self._sendRequest(method, url, params, body, headers, respons_body_type)

    @staticmethod
    def get_unicode(key):
        if isinstance(key, six.binary_type):
            key = key.decode('utf-8')
        return key

    def set_source(self, source):
        """
        Set the source of the log client

        :type source: string
        :param source: new source

        :return: None
        """
        self._source = source

    def put_logs(self, request):
        """ Put logs to log service.
        Unsuccessful opertaion will cause an LogException.
        
        :type request: PutLogsRequest
        :param request: the PutLogs request parameters class
        
        :return: PutLogsResponse
        
        :raise: LogException
        """
        if len(request.get_log_items()) > 4096:
            raise LogException('InvalidLogSize',
                               "logItems' length exceeds maximum limitation: 4096 lines.")
        logGroup = LogGroup()
        logGroup.Topic = request.get_topic()
        if request.get_source():
            logGroup.Source = request.get_source()
        else:
            if self._source == '127.0.0.1':
                self._source = Util.get_host_ip(request.get_project() + '.' + self._logHost)
            logGroup.Source = self._source
        for logItem in request.get_log_items():
            log = logGroup.Logs.add()
            log.Time = logItem.get_time()
            contents = logItem.get_contents()
            for key, value in contents:
                content = log.Contents.add()
                content.Key = self.get_unicode(key)
                content.Value = self.get_unicode(value)
        if request.get_log_tags() is not None:
            tags = request.get_log_tags()
            for key, value in tags:
                pb_tag = logGroup.LogTags.add()
                pb_tag.Key = key
                pb_tag.Value = value
        body = logGroup.SerializeToString()
        if len(body) > 3 * 1024 * 1024:  # 3 MB
            raise LogException('InvalidLogSize',
                               "logItems' size exceeds maximum limitation: 3 MB.")

        headers = {'x-log-bodyrawsize': str(len(body)), 'Content-Type': 'application/x-protobuf'}
        is_compress = request.get_compress()

        compress_data = None
        if is_compress:
            headers['x-log-compresstype'] = 'deflate'
            compress_data = zlib.compress(body)
            #compress_data = logservice_lz4.compress(body)

        params = {}
        logstore = request.get_logstore()
        project = request.get_project()
        if request.get_hash_key() is not None:
            resource = '/logstores/' + logstore + "/shards/route"
            params["key"] = request.get_hash_key()
        else:
            resource = '/logstores/' + logstore + "/shards/lb"

        if is_compress:
            (resp, header) = self._send('POST', project, compress_data, resource, params, headers)
        else:
            (resp, header) = self._send('POST', project, body, resource, params, headers)

        return PutLogsResponse(header, resp)

    def list_logstores(self, request):
        """ List all logstores of requested project.
        Unsuccessful opertaion will cause an LogException.
        
        :type request: ListLogstoresRequest
        :param request: the ListLogstores request parameters class.
        
        :return: ListLogStoresResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = '/logstores'
        project = request.get_project()
        (resp, header) = self._send("GET", project, None, resource, params, headers)
        return ListLogstoresResponse(resp, header)

    def list_topics(self, request):
        """ List all topics in a logstore.
        Unsuccessful opertaion will cause an LogException.
        
        :type request: ListTopicsRequest
        :param request: the ListTopics request parameters class.
        
        :return: ListTopicsResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        if request.get_token() is not None:
            params['token'] = request.get_token()
        if request.get_line() is not None:
            params['line'] = request.get_line()
        params['type'] = 'topic'
        logstore = request.get_logstore()
        project = request.get_project()
        resource = "/logstores/" + logstore
        (resp, header) = self._send("GET", project, None, resource, params, headers)

        return ListTopicsResponse(resp, header)

    def get_histograms(self, request):
        """ Get histograms of requested query from log service.
        Unsuccessful opertaion will cause an LogException.
        
        :type request: GetHistogramsRequest
        :param request: the GetHistograms request parameters class.
        
        :return: GetHistogramsResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        if request.get_topic() is not None:
            params['topic'] = request.get_topic()
        if request.get_from() is not None:
            params['from'] = request.get_from()
        if request.get_to() is not None:
            params['to'] = request.get_to()
        if request.get_query() is not None:
            params['query'] = request.get_query()
        params['type'] = 'histogram'
        logstore = request.get_logstore()
        project = request.get_project()
        resource = "/logstores/" + logstore
        (resp, header) = self._send("GET", project, None, resource, params, headers)
        return GetHistogramsResponse(resp, header)

    def get_logs(self, request):
        """ Get logs from log service.
        Unsuccessful opertaion will cause an LogException.
        
        :type request: GetLogsRequest
        :param request: the GetLogs request parameters class.
        
        :return: GetLogsResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        if request.get_topic() is not None:
            params['topic'] = request.get_topic()
        if request.get_from() is not None:
            params['from'] = request.get_from()
        if request.get_to() is not None:
            params['to'] = request.get_to()
        if request.get_query() is not None:
            params['query'] = request.get_query()
        params['type'] = 'log'
        if request.get_line() is not None:
            params['line'] = request.get_line()
        if request.get_offset() is not None:
            params['offset'] = request.get_offset()
        if request.get_reverse() is not None:
            params['reverse'] = 'true' if request.get_reverse() else 'false'
        logstore = request.get_logstore()
        project = request.get_project()
        resource = "/logstores/" + logstore
        (resp, header) = self._send("GET", project, None, resource, params, headers)
        return GetLogsResponse(resp, header)

    def get_cursor(self, project_name, logstore_name, shard_id, start_time):
        """ Get cursor from log service for batch pull logs
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :type start_time: string/int
        :param start_time: the start time of cursor, e.g 1441093445 or "begin"/"end"

        :return: GetCursorResponse
        
        :raise: LogException
        """

        headers = {'Content-Type': 'application/json'}
        params = {'type': 'cursor', 'from': str(start_time)}

        resource = "/logstores/" + logstore_name + "/shards/" + str(shard_id)
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetCursorResponse(resp, header)

    def get_cursor_time(self, project_name, logstore_name, shard_id, cursor):
        """ Get cursor time from log service
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :type cursor: string
        :param cursor: the cursor to get its service receive time

        :return: GetCursorTimeResponse

        :raise: LogException
        """

        headers = {'Content-Type': 'application/json'}
        params = {'type': 'cursor_time', 'cursor': cursor}
        resource = "/logstores/" + logstore_name + "/shards/" + str(shard_id)

        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetCursorTimeResponse(resp, header)

    @staticmethod
    def _get_cursor_as_int(cursor):
        return int(d64(cursor))

    def get_previous_cursor_time(self, project_name, logstore_name, shard_id, cursor, normalize=True):
        """ Get previous cursor time from log service.
        Note: normalize = true: if the cursor is out of range, it will be nornalized to nearest cursor
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :type cursor: string
        :param cursor: the cursor to get its service receive time

        :type normalize: bool
        :param normalize: fix the cursor or not if it's out of scope

        :return: GetCursorTimeResponse

        :raise: LogException
        """

        try:
            pre_cursor_int = self._get_cursor_as_int(cursor) - 1
            pre_cursor = e64(str(pre_cursor_int)).strip()
        except Exception:
            raise LogException("InvalidCursor", "Cursor {0} is invalid".format(cursor))

        try:
            return self.get_cursor_time(project_name, logstore_name, shard_id, pre_cursor)
        except LogException as ex:
            if normalize and ex.get_error_code() == "InvalidCursor":
                ret = self.get_begin_cursor(project_name, logstore_name, shard_id)
                begin_cursor_int = self._get_cursor_as_int(ret.get_cursor())

                if pre_cursor_int < begin_cursor_int:
                    return self.get_cursor_time(project_name, logstore_name, shard_id, e64(str(begin_cursor_int)))

                ret = self.get_end_cursor(project_name, logstore_name, shard_id)
                end_cursor_int = self._get_cursor_as_int(ret.get_cursor())

                if pre_cursor_int > end_cursor_int:
                    return self.get_cursor_time(project_name, logstore_name, shard_id, e64(str(end_cursor_int)))

            raise ex

    def get_begin_cursor(self, project_name, logstore_name, shard_id):
        """ Get begin cursor from log service for batch pull logs
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :return: GetLogsResponse
        
        :raise: LogException
        """
        return self.get_cursor(project_name, logstore_name, shard_id, "begin")

    def get_end_cursor(self, project_name, logstore_name, shard_id):
        """ Get end cursor from log service for batch pull logs
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :return: GetLogsResponse
        
        :raise: LogException
        """
        return self.get_cursor(project_name, logstore_name, shard_id, "end")

    def pull_logs(self, project_name, logstore_name, shard_id, cursor, count=1000, end_cursor=None, compress=False):
        """ batch pull log data from log service
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shard_id: int
        :param shard_id: the shard id

        :type cursor: string
        :param cursor: the start to cursor to get data

        :type count: int
        :param count: the required pull log package count, default 1000 packages

        :type end_cursor: string
        :param end_cursor: the end cursor position to get data

        :type compress: boolean
        :param compress: if use lz4 compress for transfer data

        :return: PullLogResponse
        
        :raise: LogException
        """
        headers = {}
        if compress:
            headers['Accept-Encoding'] = 'gzip'
        else:
            headers['Accept-Encoding'] = ''

        headers['Accept'] = 'application/x-protobuf'

        params = {}
        resource = "/logstores/" + logstore_name + "/shards/" + str(shard_id)
        params['type'] = 'log'
        params['cursor'] = cursor
        params['count'] = str(count)
        if end_cursor:
            params['end_cursor'] = end_cursor
        (resp, header) = self._send("GET", project_name, None, resource, params, headers, "binary")

        compress_type = Util.h_v_td(header,'x-log-compresstype', '').lower()
        if compress_type == 'lz4':
            raw_size = int(Util.h_v_t(header, 'x-log-bodyrawsize'))
            raw_data = logservice_lz4.uncompress(raw_size, resp)
            return PullLogResponse(raw_data, header)
        elif compress_type in ('gzip', 'deflate'):
            raw_size = int(Util.h_v_t(header, 'x-log-bodyrawsize'))
            raw_data = zlib.decompress(resp)
            return PullLogResponse(raw_data, header)
        else:
            return PullLogResponse(resp, header)

    def create_logstore(self, project_name, logstore_name, ttl, shard_count):
        """ create log store 
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type ttl: int
        :param ttl: the life cycle of log in the logstore in days

        :type shard_count: int
        :param shard_count: the shard count of the logstore to create


        :return: CreateLogStoreResponse
        
        :raise: LogException
        """
        params = {}
        resource = "/logstores"
        headers = {"x-log-bodyrawsize": '0', "Content-Type": "application/json"}
        body = {"logstoreName": logstore_name, "ttl": int(ttl), "shardCount": int(shard_count)}

        body_str = six.b(json.dumps(body))

        (resp, header) = self._send("POST", project_name, body_str, resource, params, headers)
        return CreateLogStoreResponse(header, resp)

    def delete_logstore(self, project_name, logstore_name):
        """ delete log store
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: DeleteLogStoreResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name
        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteLogStoreResponse(header, resp)

    def get_logstore(self, project_name, logstore_name):
        """ get the logstore meta info
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: GetLogStoreResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetLogStoreResponse(resp, header)

    def update_logstore(self, project_name, logstore_name, ttl, shard_count):
        """ 
        update the logstore meta info
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type ttl: int
        :param ttl: the life cycle of log in the logstore in days

        :type shard_count: int
        :param shard_count: the shard count of the logstore to create

        :return: UpdateLogStoreResponse
        
        :raise: LogException
        """

        headers = {"x-log-bodyrawsize": '0', "Content-Type": "application/json"}

        params = {}
        resource = "/logstores/" + logstore_name
        body = {"logstoreName": logstore_name, "ttl": int(ttl), "shardCount": int(shard_count)}
        body_str = six.b(json.dumps(body))
        (resp, header) = self._send("PUT", project_name, body_str, resource, params, headers)
        return UpdateLogStoreResponse(header, resp)

    def list_logstore(self, project_name, logstore_name_pattern=None, offset=0, size=100):
        """ list the logstore in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name

        :type logstore_name_pattern: string
        :param logstore_name_pattern: the sub name logstore, used for the server to return logstore names contain this sub name

        :type offset: int
        :param offset: the offset of all the matched names

        :type size: int
        :param size: the max return names count

        :return: ListLogStoreResponse

        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores"
        if logstore_name_pattern is not None:
            params['logstorename'] = logstore_name_pattern
        params['offset'] = str(offset)
        params['size'] = str(size)
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListLogStoreResponse(resp, header)

    def list_shards(self, project_name, logstore_name):
        """ list the shard meta of a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: ListShardResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/shards"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListShardResponse(resp, header)

    def split_shard(self, project_name, logstore_name, shardId, split_hash):
        """ split a  readwrite shard into two shards
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name
        
        :type shardId: int
        :param shardId: the shard id

        :type split_hash: string
        :param split_hash: the internal hash between the shard begin and end hash

        :return: ListShardResponse
        
        :raise: LogException
        """

        headers = {}
        params = {"action": "split", "key": split_hash}
        resource = "/logstores/" + logstore_name + "/shards/" + str(shardId)
        (resp, header) = self._send("POST", project_name, None, resource, params, headers)
        return ListShardResponse(resp, header)

    def merge_shard(self, project_name, logstore_name, shardId):
        """ split two adjacent  readwrite hards into one shards
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name
        
        :type shardId: int
        :param shardId: the shard id of the left shard, server will determine the right adjacent shardId

        :return: ListShardResponse
        
        :raise: LogException
        """
        headers = {}
        params = {"action": "merge"}
        resource = "/logstores/" + logstore_name + "/shards/" + str(shardId)
        (resp, header) = self._send("POST", project_name, None, resource, params, headers)
        return ListShardResponse(resp, header)

    def delete_shard(self, project_name, logstore_name, shardId):
        """ delete a readonly shard 
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name
        
        :type shardId: int
        :param shardId: the read only shard id

        :return: ListShardResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/shards/" + str(shardId)
        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteShardResponse(header, resp)

    def create_index(self, project_name, logstore_name, index_detail):
        """ create index for a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type index_detail: IndexConfig
        :param index_detail: the index config detail used to create index

        :return: CreateIndexResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/index"
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(index_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))

        (resp, header) = self._send("POST", project_name, body, resource, params, headers)
        return CreateIndexResponse(header, resp)

    def update_index(self, project_name, logstore_name, index_detail):
        """ update index for a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type index_detail: IndexConfig
        :param index_detail: the index config detail used to update index

        :return: UpdateIndexResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/index"
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(index_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))

        (resp, header) = self._send("PUT", project_name, body, resource, params, headers)
        return UpdateIndexResponse(header, resp)

    def delete_index(self, project_name, logstore_name):
        """ delete index of a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: DeleteIndexResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/index"
        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteIndexResponse(header, resp)

    def get_index_config(self, project_name, logstore_name):
        """ get index config detail of a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: GetIndexResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/index"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetIndexResponse(resp, header)

    def create_logtail_config(self, project_name, config_detail):
        """ create logtail config in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_detail: CommonRegLogConfigDetail or ApsaraLogConfigDetail
        :param config_detail: the logtail config detail info, the CommonRegLogConfigDetail is used to create common regex logs ,the ApsaraLogConfigDetail is used to create apsara log

        :return: CreateLogtailConfigResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/configs"
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(config_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))
        (resp, headers) = self._send("POST", project_name, body, resource, params, headers)
        return CreateLogtailConfigResponse(headers, resp)

    def update_logtail_config(self, project_name, config_detail):
        """ update logtail config in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_detail: CommonRegLogConfigDetail or ApsaraLogConfigDetail
        :param config_detail: the logtail config detail info, the CommonRegLogConfigDetail is used to create common regex logs, the ApsaraLogConfigDetail is used to create apsara log

        :return: UpdateLogtailConfigResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/configs/" + config_detail.config_name
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(config_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))
        (resp, headers) = self._send("PUT", project_name, body, resource, params, headers)
        return UpdateLogtailConfigResponse(headers, resp)

    def delete_logtail_config(self, project_name, config_name):
        """ delete logtail config in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_name: string
        :param config_name: the logtail config name

        :return: DeleteLogtailConfigResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/configs/" + config_name
        (resp, headers) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteLogtailConfigResponse(headers, resp)

    def get_logtail_config(self, project_name, config_name):
        """ get logtail config in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_name: string
        :param config_name: the logtail config name

        :return: GetLogtailConfigResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/configs/" + config_name
        (resp, headers) = self._send("GET", project_name, None, resource, params, headers)
        return GetLogtailConfigResponse(resp, headers)

    def list_logtail_config(self, project_name, offset=0, size=100):
        """ list logtail config name in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type offset: int
        :param offset: the offset of all config names

        :type size: int
        :param size: the max return names count

        :return: ListLogtailConfigResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/configs"
        params['offset'] = str(offset)
        params['size'] = str(size)
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListLogtailConfigResponse(resp, header)

    def create_machine_group(self, project_name, group_detail):
        """ create machine group in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type group_detail: MachineGroupDetail
        :param group_detail: the machine group detail config

        :return: CreateMachineGroupResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups"
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(group_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))
        (resp, headers) = self._send("POST", project_name, body, resource, params, headers)
        return CreateMachineGroupResponse(headers, resp)

    def delete_machine_group(self, project_name, group_name):
        """ delete machine group in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type group_name: string
        :param group_name: the group name

        :return: DeleteMachineGroupResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name
        (resp, headers) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteMachineGroupResponse(headers, resp)

    def update_machine_group(self, project_name, group_detail):
        """ update machine group in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type group_detail: MachineGroupDetail
        :param group_detail: the machine group detail config

        :return: UpdateMachineGroupResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups/" + group_detail.group_name
        headers['Content-Type'] = 'application/json'
        body = six.b(json.dumps(group_detail.to_json()))
        headers['x-log-bodyrawsize'] = str(len(body))
        (resp, headers) = self._send("PUT", project_name, body, resource, params, headers)
        return UpdateMachineGroupResponse(headers, resp)

    def get_machine_group(self, project_name, group_name):
        """ get machine group in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type group_name: string
        :param group_name: the group name to get

        :return: GetMachineGroupResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name
        (resp, headers) = self._send("GET", project_name, None, resource, params, headers)
        return GetMachineGroupResponse(resp, headers)

    def list_machine_group(self, project_name, offset=0, size=100):
        """ list machine group names in a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type offset: int
        :param offset: the offset of all group name

        :type size: int
        :param size: the max return names count

        :return: ListMachineGroupResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups"
        params['offset'] = str(offset)
        params['size'] = str(size)
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListMachineGroupResponse(resp, header)

    def list_machines(self, project_name, group_name, offset=0, size=100):
        """ list machines in a machine group
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 
        
        :type group_name: string
        :param group_name: the group name to list

        :type offset: int
        :param offset: the offset of all group name

        :type size: int
        :param size: the max return names count

        :return: ListMachinesResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name + "/machines"
        params['offset'] = str(offset)
        params['size'] = str(size)
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListMachinesResponse(resp, header)

    def apply_config_to_machine_group(self, project_name, config_name, group_name):
        """ apply a logtail config to a machine group
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_name: string
        :param config_name: the logtail config name to apply
        
        :type group_name: string
        :param group_name: the machine group name 

        :return: ApplyConfigToMachineGroupResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name + "/configs/" + config_name
        (resp, header) = self._send("PUT", project_name, None, resource, params, headers)
        return ApplyConfigToMachineGroupResponse(header, resp)

    def remove_config_to_machine_group(self, project_name, config_name, group_name):
        """ remove a logtail config to a machine group
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_name: string
        :param config_name: the logtail config name to apply
        
        :type group_name: string
        :param group_name: the machine group name 

        :return: RemoveConfigToMachineGroupResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name + "/configs/" + config_name
        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return RemoveConfigToMachineGroupResponse(header, resp)

    def get_machine_group_applied_configs(self, project_name, group_name):
        """ get the logtail config names applied in a machine group
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type group_name: string
        :param group_name: the group name list

        :return: GetMachineGroupAppliedConfigResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/machinegroups/" + group_name + "/configs"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetMachineGroupAppliedConfigResponse(resp, header)

    def get_config_applied_machine_groups(self, project_name, config_name):
        """ get machine group names where the logtail config applies to
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type config_name: string
        :param config_name: the logtail config name used to apply

        :return: GetConfigAppliedMachineGroupsResponse
        
        :raise: LogException
        """

        headers = {}
        params = {}
        resource = "/configs/" + config_name + "/machinegroups"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetConfigAppliedMachineGroupsResponse(resp, header)

    def _update_acl(self, project_name, logstore_name, acl_action, acl_config):
        headers = {}
        params = {'type': 'acl'}
        resource = "/"
        if logstore_name:
            resource = "/logstores/" + logstore_name
        body = acl_config.to_json()
        body['action'] = acl_action
        body = six.b(json.dumps(body))
        headers['Content-Type'] = 'application/json'
        headers['x-log-bodyrawsize'] = str(len(body))
        (resp, headers) = self._send("PUT", project_name, body, resource, params, headers)
        return UpdateAclResponse(headers, resp)

    def update_project_acl(self, project_name, acl_action, acl_config):
        """ update acl of a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type acl_action: string
        :param acl_action: "grant" or "revoke", grant or revoke the acl_config to/from a project

        :type acl_config: acl_config.AclConfig
        :param acl_config: the detail acl config info

        :return: UpdateAclResponse
        
        :raise: LogException
        """

        return self._update_acl(project_name, None, acl_action, acl_config)

    def update_logstore_acl(self, project_name, logstore_name, acl_action, acl_config):
        """ update acl of a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type acl_action: string
        :param acl_action: "grant" or "revoke", grant or revoke the acl_config to/from a logstore

        :type acl_config: acl_config.AclConfig
        :param acl_config: the detail acl config info

        :return: UpdateAclResponse
        
        :raise: LogException
        """
        return self._update_acl(project_name, logstore_name, acl_action, acl_config)

    def _list_acl(self, project_name, logstore_name, offset=0, size=100):
        headers = {}
        params = {'type': 'acl', 'offset': str(offset), 'size': str(size)}
        resource = "/"
        if logstore_name:
            resource = "/logstores/" + logstore_name
        (resp, headers) = self._send("GET", project_name, None, resource, params, headers)
        return ListAclResponse(resp, headers)

    def list_project_acl(self, project_name, offset=0, size=100):
        """ list acl of a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type offset: int
        :param offset: the offset of all acl

        :type size: int
        :param size: the max return acl count

        :return: ListAclResponse
        
        :raise: LogException
        """
        return self._list_acl(project_name, None, offset, size)

    def list_logstore_acl(self, project_name, logstore_name, offset=0, size=100):
        """ list acl of a logstore
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type offset: int
        :param offset: the offset of all acl

        :type size: int
        :param size: the max return acl count

        :return: ListAclResponse
        
        :raise: LogException
        """

        return self._list_acl(project_name, logstore_name, offset, size)

    def create_shipper(self, project_name, logstore_name, shipper_name, shipper_type, shipper_config):
        """ create odps/oss shipper
        for every type, it only allowed one shipper
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :type shipper_type: string
        :param shipper_type: only support "odps" or "oss" 

        :type shipper_config: OssShipperConfig or OdpsShipperConfig
        :param shipper_config: the detail shipper config, must be OssShipperConfig or OdpsShipperConfig type

        :return: CreateShipperResponse
        
        :raise: LogException
        """
        params = {}
        resource = "/logstores/" + logstore_name + "/shipper"
        body = {"shipperName": shipper_name,
                "targetType": shipper_type,
                "targetConfiguration": shipper_config.to_json()}
        body = six.b(json.dumps(body))
        headers = {'Content-Type': 'application/json', 'x-log-bodyrawsize': str(len(body))}

        (resp, headers) = self._send("POST", project_name, body, resource, params, headers)
        return CreateShipperResponse(headers, resp)

    def update_shipper(self, project_name, logstore_name, shipper_name, shipper_type, shipper_config):
        """ update  odps/oss shipper
        for every type, it only allowed one shipper
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :type shipper_type: string
        :param shipper_type: only support "odps" or "oss" , the type must be same with the oringal shipper

        :type shipper_config: OssShipperConfig or OdpsShipperConfig
        :param shipper_config: the detail shipper config, must be OssShipperConfig or OdpsShipperConfig type

        :return: UpdateShipperResponse
        
        :raise: LogException
        """
        params = {}
        resource = "/logstores/" + logstore_name + "/shipper/" + shipper_name
        body = {"shipperName": shipper_name, "targetType": shipper_type,
                "targetConfiguration": shipper_config.to_json()}
        body = six.b(json.dumps(body))
        headers = {'Content-Type': 'application/json', 'x-log-bodyrawsize': str(len(body))}

        (resp, headers) = self._send("PUT", project_name, body, resource, params, headers)
        return UpdateShipperResponse(headers, resp)

    def delete_shipper(self, project_name, logstore_name, shipper_name):
        """ delete  odps/oss shipper
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :return: DeleteShipperResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/shipper/" + shipper_name
        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteShipperResponse(header, resp)

    def get_shipper_config(self, project_name, logstore_name, shipper_name):
        """ get  odps/oss shipper
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :return: GetShipperConfigResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/shipper/" + shipper_name
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetShipperConfigResponse(resp, header)

    def list_shipper(self, project_name, logstore_name):
        """ list  odps/oss shipper
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :return: ListShipperResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/logstores/" + logstore_name + "/shipper"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return ListShipperResponse(resp, header)

    def get_shipper_tasks(self, project_name, logstore_name, shipper_name, start_time, end_time, status_type='',
                          offset=0, size=100):
        """ get  odps/oss shipper tasks in a certain time range
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :type start_time: int
        :param start_time: the start timestamp

        :type end_time: int
        :param end_time: the end timestamp 

        :type status_type: string
        :param status_type: support one of ['', 'fail', 'success', 'running'] , if the status_type = '' , return all kinds of status type

        :type offset: int
        :param offset: the begin task offset

        :type size: int
        :param size: the needed tasks count

        :return: ListShipperResponse
        
        :raise: LogException
        """
        headers = {}
        params = {"from": str(int(start_time)),
                  "to": str(int(end_time)),
                  "status": status_type,
                  "offset": str(int(offset)),
                  "size": str(int(size))}

        resource = "/logstores/" + logstore_name + "/shipper/" + shipper_name + "/tasks"
        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetShipperTasksResponse(resp, header)

    def retry_shipper_tasks(self, project_name, logstore_name, shipper_name, task_list):
        """ retry failed tasks , only the failed task can be retried
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type logstore_name: string
        :param logstore_name: the logstore name

        :type shipper_name: string
        :param shipper_name: the shipper name

        :type task_list: string array
        :param task_list: the failed task_id list, e.g ['failed_task_id_1', 'failed_task_id_2',...], currently the max retry task count 10 every time

        :return: RetryShipperTasksResponse
        
        :raise: LogException
        """
        headers = {}
        params = {}
        body = six.b(json.dumps(task_list))
        headers['Content-Type'] = 'application/json'
        headers['x-log-bodyrawsize'] = str(len(body))
        resource = "/logstores/" + logstore_name + "/shipper/" + shipper_name + "/tasks"

        (resp, header) = self._send("PUT", project_name, body, resource, params, headers)
        return RetryShipperTasksResponse(header, resp)

    def create_project(self, project_name, project_des):
        """ Create a project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :type project_des: string
        :param project_des: the description of a project

        :return: CreateProjectResponse 

        :raise: LogException
        """

        params = {}
        body = {"projectName": project_name, "description": project_des}

        body = six.b(json.dumps(body))
        headers = {'Content-Type': 'application/json', 'x-log-bodyrawsize': str(len(body))}
        resource = "/"

        (resp, header) = self._send("POST", project_name, body, resource, params, headers)
        return CreateProjectResponse(header, resp)

    def get_project(self, project_name):
        """ get project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :return: GetProjectResponse 

        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/"

        (resp, header) = self._send("GET", project_name, None, resource, params, headers)
        return GetProjectResponse(resp, header)

    def delete_project(self, project_name):
        """ delete project
        Unsuccessful opertaion will cause an LogException.

        :type project_name: string
        :param project_name: the Project name 

        :return: DeleteProjectResponse 

        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/"

        (resp, header) = self._send("DELETE", project_name, None, resource, params, headers)
        return DeleteProjectResponse(header, resp)

    def create_consumer_group(self, project, logstore, consumer_group, timeout, in_order=False):
        """ create consumer group

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type timeout: int
        :param timeout: time-out

        :type in_order: bool
        :param in_order:

        :return: CreateConsumerGroupResponse
        """
        request = CreateConsumerGroupRequest(project, logstore, ConsumerGroupEntity(consumer_group, timeout, in_order))
        consumer_group = request.consumer_group
        body_str = consumer_group.to_request_json()

        headers = {
            "x-log-bodyrawsize": '0',
            "Content-Type": "application/json"
        }
        params = {}

        project = request.get_project()
        resource = "/logstores/" + request.get_logstore() + "/consumergroups"
        (resp, header) = self._send("POST", project, body_str, resource, params, headers)
        return CreateConsumerGroupResponse(header, resp)

    def update_consumer_group(self, project, logstore, consumer_group, timeout=None, in_order=None):
        """ Update consumer group

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type timeout: int
        :param timeout: timeout

        :type in_order: bool
        :param in_order: order

        :return: None
        """
        if in_order is None and timeout is None:
            raise ValueError('in_order and timeout can\'t all be None')
        elif in_order is not None and timeout is not None:
            body_dict = {
                'order': in_order,
                'timeout': timeout
            }
        elif in_order is not None:
            body_dict = {
                'order': in_order
            }
        else:
            body_dict = {
                'timeout': timeout
            }
        body_str = six.b(json.dumps(body_dict))

        headers = {
            "x-log-bodyrawsize": str(len(body_str)),
            "Content-Type": "application/json"
        }
        params = {}
        resource = "/logstores/" + logstore + "/consumergroups/" + consumer_group
        (resp, header) = self._send("PUT", project, body_str, resource, params, headers)
        return UpdateConsumerGroupResponse(header, resp)

    def delete_consumer_group(self, project, logstore, consumer_group):
        """ Delete consumer group

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :return: None
        """

        headers = {"x-log-bodyrawsize": '0'}
        params = {}

        resource = "/logstores/" + logstore + "/consumergroups/" + consumer_group
        (resp, header) = self._send("DELETE", project, None, resource, params, headers)
        return DeleteConsumerGroupResponse(header, resp)

    def list_consumer_group(self, project, logstore):
        """ List consumer group

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :return: ListConsumerGroupResponse
        """

        resource = "/logstores/" + logstore + "/consumergroups"
        params = {}
        headers = {}

        (resp, header) = self._send("GET", project, None, resource, params, headers)
        return ListConsumerGroupResponse(resp, header)

    def update_check_point(self, project, logstore, consumer_group, shard, check_point,
                           consumer='', force_success=True):
        """ Update check point

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type shard: int
        :param shard: shard id

        :type check_point: string
        :param check_point: checkpoint name

        :type consumer: string
        :param consumer: consumer name

        :type force_success: bool
        :param force_success: if force to succeed

        :return: None
        """
        request = ConsumerGroupUpdateCheckPointRequest(project, logstore, consumer_group,
                                                       consumer, shard, check_point, force_success)
        params = request.get_request_params()
        body_str = request.get_request_body()
        headers = {"Content-Type": "application/json"}
        resource = "/logstores/" + logstore + "/consumergroups/" + consumer_group
        (resp, header) = self._send("POST", project, body_str, resource, params, headers)
        return ConsumerGroupUpdateCheckPointResponse(header, resp)

    def get_check_point(self, project, logstore, consumer_group, shard=-1):
        """ Get check point

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type shard: int
        :param shard: shard id

        :return: ConsumerGroupCheckPointResponse
        """
        request = ConsumerGroupGetCheckPointRequest(project, logstore, consumer_group, shard)
        params = request.get_params()
        headers = {}
        resource = "/logstores/" + logstore + "/consumergroups/" + consumer_group
        (resp, header) = self._send("GET", project, None, resource, params, headers)
        return ConsumerGroupCheckPointResponse(resp, header)

    def get_check_point_fixed(self, project, logstore, consumer_group, shard=-1):
        """ Get check point

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type shard: int
        :param shard: shard id

        :return: ConsumerGroupCheckPointResponse
        """

        res = self.get_check_point(project, logstore, consumer_group, shard)
        res.check_checkpoint(self, project, logstore)

        return res

    def heart_beat(self, project, logstore, consumer_group, consumer, shards=None):
        """ Heatbeat consumer group

        :type project: string
        :param project: project name

        :type logstore: string
        :param logstore: logstore name

        :type consumer_group: string
        :param consumer_group: consumer group name

        :type consumer: string
        :param consumer: consumer name

        :type shards: int list
        :param shards: shard id list e.g. [0,1,2]

        :return: None
        """
        if shards is None:
            shards = []
        request = ConsumerGroupHeartBeatRequest(project, logstore, consumer_group, consumer, shards)
        body_str = request.get_request_body()
        params = request.get_params()
        headers = {"Content-Type": "application/json"}
        resource = "/logstores/" + logstore + "/consumergroups/" + consumer_group
        (resp, header) = self._send('POST', project, body_str, resource, params, headers)
        return ConsumerGroupHeartBeatResponse(resp, header)

    def copy_project(self, from_project, to_project, to_client=None):
        """
        copy project, logstore, machine group and logtail config to target project,
        expecting the target project doens't exist

        :type from_project: string
        :param from_project: project name

        :type to_project: string
        :param to_project: project name

        :type to_client: LogClient
        :param to_client: logclient instance

        :return: None
        """
        if to_client is None:
            to_client = self
        return copy_project(self, to_client, from_project, to_project)

    def list_project(self, offset=0, size=100):
        """ list the project
        Unsuccessful opertaion will cause an LogException.

        :type offset: int
        :param offset: the offset of all the matched names

        :type size: int
        :param size: the max return names count

        :return: ListProjectResponse

        :raise: LogException
        """
        headers = {}
        params = {}
        resource = "/"
        params['offset'] = str(offset)
        params['size'] = str(size)
        (resp, header) = self._send("GET", None, None, resource, params, headers)
        return ListProjectResponse(resp, header)

