#!/usr/bin/env python
"""
replicon.py

This script may be run as a command line program or included as a python module in other scripts.

Run ./replicon.py -h for command line usage.

Credits:
- Singleton and Config classes from https://github.com/drobertadams/toggl-cli
- Replicon class __init__()/_getUrl() from example at http://www.replicon.com/help/getallenabledusers-python-example
"""

# Standard modules
import argparse
import os
import sys
import json
import datetime
from pprint import pprint, pformat

# PIP modules
import requests
from six.moves import configparser as ConfigParser

# Globals
HEADERS = {'content-type':'application/json'}
HISTORY_LENGTH = 5

def date_to_dict(datetime_date):
    """
    Convert a Python datetime.date object to a Replicon API date dict
    """
    return { 
        "year": datetime_date.year,
        "month": datetime_date.month,
        "day": datetime_date.day
    }

def dict_to_date(dict_date):
    """
    Convert a Replicon API date dict to a Python datetime.date object
    """
    return datetime.date(
        int(dict_date['year']),
        int(dict_date['month']),
        int(dict_date['day'])
    )

def dict_to_seconds(dict_duration):
    """
    Convert a Replicon API duration dict to an integer of the total seconds
    """
    seconds = 0
    seconds += int(dict_duration['hours']) * 60 * 60
    seconds += int(dict_duration['minutes']) * 60
    seconds += int(dict_duration['seconds'])
    return seconds

def uri_id(uri):
    """
    Return the end integer string part of a uri.
    """
    return uri.split(':')[-1]


class Singleton(type):
    """
    Defines a way to implement the singleton pattern in Python.
    From: http://stackoverflow.com/questions/31875/is-there-a-simple-elegant-way-to-define-singletons-in-python/33201#33201

    To use, simply put the following line in your class definition:
        __metaclass__ = Singleton
    """
    def __init__(cls, name, bases, dict):
        super(Singleton, cls).__init__(name, bases, dict)
        cls.instance = None

    def __call__(cls,*args,**kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance


class Config(object):
    """
    Singleton. replicon configuration data, read from ~/.repliconrc.
    Based on: https://github.com/drobertadams/toggl-cli/blob/master/toggl.py
    Properties:
        auth - (companykey, username, password) tuple.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Reads configuration data from ~/.repliconrc.
        """
        self.cfg = ConfigParser.ConfigParser()
        if self.cfg.read(os.path.expanduser('~/.repliconrc')) == []:
            self._create_empty_config()
            raise IOError("Missing ~/.repliconrc. A default has been created for editing.")

    def _create_empty_config(self):
        """
        Creates a blank ~/.repliconrc.
        """
        cfg = ConfigParser.RawConfigParser()
        cfg.add_section('auth')
        cfg.set('auth', 'company', 'CompanyKey')
        cfg.set('auth', 'username', 'user@example.com')
        cfg.set('auth', 'password', 'replicon_password')
        with open(os.path.expanduser('~/.repliconrc'), 'w') as cfgfile:
            cfg.write(cfgfile)
        os.chmod(os.path.expanduser('~/.togglrc'), 0o600)

    def get(self, section, key):
        """
        Returns the value of the configuration variable identified by the
        given key within the given section of the configuration file. Raises
        ConfigParser exceptions if the section or key are invalid.
        """
        return self.cfg.get(section, key).strip()

    def get_auth(self):
        """
        Returns values from auth section formatted as replicon auth tuple:
            (company\username, password)
        """
        return requests.auth.HTTPBasicAuth(
                self.get('auth', 'company') + '\\' +
                self.get('auth', 'username'),
                self.get('auth', 'password')
            )


class Replicon:
    
    def __init__(self, date=datetime.date.today(), debug=False):
        self.date = date
        self.debug = debug
        self.companyKey = Config().get('auth', 'company')
        self.loginName = Config().get('auth', 'username')
        self.auth = Config().get_auth()
        self.swimlane = ''
        self.userURI = ''
        self.uri = ''
        self.timesheet = None
        self.clients = []

        swimlaneFinderUrl = 'https://global.replicon.com/DiscoveryService1.svc/GetTenantEndpointDetails'
        swimlaneFinderJsonBody = {}
        tenant = {}
        tenant['companyKey'] = self.companyKey
        swimlaneFinderJsonBody['tenant'] = tenant
        swimlaneInfo = None

        try:
            swimlaneFinder = requests.post(swimlaneFinderUrl, headers = HEADERS, data = json.dumps(swimlaneFinderJsonBody))
            swimlaneFinder = swimlaneFinder.json()
            if swimlaneFinder.get('error'):
                print 'Error: {0}'.format(swimlaneFinder.get('error'))
                sys.exit(1)
            else:
                self.swimlane = swimlaneFinder['d']['applicationRootUrl']
        except Exception, e:
            print 'Error: {0}'.format(e)
            sys.exit(1)
 
        users = self._getUrl('services/UserService1.svc/GetEnabledUsers')
        for user in users:
            if user['loginName'] == self.loginName:
                loginUserURI = user['uri']
        if not loginUserURI:
            print 'Error: unable to find current user URI for %s' % (self.loginName)
            sys.exit(1)
        self.userURI = loginUserURI
        
        # The first 3 parts of all URI's seems common so factor it out
        self.uri = ':'.join(loginUserURI.split(':')[:3])

    def _getUrl(self, url, data_dict={}):
        try:
            fullUrl = self.swimlane + url     
            data = json.dumps(data_dict)
            if self.debug:
                print '--- POST '+'-'*30
                print 'URL:', fullUrl
                print 'Data:', pformat(data_dict)
            rawReply = requests.post(fullUrl, data = data, headers = HEADERS, auth = self.auth)
            jsonReply = rawReply.json()

            if jsonReply.get('error'):
                print 'Error: {0}'.format(jsonReply.get('error'))
                sys.exit(1)
            else:
                if self.debug:
                    print 'Reply:', pformat(jsonReply)
                return jsonReply['d']

        except Exception, e:
            print 'Error: {0}'.format
            print e
            sys.exit(1)

    def getTimesheetPeriods(self, start_date=None, end_date=None):
        url = 'services/TimeSheetPeriodService1.svc/GetTimesheetPeriodsForUser'
        if not start_date:
            start_date = self.date
        if not end_date:
            end_date = self.date
        data = {
            "userUri": self.userURI,
            "dateRange": {
                "startDate": date_to_dict(start_date),
                "endDate": date_to_dict(end_date),
                "relativeDateRangeUri": None,
                "relativeDateRangeAsOfDate": None
            },
        }
        return [TimesheetPeriod(p) for p in self._getUrl(url, data)]

    def getTimesheet(self, a_date=None):
        if not a_date:
            a_date = self.date
        url = 'services/TimeSheetService1.svc/GetTimesheetForDate2'
        data = {
            "userUri": self.userURI,
            "date": date_to_dict(a_date),
            "timesheetGetOptionUri": None
        }
        timesheet = self._getUrl(url, data)
        timesheet = timesheet['timesheet']
        url = 'services/TimeSheetService1.svc/GetTimesheetDetails'
        data = {
              "timesheetUri": timesheet['uri']
        }
        return Timesheet(self, self._getUrl(url, data))

    def getClientsAvailableForTimesheet(self, timesheet):
        url = 'services/TimesheetService1.svc/GetPageOfClientsAvailableForTimeAllocationFilteredByTextSearch'
        data = {
            "page": 1,
            "pageSize": 10000,
            "timesheetUri": timesheet.uri,
            "textSearch": None,
        }
        return [Client(c) for c in self._getUrl(url, data)]

    def getClients(self):
        """
        Return a list of all Clients currently available to the user.
        """
        if not self.clients:
            if not self.timesheet:
                self.timesheet = self.getTimesheet()
            self.clients = self.getClientsAvailableForTimesheet(self.timesheet)
        return self.clients

    def getClient(self, search):
        """
        Search for and return a Client.
        The search parameter is a string containing the ID, displayText or name of the client.
        Returns the first matching client.
        """
        self.getClients()
        for c in self.clients:
            if search == c.id or search == c.displayText or search == c.name:
                return c

    def getProjectsAvailableForTimesheetAndClient(self, timesheet_uri, client_uri):
        url = 'services/TimesheetService1.svc/GetPageOfProjectsAvailableForTimeAllocationFilteredByClientAndTextSearch'
        data = {
            "page": 1,
            "pageSize": 10000,
            "timesheetUri": timesheet_uri,
            "clientUri": client_uri,
            "textSearch": None,
            "clientNullFilterBehaviorUri": 'urn:replicon:client-null-filter-behavior:filtered'#None
        }
        return [Project(p) for p in self._getUrl(url, data)]

    def getProjects(self, client=None):
        """
        Return a list of Projects for a specified Client.
        The client parameter must be an instance of the Client() class.
        If the client parameter is omitted, will return all Projects without a client.
        """
        client_uri = None
        if client and isinstance(client, Client):
            self.getClients()
            for c in self.clients:
                if c.uri == client.uri:
                    client_uri = c.uri
        else:
            self.timesheet = self.getTimesheet()
        return self.getProjectsAvailableForTimesheetAndClient(self.timesheet.uri, client_uri)

    def getProject(self, client, search):
        """
        Search for and return a Project.
        The client parameter must be an instance of the Client() class.
        The search parameter is a string containing the ID, displayText or name of the project.
        Returns the first matching project.
        """
        projects = self.getProjects(client)
        for p in projects:
            if search == p.id or search == p.displayText or search == p.name:
                return p

    def getTasksAvailableForTimesheetAndProject(self, timesheet_uri, project_uri):
        url = 'services/TimesheetService1.svc/GetPageOfTasksAvailableForTimeAllocationFilteredByProjectAndTextSearch'
        data = {
            "page": 1,
            "pageSize": 10000,
            "timesheetUri": timesheet_uri,
            "projectUri": project_uri,
            "textSearch": None
        }
        return [Task(t['task']) for t in self._getUrl(url, data)]

    def getTasks(self, project):
        """
        Return a list of Tasks for a specified Client and Project.
        The client parameter must be an instance of the Client() class or None (for no client).
        The project parameter must be an instance of the Project() class.
        """
        tasks = []
        if project and isinstance(project, Project):
            tasks = self.getTasksAvailableForTimesheetAndProject(self.timesheet.uri, project.uri)
        return tasks

    def getTask(self, project, search):
        """
        Search for and return a Task.
        The project parameter must be an instance of the Project() class.
        The search parameter is a string containing the ID or displayText of the task.
        Returns the first matching task.
        """
        tasks = self.getTasks(project)
        for t in tasks:
            if search == t.id or search == t.displayText:
                return t

    def getStandardTimesheetEntryCustomFieldPositionDetails(self):
        url = 'services/TimesheetService1.svc/GetStandardTimesheetEntryCustomFieldPositionDetails'
        return [TimesheetEntryCustomFieldPositionDetails(f) for f in self._getUrl(url)]

    def getTimesheetEntryCustomField(self, name):
        fields = self.getStandardTimesheetEntryCustomFieldPositionDetails()
        field = None
        for f in fields:
            # Only tested with this pou type, unsure if we need to check for this
            pou = 'urn:replicon:standard-timesheet-entry-custom-field-position-option:row-'
            if f.positionOutputUri.startswith(pou):
                if f.customField.name == name:
                    field = f.customField
        return field

    def putTimesheet(self, timesheet_json):
        url = 'services/TimesheetService1.svc/PutStandardTimesheet2'
        self._getUrl(url, timesheet_json)


class TimesheetPeriod:

    def __init__(self, json):
        self.start_date = dict_to_date(json['dateRange']['startDate'])
        self.end_date = dict_to_date(json['dateRange']['endDate'])

    def __repr__(self):
        return "TimesheetPeriod " + self.start_date.isoformat() +  " to " + self.end_date.isoformat()


class Timesheet:

    def __init__(self, replicon_obj, json):
        self.replicon = replicon_obj
        self.slug = json['slug']
        self.uri = json['uri']
        self.start_date = dict_to_date(json['dateRange']['startDate'])
        self.end_date = dict_to_date(json['dateRange']['endDate'])
        self.timeAllocations = [TimesheetAllocation(a) for a in json['timeAllocations']]

    def __repr__(self):
        return "Timesheet slug: %s, uri: %s " % (self.slug, self.uri)

    def list(self):
        date  = ''
        for a in self.timeAllocations:
            if a.date != date:
                print a.date
            print a
        print

    def put_json(self):
        # TODO combine common Client/Project/Task/customeField TAs onto a single row with multiple cells
        data = {
            "timesheet": {
                "target": {
                    "uri": self.uri,
                    "user": None,
                    "date": None,
                },
                "customFields": [ ],
                "rows": [ ],
                "noticeExplicitlyAccepted": False,
                "bankedTime": None
            }
        }
        rows = {}

        for a in self.timeAllocations:
            billingRate = {
                'displayText': 'Project Rate',
                'name': 'Project Rate',
                'uri': 'urn:replicon:project-specific-billing-rate'
            }
            billingRate = None
            customFieldValues = []
            #if fieldset:
            #    field, value = fieldset
            #    customField = {
            #        'customField': {
            #                "uri": field.uri
            #            },
            #        'text': value
            #    }
            #    customFieldValues.append(customField)
            cell = {
                'date': date_to_dict(a.date),
                'duration': {
                    #'hours': 0,
                    #'minutes': 0,
                    'seconds': a.duration_seconds
                },
                'comments': a.comments,
                'customFieldValues' : customFieldValues
            }
            task = None
            if a.task:
                task = { "uri": a.task.uri }
            if a.rowkey in rows:
                rows[a.rowkey]['cells'].append(cell)
            else:
                rows[a.rowkey] = {
                    "target": None,
                    "project": {
                        "uri": a.project.uri
                    },
                    "task": task,
                    "billingRate": billingRate,
                    "activity": None,
                    "customFieldValues": [],
                    "cells": [ cell ]
               }
            data["timesheet"]["rows"] = [rows[k] for k in rows]
        return data

    def book(self, date, project, task, duration, comment, fieldset):
        # Add TimeAllocation
        if project:
            project = project.json
        if task:
            task = task.json
        ta = {
            'date': date_to_dict(date),
            'comments': comment,
            'duration': {'hours':0, 'minutes': 0, 'seconds': duration},
            'project': project,
            'task': task,
            'customFieldValues': []
        }
        updated = False
        for tb in self.timeAllocations:
            if tb.same_fields_as(ta):
                tb.duration_seconds += duration
                updated = True
                break
        if not updated:
            self.timeAllocations.append(TimesheetAllocation(ta))

    def put(self):
        self.replicon.putTimesheet(self.put_json())

    def clear(self):
        self.timeAllocations = []
        self.replicon.putTimesheet(self.put_json())

class TimesheetAllocation(object):

    def same_fields_as(self, json):
        same = True
        fields = ['date', 'project', 'task', 'customFieldValues']
        for f in fields:
            if json[f] != self.json[f]:
                same = False
                break
        return same

    def __init__(self, json):
        self.json = json

        self.date = dict_to_date(json['date'])

        self.comments = json['comments']

        self.duration_seconds = dict_to_seconds(json['duration'])

        self.project = None
        if json['project']:
            self.project = Project(json)

        self.task = None
        if json['task']:
            self.task = Task(json)

        #TODO generecise
        self.ticket_num = ''
        for field in json['customFieldValues']:
            if field['customField']['name'] == 'Ticket #' and field['text']:
                self.ticket_num = field['text']

        key = self.project.uri
        if self.task:
            key += self.task.uri
        self.rowkey = key

    def __repr__(self):
        if self.task:
            return "TimesheetAllocation %s, %s, %s, %s" % (self.date.isoformat(), self.duration_seconds, self.task.displayText, self.comments)
        else:
            return "TimesheetAllocation %s, %s, %s" % (self.date.isoformat(), self.duration_seconds, self.comments)

class TimeOff:
    # TODO
    pass

class Client:

    def __init__(self, json):
        self.uri = json['uri']
        self.id = uri_id(self.uri)
        self.displayText = json['displayText']
        self.name = json['name']
        self.slug = json['slug']

    def __repr__(self):
        return "%s. %s" % (self.id, self.displayText)

class Project:

    def __init__(self, json):
        project = json['project']
        self.json = project
        self.uri = project['uri']
        self.id = uri_id(self.uri)
        self.displayText = project['displayText']
        self.name = project['name']
        self.slug = project['slug']
#        dateRange = json['dateRangeWhereTimeAllocationIsAllowed']
#        self.start_date = dict_to_date(dateRange['startDate'])
#        self.end_date = dict_to_date(dateRange['endDate'])
#        self.client = None
#        if json['client']:
#            self.client = Client( json['client'] )
#        self.isTimeAllocationAllowed = json['isTimeAllocationAllowed']
#        self.hasTasksAvailableForTimeAllocation = json['hasTasksAvailableForTimeAllocation']

    def __repr__(self):
        return "%s. %s" % (self.id, self.displayText)

class Task:

    def __init__(self, json):
        task = json['task']
        self.json = task
        self.uri = task['uri']
        self.id = uri_id(self.uri)
        self.displayText = task['displayText']

    def __repr__(self):
        return "%s. %s" % (self.id, self.displayText)


class TimesheetEntryCustomFieldPositionDetails:

    def __init__(self, json):
        self.customField = CustomField(json['customField'])
        self.positionOutputUri = json['positionOptionUri']


class CustomField:

    def __init__(self, json):
        self.uri = json['uri']
        self.displayText = json['displayText']
        self.name = json['name']
        self.groupUri = json['groupUri']


if __name__ == '__main__':
    replicon = None # Replicon object

    def initialise(args):
        # called before each subcommand
        global replicon
        replicon = Replicon(date=args.date, debug=args.debug)

    def clients(args):
        # subcommand to list all clients
        print 'Clients:'
        for c in replicon.getClients():
            print c

    def projects(args):
        # subcommand to list all projects for the specified client
        client = None
        client_uri = None
        if args.client:
            client = replicon.getClient(args.client)
            if not client:
                print "ERROR: Unable to locate client %s." % args.client
                sys.exit(1)
        print 'Projects for client %s:' % client
        projects = replicon.getProjects(client)
        for p in projects:
            print p

    def tasks(args):
        # subcommand to list all tasks for specified client and project
        client = replicon.getClient(args.client)
        project = None
        project_uri = None
        if args.project:
            project = replicon.getProject(client, args.project)
            if not project:
                print "ERROR: Unable to locate project %s for client %s" % (args.project, client)
                sys.exit(1)
        print 'Tasks for client: %s, project %s:' % (client, project)
        tasks = replicon.getTasks(project)
        for t in tasks:
            print t

    def timesheet(args):
        # subcommand to display current timesheet
        timesheet = replicon.getTimesheet(args.date)
        timesheet.list()

    def taskhistory(args):
        # subcommand to display recent tasks
        print 'Most recent %d tasks:' % HISTORY_LENGTH
        day = args.date
        history = []
        while (len(history) < HISTORY_LENGTH):
            timesheet = replicon.getTimesheet(day)
            for allocation in timesheet.timeAllocations:
                if allocation.task and allocation.task.uri not in [x.uri for x in history]:
                    history.append(allocation.task)
            # set day to previous timesheet
            day = timesheet.start_date - datetime.timedelta(1)
        
        for t in history[:HISTORY_LENGTH]:
            print t
            
    def timesheetperiod(args):
        # subcommand to display current timesheet period dates
        print replicon.getTimesheetPeriods(args.date, args.date)[0]

    def book(args):
        # subcommand to book time to a task
        client = replicon.getClient(args.client)
        project = replicon.getProject(client, args.project)
        task = replicon.getTask(project, args.task)
        duration = args.duration
        comment = None
        if args.comment:
            comment = args.comment
        fieldset = None
        if(args.field):
            key, value = args.field
            field = replicon.getTimesheetEntryCustomField(key)
            fieldset = (field, value)
        timesheet = replicon.getTimesheet(args.date)
        timesheet.book(args.date, project, task, duration, comment, fieldset)
        timesheet.put()

    def clear(args):
        timesheet = replicon.getTimesheet(args.date)
        timesheet.clear()

    def valid_date(s):
        # From http://stackoverflow.com/questions/25470844/specify-format-for-input-arguments-argparse-python
        try:
            return datetime.datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            msg = "Not a valid date: '{0}'.".format(s)
            raise argparse.ArgumentTypeError(msg)

    def valid_duration(s):
        # <HH>:<MM>:<SS> or <HH>h<MM>m<SS>s TODO
        # Returns seconds
        return s

    def valid_key_value(s):
        # Colon delimeted string KEY:VALUE
        # Returns tuple (KEY, VALUE)
        try:
            k,v = s.split(':')
            return k,v
        except ValueError:
            msg = "Not a valid 'KEY:VALUE' string '{0}'.".format(s)
            raise argparse.ArgumentTypeError(msg)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--date', type=valid_date, help='Date. Format YYYY-MM-DD. Default is today.', default=datetime.date.today())
    parser.add_argument('-D', '--debug', action='store_true', help='Debug.   Prints JSON exchages.')

    subparsers = parser.add_subparsers(title='subcommands', help = 'run ''<subcommand>> -h for additional help')

    p = subparsers.add_parser('clients', help='List all clients for a timesheet.')
    p.set_defaults(func=clients)

    p = subparsers.add_parser('projects', help='List all projects for a client.')
    p.add_argument('client', type=str, default=None, nargs='?', help='blank list projects for "no client"')
    p.set_defaults(func=projects)

    p = subparsers.add_parser('tasks', help='List all tasks for a client and project.')
    p.add_argument('client', type=str)
    p.add_argument('project', type=str)
    p.set_defaults(func=tasks)

    p = subparsers.add_parser('taskhistory', help='Print most recent tasks that have been booked to')
    p.set_defaults(func=taskhistory)

    p = subparsers.add_parser('timesheet', help='List the timesheet.')
    p.set_defaults(func=timesheet)

    p = subparsers.add_parser('timesheetperiod', help='List the dates in the current timesheet period.')
    p.set_defaults(func=timesheetperiod)

    p = subparsers.add_parser('clear', help='Clear the timesheet.')
    p.set_defaults(func=clear)

    p = subparsers.add_parser('book', help='Book time to a client/project/task')
    p.add_argument('-c', '--comment', type=str)
    p.add_argument('-f', '--field', type=valid_key_value, help='format <NAME>:<VALUE>')
    p.add_argument('client', type=str)
    p.add_argument('project', type=str)
    p.add_argument('task', type=str)
    p.add_argument('duration', type=valid_duration)
    p.set_defaults(func=book)

    args = parser.parse_args()
    initialise(args)
    args.func(args)
